import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX PRO - Matemática Pura", layout="wide")

# --- FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES) ---
def calculate_gamma(S, K, T, r, sigma):
    """Calcula a grega Gamma matemática pura"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

# --- FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        
        # Preço atual do ativo (Spot)
        hist = tk.history(period="1d")
        if hist.empty: return pd.DataFrame(), pd.DataFrame(), 0
        S = hist['Close'].iloc[-1]
        
        # Pega o vencimento mais próximo (0DTE ou Semanal)
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        # Cálculo do tempo para expiração (T em anos)
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        d_now = datetime.now()
        days_to_expiry = (d_exp - d_now).days + 1
        T = max(days_to_expiry, 1) / 365.0
        
        r = 0.045  # Taxa de juros livre de risco (aprox. 4.5% EUA)

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()

        # 1. CÁLCULO DA GAMMA PURA (Grega)
        calls['Gamma_Puro'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        puts['Gamma_Puro'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)

        # 2. CÁLCULO DO GEX (Exposição Financeira Real)
        # Fórmula: Gamma * Open Interest * 100 * S^2 * 0.01 (impacto por 1% de movimento)
        calls['GEX'] = calls['Gamma_Puro'] * calls['openInterest'] * 100 * S**2 * 0.01
        puts['GEX'] = puts['Gamma_Puro'] * puts['openInterest'] * 100 * S**2 * 0.01 * -1
        
        return calls, puts, S
    except Exception as e:
        st.error(f"Erro no cálculo matemático: {e}")
        return pd.DataFrame(), pd.DataFrame(), 0

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
    
    # Encontrar as "Paredes" baseadas no Gamma Absoluto
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # Encontrar o Zero Gamma (ponto de inversão do Net GEX)
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- INTERFACE STREAMLIT ---
st.title("🚀 Nasdaq 100 - High Precision GEX Tracker")
st.subheader("Cálculo baseado na Grega Gamma (Black-Scholes)")

ticker = "QQQ"
calls, puts, price = get_gamma_data_v2(ticker)

if not calls.empty:
    levels = get_gamma_levels(calls, puts)
    
    # --- MÉTRICAS ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Preço Atual", f"${price:.2f}")
    m2.metric("Zero Gamma", f"${levels['zero']}")
    m3.metric("Put Wall (Suporte)", f"${levels['put']}", delta_color="normal")
    m4.metric("Call Wall (Resistência)", f"${levels['call']}", delta_color="inverse")

    # --- STATUS DO MERCADO ---
    if price > levels['zero']:
        st.success(f"🛡️ REGIME DE SUPRESSÃO (Gama Positivo): Volatilidade controlada. Suporte em ${levels['put']}")
    else:
        st.error(f"⚠️ REGIME DE EXPANSÃO (Gama Negativo): Risco de movimentos violentos! Próximo suporte em ${levels['put']}")

    # --- GRÁFICO ---
    fig = go.Figure()
    fig.add_trace(go.Bar(x=calls['strike'], y=calls['GEX'], name='Call Gamma', marker_color='green'))
    fig.add_trace(go.Bar(x=puts['strike'], y=puts['GEX'], name='Put Gamma', marker_color='red'))
    
    fig.add_vline(x=price, line_width=3, line_dash="dash", line_color="white", annotation_text="PREÇO ATUAL")
    fig.add_vline(x=levels['zero'], line_width=2, line_dash="dot", line_color="yellow", annotation_text="ZERO GEX")

    fig.update_layout(
        title="Perfil de Exposição de Gamma (GEX) por Strike",
        xaxis_title="Strike Price",
        yaxis_title="Exposição Financeira (GEX)",
        template="plotly_dark",
        xaxis=dict(range=[price*0.9, price*1.1]) # Foca no preço atual
    )
    st.plotly_chart(fig, use_container_width=True)

    st.info("💡 **Nota Técnica:** Este gráfico utiliza a Volatilidade Implícita real de cada strike para calcular o Gamma através do modelo Black-Scholes.")
