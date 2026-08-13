import os
import requests
import json
from datetime import datetime, timezone, timedelta

UPSTOX_TOKEN = os.environ.get("eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0NDUzMzIiLCJqdGkiOiI2YTdjMzFmYmM2Yzk1NDZlZTAzMzdmYTMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaXNFeHRlbmRlZCI6dHJ1ZSwiaWF0IjoxNzg2NTI0MTU1LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE4MTgxMDgwMDB9.QDozpxTAGcZt6ldjEDj__J_sQmRUOul53IFJ3KQrxIw", "")

# Instrument Keys for target equities
INSTRUMENTS = {
    "NSE_EQ|INE021A01026": "AARTIIND",
    "NSE_EQ|INE002A01018": "RELIANCE",
    "NSE_EQ|INE040A01034": "HDFCBANK",
    "NSE_EQ|INE009A01021": "INFY",
    "NSE_EQ|INE216A01030": "TATAMOTORS"
}

def get_ist_time():
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    return ist_now.strftime("%Y-%m-%d %I:%M:%S %p IST")

def fetch_historical_3yr(key):
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=3*365)).strftime("%Y-%m-%d")
    
    url = f"https://api.upstox.com/v2/historical-candle/{key}/day/{to_date}/{from_date}"
    headers = {"Accept": "application/json"}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get("data", {}).get("candles", [])
    except Exception:
        pass
    return []

