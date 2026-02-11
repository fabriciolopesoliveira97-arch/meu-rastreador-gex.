import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX & VANNA PRO", layout="wide")

def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = norm.pdf(d1) * (d2 / sigma)
    return gamma, vanna

@st.cache_data(ttl=300)
def get_market_data(ticker):
    tk = yf.Ticker(ticker)
    df_hist = tk.history(period="1d", interval="2m")
    S = df_hist['Close'].iloc[-1]
    options = tk.option_chain(tk.options[0])
    T, r = 1/365.0, 0.045
    # Filtro de strikes para precisão
    calls = options.calls[(options.calls['strike'] > S * 0.90) & (options.calls['strike'] < S * 1.10)].copy()
    puts = options.puts[(options.puts['strike'] > S * 0.90) & (options.puts['strike'] < S * 1.10)].copy()
    
    for df, multip in [(calls, 1), (puts, -1)]:
        res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        df['GEX'] = [r[0] for r in res] * df['openInterest'] * 100 * S**2 * 0.01 * multip
        df['VEX'] = [r[1] for r in res] * df['openInterest'] * 100 * multip
    return calls, puts, S, df_hist

# --- 2. EXECUÇÃO ---
ticker = "QQQ"
calls, puts, spot, hist = get_market_data(ticker)

if not calls.empty:
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    net_vex = (calls['VEX'].sum() + puts['VEX'].sum()) / 10**6
    
    # Cálculo Zero Gamma
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex_strike'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex_strike']).abs().argsort()[:1]]['strike'].values[0]
    
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']

    # --- 3. CORES DINÂMICAS ---
    cor_gex = "#00ffcc" if net_gex > 0 else "#ff4b4b"
    cor_vex = "#00ffcc" if net_vex > 0 else "#ff4b4b"
    label_status = "SUPRESSÃO" if net_gex > 0 else "EXPANSÃO"

    st.markdown(f"<h1 style='color: {cor_gex}; text-align: center; font-size: 60px;'>{label_status}</h1>", unsafe_allow_html=True)

    # Alertas Visuais
    if spot < put_wall:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Put Wall em ${put_wall} foi rompida!")
    
    # Métricas com injeção de CSS para cores
    st.markdown(f"""
        <style>
        div[data-testid="stMetricValue"] {{ color: white; }}
        div[data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] {{ color: {cor_gex} !important; }}
        div[data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] {{ color: {cor_vex} !important; }}
        </style>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("SPOT", f"${spot:.2f}")
    c2.metric("NET GEX", f"{net_gex:.2f}M")
    c3.metric("NET VANNA", f"{net_vex:.2f}M")
    c4.metric("ZERO GAMMA", f"${zero_gamma}")
    c5.metric("PUT WALL", f"${put_wall}")

    # --- 4. ABAS DE GRÁFICOS ---
    tab_price, tab_gex, tab_vanna = st.tabs(["📉 Preço Real-Time", "📊 Gamma Profile (Comparativo)", "🌊 Vanna Profile"])

    with tab_price:
        fig_p = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Price")])
        fig_p.add_hline(y=zero_gamma, line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
        fig_p.add_hline(y=put_wall, line_color="#ff4b4b", annotation_text="Put Wall")
        fig_p.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_p, use_container_width=True)

    with tab_gex:
        st.subheader("Força Relativa por Strike (%)")
        # Cálculo de % para comparação no mouse
        total_abs_gex = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
        
        fig_g = go.Figure()
        for df, name, color in [(calls, 'Calls', '#00ffcc'), (puts, 'Puts', '#ff4b4b')]:
            fig_g.add_trace(go.Bar(
                x=df['strike'], y=df['GEX'], name=name, marker_color=color,
                customdata=(df['GEX'].abs() / total_abs_gex * 100).round(2),
                hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br><b>Peso no Mercado: %{customdata}%</b><extra></extra>"
            ))
        fig_g.add_vline(x=spot, line_color="white", line_dash="dot", annotation_text="SPOT")
        fig_g.update_layout(template="plotly_dark", barmode='relative', height=550)
        st.plotly_chart(fig_g, use_container_width=True)

    with tab_vanna:
        st.subheader("Vanna por Strike (Sensibilidade IV)")
        fig_v = go.Figure()
        fig_v.add_trace(go.Bar(x=calls['strike'], y=calls['VEX'], name='Vanna Calls', marker_color='#00ffcc'))
        fig_v.add_trace(go.Bar(x=puts['strike'], y=puts['VEX'], name='Vanna Puts', marker_color='#ff4b4b'))
        fig_v.update_layout(template="plotly_dark", barmode='relative', height=550)
        st.plotly_chart(fig_v, use_container_width=True)

else:
    st.error("Dados não disponíveis no momento.")
