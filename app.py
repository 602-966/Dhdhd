import streamlit as st
import pandas as pd
import requests
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. MOBILE OPTIMIZED SETUP ---
st.set_page_config(layout="wide", page_title="Omni-Elite V3.7 Pro")

# Secrets Check
if "NVIDIA_API_KEY" not in st.secrets:
    st.error("Missing NVIDIA_API_KEY in Streamlit Settings!")
    st.stop()

NV_KEY = st.secrets["NVIDIA_API_KEY"]
PAIRS = ["EURUSDT", "GBPUSDT", "USDJPY", "AUDUSDT", "USDCAD", "USDCHF", "EURJPY", "GBPJPY"]

# Memory for signals and pair rotation
if 'signals' not in st.session_state: st.session_state.signals = []
if 'pair_index' not in st.session_state: st.session_state.pair_index = 0
if 'last_shift' not in st.session_state: st.session_state.last_shift = time.time()

# AUTO-REFRESH: Keep the market moving every 5 seconds
st_autorefresh(interval=5000, key="datarefresh")

# --- 2. THE CACHED DATA ENGINE (Method 2: Caching) ---
@st.cache_data(ttl=4) # Keeps data for 4 seconds to save battery/data
def get_live_market_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=40"
        res = requests.get(url, timeout=5).json()
        if not isinstance(res, list) or len(res) < 5: return None
        
        df = pd.DataFrame(res, columns=['t','o','h','l','c','v','ct','q','n','tb','tq','i'])
        for col in ['o','h','l','c']: 
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        return df.dropna(subset=['c'])
    except:
        return None

# --- 3. LOGIC: STABILITY & SCANNING ---
target_pair = PAIRS[st.session_state.pair_index]

# METHOD 3: Graceful Loading Placeholder
with st.spinner(f"Connecting to {target_pair} Live Feed..."):
    data = get_live_market_data(target_pair)

# Check if market is moving or "flat" (prevents NaN errors)
if data is not None and len(data) > 2:
    volat = data['c'].pct_change().std()
    is_stable = (not np.isnan(volat)) and (volat < 0.0020)
else:
    is_stable = False

# Auto-Shift Logic: If data fails or market is messy, jump after 30s
elapsed = time.time() - st.session_state.last_shift
if (data is None or not is_stable) and elapsed >= 30:
    st.session_state.pair_index = (st.session_state.pair_index + 1) % len(PAIRS)
    st.session_state.last_shift = time.time()
    st.rerun()

# --- 4. THE INTERFACE ---
st.title(f"🏛️ Live Terminal: {target_pair}")

# Split screen for Mobile
tab1, tab2 = st.tabs(["📊 Live Chart", "💎 Elite Signals"])

with tab1:
    if data is not None:
        # Create a high-contrast chart for phone screens
        fig = go.Figure(data=[go.Candlestick(
            x=data['time'], open=data['o'], high=data['h'], low=data['l'], close=data['c'],
            increasing_line_color='#00FFCC', decreasing_line_color='#FF3366'
        )])
        fig.update_layout(
            height=500,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            margin=dict(l=0, r=0, t=0, b=0),
            yaxis=dict(side="right") # Price on the right like trading apps
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        if not is_stable:
            st.warning(f"Market Volatile. Scanning next pair in {int(30-elapsed)}s...")
    else:
        st.error("Connection Error. Checking Binance servers...")

with tab2:
    # Run AI Prediction only if we have good data
    if is_stable and data is not None:
        try:
            last_p = data['c'].iloc[-1]
            headers = {"Authorization": f"Bearer {NV_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "meta/llama-3.1-70b-instruct",
                "messages": [{"role": "user", "content": f"Pair {target_pair} at {last_p}. Predict next 60s. Use pattern analysis. If 90% sure say SIGNAL: CALL or PUT."}],
                "temperature": 0.1
            }
            r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=7)
            ans = r.json()['choices'][0]['message']['content']
            
            if "SIGNAL" in ans:
                sig_entry = {"time": datetime.now().strftime("%H:%M:%S"), "body": ans}
                if not st.session_state.signals or st.session_state.signals[0]['body'] != ans:
                    st.session_state.signals.insert(0, sig_entry)
        except:
            st.write("AI is analyzing...")

    if not st.session_state.signals:
        st.info("Waiting for institutional pattern confirmation...")
    
    for s in st.session_state.signals[:5]:
        with st.expander(f"🔔 Signal Alert | {s['time']}", expanded=True):
            st.write(s['body'])
        
