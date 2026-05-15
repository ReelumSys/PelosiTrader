import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import json
import re
from datetime import datetime

st.set_page_config(page_title="PelosiTrader", layout="wide")

# ─── CUSTOM CSS ───
st.markdown("""
<style>
.stApp { background-color: #0a0a0a; color: #fff; }
h1, h2, h3 { color: #00f2ff !important; }
.green { color: #00ff88; font-weight: bold; }
.red { color: #ff4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ─── DATA FETCH ───
COLUMNS = ["Ticker", "Type", "Filed", "Traded", "Description", "Excess Return",
           "Politician", "Filing ID", "Company Name", "Asset Type", "Amount",
           "Chamber", "Party", "Sector", "Estimated Value"]

@st.cache_data(ttl=3600)
def scrape_trades():
    """Extract Nancy Pelosi's trades from embedded JS variable on QuiverQuant."""
    url = "https://www.quiverquant.com/congresstrading/politician/Nancy%20Pelosi-P000197"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        
        # Extract the tradeData JavaScript variable using regex
        match = re.search(r'let tradeData\s*=\s*(\[\[.*?\]\])\s*;', r.text, re.DOTALL)
        if not match:
            st.error("tradeData nicht gefunden. Seite hat sich geändert?")
            return []
        
        raw_data = match.group(1)
        trades = json.loads(raw_data)
        
        result = []
        for t in trades:
            result.append({
                "Ticker": t[0] if t[0] else "N/A",
                "Type": t[1],
                "Filed": t[2][:10] if t[2] else "",
                "Traded": t[3][:10] if t[3] else "",
                "Description": (t[4] or "")[:80],
                "Excess Return": t[5] if isinstance(t[5], (int, float)) and not (t[5] != t[5]) else None,  # NaN check
                "Company": t[7] if len(t) > 7 else "",
                "Asset Type": t[8] if len(t) > 8 else "",
                "Amount": t[9] if len(t) > 9 else "",
                "Sector": t[12] if len(t) > 12 and t[12] else "N/A",
                "Est. Value": t[14] if len(t) > 14 and isinstance(t[14], (int, float)) else 0
            })
        return result
    except Exception as e:
        st.error(f"Fehler beim Scrapen: {e}")
        return []

@st.cache_data(ttl=300)
def get_stock_prices(tickers):
    prices = {}
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            info = stock.info
            price = info.get("currentPrice", info.get("regularMarketPrice", 0))
            change = info.get("regularMarketChangePercent", 0)
            prices[t] = {"price": price, "change": change}
        except:
            prices[t] = {"price": 0, "change": 0}
    return prices

# ─── MAIN APP ───
st.title("🏛️ PelosiTrader")
st.markdown("Live-Tracking aller Nancy Pelosi Stock Trades | Daten von QuiverQuant + Yahoo Finance")

trades = scrape_trades()
df = pd.DataFrame(trades)

if df.empty:
    st.error("❌ Keine Trades geladen! QuiverQuant-Seite könnte sich geändert haben oder ist nicht erreichbar.")
    st.stop()

# ─── TOP STATS ───
buys = len(df[df["Type"] == "Purchase"])
sells = len(df[df["Type"].isin(["Sale", "Sell"])])
total_value = df["Est. Value"].sum()
unique_tickers = sorted(set(t for t in df["Ticker"].unique() if t != "N/A" and len(t) <= 5 and t.isalpha()))

col1, col2, col3, col4 = st.columns(4)
col1.metric("📊 Total Trades", len(df))
col2.metric("🟢 Purchases", buys)
col3.metric("🔴 Sales", sells)
col4.metric("💰 Trade Volume", f"${total_value:,.0f}")

st.divider()

# ─── LIVE WATCHLIST ───
st.subheader("💼 Live Stock Watchlist")
prices = get_stock_prices(unique_tickers)

watchlist = []
for ticker in unique_tickers[:25]:
    if ticker in prices:
        p = prices[ticker]
        trades_count = len(df[df["Ticker"] == ticker])
        avg_return = df[df["Ticker"] == ticker]["Excess Return"].dropna().mean()
        
        watchlist.append({
            "Ticker": ticker,
            "Price": f"${p['price']:.2f}" if p['price'] else "N/A",
            "Change": p['change'],
            "Trades": trades_count,
            "Avg Excess Return": avg_return
        })

if watchlist:
    wl = pd.DataFrame(watchlist)
    def fmt_change(v):
        if isinstance(v, (int, float)):
            return f"{'🟢' if v > 0 else '🔴'} {v:+.2f}%" if v != 0 else "⚪ 0.00%"
        return str(v)
    def fmt_return(v):
        if isinstance(v, (int, float)):
            return f"{'🟢' if v > 0 else '🔴'} {v:+.1f}%" if v != 0 else "0.0%"
        return "N/A"
    
    wl["Change"] = wl["Change"].apply(fmt_change)
    wl["Avg Excess Return"] = wl["Avg Excess Return"].apply(fmt_return)
    st.dataframe(wl, use_container_width=True, hide_index=True)

st.divider()

# ─── TRADES TABLE ───
st.subheader("📋 Trade History")
colf1, colf2, colf3 = st.columns(3)
with colf1:
    type_filter = st.multiselect("Type", ["All", "Purchase", "Sale", "Exchange"], default="All")
with colf2:
    tickers_all = ["All"] + unique_tickers
    ticker_filter = st.selectbox("Ticker", tickers_all)
with colf3:
    search = st.text_input("🔍 Search", placeholder="Company oder Sector")

filtered = df.copy()
if type_filter and "All" not in type_filter:
    filtered = filtered[filtered["Type"].isin(type_filter)]
if ticker_filter and ticker_filter != "All":
    filtered = filtered[filtered["Ticker"] == ticker_filter]
if search:
    mask = filtered["Company"].str.contains(search, case=False, na=False) | filtered["Sector"].str.contains(search, case=False, na=False)
    filtered = filtered[mask]

# Format display
display = filtered[["Ticker", "Type", "Filed", "Traded", "Amount", "Excess Return", "Sector"]].copy()
def fmt_excess(v):
    if v is None or (isinstance(v, float) and v != v):  # NaN check
        return "N/A"
    return f"{'🟢' if v > 0 else '🔴'} {v:+.2f}%"

display["Excess Return"] = display["Excess Return"].apply(fmt_excess)
display["Type"] = display["Type"].apply(lambda x: f"{'🟢' if 'Purchase' in x else '🔴'} {x}")

st.dataframe(display, use_container_width=True, hide_index=True)

# ─── TOP MOVERS ───
st.divider()
st.subheader("🏆 Top Performers & 🗑️ Worst Performers")

valid_returns = df[df["Excess Return"].notna() & (df["Excess Return"] != df["Excess Return"]) == False].copy()
if not valid_returns.empty:
    top5 = valid_returns.nlargest(5, "Excess Return")
    worst5 = valid_returns.nsmallest(5, "Excess Return")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🏆 Best Trades**")
        for _, row in top5.iterrows():
            st.markdown(f"**{row['Ticker']}** ({row['Type']}) — 🟢 {row['Excess Return']:+.2f}%")
            st.caption(f"{row['Company'][:50]} | {row['Traded']}")
    with c2:
        st.markdown("**🗑️ Worst Trades**")
        for _, row in worst5.iterrows():
            st.markdown(f"**{row['Ticker']}** ({row['Type']}) — 🔴 {row['Excess Return']:+.2f}%")
            st.caption(f"{row['Company'][:50]} | {row['Traded']}")

st.caption(f"📅 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
