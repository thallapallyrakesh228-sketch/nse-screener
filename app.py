import os
import json
import gzip
import csv
import io
import time
import urllib.parse
import requests
import pandas as pd
import datetime
from datetime import timedelta
import concurrent.futures
import streamlit as st

st.set_page_config(page_title="NSE Master Screener & Backtester", layout="wide")

st.title("⚡ NSE Master Screener & 3-Year Backtest Engine")
st.caption("All NSE Equity Stocks (~2,000+) | Powered by Upstox Analytics Token")

# --- TOKEN INPUT ---
raw_token = st.sidebar.text_input(
    "Upstox Access / Analytics Token", 
    type="password", 
    value="eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0NDUzMzIiLCJqdGkiOiI2YTdjMzFmYmM2Yzk1NDZlZTAzMzdmYTMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaXNFeHRlbmRlZCI6dHJ1ZSwiaWF0IjoxNzg2NTI0MTU1LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE4MTgxMDgwMDB9.QDozpxTAGcZt6ldjEDj__J_sQmRUOul53IFJ3KQrxIw"
)

if st.sidebar.button("🔄 Clear Cache & Reload Data"):
    st.cache_data.clear()
    st.rerun()

if not raw_token:
    st.info("👈 Please paste your valid Upstox Access or Analytics Token in the sidebar to begin.")
    st.stop()

clean_token = raw_token.strip()
AUTH_HEADER = clean_token if clean_token.startswith("Bearer ") else f"Bearer {clean_token}"

