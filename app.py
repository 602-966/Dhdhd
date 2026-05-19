import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- CONFIGURATION ---
NV_KEY = st.secrets["NVIDIA_API_KEY"]
PAIRS = ["EURUSDT", "GBPUSDT", "USDJPY", "AUDUSDT", "USDCAD", "USDCHF", "EURJPY", "GBPJPY"]

# --- CORE UTILITIES ---
def get_binance_data(symbol, limit=30):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}"
        res = requests.get(url, timeout=5).json()
        df = pd.DataFrame(res, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'q', 'n', 'tb', 'tq', 'i'])
        for col in ['o', 'h', 'l', 'c', 'v']: df[col] = df[col].astype(float)
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        return df
    except: return None

def analyze_stability(df):
    # Calculate volatility to predict stability return
    returns = df['c'].pct_change().dropna()
    volatility = returns.std()
    is_stable = volatility < 0.0015 # Threshold for "Elite" stability
    # Predict seconds to return based on volatility decay
    recovery_sec = int(volatility * 100000) if not is_stable else 0
    return is_stable, recovery_sec

def run_elite_ai(df, symbol):
    # Brain prompt for 1-minute lead time prediction
    prompt = f"""
    Analyze {symbol} 1m data. 
    MANDATE: Predict movement 1-2 minutes BEFORE it happens.
    OUTPUT ONLY if probability > 90%.
    FORMAT: 
    SIGNAL: [CALL/PUT]
    EXECUTION_TIME: [HH:MM:SS]
    TARGET: [Price]
    STRICT_REASON: [Short technical reason]
    """
    headers = {"Authorization": f"Bearer {NV_KEY}", "Content-Type": "application/json"}
    payload = {"model": "meta/llama-3.1-70b-instruct", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
        return r.json()['choices'][0]['message']['content']
    except: return "REJECT"

# --- UI STATE ---
if 'signals' not in st.session_state: st.session_state.signals = []
if 'pair_status' not in st.session_state: st.session_state.pair_status = {}

st.set_page_config(layout="wide", page_title="Omni-Elite V3.0")

# --- SIDEBAR SCANNER (Non-blocking) ---
with st.sidebar:
    st.title("📡 Active Scanner")
    selected_pair = st.selectbox("Focus Live Chart", PAIRS)
    st.divider()
    
    # Global Scan Display
    for p in PAIRS:
        df = get_binance_data(p, limit=10)
        if df is not None:
            stable, sec = analyze_stability(df)
            if stable:
                st.write(f"✅ {p}: Stable")
            else:
                st.write(f"❌ {p}: Unstable. Return in ~{sec}s")

# --- MAIN INTERFACE (Fragmented Refresh every 2s) ---
@st.fragment(run_every="2s")
def main_engine():
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📊 Live Chart: {selected_pair}")
        df_live = get_binance_data(selected_pair)
        if df_live is not None:
            fig = go.Figure(data=[go.Candlestick(x=df_live['time'],
                open=df_live['o'], high=df_live['h'],
                low=df_live['l'], close=df_live['c'])])
            fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
            
            # AI Check
            res = run_elite_ai(df_live, selected_pair)
            if "CALL" in res or "PUT" in res:
                timestamp = datetime.now().strftime("%H:%M:%S")
                st.session_state.signals.insert(0, {"pair": selected_pair, "time": timestamp, "details": res})

    with col2:
        st.subheader("💎 Elite Signals")
        for sig in st.session_state.signals[:5]:
            with st.expander(f"🔥 {sig['pair']} at {sig['time']}", expanded=True):
                st.write(sig['details'])

main_engine()
