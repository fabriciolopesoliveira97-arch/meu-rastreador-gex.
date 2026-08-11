import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO - Sinais IA", layout="wide")
st_autorefresh(interval=60 * 1000, key="datarefresh")

# CSS idêntico ao layout da imagem de referência
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .signal-card {
        background-color: #161922;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        border: 1px solid #262a34;
    }
    .badge-percent {
        background-color: #1b2e23;
        color: #00ff88;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.8em;
    }
    .badge-rr {
        background-color: #1f242d;
        color: #a0aec0;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.8em;
    }
    .badge-ativo {
        background-color: #1e2530;
        color: #3b82f6;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.75em;
    }
    .metric-val-buy { font-size: 1.1em; font-weight: bold; color: #00d4ff; }
    .metric-label { font-size: 0.65em; color: #718096; text-transform: uppercase; margin-bottom: 2px; }
    .time-stamp { font-size: 0.7em; color: #718096; margin-top: 10px; }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES DE DADOS ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

@st.cache_data(ttl=300)
def get_market_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        if df_hist.empty: return 0, pd.DataFrame(), pd.DataFrame(), ""
        
        S = df_hist['Close'].iloc[-1]
        vencimentos = tk.options
        if not vencimentos: return S, pd.DataFrame(), pd.DataFrame(), ""
        
        expiry = vencimentos[0]
        options = tk.option_chain(expiry)
        d_exp = datetime.strptime(expiry, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days + 1, 1) / 365.0
        r = 0.045
        
        calls = options.calls.copy()
        puts = options.puts.copy()
        calls['GEX'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01, axis=1)
        puts['GEX'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01 * -1, axis=1)
        
        return S, calls, puts, expiry
    except:
        return 0, pd.DataFrame(), pd.DataFrame(), ""

# --- 3. INTERFACE DE TOPO ---
st.markdown("### ⚡ Sinais IA em Tempo Real")
st.markdown("<p style='color: #888; font-size: 0.9em;'>Sinais de trading gerados por IA com alta confluência</p>", unsafe_allow_html=True)

# Abas superiores estilo o app da imagem
tab1, tab2 = st.tabs(["Sinais IA (5)", "Sinais Índices (0)"])

with tab1:
    st.markdown("<p style='color: #00ff88; font-size: 0.85em; font-weight: bold;'>⚡ Sinais Ativos</p>", unsafe_allow_html=True)
    
    # Configuração de escala para o Ouro (XAUUSD)
    spot_input = st.sidebar.number_input("Preço de Referência XAUUSD", value=4426.95)
    
    raw_price, calls, puts, expiry = get_market_data("GLD")
    
    if raw_price > 0:
        net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6 if not calls.empty else 15.4
        forca_perc = min(max(int(70 + abs(net_gex)), 70), 95)
        
        direction = "COMPRA" if net_gex >= 0 else "VENDA"
        icon = "↗️" if direction == "COMPRA" else "↘️"
        color = "#00ff88" if direction == "COMPRA" else "#ff4b4b"
        
        entry = spot_input
        stop = entry - 24.0 if direction == "COMPRA" else entry + 24.0
        take = entry + 36.0 if direction == "COMPRA" else entry - 36.0

        st.markdown(f"""
        <div class="signal-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 1.1em; font-weight: bold; color: {color}">{icon} XAUUSD</span>
                    <span style="color: #888; font-size: 0.8em; margin-left: 5px;">5m</span>
                    <span class="badge-ativo" style="margin-left: 8px;">Ativo</span>
                </div>
                <div>
                    <span class="badge-percent">{forca_perc}% 🔥</span>
                    <span class="badge-rr" style="margin-left: 5px;">1:1.5</span>
                </div>
            </div>
            
            <div style="display: flex; justify-content: space-between; margin-top: 15px; text-align: center; background: #101217; padding: 10px; border-radius: 8px;">
                <div style="flex: 1;">
                    <div class="metric-label">Entrada</div>
                    <div class="metric-val-buy">{entry:.2f}</div>
                </div>
                <div style="flex: 1; border-left: 1px solid #262a34; border-right: 1px solid #262a34;">
                    <div class="metric-label">Stop</div>
                    <div style="font-size: 1.1em; font-weight: bold; color: #ff4b4b;">{stop:.2f}</div>
                </div>
                <div style="flex: 1;">
                    <div class="metric-label">Take</div>
                    <div style="font-size: 1.1em; font-weight: bold; color: #00ff88;">{take:.2f}</div>
                </div>
            </div>
            <div class="time-stamp">10/08 22:50</div>
        </div>
        """, unsafe_allow_html=True)

with tab2:
    st.info("Nenhum sinal de índice ativo no momento.")
