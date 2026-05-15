import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup

st.set_page_config(page_title="PelosiTrader", layout="wide")

# ─── CUSTOM CSS ───
st.markdown("""
<style>
.stApp { background-color: #0a0a0a; color: #fff; }
h1, h2, h3 { color: #00f2ff !important; }
.trade-buy { color: #00ff88; }
.trade-sell { color: #ff4444; }
.pos { color: #00ff88; font-weight: bold; }
.neg { color: #ff4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ─── DATA FETCH ───

@st.cache_data(ttl=3600)
def scrape_trades():
    """Scrape Nancy Pelosi's trades from QuiverQuant."""
    url = "https://www.quiverquant.com/congresstrading/politician/Nancy%20Pelosi-P000197"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        
        trades = []
        if table:
            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 6:
                    raw_stock = cells[0].get_text(strip=True)
                    # Extract ticker - usually first 1-5 uppercase letters before company name
                    ticker_match = re.match(r'^([A-Z]{1,5})', raw_stock)
                    ticker = ticker_match.group(1) if ticker_match else raw_stock[:4]
                    
                    raw_trans = cells[1].get_text(strip=True)
                    trans_match = re.match(r'(Purchase|Sale|Sell|Exchange)', raw_trans)
                    trans_type = trans_match.group(1) if trans_match else "N/A"
                    
                    amt_match = re.search(r'\$([\d,]+)\s*-\s*\$([\d,]+)', raw_trans)
                    amount = f"${amt_match.group(1)} - ${amt_match.group(2)}" if amt_match else raw_trans
                    
                    filed = cells[2].get_text(strip=True)
                    traded = cells[3].get_text(strip=True)
                    desc = cells[4].get_text(strip=True)[:80]
                    excess = cells[5].get_text(strip=True)
                    
                    trades.append({
                        "Ticker": ticker,
                        "Type": trans_type,
                        "Amount": amount,
                        "Filed": filed,
                        "Traded": traded,
                        "Description": desc,
                        "Excess Return": excess
                    })
        return trades
    except Exception as e:
        st.error(f"Fehler beim Scrapen: {e}")
        return []

@st.cache_data(ttl=300)
def get_stock_prices(tickers):
    """Get live prices for a list of tickers."""
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
st.markdown("Live-Tracking aller Nancy Pelosi Stock Trades | Powered by QuiverQuant + Yahoo Finance")

# Fetch trades
trades = scrape_trades()
df = pd.DataFrame(trades)

# ─── TOP STATS ───
if not df.empty:
    total_trades = len(df)
    buys = len(df[df["Type"] == "Purchase"])
    sells = len(df[df["Type"].isin(["Sale", "Sell"])])
    
    unique_tickers = df["Ticker"].unique().tolist()
    unique_tickers = [t for t in unique_tickers if len(t) <= 5 and t.isalpha()]
    
    # Get live prices for tickers
    prices = get_stock_prices(unique_tickers)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total Trades", total_trades)
    with col2:
        st.metric("🟢 Purchases", buys)
    with col3:
        st.metric("🔴 Sales", sells)
    with col4:
        st.metric("📈 Trade Volume", "$212.99M")
    
    st.divider()
    
    # ─── LIVE PORTFOLIO ───
    st.subheader("💼 Live Stock Watchlist")
    
    portfolio_data = []
    for ticker in unique_tickers[:20]:  # top 20 unique tickers
        if ticker in prices:
            p = prices[ticker]
            # Count how many times this ticker was traded
            trade_count = len(df[df["Ticker"] == ticker])
            portfolio_data.append({
                "Ticker": ticker,
                "Price": f"${p['price']:.2f}" if p['price'] else "N/A",
                "Change": p['change'],
                "Volume": trade_count
            })
    
    port_df = pd.DataFrame(portfolio_data)
    if not port_df.empty:
        # Style the change column
        def style_change(val):
            if isinstance(val, (int, float)):
                if val > 0: return f"🟢 +{val:.2f}%"
                elif val < 0: return f"🔴 {val:.2f}%"
                else: return "⚪ 0.00%"
            return str(val)
        
        port_df["Change"] = port_df["Change"].apply(style_change)
        st.dataframe(port_df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # ─── TRADES TABLE ───
    st.subheader("📋 Trade History")
    
    # Filters
    colf1, colf2 = st.columns(2)
    with colf1:
        type_filter = st.multiselect("Transaction Type", ["All", "Purchase", "Sale"], default="All")
    with colf2:
        search = st.text_input("🔍 Search Ticker", placeholder="e.g. NVDA, AAPL")
    
    filtered = df.copy()
    if type_filter and "All" not in type_filter:
        filtered = filtered[filtered["Type"].isin(type_filter)]
    if search:
        filtered = filtered[filtered["Ticker"].str.contains(search.upper(), na=False)]
    
    # Style the table
    def highlight_type(val):
        if "Purchase" in val: return "color: #00ff88"
        elif "Sale" in val or "Sell" in val: return "color: #ff4444"
        return ""
    
    styled = filtered.style.map(highlight_type, subset=["Type"])
    st.dataframe(styled, use_container_width=True, hide_index=True)
    
    st.caption(f"📅 Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
else:
    st.warning("Keine Trades geladen. Versuche es später erneut.")
