import streamlit as st
import pandas as pd
import requests
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. SETUP & MEMORY ---
st.set_page_config(layout="wide", page_title="Omni-Elite V3.3")
NV_KEY = st.secrets["NVIDIA_API_KEY"]
PAIRS = ["EURUSDT", "GBPUSDT", "USDJPY", "AUDUSDT", "USDCAD", "USDCHF", "EURJPY", "GBPJPY"]

# Initialize tracking memory
if 'signals' not in st.session_state: st.session_state.signals = []
if 'pair_index' not in st.session_state: st.session_state.pair_index = 0
if 'last_shift' not in st.session_state: st.session_state.last_shift = time.time()

# Refresh the page every 5 seconds to keep the chart moving
st_autorefresh(interval=5000, key="datarefresh")

# --- 2. DATA ENGINE ---
def get_clean_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=30"
        res = requests.get(url, timeout=4).json()
        df = pd.DataFrame(res, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'q', 'n', 'tb', 'tq', 'i'])
        for col in ['o', 'h', 'l', 'c']: df[col] = pd.to_numeric(df[col])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        return df
    except Exception as e:
        return None

def check_stability(df):
    if df is None or len(df) < 10: return False
    volat = df['c'].pct_change().std()
    if np.isnan(volat): return True
    return volat < 0.0015  # Strict threshold for a "Stable" market

def get_ai_prediction(df, symbol):
    last_price = df['c'].iloc[-1]
    prompt = f"Market: {symbol} at {last_price}. Analyze last 30 mins. Predict movement 60-120 seconds from now. If 90% sure, give SIGNAL: CALL or PUT. Also give HH:MM:SS for entry."
    headers = {"Authorization": f"Bearer {NV_KEY}", "Content-Type": "application/json"}
    payload = {"model": "meta/llama-3.1-70b-instruct", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
        return r.json()['choices'][0]['message']['content']
    except: return "REJECT"

# --- 3. AUTO-SHIFT LOGIC (30 Second Timer) ---
current_time = time.time()
elapsed_seconds = int(current_time - st.session_state.last_shift)
target_pair = PAIRS[st.session_state.pair_index]

data = get_clean_data(target_pair)
is_stable = check_stability(data)

# If 30 seconds have passed AND the market is messy, shift to the next pair
if elapsed_seconds >= 30 and not is_stable:
    st.session_state.pair_index = (st.session_state.pair_index + 1) % len(PAIRS)
    st.session_state.last_shift = time.time()
    st.rerun() # Immediately load the new pair to save time

# --- 4. MAIN INTERFACE ---
st.title("🏛️ Omni-Elite V3.3: Smart Auto-Scan")

col_left, col_right = st.columns([2, 1])

with col_left:
    # Display the countdown timer so you know when it might shift
    status_text = "✅ Stable Market - Holding" if is_stable else f"⚠️ Unstable - Scanning next in {max(0, 30 - elapsed_seconds)}s"
    st.subheader(f"📊 Live Market: {target_pair} ({status_text})")
    
    if data is not None:
        # Build the Mobile-Friendly Chart
        fig = go.Figure(data=[go.Candlestick(
            x=data['time'], open=data['o'], high=data['h'], low=data['l'], close=data['c'],
            increasing_line_color='#00ff00', decreasing_line_color='#ff0000'
        )])
        fig.update_layout(
            height=450, 
            template="plotly_dark", 
            xaxis_rangeslider_visible=False, 
            margin=dict(l=5, r=5, t=5, b=5)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # AI Check (Runs quietly in the background while chart is loaded)
        prediction = get_ai_prediction(data, target_pair)
        if "SIGNAL" in prediction:
            new_sig = {"pair": target_pair, "time": datetime.now().strftime("%H:%M:%S"), "body": prediction}
            if not st.session_state.signals or st.session_state.signals[0]['body'] != prediction:
                st.session_state.signals.insert(0, new_sig)
    else:
        st.warning("Loading Chart Data...")

with col_right:
    st.subheader("💎 Elite Signals (1m Lead)")
    for s in st.session_state.signals[:5]:
        with st.expander(f"🔥 {s['pair']} | {s['time']}", expanded=True):
            st.write(s['body'])
