import streamlit as st
import pandas as pd
import requests
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Omni-Elite V4.0")

# Verify NVIDIA API Key is set in Streamlit Secrets
if "NVIDIA_API_KEY" not in st.secrets:
    st.error("Please add NVIDIA_API_KEY to your Streamlit secrets.")
    st.stop()

NV_KEY = st.secrets["NVIDIA_API_KEY"]
PAIRS = ["EURUSDT", "GBPUSDT", "USDJPY", "AUDUSDT", "USDCAD", "USDCHF", "EURJPY", "GBPJPY"]

# Session state initialization
if 'signals' not in st.session_state: st.session_state.signals = []
if 'pair_index' not in st.session_state: st.session_state.pair_index = 0
if 'last_shift' not in st.session_state: st.session_state.last_shift = time.time()

# Refresh data every 5 seconds
st_autorefresh(interval=5000, key="datarefresh")

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=4)
def fetch_market_data(symbol):
    """Fetches live market data from Binance with error handling."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=50"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not isinstance(data, list) or len(data) < 10:
            return None
            
        df = pd.DataFrame(data, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'q', 'n', 'tb', 'tq', 'i'])
        for col in ['o', 'h', 'l', 'c']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        return df.dropna(subset=['c'])
    except Exception:
        return None

# --- 3. ANALYSIS & SIGNALS ---
def get_prediction(df, symbol):
    """Sends current market data to AI for prediction."""
    if df is None or len(df) < 5:
        return None
        
    try:
        last_price = df['c'].iloc[-1]
        prompt = f"Analyze {symbol} at {last_price}. Provide a trade signal: CALL or PUT if 90% confident. Include the entry time (HH:MM:SS)."
        headers = {"Authorization": f"Bearer {NV_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "meta/llama-3.1-70b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1
        }
        
        response = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception:
        return None

# --- 4. MAIN INTERFACE ---
current_pair = PAIRS[st.session_state.pair_index]
market_data = fetch_market_data(current_pair)

# Automatically switch pairs if data is missing or unstable
if market_data is None and (time.time() - st.session_state.last_shift >= 30):
    st.session_state.pair_index = (st.session_state.pair_index + 1) % len(PAIRS)
    st.session_state.last_shift = time.time()
    st.rerun()

st.title(f"🏛️ Live Terminal: {current_pair}")
tab1, tab2 = st.tabs(["📊 Live Chart", "💎 Trade Signals"])

with tab1:
    if market_data is not None:
        fig = go.Figure(data=[go.Candlestick(
            x=market_data['time'], open=market_data['o'], high=market_data['h'], 
            low=market_data['l'], close=market_data['c'],
            increasing_line_color='#00FFCC', decreasing_line_color='#FF3366'
        )])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"Searching for stable {current_pair} connection...")

with tab2:
    if market_data is not None:
        prediction = get_prediction(market_data, current_pair)
        if prediction and "SIGNAL" in prediction:
            signal_data = {"time": datetime.now().strftime("%H:%M:%S"), "content": prediction}
            if not st.session_state.signals or st.session_state.signals[0]['content'] != prediction:
                st.session_state.signals.insert(0, signal_data)
    
    if not st.session_state.signals:
        st.info("Analyzing market patterns...")
    else:
        for signal in st.session_state.signals[:5]:
            with st.expander(f"🔔 Trade Alert | {signal['time']}", expanded=True):
                st.write(signal['content'])
