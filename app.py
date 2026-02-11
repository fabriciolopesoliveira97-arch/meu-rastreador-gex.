import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX & VANNA PRO 2026", layout="wide")

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
    # Filtro de strikes para precisão (Spot +- 8%)
    calls = options.calls[(options.calls['strike'] > S * 0.92) & (options.calls['strike'] < S * 1.08)].copy()
    puts = options.puts[(options.puts['strike'] > S * 0.92) & (options.puts['strike'] < S * 1.08)].copy()
    for df, multip in [(calls, 1), (puts, -1)]:
        res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        df['GEX'] = [r[0] for r in res] * df['openInterest'] * 100 * S**2 * 0.01 * multip
        df['VEX'] = [r[1] for r in res] * df['openInterest'] * 100 * multip
    return calls, puts, S, df_hist

# --- EXECUÇÃO ---
ticker = "QQQ"
calls, puts, spot, hist = get_market_data(ticker)

if not calls.empty:
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # --- STATUS VISUAL ---
    cor_status = "#00ffcc" if net_gex > 0 else "#ff4b4b"
    label_status = "SUPRESSÃO" if net_gex > 0 else "EXPANSÃO"
    
    st.markdown(f"### {datetime.now().strftime('%b %d, %Y')}")
    st.markdown(f"<h1 style='color: {cor_status}; font-size: 60px;'>{label_status}</h1>", unsafe_allow_html=True)

    # --- ALERTAS (CONFORME IMAGEM) ---
    if spot < put_wall:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${put_wall})")
    
    # --- MÉTRICAS ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço SPOT", f"${spot:.2f}")
    c2.metric("Net GEX", f"{net_gex:.2f}M", delta="Bullish" if net_gex > 0 else "Bearish")
    c3.metric("Put Wall", f"${put_wall}")
    c4.metric("Call Wall", f"${call_wall}")

    # --- HISTOGRAMA DE GAMMA (CORRIGIDO) ---
    st.subheader("📊 Histograma de Gamma Exposure")
    total_abs = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
    fig_hist = go.Figure()
    
    fig_hist.add_trace(go.Bar(
        x=calls['strike'], y=calls['GEX'], name='Calls', marker_color='#00ffcc',
        customdata=(calls['GEX'].abs() / total_abs * 100).round(2),
        hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"
    ))
    fig_hist.add_trace(go.Bar(
        x=puts['strike'], y=puts['GEX'], name='Puts', marker_color='#ff4b4b',
        customdata=(puts['GEX'].abs() / total_abs * 100).round(2),
        hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"
    ))
    fig_hist.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text="SPOT")
    fig_hist.update_layout(template="plotly_dark", barmode='relative', height=500)
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- GRÁFICO VANNA ---
    st.subheader("🌊 Vanna Exposure (VEX)")
    fig_vex = go.Figure()
    fig_vex.add_trace(go.Scatter(x=calls['strike'], y=calls['VEX'], name='Vanna Calls', line=dict(color='#00ffcc')))
    fig_vex.add_trace(go.Scatter(x=puts['strike'], y=puts['VEX'], name='Vanna Puts', line=dict(color='#ff4b4b')))
    fig_vex.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig_vex, use_container_width=True)

    # --- DICIONÁRIO ---
    st.divider()
    st.markdown(f"### 🧠 Cenário Atual: <span style='color:{cor_status}'>{label_status}</span>", unsafe_allow_html=True)
    st.write("Em **Supressão**, o mercado tende a subir de escada. Em **Expansão**, o risco de queda rápida aumenta abaixo do Spot.")

else:
    st.error("Dados não encontrados.")