def run_screener_engine():
    date_records = {} # { "YYYY-MM-DD": [ {stock_data}, ... ] }

    for key, symbol in INSTRUMENTS.items():
        candles = fetch_historical_3yr(key)
        if not candles:
            continue

        chrono_candles = list(reversed(candles))
        closes = [c[4] for c in chrono_candles]
        
        # Precompute EMA 20 history
        ema20_series = []
        k = 2 / (20 + 1)
        current_ema = None
        for idx, cl in enumerate(closes):
            if idx < 19:
                ema20_series.append(cl)
            elif idx == 19:
                current_ema = sum(closes[:20]) / 20.0
                ema20_series.append(current_ema)
            else:
                current_ema = (cl * k) + (current_ema * (1 - k))
                ema20_series.append(current_ema)

        for i in range(len(chrono_candles)):
            c = chrono_candles[i]
            dt = c[0].split("T")[0]
            op, hi, lo, cl, vol = c[1], c[2], c[3], c[4], c[5]
            
            prev_cl = chrono_candles[i-1][4] if i > 0 else cl
            prev_ema20 = ema20_series[i-1] if i > 0 else ema20_series[i]
            curr_ema20 = ema20_series[i]
            
            pct_chg = round(((cl - prev_cl) / prev_cl) * 100.0, 2) if prev_cl > 0 else 0.0
            turnover_cr = round((cl * vol) / 10000000.0, 2)
            
            span = hi - lo
            upper_wick = round((((hi - max(op, cl)) / span) * 100.0), 1) if span > 0 else 0.0
            
            # 20-day Average Volume for RVOL
            past_vols = [x[5] for x in chrono_candles[max(0, i-20):i]]
            avg_vol20 = sum(past_vols) / len(past_vols) if past_vols else vol
            rvol = round(vol / avg_vol20, 2) if avg_vol20 > 0 else 1.0
            
            # 365-day High
            past_365_highs = [x[2] for x in chrono_candles[max(0, i-365):i]]
            max_365 = max(past_365_highs) if past_365_highs else hi
            
            crossed_above_ema20 = (prev_cl <= prev_ema20 and cl > curr_ema20)
            crossed_below_ema20 = (prev_cl >= prev_ema20 and cl < curr_ema20)

            record = {
                "sym": symbol,
                "close": round(cl, 2),
                "pct": pct_chg,
                "turnover": turnover_cr,
                "rvol": rvol,
                "ema20": round(curr_ema20, 2),
                "prev_close": round(prev_cl, 2),
                "prev_ema20": round(prev_ema20, 2),
                "crossed_above_ema20": crossed_above_ema20,
                "crossed_below_ema20": crossed_below_ema20,
                "max_365": round(max_365, 2),
                "wick": upper_wick
            }
            
            if dt not in date_records:
                date_records[dt] = []
            date_records[dt].append(record)

    json_records = json.dumps(date_records)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Master Screener & Backtester</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #121212; color: #e0e0e0; padding: 10px; margin: 0; }}
        .card {{ background: #1e1e1e; padding: 12px; border-radius: 8px; border: 1px solid #333; margin-bottom: 12px; }}
        .header {{ font-size: 16px; font-weight: bold; color: #00e676; margin-bottom: 2px; }}
        .subtitle {{ font-size: 10px; color: #aaa; margin-bottom: 10px; }}
        .section-title {{ font-size: 12px; font-weight: bold; color: #00e676; margin: 10px 0 6px 0; border-bottom: 1px solid #333; padding-bottom: 4px; }}
        .filter-row {{ display: grid; grid-template-columns: 24px 1fr 100px 80px; gap: 6px; align-items: center; margin-bottom: 6px; font-size: 11px; }}
        .filter-row input[type="text"], .filter-row input[type="number"], .filter-row select {{ background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 4px; border-radius: 4px; font-size: 11px; width: 100%; box-sizing: border-box; }}
        .date-panel {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }}
        .date-panel label {{ font-size: 10px; color: #aaa; display: block; margin-bottom: 2px; }}
        .date-panel input {{ background: #2a2a2a; border: 1px solid #444; color: #fff; padding: 6px; border-radius: 4px; font-size: 11px; width: 100%; box-sizing: border-box; }}
        .btn {{ background: #00e676; color: #121212; font-weight: bold; border: none; padding: 8px 12px; border-radius: 4px; font-size: 11px; cursor: pointer; width: 100%; margin-top: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
        th, td {{ padding: 6px; text-align: left; border-bottom: 1px solid #2a2a2a; font-size: 11px; }}
        th {{ color: #888; background: #181818; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">⚡ Master Screener & Backtest Engine</div>
        <div class="subtitle">Snapshot: {get_ist_time()} | Matches: <span id="match-count">0</span></div>
        
        <div class="date-panel">
            <div>
                <label>Inspector Date (Screen View)</label>
                <input type="date" id="singleDate" onchange="applyFilters()">
            </div>
            <div>
                <label>Search Symbol</label>
                <input type="text" id="searchSym" placeholder="e.g. AARTI" oninput="applyFilters()" style="background:#2a2a2a; border:1px solid #444; color:#fff; padding:6px; border-radius:4px; font-size:11px; width:100%; box-sizing:border-box;">
            </div>
        </div>

        <div class="section-title">🎛️ 9 Master Customizable Filters (Update 1)</div>

        <div class="filter-row">
            <input type="checkbox" id="f1_en" checked onchange="applyFilters()">
            <span>1. Close vs EMA 20</span>
            <select id="f1_op" onchange="applyFilters()">
                <option value="&gt;">&gt;</option>
                <option value="&gt;=" selected>&gt;=</option>
                <option value="&lt;">&lt;</option>
                <option value="&lt;=">&lt;=</option>
                <option value="==">==</option>
                <option value="crossed_above">Crossed Above</option>
                <option value="crossed_below">Crossed Below</option>
            </select>
            <span>EMA 20</span>
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f2_en" checked onchange="applyFilters()">
            <span>2. RVOL</span>
            <select id="f2_op" onchange="applyFilters()">
                <option value="&gt;">&gt;</option>
                <option value="&gt;=" selected>&gt;=</option>
                <option value="&lt;">&lt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f2_val" value="1.5" step="0.1" oninput="applyFilters()">
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f3_en" checked onchange="applyFilters()">
            <span>3. Min % Change</span>
            <select id="f3_op" onchange="applyFilters()">
                <option value="&gt;">&gt;</option>
                <option value="&gt;=" selected>&gt;=</option>
                <option value="&lt;">&lt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f3_val" value="2.0" step="0.5" oninput="applyFilters()">
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f4_en" checked onchange="applyFilters()">
            <span>4. Max % Change</span>
            <select id="f4_op" onchange="applyFilters()">
                <option value="&lt;">&lt;</option>
                <option value="&lt;=" selected>&lt;=</option>
                <option value="&gt;">&gt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f4_val" value="10.0" step="0.5" oninput="applyFilters()">
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f5_en" checked onchange="applyFilters()">
            <span>5. Min Daily Close</span>
            <select id="f5_op" onchange="applyFilters()">
                <option value="&gt;">&gt;</option>
                <option value="&gt;=" selected>&gt;=</option>
                <option value="&lt;">&lt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f5_val" value="100" step="10" oninput="applyFilters()">
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f6_en" checked onchange="applyFilters()">
            <span>6. Max Daily Close</span>
            <select id="f6_op" onchange="applyFilters()">
                <option value="&lt;">&lt;</option>
                <option value="&lt;=" selected>&lt;=</option>
                <option value="&gt;">&gt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f6_val" value="2000" step="50" oninput="applyFilters()">
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f7_en" checked onchange="applyFilters()">
            <span>7. Min Turnover (Cr)</span>
            <select id="f7_op" onchange="applyFilters()">
                <option value="&gt;">&gt;</option>
                <option value="&gt;=" selected>&gt;=</option>
                <option value="&lt;">&lt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f7_val" value="50" step="5" oninput="applyFilters()">
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f8_en" checked onchange="applyFilters()">
            <span>8. Close vs 365D High</span>
            <select id="f8_op" onchange="applyFilters()">
                <option value="&gt;=" selected>&gt;= 365D High</option>
                <option value="&lt;">&lt; 365D High</option>
            </select>
            <span>High</span>
        </div>

        <div class="filter-row">
            <input type="checkbox" id="f9_en" checked onchange="applyFilters()">
            <span>9. Min Upper Wick %</span>
            <select id="f9_op" onchange="applyFilters()">
                <option value="&gt;">&gt;</option>
                <option value="&gt;=" selected>&gt;=</option>
                <option value="&lt;">&lt;</option>
                <option value="==">==</option>
            </select>
            <input type="number" id="f9_val" value="40" step="5" oninput="applyFilters()">
        </div>

        <div class="section-title">📊 Backtest CSV Downloader (Update 2)</div>
        <div class="date-panel">
            <div>
                <label>From Date</label>
                <input type="date" id="fromDate">
            </div>
            <div>
                <label>To Date</label>
                <input type="date" id="toDate">
            </div>
        </div>
        <button class="btn" onclick="downloadBacktestCSV()">📥 Download Backtest CSV (Active Filters)</button>

        <div class="section-title">📋 Stock Screening Results</div>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Close</th>
                    <th>Chg%</th>
                    <th>RVOL</th>
                    <th>Turnover</th>
                    <th>Wick%</th>
                </tr>
            </thead>
            <tbody id="table-body">
            </tbody>
        </table>
    </div>

    <script>
        const records = {json_records};
        const dates = Object.keys(records).sort().reverse();

        if (dates.length > 0) {{
            const latest = dates[0];
            const oldest = dates[dates.length - 1];

            document.getElementById('singleDate').value = latest;
            document.getElementById('singleDate').min = oldest;
            document.getElementById('singleDate').max = latest;

            document.getElementById('fromDate').value = dates[Math.min(20, dates.length - 1)];
            document.getElementById('fromDate').min = oldest;
            document.getElementById('fromDate').max = latest;

            document.getElementById('toDate').value = latest;
            document.getElementById('toDate').min = oldest;
            document.getElementById('toDate').max = latest;
        }}

        function compare(val1, op, val2) {{
            if (op === '>' || op === '&gt;') return val1 > val2;
            if (op === '>=' || op === '&gt;=') return val1 >= val2;
            if (op === '<' || op === '&lt;') return val1 < val2;
            if (op === '<=' || op === '&lt;=') return val1 <= val2;
            if (op === '==') return val1 === val2;
            return true;
        }}

        function evalStock(s) {{
            if (document.getElementById('f1_en').checked) {{
                const op = document.getElementById('f1_op').value;
                if (op === 'crossed_above' && !s.crossed_above_ema20) return false;
                if (op === 'crossed_below' && !s.crossed_below_ema20) return false;
                if (op !== 'crossed_above' && op !== 'crossed_below') {{
                    if (!compare(s.close, op, s.ema20)) return false;
                }}
            }}

            if (document.getElementById('f2_en').checked) {{
                const op = document.getElementById('f2_op').value;
                const val = parseFloat(document.getElementById('f2_val').value) || 0;
                if (!compare(s.rvol, op, val)) return false;
            }}

            if (document.getElementById('f3_en').checked) {{
                const op = document.getElementById('f3_op').value;
                const val = parseFloat(document.getElementById('f3_val').value) || 0;
                if (!compare(s.pct, op, val)) return false;
            }}

            if (document.getElementById('f4_en').checked) {{
                const op = document.getElementById('f4_op').value;
                const val = parseFloat(document.getElementById('f4_val').value) || 0;
                if (!compare(s.pct, op, val)) return false;
            }}

            if (document.getElementById('f5_en').checked) {{
                const op = document.getElementById('f5_op').value;
                const val = parseFloat(document.getElementById('f5_val').value) || 0;
                if (!compare(s.close, op, val)) return false;
            }}

            if (document.getElementById('f6_en').checked) {{
                const op = document.getElementById('f6_op').value;
                const val = parseFloat(document.getElementById('f6_val').value) || 0;
                if (!compare(s.close, op, val)) return false;
            }}

            if (document.getElementById('f7_en').checked) {{
                const op = document.getElementById('f7_op').value;
                const val = parseFloat(document.getElementById('f7_val').value) || 0;
                if (!compare(s.turnover, op, val)) return false;
            }}

            if (document.getElementById('f8_en').checked) {{
                const op = document.getElementById('f8_op').value;
                if ((op === '>=' || op === '&gt;=') && s.close < s.max_365) return false;
                if ((op === '<' || op === '&lt;') && s.close >= s.max_365) return false;
            }}

            if (document.getElementById('f9_en').checked) {{
                const op = document.getElementById('f9_op').value;
                const val = parseFloat(document.getElementById('f9_val').value) || 0;
                if (!compare(s.wick, op, val)) return false;
            }}

            return true;
        }}

        function applyFilters() {{
            const selDate = document.getElementById('singleDate').value;
            const searchSym = document.getElementById('searchSym').value.toUpperCase().trim();

            const tbody = document.getElementById('table-body');
            tbody.innerHTML = '';

            const dayData = records[selDate] || [];
            let matches = 0;

            dayData.forEach(s => {{
                if (evalStock(s)) {{
                    if (searchSym === '' || s.sym.includes(searchSym)) {{
                        matches++;
                        const color = s.pct > 0 ? '#00e676' : (s.pct < 0 ? '#ff5252' : '#888');
                        const sign = s.pct > 0 ? '+' : '';

                        const row = `<tr>
                            <td><b>${{s.sym}}</b></td>
                            <td>₹${{s.close}}</td>
                            <td style="color:${{color}}; font-weight:bold;">${{sign}}${{s.pct}}%</td>
                            <td>${{s.rvol}}x</td>
                            <td>₹${{s.turnover}} Cr</td>
                            <td>${{s.wick}}%</td>
                        </tr>`;
                        tbody.innerHTML += row;
                    }}
                }}
            }});

            document.getElementById('match-count').innerText = matches;
            if (matches === 0) {{
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:#888;">No stocks match your active filters on selected date.</td></tr>';
            }}
        }}

        function downloadBacktestCSV() {{
            const fromStr = document.getElementById('fromDate').value;
            const toStr = document.getElementById('toDate').value;

            if (!fromStr || !toStr) {{
                alert('Please select both From Date and To Date');
                return;
            }}

            let csvRows = ['Date,Symbol,Close,PctChange,RVOL,Turnover_Cr,UpperWickPct,EMA20'];

            dates.forEach(d => {{
                if (d >= fromStr && d <= toStr) {{
                    const dayData = records[d] || [];
                    dayData.forEach(s => {{
                        if (evalStock(s)) {{
                            csvRows.push(`${{d}},${{s.sym}},${{s.close}},${{s.pct}},${{s.rvol}},${{s.turnover}},${{s.wick}},${{s.ema20}}`);
                        }}
                    }});
                }}
            }});

            if (csvRows.length <= 1) {{
                alert('No stocks matched your active filters in the chosen date range.');
                return;
            }}

            const csvContent = "data:text/csv;charset=utf-8," + csvRows.join("\\n");
            const encodedUri = encodeURI(csvContent);
            const link = document.createElement("a");
            link.setAttribute("href", encodedUri);
            link.setAttribute("download", `backtest_${{fromStr}}_to_${{toStr}}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}
