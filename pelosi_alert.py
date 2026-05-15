#!/usr/bin/env python3
"""Pelosi Trade Alert Script - detects new trades and outputs them for delivery.

Runs as a cronjob (no_agent=True). Stores last seen filing IDs in ~/.hermes/pelosi_alerts.json.
Only outputs when new trades are detected (silent otherwise).
"""

import requests
import json
import re
import os
from datetime import datetime

DATA_FILE = os.path.expanduser("~/.hermes/pelosi_alerts.json")

def fetch_current_trades():
    url = "https://www.quiverquant.com/congresstrading/politician/Nancy%20Pelosi-P000197"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=15)
    match = re.search(r'let tradeData\s*=\s*(\[\[.*?\]\])\s*;', r.text, re.DOTALL)
    if not match:
        return []
    trades = json.loads(match.group(1))
    result = []
    for t in trades:
        result.append({
            "ticker": t[0] if t[0] else "N/A",
            "type": t[1],
            "filed": t[2][:10] if t[2] else "",
            "traded": t[3][:10] if t[3] else "",
            "desc": (t[4] or "")[:80],
            "excess_return": t[5] if isinstance(t[5], (int, float)) and not (t[5] != t[5]) else None,
            "company": t[7] if len(t) > 7 else "",
            "amount": t[9] if len(t) > 9 else "",
            "sector": t[12] if len(t) > 12 and t[12] else "N/A",
            "filing_id": t[7] if len(t) > 7 else "",  # Use company name as fingerprint
            "est_value": t[14] if len(t) > 14 and isinstance(t[14], (int, float)) else 0
        })
    return result

def load_snapshot():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"last_seen_ids": [], "total_trades": 0}

def save_snapshot(snapshot):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(snapshot, f)

def fmt_trade(t):
    ticker = t["ticker"]
    company = t["company"][:40]
    ttype = t["type"]
    amount = t["amount"]
    traded = t["traded"]
    sector = t["sector"]
    ret = t["excess_return"]
    ret_str = f" ({'+' if ret > 0 else ''}{ret:.1f}%)" if ret else ""
    
    emoji = "🟢" if ttype == "Purchase" else "🔴" if ttype in ("Sale", "Sell") else "🔄"
    return f"{emoji} **{ticker}** ({company}) — {ttype}\n   💰 {amount} | 📅 {traded}{ret_str}"

def main():
    trades = fetch_current_trades()
    if not trades:
        # If we can't reach the page, stay silent (don't spam errors)
        return
    
    snapshot = load_snapshot()
    current_ids = set(t["filing_id"] + t["filed"] + t["type"] + str(t["ticker"]) for t in trades)
    
    if not snapshot["last_seen_ids"]:
        # First run - just save and stay silent
        snapshot["last_seen_ids"] = list(current_ids)
        snapshot["total_trades"] = len(trades)
        save_snapshot(snapshot)
        return
    
    # Find new trades
    new_ids = current_ids - set(snapshot["last_seen_ids"])
    new_trades = [t for t in trades if (t["filing_id"] + t["filed"] + t["type"] + str(t["ticker"])) in new_ids]
    
    if new_trades:
        # Sort by most recent
        new_trades.sort(key=lambda x: x.get("traded", ""), reverse=True)
        report = []
        report.append(f"🚨 **NEUE PELOSI TRADES ENTDECKT!**")
        report.append(f"📊 {len(new_trades)} neue Transaktion(en)\n")
        
        for t in new_trades[:10]:  # Max 10 per alert
            report.append(fmt_trade(t))
        
        report.append(f"\n📈 Total Trades Now: {len(trades)}")
        
        # Update snapshot
        snapshot["last_seen_ids"] = list(current_ids)
        snapshot["total_trades"] = len(trades)
        save_snapshot(snapshot)
        
        print("\n".join(report))
    else:
        # No new trades - silent
        pass

if __name__ == "__main__":
    main()
