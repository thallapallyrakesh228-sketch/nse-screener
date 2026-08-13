import os
import requests
from datetime import datetime, timezone, timedelta

UPSTOX_TOKEN = os.environ.get("eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0NDUzMzIiLCJqdGkiOiI2YTdjMzFmYmM2Yzk1NDZlZTAzMzdmYTMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaXNFeHRlbmRlZCI6dHJ1ZSwiaWF0IjoxNzg2NTI0MTU1LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE4MTgxMDgwMDB9.QDozpxTAGcZt6ldjEDj__J_sQmRUOul53IFJ3KQrxIw", "")

# Sample Instrument Keys for standard equities
INSTRUMENTS = [
    "NSE_EQ|INE021A01026", # AARTIIND
    "NSE_EQ|INE002A01018", # RELIANCE
    "NSE_EQ|INE040A01034", # HDFCBANK
    "NSE_EQ|INE009A01021", # INFY
    "NSE_EQ|INE216A01030"  # TATAMOTORS
]

def get_ist_time():
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    return ist_now.strftime("%Y-%m-%d %I:%M:%S %p IST")

def run_realtime_screener():
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {UPSTOX_TOKEN}"
    }
    
    keys = ",".join(INSTRUMENTS)
    url = f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={keys}"
    
    res = requests.get(url, headers=headers, timeout=15)
    rows_html = ""
    match_count = 0

    if res.status_code == 200:
        data = res.json().get("data", {})
        
        for key, quote in data.items():
            sym = quote.get("symbol")
            ltp = quote.get("last_price", 0.0)
            volume = quote.get("volume", 0)
            
            ohlc = quote.get("ohlc", {})
            op = ohlc.get("open", 0.0)
            hi = ohlc.get("high", 0.0)
            lo = ohlc.get("low", 0.0)
            prev_close = ohlc.get("close", 0.0)
            
            if prev_close == 0:
                continue

            pct_change = ((ltp - prev_close) / prev_close) * 100.0
            turnover_cr = (ltp * volume) / 10000000.0
            
            candle_span = hi - lo
            upper_wick = (((hi - max(op, ltp)) / candle_span) * 100.0) if candle_span > 0 else 0.0

            chg_color = "#00e676" if pct_change > 0 else ("#ff5252" if pct_change < 0 else "#888")
            chg_sign = "+" if pct_change > 0 else ""

            # Filter Condition
            if pct_change >= 0.5:
                match_count += 1
                rows_html += f"""
                <tr>
                    <td><b>{sym}</b></td>
                    <td>₹{round(ltp, 2)}</td>
                    <td style="color:{chg_color}; font-weight:bold;">{chg_sign}{round(pct_change, 2)}%</td>
                    <td>₹{round(turnover_cr, 2)} Cr</td>
                    <td>{round(upper_wick, 1)}%</td>
                </tr>
                """

    if not rows_html:
        rows_html = '<tr><td colspan="5" style="text-align:center; color:#888;">No stocks matched criteria at this snapshot time.</td></tr>'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-Time Live Screener</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #121212; color: #e0e0e0; padding: 12px; margin: 0; }}
        .card {{ background: #1e1e1e; padding: 12px; border-radius: 8px; border: 1px solid #333; }}
        .header {{ font-size: 15px; font-weight: bold; color: #00e676; margin-bottom: 4px; }}
        .subtitle {{ font-size: 11px; color: #aaa; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #2a2a2a; font-size: 12px; }}
        th {{ color: #888; background: #181818; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">⚡ NSE Breakout Screener (Live Candle Mode)</div>
        <div class="subtitle">Snapshot Time: {get_ist_time()} | Matches: {match_count}</div>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>LTP</th>
                    <th>Change</th>
                    <th>Turnover</th>
                    <th>Upper Wick</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
</body>
</html>"""

    with open("index.html", "w") as f:
        f.write(html_content)

if __name__ == "__main__":
    run_realtime_screener()
  