# --- 1. TRIPLE-FALLBACK INSTRUMENT MASTER FETCH ---
@st.cache_data(ttl=86400)
def load_all_nse_instruments():
    # Fallback 1: Local disk path relative to app.py
    local_path = os.path.join(os.path.dirname(__file__), "instruments.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and len(data) > 0:
                    return data
        except Exception:
            pass

    # Fallback 2: Direct GitHub Raw URL
    raw_url = "https://raw.githubusercontent.com/thallapallyrakesh228-sketch/nse-screener/main/instruments.json"
    try:
        res = requests.get(raw_url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data and len(data) > 0:
                return data
    except Exception:
        pass

    # Fallback 3: Live Upstox Master CSV
    upstox_url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    instruments = {}
    try:
        res = requests.get(upstox_url, headers=headers, timeout=15)
        if res.status_code == 200:
            with gzip.open(io.BytesIO(res.content), mode='rt', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    seg = str(row.get('segment') or row.get('exchange') or '').upper()
                    itype = str(row.get('instrument_type') or '').upper()
                    key = row.get('instrument_key')
                    sym = row.get('tradingsymbol') or row.get('trading_symbol') or row.get('name')
                    if ('NSE_EQ' in seg or seg == 'NSE') and itype == 'EQ':
                        if key and sym and not sym.endswith('-BE') and not sym.endswith('-BZ'):
                            instruments[key] = sym
            if instruments:
                return instruments
    except Exception:
        pass

    return {}

# --- 2. SINGLE STOCK CANDLE FETCH ---
def fetch_single_stock_history(key_sym_tuple, auth_token):
    key, symbol = key_sym_tuple
    to_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.datetime.now(datetime.timezone.utc) - timedelta(days=3*365)).strftime("%Y-%m-%d")
    
    encoded_key = urllib.parse.quote(key, safe='')
    url = f"https://api.upstox.com/v2/historical-candle/{encoded_key}/day/{to_date}/{from_date}"
    headers = {
        "Accept": "application/json", 
        "Authorization": auth_token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            candles = res.json().get("data", {}).get("candles", [])
            if candles and len(candles) >= 20:
                return symbol, candles, 200
        return symbol, None, res.status_code
    except Exception:
        return symbol, None, 500

@st.cache_data(ttl=14400, show_spinner=False)
def load_all_market_data(auth_token):
    instruments = load_all_nse_instruments()
    items = list(instruments.items())
    
    if not items:
        return {}, {0: "Unable to load stock list from local file, GitHub raw URL, or Upstox master file."}

    date_records = {}
    error_summary = {}

    batch_size = 50
    total_items = len(items)
    
    progress_bar = st.progress(0, text=f"Fetching 3-Year Data for {total_items} NSE Stocks...")

    for b_idx in range(0, total_items, batch_size):
        batch = items[b_idx:b_idx + batch_size]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(fetch_single_stock_history, item, auth_token) for item in batch]
            
            for future in concurrent.futures.as_completed(futures):
                symbol, candles, status = future.result()
                
                if status != 200:
                    error_summary[status] = error_summary.get(status, 0) + 1
                    
                if not candles:
                    continue

                chrono_candles = list(reversed(candles))
                closes = [c[4] for c in chrono_candles]
                
                # EMA 20 Series
                ema20_series = []
                k = 2 / (20 + 1)
                curr_ema = None
                for idx, cl in enumerate(closes):
                    if idx < 19:
                        ema20_series.append(cl)
                    elif idx == 19:
                        curr_ema = sum(closes[:20]) / 20.0
                        ema20_series.append(curr_ema)
                    else:
                        curr_ema = (cl * k) + (curr_ema * (1 - k))
                        ema20_series.append(curr_ema)

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
                    
                    past_vols = [x[5] for x in chrono_candles[max(0, i-20):i]]
                    avg_vol20 = sum(past_vols) / len(past_vols) if past_vols else vol
                    rvol = round(vol / avg_vol20, 2) if avg_vol20 > 0 else 1.0
                    
                    past_365_highs = [x[2] for x in chrono_candles[max(0, i-365):i]]
                    max_365 = max(past_365_highs) if past_365_highs else hi
                    
                    crossed_above_ema20 = (prev_cl <= prev_ema20 and cl > curr_ema20)
                    crossed_below_ema20 = (prev_cl >= prev_ema20 and cl < curr_ema20)

                    rec = {
                        "sym": symbol,
                        "close": round(cl, 2),
                        "pct": pct_chg,
                        "turnover": turnover_cr,
                        "rvol": rvol,
                        "ema20": round(curr_ema20, 2),
                        "max_365": round(max_365, 2),
                        "crossed_above": crossed_above_ema20,
                        "crossed_below": crossed_below_ema20,
                        "wick": upper_wick
                    }
                    
                    if dt not in date_records:
                        date_records[dt] = []
                    date_records[dt].append(rec)
                    
        pct_done = min(1.0, (b_idx + batch_size) / total_items)
        progress_bar.progress(pct_done, text=f"Processed {min(b_idx + batch_size, total_items)} / {total_items} NSE Stocks...")
        time.sleep(0.05)

    progress_bar.empty()
    return date_records, error_summary

market_data, err_summary = load_all_market_data(AUTH_HEADER)
all_dates = sorted(list(market_data.keys()), reverse=True)

if not all_dates:
    st.error("⚠️ Failed to load stock data. Status Summary:")
    st.write(err_summary)
    st.info("Please click '🔄 Clear Cache & Reload Data' in the sidebar.")
    st.stop()

# --- SIDEBAR 9 MASTER FILTERS ---
st.sidebar.markdown("### 🎛️ 9 Master Filters")
ops = [">=", ">", "<=", "<", "=="]

f1_en = st.sidebar.checkbox("1. Close vs EMA 20", value=True)
f1_op = st.sidebar.selectbox("EMA 20 Operator", [">=", ">", "<=", "<", "==", "Crossed Above", "Crossed Below"], index=0)

f2_en = st.sidebar.checkbox("2. Relative Volume (RVOL)", value=True)
c1, c2 = st.sidebar.columns(2)
f2_op = c1.selectbox("RVOL Op", ops, index=0)
f2_val = c2.number_input("RVOL Min", value=1.5, step=0.1)

f3_en = st.sidebar.checkbox("3. Min % Change", value=True)
c1, c2 = st.sidebar.columns(2)
f3_op = c1.selectbox("Min % Op", ops, index=0)
f3_val = c2.number_input("Min % Val", value=2.0, step=0.5)

f4_en = st.sidebar.checkbox("4. Max % Change", value=True)
c1, c2 = st.sidebar.columns(2)
f4_op = c1.selectbox("Max % Op", ops, index=2)
f4_val = c2.number_input("Max % Val", value=10.0, step=0.5)

f5_en = st.sidebar.checkbox("5. Min Daily Close", value=True)
c1, c2 = st.sidebar.columns(2)
f5_op = c1.selectbox("Min Price Op", ops, index=0)
f5_val = c2.number_input("Min Price (₹)", value=100.0, step=10.0)

f6_en = st.sidebar.checkbox("6. Max Daily Close", value=True)
c1, c2 = st.sidebar.columns(2)
f6_op = c1.selectbox("Max Price Op", ops, index=2)
f6_val = c2.number_input("Max Price (₹)", value=2000.0, step=50.0)

f7_en = st.sidebar.checkbox("7. Min Turnover (Cr)", value=True)
c1, c2 = st.sidebar.columns(2)
f7_op = c1.selectbox("Turnover Op", ops, index=0)
f7_val = c2.number_input("Turnover (Cr)", value=50.0, step=5.0)

f8_en = st.sidebar.checkbox("8. Close vs 365D High", value=True)
c1, c2 = st.sidebar.columns(2)
f8_op = c1.selectbox("365D Op", ops, index=0)
f8_val = c2.number_input("365D High Mult", value=1.0, step=0.05)

f9_en = st.sidebar.checkbox("9. Min Upper Wick %", value=True)
c1, c2 = st.sidebar.columns(2)
f9_op = c1.selectbox("Wick Op", ops, index=0)
f9_val = c2.number_input("Upper Wick %", value=40.0, step=5.0)

def compare_vals(val1, op, val2):
    if op == ">": return val1 > val2
    if op == ">=": return val1 >= val2
    if op == "<": return val1 < val2
    if op == "<=": return val1 <= val2
    if op == "==": return val1 == val2
    return True

def eval_stock_record(s):
    if f1_en:
        if f1_op == "Crossed Above" and not s["crossed_above"]: return False
        elif f1_op == "Crossed Below" and not s["crossed_below"]: return False
        elif f1_op not in ["Crossed Above", "Crossed Below"]:
            if not compare_vals(s["close"], f1_op, s["ema20"]): return False

    if f2_en and not compare_vals(s["rvol"], f2_op, f2_val): return False
    if f3_en and not compare_vals(s["pct"], f3_op, f3_val): return False
    if f4_en and not compare_vals(s["pct"], f4_op, f4_val): return False
    if f5_en and not compare_vals(s["close"], f5_op, f5_val): return False
    if f6_en and not compare_vals(s["close"], f6_op, f6_val): return False
    if f7_en and not compare_vals(s["turnover"], f7_op, f7_val): return False
    if f8_en and not compare_vals(s["close"], f8_op, s["max_365"] * f8_val): return False
    if f9_en and not compare_vals(s["wick"], f9_op, f9_val): return False
    return True

# --- MAIN SCREEN VIEW ---
col_date, col_search = st.columns([1, 1])

sel_date = col_date.date_input("Inspector Date", value=datetime.datetime.strptime(all_dates[0], "%Y-%m-%d").date(),
                                min_value=datetime.datetime.strptime(all_dates[-1], "%Y-%m-%d").date(),
                                max_value=datetime.datetime.strptime(all_dates[0], "%Y-%m-%d").date())

search_sym = col_search.text_input("Search Stock Symbol", "").strip().upper()

day_data = market_data.get(sel_date.strftime("%Y-%m-%d"), [])
filtered_stocks = [s for s in day_data if eval_stock_record(s) and (search_sym == "" or search_sym in s["sym"])]

st.markdown(f"#### 📋 Screener Matches: `{len(filtered_stocks)}` stocks on `{sel_date}`")

if filtered_stocks:
    df_disp = pd.DataFrame(filtered_stocks)[["sym", "close", "pct", "rvol", "turnover", "wick", "ema20", "max_365"]]
    df_disp.columns = ["Symbol", "Close (₹)", "Change (%)", "RVOL", "Turnover (Cr)", "Wick (%)", "EMA 20", "365D High"]
    st.dataframe(df_disp, use_container_width=True)
else:
    st.info("No stocks matched your active filters on the selected date.")

st.divider()

# --- BACKTEST CSV DOWNLOADER ---
st.subheader("📊 Backtest CSV Downloader")
col_b1, col_b2 = st.columns(2)

default_from = datetime.datetime.strptime(all_dates[min(20, len(all_dates)-1)], "%Y-%m-%d").date()
default_to = datetime.datetime.strptime(all_dates[0], "%Y-%m-%d").date()

from_date = col_b1.date_input("From Date", value=default_from)
to_date = col_b2.date_input("To Date", value=default_to)

if st.button("📥 Generate Backtest CSV (Active Filters)", type="primary"):
    backtest_rows = []
    from_str = from_date.strftime("%Y-%m-%d")
    to_str = to_date.strftime("%Y-%m-%d")
    
    for d in all_dates:
        if from_str <= d <= to_str:
            for s in market_data.get(d, []):
                if eval_stock_record(s):
                    backtest_rows.append({
                        "Date": d,
                        "Symbol": s["sym"],
                        "Close": s["close"],
                        "PctChange": s["pct"],
                        "RVOL": s["rvol"],
                        "Turnover_Cr": s["turnover"],
                        "UpperWickPct": s["wick"],
                        "EMA20": s["ema20"]
                    })
                    
    if backtest_rows:
        df_bt = pd.DataFrame(backtest_rows)
        csv_bytes = df_bt.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download CSV File",
            data=csv_bytes,
            file_name=f"backtest_{from_str}_to_{to_str}.csv",
            mime="text/csv"
        )
        st.success(f"Backtest complete! Found {len(backtest_rows)} total matching trades across range.")
    else:
        st.warning("No stock matches found in selected date range with active filters.")
