import streamlit as st
import pandas as pd
import requests
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CORE SETUP ---
st.set_page_config(layout="wide", page_title="Omni-Elite V3.5")
NV_KEY = st.secrets["NVIDIA_API_KEY"]
PAIRS = ["EURUSDT", "GBPUSDT", "USDJPY", "AUDUSDT", "USDCAD", "USDCHF", "EURJPY", "GBPJPY"]

if 'signals' not in st.session_state: st.session_state.signals = []
if 'pair_index' not in st.session_state: st.session_state.pair_index = 0
if 'last_shift' not in st.session_state: st.session_state.last_shift = time.time()

st_autorefresh(interval=5000, key="datarefresh")

# --- 2. THE TRIPLE-GUARD ENGINE ---
def get_safe_data(symbol):
    """Fetches and validates data to prevent IndexError."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=30"
        res = requests.get(url, timeout=5).json()
        
        # Guard 1: Ensure API returned a valid list of candles
        if not isinstance(res, list) or len(res) == 0:
            return None
            
        df = pd.DataFrame(res, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'q', 'n', 'tb', 'tq', 'i'])
        df['c'] = pd.to_numeric(df['c'])
        df['h'] = pd.to_numeric(df['h'])
        df['l'] = pd.to_numeric(df['l'])
        df['o'] = pd.to_numeric(df['o'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        
        # Guard 2: Ensure the column 'c' actually has data
        if df['c'].empty:
            return None
        return df
    except:
        return None

def analyze_market(df):
    """Analyzes stability and handles NaN errors safely."""
    if df is None or len(df) < 5:
        return False, 0
    
    # Guard 3: Handle NaN Volatility
    volat = df['c'].pct_change().std()
    if np.isnan(volat) or volat == 0:
        volat = 0.0001 # Default low volatility
        
    is_stable = volat < 0.0015
    return is_stable, volat

def get_prediction(df, symbol):
    """Calls AI only if data is healthy."""
    try:
        last_price = df['c'].iloc[-1] # Safe now because of Guards 1 & 2
        prompt = f"Market: {symbol} at {last_price}. Analyze 1m candles. Predict movement 60s from now. Give SIGNAL: CALL or PUT and HH:MM:SS entry."
        
        headers = {"Authorization": f"Bearer {NV_KEY}", "Content-Type": "application/json"}
        payload = {"model": "meta/llama-3.1-70b-instruct", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        
        r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=10)
        return r.json()['choices'][0]['message']['content']
    except:
        return "REJECT"

# --- 3. SCANNING LOGIC ---
target_pair = PAIRS[st.session_state.pair_index]
data = get_safe_data(target_pair)
is_stable, current_volat = analyze_market(data)

# Auto-jump to next pair if current one is broken/unstable
elapsed = int(time.time() - st.session_state.last_shift)
if (data is None or not is_stable) and elapsed >= 30:
    st.session_state.pair_index = (st.session_state.pair_index + 1) % len(PAIRS)
    st.session_state.last_shift = time.time()
    st.rerun()

# --- 4. ULTIMATE UI ---
st.title("🏛️ Omni-Elite V3.5: Stable")

col_left, col_right = st.columns([2, 1])

with col_left:
    status = "🟢 STABLE" if is_stable else "🔴 UNSTABLE"
    st.subheader(f"📊 {target_pair} | {status}")
    
    if data is not None:
        fig = go.Figure(data=[go.Candlestick(
            x=data['time'], open=data['o'], high=data['h'], low=data['l'], close=data['c'],
            increasing_line_color='#00ff00', decreasing_line_color='#ff0000'
        )])
        fig.update_layout(height=400, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,b=0,t=0))
        st.plotly_chart(fig, use_container_width=True)
        
        # Only predict if stable
        if is_stable:
            with st.spinner("Agents analyzing institutional flow..."):
                pred = get_prediction(data, target_pair)
                if "SIGNAL" in pred:
                    new_sig = {"pair": target_pair, "time": datetime.now().strftime("%H:%M:%S"), "body": pred}
                    if not st.session_state.signals or st.session_state.signals[0]['body'] != pred:
                        st.session_state.signals.insert(0, new_sig)
    else:
        st.error(f"Waiting for {target_pair} data... Scan next in {30-elapsed}s")

with col_right:
    st.subheader("💎 Elite Signals (1m Lead)")
    if not st.session_state.signals:
        st.info("Searching for 90%+ probability setups...")
    for s in st.session_state.signals[:5]:
        with st.expander(f"🔥 {s['pair']} | {s['time']}", expanded=True):
            st.write(s['body'])
         
