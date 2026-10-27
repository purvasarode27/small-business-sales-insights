"""
Small Business Sales Insights: Streamlit app.
Upload a sales export (Shopify, Square, Etsy or any spreadsheet) and get
plain-English insights, customer segments and a win-back list.
"""
import io
import os
import altair as alt
import pandas as pd
import streamlit as st

import insights as ins
import tracking

st.set_page_config(page_title="Small Business Sales Insights", page_icon="📈", layout="wide")

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "sample_sales.csv")
ROLE_LABELS = {
    "date": "Order date *", "order": "Order / invoice ID *", "product": "Product name *",
    "quantity": "Quantity *", "price": "Unit price", "revenue": "Line total (if no unit price)",
    "customer": "Customer ID or email (for customer insights)",
}


@st.cache_data(show_spinner=False)
def read_file(data: bytes, name: str) -> pd.DataFrame:
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    return pd.read_csv(io.BytesIO(data), encoding_errors="replace", low_memory=False)


@st.cache_data(show_spinner="Crunching your numbers...")
def analyse(df: pd.DataFrame, mapping: dict, cur: str):
    clean, report = ins.prepare(df, mapping)
    r = ins.rfm(clean)
    return {
        "clean": clean, "report": report, "kpis": ins.kpis(clean),
        "monthly": ins.monthly(clean), "products": ins.top_products(clean, 10),
        "weekday": ins.weekday(clean), "rfm": r,
        "segments": ins.segment_summary(r) if r is not None else None,
        "winback": ins.winback_list(r) if r is not None else None,
        "insights": ins.generate_insights(clean, r, cur),
    }


def money(x, cur):
    x = float(x)
    if abs(x) >= 1_000_000:
        return f"{cur}{x/1_000_000:.2f}M"
    if abs(x) >= 10_000:
        return f"{cur}{x/1_000:.1f}K"
    return f"{cur}{x:,.2f}"


# ---------------------------------------------------------------- header
st.title("📈 Small Business Sales Insights")
st.markdown("Upload your sales export and get **plain-English answers**: what's selling, "
            "who your best customers are, who's slipping away, and what to do next.")

with st.sidebar:
    st.header("1. Your data")
    source = st.radio("Data source", ["Try with sample data", "Upload my sales file"], index=0)
    uploaded = None
    if source == "Upload my sales file":
        uploaded = st.file_uploader("Sales export (CSV or Excel)", type=["csv", "xlsx", "xls"],
                                    help="One row per item sold. Shopify 'Orders' export, Square "
                                         "'Item details', Etsy 'Sold order items' and most spreadsheets work.")
    cur = st.selectbox("Currency", ["£", "$", "€", "₹", "C$", "A$"], index=0)
    st.caption("🔒 Your file is analysed in memory and never stored.")
    st.divider()
    st.caption("Built by Purva Sarode as a product + analytics portfolio project.")

# ---------------------------------------------------------------- load
if source == "Try with sample data":
    if not os.path.exists(SAMPLE_PATH):
        st.error("Sample file `sample_sales.csv` is missing from the app folder.")
        st.stop()
    with open(SAMPLE_PATH, "rb") as f:
        raw = read_file(f.read(), "sample_sales.csv")
    st.info("Showing **sample data**: real transactions from a UK online gift retailer "
            "(UCI Online Retail II). Switch to *Upload my sales file* in the sidebar to use your own.")
else:
    if uploaded is None:
        st.markdown("#### 👈 Upload a sales file in the sidebar to get started")
        st.markdown("- **Shopify:** Orders → Export → CSV\n"
                    "- **Square:** Reports → Item sales → Export → Item details CSV\n"
                    "- **Etsy:** Shop Manager → Settings → Options → Download data → Order items\n"
                    "- **Anything else:** a spreadsheet with date, order ID, product, quantity and price columns")
        st.stop()
    try:
        raw = read_file(uploaded.getvalue(), uploaded.name)
    except Exception as e:
        st.error(f"Couldn't read that file. Is it a CSV or Excel file? ({e})")
        st.stop()

if raw.empty:
    st.error("The file has no rows.")
    st.stop()

# ---------------------------------------------------------------- column mapping
guess = ins.guess_columns(list(raw.columns))
needs_check = any(guess.get(r) is None for r in ins.REQUIRED) or (guess["price"] is None and guess["revenue"] is None)
options = ["(none)"] + list(raw.columns)
with st.expander("2. Check your columns", expanded=needs_check):
    st.caption("We guessed which column is which. Fix anything that looks wrong. * = required.")
    mapping = {}
    cols = st.columns(4)
    for i, role in enumerate(ins.COLUMN_GUESSES):
        default = options.index(guess[role]) if guess.get(role) in options else 0
        choice = cols[i % 4].selectbox(ROLE_LABELS[role], options, index=default, key=f"map_{role}")
        mapping[role] = None if choice == "(none)" else choice
    st.dataframe(raw.head(5), use_container_width=True)

try:
    res = analyse(raw, mapping, cur)
except ValueError as e:
    st.warning(str(e))
    st.stop()

clean, report, k = res["clean"], res["report"], res["kpis"]
if clean.empty:
    st.error("No usable sales rows after cleaning. Please check the column choices above.")
    st.stop()

# ---------------------------------------------------------------- anonymous usage counter
src = "sample" if source == "Try with sample data" else "own"
if not st.session_state.get("tracked_start"):
    st.session_state["tracked_start"] = True
    tracking.track("start", src, report["rows_used"])
