import streamlit as st
import pandas as pd
import requests
import time
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIG ---
NV_KEY = st.secrets["NVIDIA_API_KEY"]
PAIRS = ["EURUSDT", "GBPUSDT", "USDJPY", "AUDUSDT", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "GBPCAD", "AUDJPY"]

def get_data(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=25"
        res = requests.get(url, timeout=3).json()
        df = pd.DataFrame(res, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'q', 'n', 'tb', 'tq', 'i'])
        df[['o', 'h', 'l', 'c', 'v']] = df[['o', 'h', 'l', 'c', 'v']].astype(float)
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        return df
    except: return None

def check_stability(df):
    if df is None or len(df) < 5: return False, 30
    volat = df['c'].pct_change().std()
    # Fix for the NaN problem
    if np.isnan(volat): return True, 0 
    
    is_stable = volat < 0.0012
    # Estimate return time based on market 'noise'
    return_sec = int(volat * 50000) if not is_stable else 0
    return is_stable, return_sec

def predict_future(df, symbol):
    # Prompting Llama 3.1 70B for a 60-second lead prediction
    prompt = f"ACT AS ELITE ANALYST. Analyze {symbol} 1m chart. Find MSS/OrderBlocks. Predict the price 1 minute from now. Output ONLY if 90%+ sure. Format: SIGNAL: [CALL/PUT], TARGET: [Price], LEAD_TIME: 60s, REASON: [1 sentence]."
    headers = {"Authorization": f"Bearer {NV_KEY}", "Content-Type": "application/json"}
    payload = {"model": "meta/llama-3.1-70b-instruct", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    try:
        r = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=7)
        return r.json()['choices'][0]['message']['content']
    except: return "REJECT"

# --- UI SETUP ---
st.set_page_config(layout="wide", page_title="Omni-Elite V3.1")
if 'signals' not in st.session_state: st.session_state.signals = []

st.title("🏛️ Omni-Elite V3.1: Predictive Intelligence")

# --- AUTO-SCAN FRAGMENT ---
@st.fragment(run_every="2s")
def scanner_engine():
    # Left Side: Monitoring & Prediction
    col_chart, col_signals = st.columns([2, 1])
    
    with col_chart:
        # We rotate the "Active" pair every 2 seconds to find the best setup
        current_pair = PAIRS[int(time.time() / 2) % len(PAIRS)]
        df = get_data(current_pair)
        
        stable, sec_to_wait = check_stability(df)
        
        if not stable:
            st.warning(f"⚠️ {current_pair} UNSTABLE. Shifting to next pair... (Recheck in {sec_to_wait}s)")
            # Auto-skip to the next pair in the list
            current_pair = PAIRS[(int(time.time() / 2) + 1) % len(PAIRS)]
            df = get_data(current_pair)

        st.subheader(f"📊 Live Analysis: {current_pair}")
        if df is not None:
            fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['o'], high=df['h'], low=df['l'], close=df['c'])])
            fig.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

            # Check for 1-minute lead signal
            analysis = predict_future(df, current_pair)
            if "SIGNAL" in analysis:
                sig_data = {
                    "pair": current_pair,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "details": analysis
                }
                # Prevent duplicate signals
                if not any(s['pair'] == current_pair for s in st.session_state.signals[:1]):
                    st.session_state.signals.insert(0, sig_data)

    with col_signals:
        st.subheader("💎 Elite Predictions")
        for s in st.session_state.signals[:6]:
            with st.expander(f"🔥 {s['pair']} | {s['time']}", expanded=True):
                st.code(s['details'])

scanner_engine()
       
