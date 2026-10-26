# 📈 Small Business Sales Insights

**Upload your store's sales export and get plain-English answers in seconds:** what's selling, who your best customers are, who's slipping away, and what to do next.

🔗 **Live app:** _add your Streamlit link here_
📊 **Dashboard:** _add your Data Studio link here_
📝 **Case study:** _add your Notion link here_

---

## The problem
I analysed ~500 real posts and reviews from small business owners (Shopify Community, Square Seller Community, Etsy forums, Capterra). The top pains:
- **29%** of owner complaints: numbers they can't trust (sales ≠ payouts, missing visitors)
- **12%**: manual spreadsheet work to get basic answers
- **9%**: reports they need simply don't exist
- Shopify owners mostly **distrust their numbers**; Square owners mostly **lack reports** and rebuild them in Excel

Owners don't want more dashboards. They want **simple answers and next steps**.

## What the app does
1. **Upload** a Shopify, Square, Etsy or any spreadsheet export (CSV or Excel), or try the built-in sample.
2. **Auto-detects columns** (date, order, product, quantity, price/total, customer) and lets you fix any guesses.
3. **Cleans the data:** removes cancellations, returns, zero-price rows and duplicates, and shows what was removed.
4. Shows **KPIs**: revenue, orders, average order value, customers, repeat-customer rate.
5. Writes **"Insights for you"**: plain-English findings, each with a recommended action (customer concentration, lapsed customers, one-time buyers, seasonality, trend vs last year, best weekday, product concentration).
6. **Customer segments (RFM):** Champions, Loyal, At Risk, Can't Lose Them, and more.
7. **Win-back list:** a downloadable CSV of valuable customers who've gone quiet.

## Findings on the sample data (UCI Online Retail II, 1M+ transactions)
- **25% of customers (Champions) drive 70% of revenue**
- **825 lapsed high-value customers**, worth **£1.4M** in past sales
- **Sep–Nov brings in 36–38% of yearly revenue**
- Only ~20% of new customers buy again in any given month, so **the second order is the key moment**

## How it's built
| File | What it does |
|---|---|
| `app.py` | Streamlit interface: upload, column mapping, KPIs, charts, insights, downloads |
| `insights.py` | Analysis engine (pure pandas): cleaning, KPIs, RFM segmentation, insight rules |
| `sample_sales.csv` | 600 real customers' full purchase histories from UCI Online Retail II |

**Tools:** Python, pandas, Streamlit, Altair. Analysis prototyped in Google Colab, dashboard in Data Studio (Looker Studio).

## Run it locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Limitations and next steps
- Insight rules are simple and transparent by design. Next step: an LLM to phrase insights, using summary numbers only (never customer data).
- Works best with at least a few months of data and 20+ identified customers.
- Next features: direct Shopify/Square connection, weekly email summary, inventory reorder alerts.

## Data source
*Online Retail II*, UCI Machine Learning Repository: https://archive.ics.uci.edu/dataset/502/online+retail+ii
