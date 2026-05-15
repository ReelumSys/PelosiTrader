import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import json
import re
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="PelosiTrader", layout="wide")

# ─── CUSTOM CSS ───
st.markdown("""
<style>
.stApp { background-color: #0a0a0a; color: #fff; }
h1, h2, h3, h4 { color: #00f2ff !important; }
.green { color: #00ff88; font-weight: bold; }
.red { color: #ff4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ─── DATA FETCH ───

@st.cache_data(ttl=3600)
def scrape_trades():
    url = "https://www.quiverquant.com/congresstrading/politician/Nancy%20Pelosi-P000197"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        match = re.search(r'let tradeData\s*=\s*(\[\[.*?\]\])\s*;', r.text, re.DOTALL)
        if not match: return []
        trades = json.loads(match.group(1))
        result = []
        for t in trades:
            result.append({
                "Ticker": t[0] if t[0] else "N/A",
                "Type": t[1],
                "Filed": t[2][:10] if t[2] else "",
                "Traded": t[3][:10] if t[3] else "",
                "Description": (t[4] or "")[:80],
                "Excess Return": t[5] if isinstance(t[5], (int, float)) and not (t[5] != t[5]) else None,
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

@st.cache_data(ttl=3600)
def get_price_history(ticker):
    """Fetch up to 20 years of daily price history."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="20y")
        if hist.empty:
            return None
        hist = hist.reset_index()
        hist["Date"] = hist["Date"].dt.tz_localize(None)
        return hist
    except:
        return None

def plotly_bg():
    return dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#ccc'))

# ─── MAIN APP ───
st.title("🏛️ PelosiTrader")
st.markdown("Live-Tracking Nancy Pelosi Stock Trades | QuiverQuant + Yahoo Finance")

trades = scrape_trades()
df = pd.DataFrame(trades)

if df.empty:
    st.error("❌ Keine Trades geladen!")
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

# Timestamp
# Convert Traded dates
df["Traded_dt"] = pd.to_datetime(df["Traded"], errors="coerce")
df["Year"] = df["Traded_dt"].dt.year

st.divider()

# ─── PERFORMANCE GRAPHEN ───
st.subheader("📈 Performance Graphen")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Excess Return", "📦 Volume by Year", "🏷️ Sector", "🎯 Win/Loss Ratio", "📈 20-Jahre Kursverlauf"])

with tab1:
    # Cumulative excess return over time
    plot_df = df.dropna(subset=["Excess Return", "Traded_dt"]).sort_values("Traded_dt").copy()
    plot_df["Cumulative Return"] = plot_df["Excess Return"].cumsum()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df["Traded_dt"], y=plot_df["Cumulative Return"],
        mode='lines', name='Cumulative Excess Return',
        line=dict(color='#00f2ff', width=2),
        fill='tozeroy', fillcolor='rgba(0, 242, 255, 0.1)'
    ))
    fig.update_layout(
        title="Cumulative Excess Return Over Time",
        xaxis_title="Trade Date", yaxis_title="Cumulative Return (%)",
        **plotly_bg(), height=400
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    # Trade volume by year (buy/sell stacked)
    volume_by_year = df.groupby(["Year", "Type"]).agg(Volume=("Est. Value", "sum")).reset_index()
    vol_pivot = volume_by_year.pivot(index="Year", columns="Type", values="Volume").fillna(0)
    # Only keep Purchase and Sale
    vol_pivot = vol_pivot[[c for c in ["Purchase", "Sale", "Sell", "Exchange"] if c in vol_pivot.columns]]
    if "Sale" in vol_pivot and "Sell" in vol_pivot:
        vol_pivot["Sale"] = vol_pivot.get("Sale", 0) + vol_pivot.get("Sell", 0)
        vol_pivot = vol_pivot.drop(columns=["Sell"], errors="ignore")
    
    fig = go.Figure()
    for col in vol_pivot.columns:
        color = '#00ff88' if col == "Purchase" else '#ff4444'
        fig.add_trace(go.Bar(name=col, x=vol_pivot.index, y=vol_pivot[col], marker_color=color))
    fig.update_layout(barmode='stack', title="Trade Volume by Year", **plotly_bg(), height=400,
                      yaxis_title="Volume ($)")
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    # Sector distribution
    sector_counts = df["Sector"].value_counts().reset_index()
    sector_counts.columns = ["Sector", "Trades"]
    fig = px.pie(sector_counts, values="Trades", names="Sector", title="Trades by Sector",
                 color_discrete_sequence=px.colors.sequential.Tealgrn,
                 hole=0.4)
    fig.update_layout(**plotly_bg(), height=400)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    # Win/Loss ratio by year
    df_wl = df.dropna(subset=["Excess Return"]).copy()
    df_wl["Result"] = df_wl["Excess Return"].apply(lambda x: "Win 🟢" if x > 0 else "Loss 🔴" if x < 0 else "Neutral")
    wl_by_year = df_wl.groupby(["Year", "Result"]).size().reset_index(name="Count")
    
    fig = px.bar(wl_by_year, x="Year", y="Count", color="Result",
                 color_discrete_map={"Win 🟢": "#00ff88", "Loss 🔴": "#ff4444", "Neutral": "#888"},
                 title="Win/Loss Ratio by Year", barmode="group")
    fig.update_layout(**plotly_bg(), height=400)
    st.plotly_chart(fig, use_container_width=True)

with tab5:
    st.markdown("**Wähle einen Ticker für 20 Jahre Kursverlauf**")
    
    valid_tickers = [t for t in unique_tickers if t not in ("N/A", "") and len(t) <= 5 and t.isalpha()]
    selected = st.selectbox("Ticker auswählen", valid_tickers, key="hist_ticker")
    
    if selected:
        with st.spinner(f"Lade 20 Jahre Kursdaten für {selected}..."):
            hist = get_price_history(selected)
        if hist is not None:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist["Date"], y=hist["Close"],
                mode='lines', name=f"{selected} Close",
                line=dict(color='#00f2ff', width=1.5),
                fill='tozeroy', fillcolor='rgba(0, 242, 255, 0.05)'
            ))
            # Add moving averages
            hist["MA50"] = hist["Close"].rolling(50).mean()
            hist["MA200"] = hist["Close"].rolling(200).mean()
            fig.add_trace(go.Scatter(x=hist["Date"], y=hist["MA50"], mode='lines',
                                     name="MA50", line=dict(color='#ffaa00', width=1)))
            fig.add_trace(go.Scatter(x=hist["Date"], y=hist["MA200"], mode='lines',
                                     name="MA200", line=dict(color='#ff4444', width=1)))
            
            start_price = hist["Close"].iloc[0]
            end_price = hist["Close"].iloc[-1]
            total_return = ((end_price - start_price) / start_price) * 100
            
            fig.update_layout(
                title=f"{selected} — 20-Jahre Kursverlauf",
                xaxis_title="Date", yaxis_title="Price ($)",
                **plotly_bg(), height=500,
                hovermode='x unified'
            )
            
            # Trade markers directly on the chart
            ticker_trades = df[df["Ticker"] == selected].dropna(subset=["Traded_dt"])
            for _, trade in ticker_trades.iterrows():
                td = trade["Traded_dt"]
                if pd.notna(td):
                    closest = hist.iloc[(hist["Date"] - td).abs().argsort()[:1]]
                    if not closest.empty:
                        px_val = closest["Close"].values[0]
                        color = '#00ff88' if "Purchase" in str(trade["Type"]) else '#ff4444'
                        symbol = "triangle-up" if "Purchase" in str(trade["Type"]) else "triangle-down"
                        fig.add_trace(go.Scatter(
                            x=[td], y=[px_val],
                            mode='markers',
                            marker=dict(color=color, size=10, symbol=symbol,
                                        line=dict(color='white', width=1)),
                            showlegend=False,
                            hovertemplate=f"{trade['Type']}: {trade['Amount']}<br>Return: {trade['Excess Return']}%<extra></extra>"
                        ))
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Stats
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("💰 Aktuell", f"${end_price:.2f}" if not pd.isna(end_price) else "N/A")
            col_b.metric("📈 20J Return", f"{total_return:+.1f}%")
            col_c.metric("🔝 High", f"${hist['High'].max():.2f}")
            col_d.metric("🔽 Low", f"${hist['Low'].min():.2f}")
        else:
            st.error(f"❌ Keine Kursdaten für {selected} verfügbar")

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
            "Ticker": ticker, "Price": f"${p['price']:.2f}" if p['price'] else "N/A",
            "Change": p['change'], "Trades": trades_count, "Avg Excess Return": avg_return
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

display = filtered[["Ticker", "Type", "Filed", "Traded", "Amount", "Excess Return", "Sector"]].copy()
def fmt_excess(v):
    if v is None or (isinstance(v, float) and v != v):
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
