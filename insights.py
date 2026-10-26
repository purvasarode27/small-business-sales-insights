"""
Analysis engine for the Small Business Sales Insights app.

Takes a raw sales export (Shopify, Square, Etsy, or any spreadsheet with one row
per item sold) and turns it into KPIs, charts data, customer segments and
plain-English insights. Pure pandas, no Streamlit, so it can be tested on its own.
"""
import re
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# 1. Column detection: common column names from popular store exports
# --------------------------------------------------------------------------
COLUMN_GUESSES = {
    "date":     ["invoicedate", "date", "created at", "created_at", "sale date", "order date",
                 "paid at", "transaction date", "datetime", "timestamp"],
    "order":    ["invoice", "order id", "order_id", "order", "name", "order number",
                 "transaction id", "receipt id", "invoice no", "invoiceno", "sale id"],
    "product":  ["description", "lineitem name", "item name", "item", "product", "product name",
                 "product title", "title", "sku name"],
    "quantity": ["quantity", "lineitem quantity", "qty", "units", "count"],
    "price":    ["price", "unitprice", "unit price", "lineitem price", "item price"],
    "revenue":  ["revenue", "net sales", "gross sales", "sales", "line total", "total sales",
                 "amount", "item total"],
    "customer": ["customer id", "customerid", "customer", "customer email", "email", "buyer",
                 "buyer user id", "customer name", "client"],
}

REQUIRED = ["date", "order", "product", "quantity"]


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", str(s).lower().replace("_", " ")).strip()


def guess_columns(columns):
    """Return {role: column name or None} using common export column names."""
    normed = {c: _norm(c) for c in columns}
    used, guess = set(), {}
    for role, candidates in COLUMN_GUESSES.items():
        match = None
        for cand in candidates:                      # exact matches first
            for col, n in normed.items():
                if col not in used and n == _norm(cand):
                    match = col
                    break
            if match:
                break
        if match is None:                            # then "contains" matches
            for cand in candidates:
                for col, n in normed.items():
                    if col not in used and _norm(cand) in n:
                        match = col
                        break
                if match:
                    break
        guess[role] = match
        if match:
            used.add(match)
    return guess


