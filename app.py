import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX & VANNA PRO", layout="wide")

# --- 2. MOTOR MATEMÁTICO (BLACK-SCHOLES) ---
def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T)) # Gamma
    vanna = norm.pdf(d1) * (d2 / sigma) # Vanna
    return gamma, vanna

@st.cache_data(ttl=300)
def get_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        S = df_hist['Close'].iloc[-1]
        
        expiry = tk.options[0]
        options = tk.option_chain(expiry)
        T = 1/365.0 # Foco em 0DTE
        r = 0.045

        # FILTRO DE RELEVÂNCIA (Corrige o erro dos $525)
        # Foca apenas nos strikes onde o dinheiro está se movendo hoje
        calls = options.calls[(options.calls['strike'] > S * 0.90) & (options.calls['strike'] < S * 1.10)].copy()
        puts = options.puts[(options.puts['strike'] > S * 0.90) & (options.puts['strike'] < S * 1.10)].copy()

        for df, multip in [(calls, 1), (puts, -1)]:
            res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
            df['Gamma'] = [r[0] for r in res]
            df['Vanna'] = [r[1] for r in res]
            df['GEX'] = df['Gamma'] * df['openInterest'] * 100 * S**2 * 0.01 * multip
            df['VEX'] = df['Vanna'] * df['openInterest'] * 100 * multip 

        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

# --- 3. PROCESSAMENTO DE DADOS ---
ticker = "QQQ"
calls, puts, spot, hist = get_data(ticker)

if not calls.empty:
    # Cálculos de Níveis
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    zero_gamma = df_total.iloc[(df_total['GEX_c'] + df_total['GEX_p']).abs().argsort()[:1]]['strike'].values[0]
    
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    net_vex = (calls['VEX'].sum() + puts['VEX'].sum()) / 10**6

    # --- 4. ALERTAS VISUAIS (CONFORME IMAGEM) ---
    st.write(f"### {datetime.now().strftime('%b %d, %Y')}")
    
    if spot < put_wall:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${put_wall})")
    
    if net_gex < 0:
        st.warning("🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)")
    else:
        st.success("🛡️ SUPRESSÃO: GAMA POSITIVO (Mercado Protegido)")

    # --- 5. MÉTRICAS PRINCIPAIS ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço SPOT", f"${spot:.2f}")
    c2.metric("Net GEX", f"{net_gex:.2f}M", delta="Positivo" if net_gex > 0 else "Negativo")
    c3.metric("Put Wall", f"${put_wall}")
    c4.metric("Call Wall", f"${call_wall}")

    # --- 6. GRÁFICOS ---
    # Histograma de GEX
    st.subheader("📊 Histograma de Gamma Exposure")
    fig_gex = go.Figure()
    fig_gex.add_trace(go.Bar(x=calls['strike'], y=calls['GEX'], name='Calls (Alta)', marker_color='#00ffcc'))
    fig_hist.add_trace(go.Bar(x=puts['strike'], y=puts['GEX'], name='Puts (Baixa)', marker_color='#ff4b4b'))
    fig_gex.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text=f"Spot: ${spot:.2f}")
    fig_gex.update_layout(template="plotly_dark", barmode='relative', height=400)
    st.plotly_chart(fig_gex, use_container_width=True)

    # Gráfico de Vanna (VEX)
    st.subheader("🌊 Vanna Exposure (Sensibilidade à Volatilidade)")
    fig_vex = go.Figure()
    fig_vex.add_trace(go.Scatter(x=df_total['strike'], y=df_total['VEX_c'] + df_total['VEX_p'], mode='lines+markers', name='Net Vanna', line=dict(color='orange')))
    fig_vex.add_hline(y=0, line_color="white", line_dash="dash")
    fig_vex.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig_vex, use_container_width=True)

    # --- 7. DICIONÁRIO ESTRATÉGICO ---
    st.divider()
    st.header("🧠 Dicionário Estratégico de Mercado")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**🟢 SUPRESSÃO:** Preço acima do Zero Gamma (${zero_gamma}). Volatilidade controlada.")
        st.markdown(f"**🧱 Put Wall (${put_wall}):** Suporte institucional mais forte do dia.")
    with col_b:
        st.markdown(f"**🔴 EXPANSÃO:** Gex negativo ou preço abaixo do Zero Gamma. Risco de quedas rápidas.")
        st.markdown(f"**🌊 Net Vanna ({net_vex:.2f}M):** Se positivo, quedas na volatilidade impulsionam o preço.")

else:
    st.error("Erro ao carregar dados do Yahoo Finance.")
