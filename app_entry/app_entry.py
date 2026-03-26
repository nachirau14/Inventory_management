"""
Material Entry (Inward) – Streamlit Community Cloud App
========================================================
Records incoming materials into the inventory system.

Deployment : Streamlit Community Cloud
Database   : AWS DynamoDB
Secrets    : st.secrets["aws"] for credentials
"""

import streamlit as st
import pandas as pd
from decimal import Decimal
from datetime import datetime

import db_operations as db

# ──────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Material Entry – Inventory",
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────
# CUSTOM CSS
# ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1rem; max-width: 1200px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 24px; font-weight: 600; }
    div[data-testid="metric-container"] {
        background: #f0f2f6; border-radius: 8px; padding: 12px 16px;
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────
# VALIDATE SECRETS
# ──────────────────────────────────────────────────────────────
if "aws" not in st.secrets:
    st.error(
        "⚠️ AWS credentials not configured.\n\n"
        "Add your credentials in **Settings → Secrets** (on Streamlit Cloud) "
        "or in `.streamlit/secrets.toml` (locally).\n\n"
        "```toml\n[aws]\n"
        'AWS_ACCESS_KEY_ID     = "..."\n'
        'AWS_SECRET_ACCESS_KEY = "..."\n'
        'AWS_DEFAULT_REGION    = "ap-south-1"\n```'
    )
    st.stop()

# ──────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────
st.title("📥 Material Entry (Inward)")
st.caption("Record incoming materials into inventory")

# ──────────────────────────────────────────────────────────────
# DATA LOADERS
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_materials():
    return db.get_all_materials()

@st.cache_data(ttl=30)
def load_stock():
    return db.get_all_stock()


CATEGORY_LABELS = {
    "SHEET": "🔲 Sheets (MS / SS)",
    "SQUARE_TUBE": "▪️ Square Tubes",
    "C_SECTION": "🔩 C Sections",
    "ANGLE": "📐 Angles",
    "PIPE": "⭕ Pipes",
    "CUSTOM": "🔧 Custom Material",
}

# ──────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────
tab_entry, tab_custom, tab_stock, tab_history = st.tabs([
    "📥 Record Entry",
    "➕ Add Custom Material",
    "📊 Current Stock",
    "📜 Transaction History",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 – RECORD MATERIAL ENTRY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_entry:
    materials = load_materials()

    col_filter, _ = st.columns([1, 2])
    with col_filter:
        categories = sorted({m.get("category", "OTHER") for m in materials})
        selected_cat = st.selectbox(
            "Material Category",
            categories,
            format_func=lambda c: CATEGORY_LABELS.get(c, c),
        )

    filtered = sorted(
        [m for m in materials if m.get("category") == selected_cat],
        key=lambda m: m.get("description", ""),
    )

    if not filtered:
        st.warning("No materials found in this category.")
    else:
        material_options = {
            m["material_id"]: (
                f"{m['description']}  (Unit wt: {m.get('unit_weight_kg', '—')} kg)"
            )
            for m in filtered
        }

        st.divider()
        col_left, col_right = st.columns(2)

        with col_left:
            selected_id = st.selectbox(
                "Select Material",
                list(material_options.keys()),
                format_func=lambda mid: material_options[mid],
            )
            quantity = st.number_input(
                "Quantity (sheets / pieces)",
                min_value=1, max_value=10000, value=1, step=1,
            )
            supplier = st.text_input("Supplier Name", placeholder="e.g. Tata Steel Dealers")
            invoice_no = st.text_input("Invoice / GRN No.", placeholder="e.g. INV-2025-0042")

        with col_right:
            received_by = st.text_input("Received By", placeholder="Name of person receiving")
            remarks = st.text_area("Remarks", placeholder="Any additional notes…", height=100)

            mat_detail = next((m for m in filtered if m["material_id"] == selected_id), None)
            if mat_detail:
                unit_wt = float(mat_detail.get("unit_weight_kg", 0))
                total_wt = round(unit_wt * quantity, 3)
                st.divider()
                c1, c2, c3 = st.columns(3)
                c1.metric("Unit Weight", f"{unit_wt} kg")
                c2.metric("Quantity", f"{quantity}")
                c3.metric("Total Weight", f"{total_wt} kg")

        st.divider()

        if st.button("✅ Record Material Entry", type="primary", use_container_width=True):
            try:
                txn_id = db.record_inward(
                    material_id=selected_id,
                    quantity=quantity,
                    remarks=remarks,
                    supplier=supplier,
                    invoice_no=invoice_no,
                    received_by=received_by,
                )
                st.success(f"Entry recorded!  Transaction ID: **{txn_id}**")
                st.balloons()
                load_stock.clear()
            except Exception as e:
                st.error(f"Error recording entry: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 – ADD CUSTOM MATERIAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_custom:
    st.subheader("Add a Custom Material")
    st.caption("Register any non-standard material into the inventory master.")

    col1, col2 = st.columns(2)
    with col1:
        custom_id = st.text_input(
            "Material ID (unique code)",
            placeholder="e.g. CUSTOM-GASKET-50MM",
            help="Must be unique. Suggested: CUSTOM-<type>-<size>",
        )
        custom_desc = st.text_input("Description", placeholder="e.g. Neoprene Gasket 50 mm")
        custom_category = st.selectbox(
            "Category",
            ["CUSTOM", "SHEET", "SQUARE_TUBE", "C_SECTION", "ANGLE", "PIPE"],
        )
    with col2:
        custom_unit = st.selectbox("Unit", ["piece", "sheet", "kg", "metre", "set"])
        custom_weight = st.number_input("Unit Weight (kg)", min_value=0.0, step=0.1, value=0.0)
        custom_material_type = st.selectbox("Material Type", ["MS", "SS", "Aluminium", "Other"])

    custom_notes = st.text_area("Notes", placeholder="Any specifications…", height=80)

    if st.button("➕ Add Custom Material", type="primary"):
        if not custom_id or not custom_desc:
            st.error("Material ID and Description are required.")
        else:
            try:
                db.add_custom_material({
                    "material_id": custom_id,
                    "category": custom_category,
                    "material_type": custom_material_type,
                    "description": custom_desc,
                    "unit": custom_unit,
                    "unit_weight_kg": Decimal(str(custom_weight)),
                    "notes": custom_notes,
                })
                st.success(f"Custom material **{custom_id}** added!")
                load_materials.clear()
            except Exception as e:
                st.error(f"Error: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 – CURRENT STOCK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_stock:
    st.subheader("📊 Current Stock Levels")

    if st.button("🔄 Refresh", key="refresh_entry"):
        load_stock.clear()
        load_materials.clear()

    stock_data = load_stock()
    materials_data = load_materials()
    mat_lookup = {m["material_id"]: m for m in materials_data}

    rows = []
    for s in stock_data:
        mid = s["material_id"]
        mat = mat_lookup.get(mid, {})
        rows.append({
            "Material ID": mid,
            "Description": mat.get("description", "—"),
            "Category": mat.get("category", "—"),
            "Type": mat.get("material_type", "—"),
            "Unit": mat.get("unit", "—"),
            "Unit Wt (kg)": float(mat.get("unit_weight_kg", 0)),
            "Qty in Stock": int(s.get("quantity", 0)),
            "Total Weight (kg)": float(s.get("total_weight_kg", 0)),
            "Last Updated": s.get("last_updated", "—"),
        })

    if rows:
        df = pd.DataFrame(rows)
        cat_filter = st.multiselect(
            "Filter by Category",
            df["Category"].unique().tolist(),
            default=df["Category"].unique().tolist(),
        )
        df_f = df[df["Category"].isin(cat_filter)]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total SKUs", len(df_f))
        c2.metric("Items in Stock", int(df_f["Qty in Stock"].sum()))
        c3.metric("Total Weight", f"{df_f['Total Weight (kg)'].sum():,.1f} kg")
        c4.metric("Low Stock (< 5)", int((df_f["Qty in Stock"].between(1, 4)).sum()))

        st.dataframe(df_f.sort_values("Category"), use_container_width=True, hide_index=True, height=500)
    else:
        st.info("No stock data yet. Record some entries first!")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 4 – TRANSACTION HISTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_history:
    st.subheader("📜 Recent Inward Transactions")

    try:
        txns = db.get_recent_transactions(limit=200)
        inward = [t for t in txns if t.get("type") == "INWARD"]

        if inward:
            materials_data = load_materials()
            mat_lookup = {m["material_id"]: m for m in materials_data}

            txn_rows = [
                {
                    "Transaction ID": t["transaction_id"],
                    "Timestamp": t.get("timestamp", "—"),
                    "Material": mat_lookup.get(t["material_id"], {}).get("description", t["material_id"]),
                    "Qty": int(t.get("quantity", 0)),
                    "Total Wt (kg)": float(t.get("total_weight_kg", 0)),
                    "Supplier": t.get("supplier", "—"),
                    "Invoice": t.get("invoice_no", "—"),
                    "Received By": t.get("received_by", "—"),
                    "Remarks": t.get("remarks", "—"),
                }
                for t in inward
            ]
            df_txn = pd.DataFrame(txn_rows)
            st.dataframe(df_txn, use_container_width=True, hide_index=True, height=400)

            csv = df_txn.to_csv(index=False)
            st.download_button(
                "⬇️ Download Entry Report (CSV)",
                csv,
                file_name=f"entry_report_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("No inward transactions recorded yet.")
    except Exception as e:
        st.error(f"Could not load transactions: {e}")


# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📥 Material Entry")
    st.markdown("---")
    st.markdown(
        "**Factory Inventory System**\n\n"
        "Use this app to:\n"
        "- Record incoming materials\n"
        "- Add custom material types\n"
        "- View current stock levels\n"
        "- Review entry history"
    )
    st.markdown("---")
    st.caption(f"Region: {st.secrets['aws'].get('AWS_DEFAULT_REGION', 'ap-south-1')}")
    st.caption(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
