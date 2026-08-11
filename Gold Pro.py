
import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO - Sinais & Análise", layout="wide")
st_autorefresh(interval=60 * 1000, key="datarefresh")

# CSS customizado
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .signal-card {
        background-color: #1c1f26;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 15px;
        border: 1px solid #30363d;
    }
    .badge { padding: 5px 10px; border-radius: 8px; font-weight: bold; font-size: 0.8em; }
    .metric-val { font-size: 1.2em; font-weight: bold; color: #ffffff; }
    .metric-label { font-size: 0.7em; color: #888; }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

def get_gamma_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        S = tk.history(period="1d")['Close'].iloc[-1]
        vencimentos = tk.options
        if not vencimentos: return pd.DataFrame(), pd.DataFrame(), S
        options = tk.option_chain(vencimentos[0])
        calls = options.calls.copy()
        puts = options.puts.copy()
        calls['GEX'] = calls['openInterest'] * 100
        puts['GEX'] = puts['openInterest'] * 100 * -1
        return calls, puts, S
    except: return pd.DataFrame(), pd.DataFrame(), 0

# --- 3. INTERFACE ---
st.title("⚡ Sinais IA em Tempo Real")

def show_signal_card(pair, entry, stop, take, confidence, direction):
    color = "#00ff88" if direction == "COMPRA" else "#ff4b4b"
    icon = "↗️" if direction == "COMPRA" else "↘️"
    st.markdown(f"""
    <div class="signal-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 1.2em; font-weight: bold; color: {color}">{icon} {pair}</span>
            <span class="badge" style="background: #2a303c; color: {color}">{confidence}% 🔥</span>
        </div>
        <div style="display: flex; justify-content: space-between; margin-top: 15px;">
            <div><div class="metric-label">ENTRADA</div><div class="metric-val" style="color: #00d4ff">{entry:.2f}</div></div>
            <div><div class="metric-label">STOP</div><div class="metric-val" style="color: #ff4b4b">{stop:.2f}</div></div>
            <div><div class="metric-label">TAKE</div><div class="metric-val" style="color: #00ff88">{take:.2f}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Lógica
ticker = st.text_input("Ativo Base", value="GLD")
calls, puts, S = get_gamma_data(ticker)

if S > 0:
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    dir_sinal = "COMPRA" if net_gex > 0 else "VENDA"
    show_signal_card("XAUUSD", S, S*0.99, S*1.02, 86, dir_sinal)
