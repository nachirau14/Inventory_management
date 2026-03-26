"""
Material Dispatch (Outward) – Streamlit Community Cloud App
=============================================================
Issues materials from inventory for manufacturing jobs.

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
    page_title="Material Dispatch – Inventory",
    page_icon="📤",
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
st.title("📤 Material Dispatch (Outward)")
st.caption("Issue materials from inventory for manufacturing")

# ──────────────────────────────────────────────────────────────
# DATA LOADERS
# ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_materials():
    return db.get_all_materials()

@st.cache_data(ttl=15)
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
tab_dispatch, tab_stock, tab_history = st.tabs([
    "📤 Issue Material",
    "📊 Current Stock",
    "📜 Dispatch History",
])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 – DISPATCH MATERIAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_dispatch:
    materials = load_materials()
    stock_data = load_stock()
    stock_lookup = {s["material_id"]: s for s in stock_data}

    col_filter, _ = st.columns([1, 2])
    with col_filter:
        categories = sorted({m.get("category", "OTHER") for m in materials})
        selected_cat = st.selectbox(
            "Material Category",
            categories,
            format_func=lambda c: CATEGORY_LABELS.get(c, c),
            key="dispatch_cat",
        )

    filtered = sorted(
        [m for m in materials if m.get("category") == selected_cat],
        key=lambda m: m.get("description", ""),
    )

    if not filtered:
        st.warning("No materials found in this category.")
    else:
        material_options = {}
        for m in filtered:
            mid = m["material_id"]
            stk = stock_lookup.get(mid, {})
            qty = int(stk.get("quantity", 0))
            material_options[mid] = (
                f"{m['description']}  │  Stock: {qty} {m.get('unit', 'pcs')}  │  "
                f"Unit wt: {m.get('unit_weight_kg', '—')} kg"
            )

        st.divider()
        col_left, col_right = st.columns(2)

        with col_left:
            selected_id = st.selectbox(
                "Select Material to Issue",
                list(material_options.keys()),
                format_func=lambda mid: material_options[mid],
                key="dispatch_material",
            )

            current_stock = stock_lookup.get(selected_id, {})
            available_qty = int(current_stock.get("quantity", 0))

            if available_qty == 0:
                st.error("⚠️ This material is OUT OF STOCK")

            quantity = st.number_input(
                f"Quantity to Issue (available: {available_qty})",
                min_value=1,
                max_value=max(available_qty, 1),
                value=min(1, available_qty) if available_qty > 0 else 1,
                step=1,
                key="dispatch_qty",
            )

            job_order = st.text_input(
                "Job Order / Work Order No.",
                placeholder="e.g. JO-2025-0108",
            )

        with col_right:
            issued_to = st.text_input(
                "Issued To (department / person)",
                placeholder="e.g. Fabrication – Ravi",
            )
            issued_by = st.text_input(
                "Issued By (store keeper)",
                placeholder="e.g. Suresh",
            )
            remarks = st.text_area(
                "Remarks / Purpose",
                placeholder="e.g. For conveyor frame assembly",
                height=80,
            )

            mat_detail = next((m for m in filtered if m["material_id"] == selected_id), None)
            if mat_detail:
                unit_wt = float(mat_detail.get("unit_weight_kg", 0))
                total_wt = round(unit_wt * quantity, 3)
                st.divider()
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Available", f"{available_qty}")
                c2.metric("Issuing", f"{quantity}")
                c3.metric("Remaining", f"{available_qty - quantity}")
                c4.metric("Weight Issued", f"{total_wt} kg")

        st.divider()

        if available_qty > 0:
            col_btn, _ = st.columns([1, 2])
            with col_btn:
                confirm = st.checkbox("I confirm the above details are correct")

            if confirm:
                if st.button("📤 Issue Material", type="primary", use_container_width=True):
                    try:
                        txn_id = db.record_outward(
                            material_id=selected_id,
                            quantity=quantity,
                            remarks=remarks,
                            job_order=job_order,
                            issued_to=issued_to,
                            issued_by=issued_by,
                        )
                        st.success(f"Material issued!  Transaction ID: **{txn_id}**")
                        load_stock.clear()
                    except ValueError as ve:
                        st.error(f"Cannot issue: {ve}")
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.warning("Cannot issue — stock is zero. Record an inward entry first.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 – CURRENT STOCK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_stock:
    st.subheader("📊 Current Stock Levels")

    if st.button("🔄 Refresh", key="refresh_dispatch"):
        load_stock.clear()
        load_materials.clear()

    stock_data = load_stock()
    materials_data = load_materials()
    mat_lookup = {m["material_id"]: m for m in materials_data}

    rows = []
    for s in stock_data:
        mid = s["material_id"]
        mat = mat_lookup.get(mid, {})
        qty = int(s.get("quantity", 0))
        rows.append({
            "Material ID": mid,
            "Description": mat.get("description", "—"),
            "Category": mat.get("category", "—"),
            "Type": mat.get("material_type", "—"),
            "Unit": mat.get("unit", "—"),
            "Unit Wt (kg)": float(mat.get("unit_weight_kg", 0)),
            "Qty in Stock": qty,
            "Total Weight (kg)": float(s.get("total_weight_kg", 0)),
            "Status": "🔴 Out" if qty == 0 else ("🟡 Low" if qty < 5 else "🟢 OK"),
        })

    if rows:
        df = pd.DataFrame(rows)
        cat_filter = st.multiselect(
            "Filter by Category",
            df["Category"].unique().tolist(),
            default=df["Category"].unique().tolist(),
            key="stock_filter_dispatch",
        )
        show_in_stock = st.checkbox("Show only items with stock > 0", value=False)

        df_f = df[df["Category"].isin(cat_filter)]
        if show_in_stock:
            df_f = df_f[df_f["Qty in Stock"] > 0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total SKUs", len(df_f))
        c2.metric("In Stock", int((df_f["Qty in Stock"] > 0).sum()))
        c3.metric("Out of Stock", int((df_f["Qty in Stock"] == 0).sum()))
        c4.metric("Total Weight", f"{df_f['Total Weight (kg)'].sum():,.1f} kg")

        st.dataframe(
            df_f.sort_values(["Category", "Description"]),
            use_container_width=True, hide_index=True, height=500,
        )
    else:
        st.info("No stock data available.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 – DISPATCH HISTORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_history:
    st.subheader("📜 Dispatch History (Outward)")

    try:
        txns = db.get_recent_transactions(limit=200)
        outward = [t for t in txns if t.get("type") == "OUTWARD"]

        if outward:
            materials_data = load_materials()
            mat_lookup = {m["material_id"]: m for m in materials_data}

            txn_rows = [
                {
                    "Transaction ID": t["transaction_id"],
                    "Timestamp": t.get("timestamp", "—"),
                    "Material": mat_lookup.get(t["material_id"], {}).get("description", t["material_id"]),
                    "Qty": int(t.get("quantity", 0)),
                    "Total Wt (kg)": float(t.get("total_weight_kg", 0)),
                    "Job Order": t.get("job_order", "—"),
                    "Issued To": t.get("issued_to", "—"),
                    "Issued By": t.get("issued_by", "—"),
                    "Remarks": t.get("remarks", "—"),
                }
                for t in outward
            ]
            df_txn = pd.DataFrame(txn_rows)
            st.dataframe(df_txn, use_container_width=True, hide_index=True, height=400)

            csv = df_txn.to_csv(index=False)
            st.download_button(
                "⬇️ Download Dispatch Report (CSV)",
                csv,
                file_name=f"dispatch_report_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("No outward transactions recorded yet.")
    except Exception as e:
        st.error(f"Could not load transactions: {e}")


# ──────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📤 Material Dispatch")
    st.markdown("---")
    st.markdown(
        "**Factory Inventory System**\n\n"
        "Use this app to:\n"
        "- Issue materials for manufacturing\n"
        "- Track job-wise consumption\n"
        "- View current stock levels\n"
        "- Review dispatch history"
    )
    st.markdown("---")

    st.subheader("⚠️ Low Stock Alerts")
    try:
        all_stock = load_stock()
        all_mats = load_materials()
        ml = {m["material_id"]: m for m in all_mats}
        low = [s for s in all_stock if 0 < int(s.get("quantity", 0)) < 5]
        if low:
            for s in low[:10]:
                mat = ml.get(s["material_id"], {})
                st.warning(
                    f"**{mat.get('description', s['material_id'])}**\n"
                    f"Only {int(s['quantity'])} left"
                )
        else:
            st.info("No low-stock items")
    except Exception:
        pass

    st.markdown("---")
    st.caption(f"Region: {st.secrets['aws'].get('AWS_DEFAULT_REGION', 'ap-south-1')}")
    st.caption(f"Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
