"""
db_operations.py – Shared DynamoDB operations for the Inventory System.

Designed for Streamlit Community Cloud deployment.
AWS credentials are read from st.secrets (configured in the Streamlit Cloud dashboard
or .streamlit/secrets.toml locally).

Tables:
    MaterialMaster       – all material definitions + pre-calculated weights
    InventoryStock       – current stock levels per material
    InventoryTransactions – full audit trail of every inward / outward entry
"""

import uuid
from datetime import datetime
from decimal import Decimal

import boto3
import streamlit as st
from boto3.dynamodb.conditions import Key


# ──────────────────────────────────────────────────────────────
# AWS SESSION (from Streamlit secrets)
# ──────────────────────────────────────────────────────────────

@st.cache_resource
def _get_dynamodb():
    """
    Create a single boto3 DynamoDB resource, cached for the app's lifetime.
    Reads credentials from st.secrets["aws"].
    """
    aws_cfg = st.secrets["aws"]
    session = boto3.Session(
        aws_access_key_id=aws_cfg["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=aws_cfg["AWS_SECRET_ACCESS_KEY"],
        region_name=aws_cfg.get("AWS_DEFAULT_REGION", "ap-south-1"),
    )
    return session.resource("dynamodb")


def _tables():
    db = _get_dynamodb()
    return {
        "master": db.Table("MaterialMaster"),
        "stock": db.Table("InventoryStock"),
        "transactions": db.Table("InventoryTransactions"),
    }


# ──────────────────────────────────────────────────────────────
# MATERIAL MASTER
# ──────────────────────────────────────────────────────────────

def get_all_materials():
    """Fetch every item from MaterialMaster."""
    table = _tables()["master"]
    items, response = [], table.scan()
    items.extend(response["Items"])
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response["Items"])
    return items


def get_materials_by_category(category: str):
    """Query MaterialMaster by category using GSI."""
    table = _tables()["master"]
    response = table.query(
        IndexName="category-index",
        KeyConditionExpression=Key("category").eq(category),
    )
    return response["Items"]


def get_material(material_id: str):
    """Get a single material by ID."""
    table = _tables()["master"]
    response = table.get_item(Key={"material_id": material_id})
    return response.get("Item")


def add_custom_material(material_data: dict):
    """
    Add a custom material to MaterialMaster and initialise its stock row.
    material_data must include: material_id, category, description, unit, unit_weight_kg
    """
    t = _tables()
    t["master"].put_item(Item=material_data)
    t["stock"].put_item(
        Item={
            "material_id": material_data["material_id"],
            "quantity": Decimal("0"),
            "total_weight_kg": Decimal("0"),
            "last_updated": datetime.utcnow().isoformat(),
        }
    )


# ──────────────────────────────────────────────────────────────
# INVENTORY STOCK
# ──────────────────────────────────────────────────────────────

def get_stock(material_id: str):
    """Get current stock for a single material."""
    table = _tables()["stock"]
    response = table.get_item(Key={"material_id": material_id})
    return response.get("Item")


def get_all_stock():
    """Get all stock records."""
    table = _tables()["stock"]
    items, response = [], table.scan()
    items.extend(response["Items"])
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response["Items"])
    return items


# ──────────────────────────────────────────────────────────────
# TRANSACTIONS – INWARD & OUTWARD
# ──────────────────────────────────────────────────────────────

def record_inward(
    material_id: str,
    quantity: int,
    remarks: str = "",
    supplier: str = "",
    invoice_no: str = "",
    received_by: str = "",
):
    """
    Record material received (inward entry).
    1. Writes a transaction record.
    2. Atomically increments InventoryStock.
    """
    t = _tables()
    material = get_material(material_id)
    if not material:
        raise ValueError(f"Material {material_id} not found in master")

    unit_weight = float(material.get("unit_weight_kg", 0))
    total_weight = round(unit_weight * quantity, 3)
    now = datetime.utcnow().isoformat()
    txn_id = f"IN-{uuid.uuid4().hex[:12]}"

    t["transactions"].put_item(
        Item={
            "transaction_id": txn_id,
            "material_id": material_id,
            "type": "INWARD",
            "quantity": Decimal(str(quantity)),
            "unit_weight_kg": Decimal(str(unit_weight)),
            "total_weight_kg": Decimal(str(total_weight)),
            "timestamp": now,
            "remarks": remarks,
            "supplier": supplier,
            "invoice_no": invoice_no,
            "received_by": received_by,
        }
    )

    t["stock"].update_item(
        Key={"material_id": material_id},
        UpdateExpression=(
            "SET quantity = if_not_exists(quantity, :zero) + :qty, "
            "    total_weight_kg = if_not_exists(total_weight_kg, :zero) + :wt, "
            "    last_updated = :ts"
        ),
        ExpressionAttributeValues={
            ":qty": Decimal(str(quantity)),
            ":wt": Decimal(str(total_weight)),
            ":zero": Decimal("0"),
            ":ts": now,
        },
    )
    return txn_id


def record_outward(
    material_id: str,
    quantity: int,
    remarks: str = "",
    job_order: str = "",
    issued_to: str = "",
    issued_by: str = "",
):
    """
    Record material dispatched / issued (outward entry).
    1. Validates sufficient stock.
    2. Writes a transaction record.
    3. Atomically decrements InventoryStock.
    """
    t = _tables()
    material = get_material(material_id)
    if not material:
        raise ValueError(f"Material {material_id} not found in master")

    stock = get_stock(material_id)
    current_qty = int(stock.get("quantity", 0)) if stock else 0
    if quantity > current_qty:
        raise ValueError(
            f"Insufficient stock. Available: {current_qty}, Requested: {quantity}"
        )

    unit_weight = float(material.get("unit_weight_kg", 0))
    total_weight = round(unit_weight * quantity, 3)
    now = datetime.utcnow().isoformat()
    txn_id = f"OUT-{uuid.uuid4().hex[:12]}"

    t["transactions"].put_item(
        Item={
            "transaction_id": txn_id,
            "material_id": material_id,
            "type": "OUTWARD",
            "quantity": Decimal(str(quantity)),
            "unit_weight_kg": Decimal(str(unit_weight)),
            "total_weight_kg": Decimal(str(total_weight)),
            "timestamp": now,
            "remarks": remarks,
            "job_order": job_order,
            "issued_to": issued_to,
            "issued_by": issued_by,
        }
    )

    t["stock"].update_item(
        Key={"material_id": material_id},
        UpdateExpression=(
            "SET quantity = quantity - :qty, "
            "    total_weight_kg = total_weight_kg - :wt, "
            "    last_updated = :ts"
        ),
        ExpressionAttributeValues={
            ":qty": Decimal(str(quantity)),
            ":wt": Decimal(str(total_weight)),
            ":ts": now,
        },
    )
    return txn_id


# ──────────────────────────────────────────────────────────────
# TRANSACTION HISTORY
# ──────────────────────────────────────────────────────────────

def get_transactions_for_material(material_id: str, limit: int = 50):
    """Get recent transactions for a given material (newest first)."""
    table = _tables()["transactions"]
    response = table.query(
        IndexName="material-time-index",
        KeyConditionExpression=Key("material_id").eq(material_id),
        ScanIndexForward=False,
        Limit=limit,
    )
    return response["Items"]


def get_recent_transactions(limit: int = 100):
    """Get all recent transactions (scan – use sparingly)."""
    table = _tables()["transactions"]
    response = table.scan(Limit=limit)
    items = response["Items"]
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return items[:limit]
