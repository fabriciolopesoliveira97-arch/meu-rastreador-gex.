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
    # Filtro de liquidez (Spot +- 10%)
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
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # --- CÁLCULO ZERO GAMMA (PONTO DE INFLEXÃO) ---
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]

    # --- 3. DASHBOARD PRINCIPAL (ALERTAS E STATUS) ---
    cor_status = "#00ffcc" if net_gex > 0 else "#ff4b4b"
    label_status = "SUPRESSÃO" if net_gex > 0 else "EXPANSÃO"
    
    st.write(f"### {datetime.now().strftime('%b %d, %Y')}")
    st.markdown(f"<h1 style='color: {cor_status}; font-size: 55px; margin-bottom: 0px;'>{label_status}</h1>", unsafe_allow_html=True)

    # Alertas conforme as imagens enviadas
    if spot < put_wall:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${put_wall})")
    if net_gex < 0:
        st.warning("🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)")

    # Métricas incluindo Zero Gamma
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço SPOT", f"${spot:.2f}")
    c2.metric("Net GEX", f"{net_gex:.2f}M")
    c3.metric("Zero Gamma", f"${zero_gamma}")
    c4.metric("Put Wall", f"${put_wall}")
    c5.metric("Call Wall", f"${call_wall}")

    # --- 4. SISTEMA DE ABAS ---
    tab_price, tab_gex, tab_vanna = st.tabs(["📈 Gráfico de Preço", "📊 Gamma Profile", "🌊 Vanna Exposure"])

    with tab_price:
        fig_price = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="QQQ")])
        fig_price.add_hline(y=call_wall, line_color="#00ffcc", annotation_text="Call Wall")
        fig_price.add_hline(y=put_wall, line_color="#ff4b4b", annotation_text="Put Wall")
        fig_price.add_hline(y=zero_gamma, line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
        fig_price.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_price, use_container_width=True)

    with tab_gex:
        st.subheader("Peso e Força por Strike")
        # Cálculo do peso percentual de cada strike
        total_abs_gex = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
        
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(
            x=calls['strike'], y=calls['GEX'], name='Calls', marker_color='#00ffcc',
            customdata=(calls['GEX'].abs() / total_abs_gex * 100).round(2),
            hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"
        ))
        
        fig_hist.add_trace(go.Bar(
            x=puts['strike'], y=puts['GEX'], name='Puts', marker_color='#ff4b4b',
            customdata=(puts['GEX'].abs() / total_abs_gex * 100).round(2),
            hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"
        ))
        
        fig_hist.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text="SPOT")
        fig_hist.update_layout(template="plotly_dark", barmode='relative', height=500)
        st.plotly_chart(fig_hist, use_container_width=True)

    with tab_vanna:
        st.subheader("Vanna Exposure (VEX)")
        fig_vex = go.Figure()
        fig_vex.add_trace(go.Scatter(x=df_total['strike'], y=df_total['VEX_c'] + df_total['VEX_p'], name='Net Vanna', line=dict(color='orange')))
        fig_vex.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_vex, use_container_width=True)

    # --- 5. DICIONÁRIO ---
    st.divider()
    st.markdown(f"### 🧠 Cenário Atual: <span style='color:{cor_status}'>{label_status}</span>", unsafe_allow_html=True)
    st.write(f"O **Zero Gamma (${zero_gamma})** é o ponto onde o viés muda. Acima dele, Market Makers seguram o mercado.")

else:
    st.error("Erro ao carregar dados.")