# --------------------------------------------------------------------------
# 2. Cleaning
# --------------------------------------------------------------------------
def _to_number(series):
    """Turn '$1,234.50', '£12', '(5.00)' etc. into numbers."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    s = series.astype(str).str.strip()
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)      # (5.00) -> -5.00
    s = s.str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def prepare(df, mapping):
    """
    Standardise the user's data.

    mapping: {role: column name}. Needs date, order, product, quantity and
    either price (per unit) or revenue (line total). Customer is optional.
    Returns (clean DataFrame, cleaning report dict).
    """
    missing = [r for r in REQUIRED if not mapping.get(r)]
    if not mapping.get("price") and not mapping.get("revenue"):
        missing.append("price or revenue")
    if missing:
        raise ValueError("Please choose a column for: " + ", ".join(missing))

    report = {"rows_in": len(df)}
    # utc=True handles exports with time-zone offsets (e.g. Shopify "-0500"); then drop the zone
    dates = pd.to_datetime(df[mapping["date"]], errors="coerce", utc=True).dt.tz_localize(None)
    out = pd.DataFrame({
        "order_id": df[mapping["order"]].astype(str).str.strip(),
        "date": dates,
        "product": df[mapping["product"]].astype(str).str.strip(),
        "quantity": _to_number(df[mapping["quantity"]]),
    })
    if mapping.get("price"):
        out["price"] = _to_number(df[mapping["price"]])
        out["revenue"] = out["quantity"] * out["price"]
    else:
        out["revenue"] = _to_number(df[mapping["revenue"]])
        out["price"] = out["revenue"] / out["quantity"].replace(0, np.nan)

    if mapping.get("customer"):
        cust = df[mapping["customer"]]
        if pd.api.types.is_float_dtype(cust):                 # 13085.0 -> "13085"
            cust = cust.map(lambda x: str(int(x)) if pd.notna(x) else np.nan)
        cust = cust.astype("string").str.strip()
        cust = cust.mask(cust.isin(["", "nan", "None", "NaN"]))
        out["customer"] = cust
    else:
        out["customer"] = pd.Series(pd.NA, index=out.index, dtype="string")

    # Some exports (e.g. Shopify) only fill date/customer on an order's first line: copy them down
    out["date"] = out.groupby("order_id")["date"].transform("first")
    out["customer"] = out.groupby("order_id")["customer"].transform("first")

    # Remove unusable rows, counting each reason
    n = len(out)
    out = out.dropna(subset=["date"])
    report["bad_dates"] = n - len(out)

    n = len(out)
    is_cancel = out["order_id"].str.upper().str.startswith("C") & out["order_id"].str[1:].str.isdigit()
    out = out[~is_cancel]
    report["cancellations"] = n - len(out)

    n = len(out)
    out = out[(out["quantity"] > 0) & (out["revenue"] > 0)]
    report["returns_or_zero"] = n - len(out)

    n = len(out)
    out = out.drop_duplicates()
    report["duplicates"] = n - len(out)

    report["rows_used"] = len(out)
    report["has_customers"] = bool(out["customer"].notna().any())
    report["date_min"] = out["date"].min()
    report["date_max"] = out["date"].max()
    return out.reset_index(drop=True), report


# --------------------------------------------------------------------------
# 3. KPIs and chart tables
# --------------------------------------------------------------------------
def kpis(clean):
    orders = clean["order_id"].nunique()
    revenue = clean["revenue"].sum()
    k = {"revenue": revenue, "orders": orders,
         "aov": revenue / orders if orders else 0.0,
         "customers": None, "repeat_rate": None}
    cust = clean.dropna(subset=["customer"])
    if len(cust):
        per = cust.groupby("customer")["order_id"].nunique()
        k["customers"] = len(per)
        k["repeat_rate"] = (per > 1).mean()
    return k


def _full_months(clean):
    """Monthly revenue, dropping a last month that is clearly incomplete."""
    m = (clean.assign(month=clean["date"].dt.to_period("M"))
              .groupby("month")
              .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique")))
    last_day = clean["date"].max()
    if len(m) > 1 and last_day.day < last_day.days_in_month - 3:
        m = m.iloc[:-1]
    return m


def monthly(clean):
    m = _full_months(clean).reset_index()
    m["month"] = m["month"].dt.to_timestamp()
    return m


def top_products(clean, n=10):
    p = (clean.groupby("product")
              .agg(revenue=("revenue", "sum"), units=("quantity", "sum"),
                   orders=("order_id", "nunique"))
              .sort_values("revenue", ascending=False))
    p["share"] = p["revenue"] / p["revenue"].sum()
    return p.head(n).reset_index()


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def weekday(clean):
    w = clean.groupby(clean["date"].dt.day_name())["revenue"].sum()
    return w.reindex(DAYS, fill_value=0).reset_index().rename(columns={"date": "day"})


# --------------------------------------------------------------------------
# 4. Customer segments (RFM)
# --------------------------------------------------------------------------
SEGMENT_ORDER = ["Champions", "Loyal", "Potential Loyalists", "New",
                 "At Risk", "Can't Lose Them", "Hibernating"]

SEGMENT_HELP = {
    "Champions": "Bought recently and often. Your best customers.",
    "Loyal": "Buy regularly. Keep them happy.",
    "Potential Loyalists": "Recent buyers who could become regulars.",
    "New": "First purchase recently. Win the second order.",
    "At Risk": "Used to buy often but haven't for a while.",
    "Can't Lose Them": "Were among your best customers, now gone quiet.",
    "Hibernating": "Bought rarely and long ago.",
}


def _segment(r, f):
    if r >= 4 and f >= 4: return "Champions"
    if r >= 3 and f >= 3: return "Loyal"
    if r >= 4 and f == 1: return "New"
    if r >= 3:            return "Potential Loyalists"
    if r == 1 and f >= 4: return "Can't Lose Them"
    if f >= 3:            return "At Risk"
    return "Hibernating"


def rfm(clean, min_customers=20):
    """One row per customer with Recency, Frequency, Monetary, scores and segment.
    Returns None if there aren't enough identified customers."""
    cust = clean.dropna(subset=["customer"])
    if cust["customer"].nunique() < min_customers:
        return None
    snapshot = cust["date"].max() + pd.Timedelta(days=1)
    t = cust.groupby("customer").agg(
        last_purchase=("date", "max"),
        orders=("order_id", "nunique"),
        revenue=("revenue", "sum"))
    t["days_since_last"] = (snapshot - t["last_purchase"]).dt.days
    t["R"] = pd.qcut(t["days_since_last"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    t["F"] = pd.qcut(t["orders"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    t["M"] = pd.qcut(t["revenue"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    t["segment"] = [_segment(r, f) for r, f in zip(t["R"], t["F"])]
    return t.reset_index()


def segment_summary(r):
    s = r.groupby("segment").agg(customers=("customer", "size"), revenue=("revenue", "sum"),
                                 avg_days_since_last=("days_since_last", "mean"),
                                 avg_orders=("orders", "mean"))
    s["pct_customers"] = s["customers"] / s["customers"].sum()
    s["pct_revenue"] = s["revenue"] / s["revenue"].sum()
    s = s.reindex([x for x in SEGMENT_ORDER if x in s.index])
    s["what_it_means"] = [SEGMENT_HELP[x] for x in s.index]
    return s.reset_index()


def winback_list(r):
    w = r[r["segment"].isin(["At Risk", "Can't Lose Them"])].copy()
    w = w.sort_values("revenue", ascending=False)
    w["last_purchase"] = w["last_purchase"].dt.date
    return w[["customer", "segment", "last_purchase", "days_since_last", "orders", "revenue"]]


# --------------------------------------------------------------------------
# 5. Plain-English insights
# --------------------------------------------------------------------------
def _money(x, cur):
    x = float(x)
    if abs(x) >= 1_000_000:
        return f"{cur}{x/1_000_000:.1f}M"
    if abs(x) >= 1_000:
        return f"{cur}{x/1_000:.1f}K"
    return f"{cur}{x:,.0f}"


def generate_insights(clean, r=None, cur="£"):
    """Return a list of {'title', 'detail', 'action'} dicts, most important first."""
    out = []
    total = clean["revenue"].sum()

    # A. Customer concentration + win-back (needs customers)
    if r is not None and len(r):
        top = r.sort_values("revenue", ascending=False)
        n20 = max(1, int(round(len(top) * 0.2)))
        share = top["revenue"].head(n20).sum() / top["revenue"].sum()
        out.append({
            "title": f"Your top 20% of customers bring in {share:.0%} of revenue",
            "detail": f"{n20:,} customers out of {len(top):,} generate most of your sales.",
            "action": "Treat them as VIPs: early access to new stock, a personal thank-you, or a loyalty perk.",
        })
        w = r[r["segment"].isin(["At Risk", "Can't Lose Them"])]
        if len(w):
            cl = (r["segment"] == "Can't Lose Them").sum()
            extra = f" Start with the {cl:,} 'Can't Lose Them' customers." if cl else ""
            out.append({
                "title": f"{len(w):,} valuable customers have gone quiet",
                "detail": (f"They used to buy regularly ({w['orders'].mean():.0f} orders on average) and spent "
                           f"{_money(w['revenue'].sum(), cur)} in total, but haven't ordered in about "
                           f"{w['days_since_last'].median():.0f} days."),
                "action": "Download the win-back list below and send a personal 'we miss you' message or offer." + extra,
            })
        once = (r["orders"] == 1).mean()
        if once >= 0.2:
            out.append({
                "title": f"{once:.0%} of customers have only ordered once",
                "detail": "The biggest drop-off happens after the first purchase.",
                "action": "Send a follow-up offer within 30 days of a first order to win the second purchase.",
            })

    # B. Seasonality (needs ~a year of data)
    m = _full_months(clean)["revenue"]
    if len(m) >= 12:
        last12 = m.iloc[-12:]
        roll = last12.rolling(3).sum()
        end = roll.idxmax()
        pos = list(last12.index).index(end)
        months = list(last12.index[pos - 2: pos + 1])
        share = roll.max() / last12.sum()
        names = f"{months[0].strftime('%b')}–{months[-1].strftime('%b')}"
        prep = (months[0] - 1).strftime("%B")
        if share >= 0.30:
            out.append({
                "title": f"{names} brings in {share:.0%} of your yearly sales",
                "detail": f"Your three busiest months in a row, versus 25% if sales were even all year.",
                "action": f"Have your best sellers in stock and promotions planned by {prep}.",
            })

    # C. Recent trend: last 3 full months vs same 3 months a year earlier (or previous 3)
    if len(m) >= 15:
        recent, year_ago = m.iloc[-3:].sum(), m.iloc[-15:-12].sum()
        if year_ago > 0:
            ch = recent / year_ago - 1
            out.append({
                "title": f"Sales are {'up' if ch >= 0 else 'down'} {abs(ch):.0%} versus the same months last year",
                "detail": f"Last 3 full months: {_money(recent, cur)} vs {_money(year_ago, cur)} a year earlier.",
                "action": ("Keep doing what's working and check which products drove the growth."
                           if ch >= 0 else "Check which products and customers dropped off, and start with the win-back list."),
            })
    elif len(m) >= 6:
        recent, prev = m.iloc[-3:].sum(), m.iloc[-6:-3].sum()
        if prev > 0:
            ch = recent / prev - 1
            out.append({
                "title": f"Sales are {'up' if ch >= 0 else 'down'} {abs(ch):.0%} versus the previous 3 months",
                "detail": f"Last 3 full months: {_money(recent, cur)} vs {_money(prev, cur)} before that.",
                "action": "Compare with the same season last year before reacting. Some swings are seasonal.",
            })

    # D. Best weekday
    wd = weekday(clean).set_index("day")["revenue"]
    if wd.sum() > 0:
        best, share = wd.idxmax(), wd.max() / wd.sum()
        if share >= 0.18:
            prev_day = DAYS[(DAYS.index(best) - 1) % 7]
            out.append({
                "title": f"{best} is your biggest sales day ({share:.0%} of revenue)",
                "detail": "Even split would be 14% per day.",
                "action": f"Send emails or post offers on {prev_day} to catch {best}'s buyers.",
            })

    # E. Product concentration
    p = top_products(clean, n=10)
    if len(p) >= 5:
        share10 = p["revenue"].sum() / total
        out.append({
            "title": f"Your top 10 products make up {share10:.0%} of revenue",
            "detail": f"Best seller: {p.iloc[0]['product']} ({_money(p.iloc[0]['revenue'], cur)}).",
            "action": ("Never let these run out of stock." if share10 >= 0.2
                       else "Sales are spread across many products. Review slow sellers that tie up cash."),
        })
    return out
