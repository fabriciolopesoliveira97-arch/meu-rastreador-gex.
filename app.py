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
    # Vanna apurado (Derivada do Delta em relação à Vol)
    vanna = norm.pdf(d1) * (d2 / sigma)
    return gamma, vanna

@st.cache_data(ttl=300)
def get_market_data(ticker):
    tk = yf.Ticker(ticker)
    df_hist = tk.history(period="1d", interval="2m")
    S = df_hist['Close'].iloc[-1]
    options = tk.option_chain(tk.options[0])
    T, r = 1/365.0, 0.045
    # Filtro de liquidez institucional (Spot +- 12%)
    calls = options.calls[(options.calls['strike'] > S * 0.88) & (options.calls['strike'] < S * 1.12)].copy()
    puts = options.puts[(options.puts['strike'] > S * 0.88) & (options.puts['strike'] < S * 1.12)].copy()
    
    for df, multip in [(calls, 1), (puts, -1)]:
        res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        df['GEX'] = [r[0] for r in res] * df['openInterest'] * 100 * S**2 * 0.01 * multip
        df['VEX'] = [r[1] for r in res] * df['openInterest'] * 100 * multip
    return calls, puts, S, df_hist

# --- 2. PROCESSAMENTO ---
ticker = "QQQ"
calls, puts, spot, hist = get_market_data(ticker)

if not calls.empty:
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    net_vex = (calls['VEX'].sum() + puts['VEX'].sum()) / 10**6
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]

    # --- 3. DASHBOARD VISUAL ---
    cor_gex = "#00ffcc" if net_gex > 0 else "#ff4b4b"
    cor_vex = "#00ffcc" if net_vex > 0 else "#ff4b4b"
    label_status = "SUPRESSÃO" if net_gex > 0 else "EXPANSÃO"
    
    st.write(f"### {datetime.now().strftime('%b %d, %Y')}")
    st.markdown(f"<h1 style='color: {cor_gex}; font-size: 55px; margin-bottom: 0px;'>{label_status}</h1>", unsafe_allow_html=True)

    # Alertas
    if spot < put_wall:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${put_wall})")
    
    # Métricas com Cores Dinâmicas
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço SPOT", f"${spot:.2f}")
    
    # Valor Verde se positivo, Vermelho se negativo
    st.markdown(f"""
        <style>
        [data-testid="stMetricValue"] {{ color: white; }}
        div[data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] {{ color: {cor_gex}; }}
        div[data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] {{ color: {cor_vex}; }}
        </style>
        """, unsafe_allow_html=True)
    
    c2.metric("Net GEX", f"{net_gex:.2f}M")
    c3.metric("Net Vanna", f"{net_vex:.2f}M")
    c4.metric("Put Wall", f"${put_wall}")
    c5.metric("Call Wall", f"${call_wall}")

    # --- 4. ABAS ---
    tab_price, tab_gex, tab_vanna = st.tabs(["📈 Gráfico", "📊 Gamma Profile", "🌊 Vanna Exposure"])

    with tab_price:
        fig_price = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name=ticker)])
        fig_price.add_hline(y=call_wall, line_color="#00ffcc", annotation_text="Call Wall")
        fig_price.add_hline(y=put_wall, line_color="#ff4b4b", annotation_text="Put Wall")
        fig_price.add_hline(y=zero_gamma, line_dash="dash", line_color="yellow", annotation_text=f"Zero Gamma: {zero_gamma}")
        fig_price.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_price, use_container_width=True)

    with tab_gex:
        st.subheader("Peso e Percentual por Strike")
        # Porcentagem relativa de força (quem é maior)
        total_gex_abs = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
        
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(
            x=calls['strike'], y=calls['GEX'], name='Calls', marker_color='#00ffcc',
            customdata=(calls['GEX'].abs() / total_gex_abs * 100).round(2),
            hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br><b>Peso no Mercado: %{customdata}%</b><extra></extra>"
        ))
        fig_hist.add_trace(go.Bar(
            x=puts['strike'], y=puts['GEX'], name='Puts', marker_color='#ff4b4b',
            customdata=(puts['GEX'].abs() / total_gex_abs * 100).round(2),
            hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br><b>Peso no Mercado: %{customdata}%</b><extra></extra>"
        ))
        fig_hist.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text="SPOT")
        fig_hist.update_layout(template="plotly_dark", barmode='relative', height=500)
        st.plotly_chart(fig_hist, use_container_width=True)

    with tab_vanna:
        st.subheader("Vanna Exposure (Sensibilidade Vol)")
        # Gráfico Vanna igual ao modelo que você gostou
        fig_vex = go.Figure()
        fig_vex.add_trace(go.Bar(x=calls['strike'], y=calls['VEX'], name='Vanna Calls', marker_color='#00ffcc'))
        fig_vex.add_trace(go.Bar(x=puts['strike'], y=puts['VEX'], name='Vanna Puts', marker_color='#ff4b4b'))
        fig_vex.update_layout(template="plotly_dark", barmode='relative', height=500)
        st.plotly_chart(fig_vex, use_container_width=True)

else:
    st.error("Erro ao carregar dados.")
