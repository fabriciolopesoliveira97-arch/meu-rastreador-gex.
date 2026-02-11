import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DE TELA ---
st.set_page_config(page_title="GEX & VANNA PRO 2026", layout="wide")

# CSS para métricas dinâmicas e alertas (IDÊNTICO ÀS IMAGENS)
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 42px !important; font-weight: bold; }
    .status-box { padding: 15px; border-radius: 8px; margin-bottom: 15px; font-weight: bold; font-family: sans-serif; }
    </style>
""", unsafe_allow_html=True)

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
    
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex_strike'] = df_total['GEX_c'] + df_total['GEX_p']
    df_total['net_vex_strike'] = df_total['VEX_c'] + df_total['VEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex_strike']).abs().argsort()[:1]]['strike'].values[0]
    
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']

    # --- 3. LÓGICA DE CORES E STATUS ---
    cor_gex = "#00ffcc" if net_gex > 0 else "#ff4b4b"
    cor_vex = "#00ffcc" if net_vex > 0 else "#ff4b4b"
    cor_zero = "#00ffcc" if spot > zero_gamma else "#ff4b4b"
    label_status = "SUPRESSÃO" if net_gex > 0 else "EXPANSÃO"

    st.write(f"### {datetime.now().strftime('%b %d, %Y')}")
    st.markdown(f"<h1 style='color: white; font-size: 55px; margin-bottom: 20px;'>{label_status}</h1>", unsafe_allow_html=True)

    # RESTAURADO: ALERTAS COLORIDOS (IDÊNTICO ÀS IMAGENS)
    if spot < put_wall:
        st.markdown(f"<div class='status-box' style='background-color: #411b1b; color: #ff4b4b; border: 1px solid #ff4b4b;'>⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${put_wall})</div>", unsafe_allow_html=True)
    if net_gex < 0:
        st.markdown(f"<div class='status-box' style='background-color: #3d3d1b; color: #ffff00; border: 1px solid #ffff00;'>🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)</div>", unsafe_allow_html=True)

    # RESTAURADO: MÉTRICAS COM CORES DINÂMICAS
    st.markdown(f"""
        <style>
        div[data-testid="column"]:nth-child(1) [data-testid="stMetricValue"] {{ color: {cor_gex} !important; }}
        div[data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] {{ color: {cor_vex} !important; }}
        div[data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] {{ color: {cor_zero} !important; }}
        </style>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net GEX", f"{net_gex:.2f}M")
    c2.metric("Net Vanna", f"{net_vex:.2f}M")
    c3.metric("Zero Gamma", f"${zero_gamma}")
    c4.metric("Put Wall", f"${put_wall}")
    c5.metric("Spot Price", f"${spot:.2f}")

    # --- 4. ABAS DE GRÁFICOS ---
    tab_price, tab_gex, tab_vanna = st.tabs(["📈 Gráfico de Preço", "📊 Gamma Profile", "🌊 Vanna Exposure"])

    with tab_price:
        fig_p = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Preço")])
        fig_p.add_hline(y=call_wall, line_color="#00ffcc", annotation_text="Call Wall")
        fig_p.add_hline(y=put_wall, line_color="#ff4b4b", annotation_text="Put Wall")
        fig_p.add_hline(y=zero_gamma, line_dash="dash", line_color=cor_zero, annotation_text=f"Zero Gamma: ${zero_gamma}")
        fig_p.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_p, use_container_width=True)

    with tab_gex:
        total_gex_abs = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
        fig_g = go.Figure()
        fig_g.add_trace(go.Bar(x=calls['strike'], y=calls['GEX'], name='Calls', marker_color='#00ffcc',
                               customdata=(calls['GEX'].abs()/total_gex_abs*100).round(2),
                               hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"))
        fig_g.add_trace(go.Bar(x=puts['strike'], y=puts['GEX'], name='Puts', marker_color='#ff4b4b',
                               customdata=(puts['GEX'].abs()/total_gex_abs*100).round(2),
                               hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"))
        fig_g.update_layout(template="plotly_dark", barmode='relative', height=500, hovermode="x unified")
        st.plotly_chart(fig_g, use_container_width=True)

    with tab_vanna:
        # VANNA COM LINHA VERDE/VERMELHA (DINÂMICO)
        fig_v = go.Figure()
        # Linha base
        fig_v.add_trace(go.Scatter(x=df_total['strike'], y=df_total['net_vex_strike'],
                                   mode='lines+markers', name='Net Vanna',
                                   line=dict(color='white', width=1), showlegend=False))
        
        # Segmentos coloridos
        y_vals = df_total['net_vex_strike'].values
        x_vals = df_total['strike'].values
        
        # Verde para Positivo
        fig_v.add_trace(go.Scatter(x=x_vals, y=[y if y > 0 else None for y in y_vals],
                                   mode='lines+markers', name='Vanna Positivo',
                                   line=dict(color='#00ffcc', width=4), connectgaps=False))
        # Vermelho para Negativo
        fig_v.add_trace(go.Scatter(x=x_vals, y=[y if y < 0 else None for y in y_vals],
                                   mode='lines+markers', name='Vanna Negativo',
                                   line=dict(color='#ff4b4b', width=4), connectgaps=False))
        
        fig_v.add_hline(y=0, line_color="gray", line_dash="dash")
        fig_v.add_vline(x=spot, line_color="yellow", line_dash="dot", annotation_text="SPOT")
        fig_v.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_v, use_container_width=True)

else:
    st.error("Erro ao processar dados.")