if src == "own":
    upload_key = f"tracked_{uploaded.name}_{uploaded.size}"
    if not st.session_state.get(upload_key):
        st.session_state[upload_key] = True
        tracking.track("upload", src, report["rows_used"])

removed = report["rows_in"] - report["rows_used"]
st.caption(f"Analysed **{report['rows_used']:,}** sales rows from "
           f"{report['date_min']:%d %b %Y} to {report['date_max']:%d %b %Y}. "
           f"Set aside {removed:,} rows (cancellations {report['cancellations']:,}, returns/zero "
           f"{report['returns_or_zero']:,}, duplicates {report['duplicates']:,}, unreadable dates "
           f"{report['bad_dates']:,}).")

# ---------------------------------------------------------------- KPIs
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Revenue", money(k["revenue"], cur))
c2.metric("Orders", f"{k['orders']:,}")
c3.metric("Average order", money(k["aov"], cur))
c4.metric("Customers", f"{k['customers']:,}" if k["customers"] else "–")
c5.metric("Repeat customers", f"{k['repeat_rate']:.0%}" if k["repeat_rate"] is not None else "–")

# ---------------------------------------------------------------- insights
st.subheader("💡 Insights for you")
if not res["insights"]:
    st.write("Not enough data for insights yet. Try a file covering a few months of sales.")
for item in res["insights"]:
    with st.container(border=True):
        st.markdown(f"**{item['title']}**  \n{item['detail']}  \n👉 *{item['action']}*")

# ---------------------------------------------------------------- tabs
t1, t2, t3 = st.tabs(["📅 Sales over time", "🛍️ Products", "👥 Customers"])

with t1:
    m = res["monthly"]
    if len(m) >= 2:
        chart = alt.Chart(m).mark_line(point=True).encode(
            x=alt.X("month:T", title=None),
            y=alt.Y("revenue:Q", title=f"Revenue ({cur})"),
            tooltip=[alt.Tooltip("month:T", format="%b %Y"), alt.Tooltip("revenue:Q", format=",.0f"),
                     alt.Tooltip("orders:Q", format=",")])
        st.altair_chart(chart.properties(title="Monthly revenue", height=320), use_container_width=True)
    w = res["weekday"]
    chart = alt.Chart(w).mark_bar().encode(
        x=alt.X("day:N", sort=ins.DAYS, title=None),
        y=alt.Y("revenue:Q", title=f"Revenue ({cur})"),
        tooltip=["day", alt.Tooltip("revenue:Q", format=",.0f")])
    st.altair_chart(chart.properties(title="Revenue by day of week", height=260), use_container_width=True)

with t2:
    p = res["products"]
    chart = alt.Chart(p).mark_bar().encode(
        x=alt.X("revenue:Q", title=f"Revenue ({cur})"),
        y=alt.Y("product:N", sort="-x", title=None),
        tooltip=["product", alt.Tooltip("revenue:Q", format=",.0f"), alt.Tooltip("units:Q", format=","),
                 alt.Tooltip("share:Q", format=".1%")])
    st.altair_chart(chart.properties(title="Top 10 products by revenue", height=360), use_container_width=True)
    table = p.copy()
    table["revenue"] = table["revenue"].map(lambda x: money(x, cur))
    table["share"] = table["share"].map(lambda x: f"{x:.1%}")
    table.columns = ["Product", "Revenue", "Units", "Orders", "Share of revenue"]
    st.dataframe(table, use_container_width=True, hide_index=True)

with t3:
    if res["segments"] is None:
        st.info("Add a **customer ID or email** column in *Check your columns* (with at least 20 customers) "
                "to see customer segments and your win-back list.")
    else:
        s = res["segments"]
        long = s.melt(id_vars="segment", value_vars=["pct_customers", "pct_revenue"],
                      var_name="measure", value_name="share")
        long["measure"] = long["measure"].map({"pct_customers": "% of customers", "pct_revenue": "% of revenue"})
        chart = alt.Chart(long).mark_bar().encode(
            y=alt.Y("segment:N", sort=ins.SEGMENT_ORDER, title=None),
            x=alt.X("share:Q", axis=alt.Axis(format="%"), title=None),
            color=alt.Color("measure:N", title=None, legend=alt.Legend(orient="top")),
            yOffset="measure:N",
            tooltip=["segment", "measure", alt.Tooltip("share:Q", format=".1%")])
        st.altair_chart(chart.properties(title="Customer segments: share of customers vs share of revenue",
                                         height=380), use_container_width=True)
        show = s[["segment", "customers", "revenue", "avg_days_since_last", "avg_orders", "what_it_means"]].copy()
        show["revenue"] = show["revenue"].map(lambda x: money(x, cur))
        show["avg_days_since_last"] = show["avg_days_since_last"].round(0).astype(int)
        show["avg_orders"] = show["avg_orders"].round(1)
        show.columns = ["Segment", "Customers", "Revenue", "Avg days since last order", "Avg orders", "What it means"]
        st.dataframe(show, use_container_width=True, hide_index=True)

        wb = res["winback"]
        st.markdown(f"#### 🔁 Win-back list: {len(wb):,} customers worth "
                    f"{money(wb['revenue'].sum(), cur)} in past sales")
        st.dataframe(wb.head(20), use_container_width=True, hide_index=True)
        st.download_button("⬇️ Download full win-back list (CSV)", wb.to_csv(index=False).encode("utf-8"),
                           file_name="winback_list.csv", mime="text/csv",
                           on_click=tracking.track, args=("download", src, report["rows_used"]))
