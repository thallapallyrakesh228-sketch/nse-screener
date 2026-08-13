import os
import requests
import json
from datetime import datetime, timezone, timedelta

UPSTOX_TOKEN = os.environ.get("eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0NDUzMzIiLCJqdGkiOiI2YTdjMzFmYmM2Yzk1NDZlZTAzMzdmYTMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaXNFeHRlbmRlZCI6dHJ1ZSwiaWF0IjoxNzg2NTI0MTU1LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE4MTgxMDgwMDB9.QDozpxTAGcZt6ldjEDj__J_sQmRUOul53IFJ3KQrxIw", "")

# Instrument Keys for target equities
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
    stocks_list = []

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

            pct_change = round(((ltp - prev_close) / prev_close) * 100.0, 2)
            turnover_cr = round((ltp * volume) / 10000000.0, 2)
            
            candle_span = hi - lo
            upper_wick = round((((hi - max(op, ltp)) / candle_span) * 100.0), 1) if candle_span > 0 else 0.0

            stocks_list.append({
                "sym": sym,
                "ltp": round(ltp, 2),
                "pct": pct_change,
                "turnover": turnover_cr,
                "wick": upper_wick
            })

    json_stocks = json.dumps(stocks_list)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-Time Live Screener</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #121212; color: #e0e0e0; padding: 12px; margin: 0; }}
        .card {{ background: #1e1e1e; padding: 12px; border-radius: 8px; border: 1px solid #333; margin-bottom: 12px; }}
        .header {{ font-size: 16px; font-weight: bold; color: #00e676; margin-bottom: 4px; }}
        .subtitle {{ font-size: 11px; color: #aaa; margin-bottom: 12px; }}
        
        /* Filter Controls Styling */
        .filter-panel {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }}
        .filter-group {{ display: flex; flex-direction: column; }}
        .filter-group label {{ font-size: 11px; color: #aaa; margin-bottom: 2px; }}
        .filter-group input {{ background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 6px; border-radius: 4px; font-size: 12px; }}
        
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #2a2a2a; font-size: 12px; }}
        th {{ color: #888; background: #181818; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">⚡ Dynamic NSE Breakout Screener</div>
        <div class="subtitle">Snapshot Time: {get_ist_time()} | <span id="match-count">0</span> Matches</div>
        
        <!-- Interactive Mobile Filter Panel -->
        <div class="filter-panel">
            <div class="filter-group">
                <label>Min % Change</label>
                <input type="number" id="minPct" value="0.5" step="0.5" oninput="applyFilters()">
            </div>
            <div class="filter-group">
                <label>Min Turnover (Cr)</label>
                <input type="number" id="minTurnover" value="0" step="0.5" oninput="applyFilters()">
            </div>
            <div class="filter-group">
                <label>Max Upper Wick %</label>
                <input type="number" id="maxWick" value="100" step="5" oninput="applyFilters()">
            </div>
            <div class="filter-group">
                <label>Search Stock</label>
                <input type="text" id="searchSym" placeholder="e.g. AARTI" oninput="applyFilters()">
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>LTP</th>
                    <th>Change</th>
                    <th>Turnover</th>
                    <th>Wick</th>
                </tr>
            </thead>
            <tbody id="table-body">
            </tbody>
        </table>
    </div>

    <script>
        const stocks = {json_stocks};

        function applyFilters() {{
            const minPct = parseFloat(document.getElementById('minPct').value) || -100;
            const minTurnover = parseFloat(document.getElementById('minTurnover').value) || 0;
            const maxWick = parseFloat(document.getElementById('maxWick').value) || 100;
            const searchSym = document.getElementById('searchSym').value.toUpperCase().trim();

            const tbody = document.getElementById('table-body');
            tbody.innerHTML = '';
            
            let matches = 0;

            stocks.forEach(s => {{
                if (s.pct >= minPct && s.turnover >= minTurnover && s.wick <= maxWick) {{
                    if (searchSym === '' || s.sym.includes(searchSym)) {{
                        matches++;
                        const color = s.pct > 0 ? '#00e676' : (s.pct < 0 ? '#ff5252' : '#888');
                        const sign = s.pct > 0 ? '+' : '';
                        
                        const row = `<tr>
                            <td><b>${{s.sym}}</b></td>
                            <td>₹${{s.ltp}}</td>
                            <td style="color:${{color}}; font-weight:bold;">${{sign}}${{s.pct}}%</td>
                            <td>₹${{s.turnover}} Cr</td>
                            <td>${{s.wick}}%</td>
                        </tr>`;
                        tbody.innerHTML += row;
                    }}
                }}
            }});

            document.getElementById('match-count').innerText = matches;
            if (matches === 0) {{
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#888;">No stocks match your active filters.</td></tr>';
            }}
        }}

        // Run filter on initial page load
        applyFilters();
    </script>
</body>
</html>"""

    with open("index.html", "w") as f:
        f.write(html_content)

if __name__ == "__main__":
    run_realtime_screener()
