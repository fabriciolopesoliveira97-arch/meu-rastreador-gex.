import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DE TELA ---
st.set_page_config(page_title="GEX & VANNA PRO", layout="wide")

# CSS para forçar o visual das imagens (Cards, Cores e Fontes)
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 45px !important; font-weight: bold; }
    .status-box { padding: 20px; border-radius: 10px; margin-bottom: 20px; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; font-size: 16px; }
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
    calls = options.calls[(options.calls['strike'] > S * 0.92) & (options.calls['strike'] < S * 1.08)].copy()
    puts = options.puts[(options.puts['strike'] > S * 0.92) & (options.puts['strike'] < S * 1.08)].copy()
    
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
    # Cálculo Zero Gamma
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex_strike'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex_strike']).abs().argsort()[:1]]['strike'].values[0]
    
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']

    # --- 3. CABEÇALHO E ALERTAS (IDÊNTICO ÀS IMAGENS) ---
    st.write(f"### {datetime.now().strftime('%b %d, %Y')}")
    
    cor_status = "#00ffcc" if net_gex > 0 else "#ff4b4b"
    txt_status = "SUPRESSÃO" if net_gex > 0 else "EXPANSÃO"
    st.markdown(f"<h1 style='color: white; font-size: 60px;'>{txt_status}</h1>", unsafe_allow_html=True)

    if spot < put_wall:
        st.markdown(f"<div class='status-box' style='background-color: #411b1b; color: #ff4b4b; border: 1px solid #ff4b4b;'>⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${put_wall})</div>", unsafe_allow_html=True)
    if net_gex < 0:
        st.markdown(f"<div class='status-box' style='background-color: #3d3d1b; color: #ffff00; border: 1px solid #ffff00;'>🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)</div>", unsafe_allow_html=True)

    # Métricas Verticais
    st.metric("Net GEX", f"{net_gex:.2f}M", delta="Positivo" if net_gex > 0 else "Negativo")
    st.metric("Zero Gamma", f"${zero_gamma}")
    st.metric("Put Wall", f"${put_wall}")
    st.metric("Call Wall", f"${call_wall}")

    st.markdown(f"## Cenário Atual: <span style='color: {cor_status}'>{txt_status}</span>", unsafe_allow_html=True)

    # --- 4. SISTEMA DE ABAS ---
    tab_price, tab_gex, tab_vanna = st.tabs(["📈 Gráfico de Preço", "📊 Gamma Profile", "🌊 Vanna Exposure"])

    with tab_price:
        fig_p = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Price")])
        fig_p.add_hline(y=call_wall, line_color="green", annotation_text="Call Wall")
        fig_p.add_hline(y=put_wall, line_color="red", annotation_text="Put Wall")
        fig_p.add_hline(y=zero_gamma, line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
        fig_p.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_p, use_container_width=True)

    with tab_gex:
        st.subheader("📊 Histograma de Gamma Exposure")
        total_abs_gex = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
        
        fig_g = go.Figure()
        fig_g.add_trace(go.Bar(
            x=calls['strike'], y=calls['GEX'], name='Calls (Alta)', marker_color='#00ffcc',
            customdata=(calls['GEX'].abs() / total_abs_gex * 100).round(2),
            hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br><b>Peso: %{customdata}%</b><extra></extra>"
        ))
        fig_g.add_trace(go.Bar(
            x=puts['strike'], y=puts['GEX'], name='Puts (Baixa)', marker_color='#ff4b4b',
            customdata=(puts['GEX'].abs() / total_abs_gex * 100).round(2),
            hovertemplate="<b>Strike: $%{x}</b><br>GEX: %{y:.2f}M<br><b>Peso: %{customdata}%</b><extra></extra>"
        ))
        fig_g.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text=f"Spot: ${spot:.2f}")
        fig_g.update_layout(template="plotly_dark", barmode='relative', height=500, hovermode="x unified")
        st.plotly_chart(fig_g, use_container_width=True)

    with tab_vanna:
        st.subheader("🌊 Histograma de Vanna (VEX)")
        fig_v = go.Figure()
        fig_v.add_trace(go.Bar(x=calls['strike'], y=calls['VEX'], name='Vanna Calls', marker_color='#00ffcc'))
        fig_v.add_trace(go.Bar(x=puts['strike'], y=puts['VEX'], name='Vanna Puts', marker_color='#ff4b4b'))
        fig_v.update_layout(template="plotly_dark", barmode='relative', height=500)
        st.plotly_chart(fig_v, use_container_width=True)

    # --- 5. DICIONÁRIO ESTRATÉGICO ---
    st.divider()
    st.header("🧠 Dicionário Estratégico de Mercado")
    st.markdown(f"🟢 **{txt_status} (Gama {'Positivo' if net_gex > 0 else 'Negativo'})**")
    st.write(f"Cenário: O preço atual está {'acima' if spot > zero_gamma else 'abaixo'} do Zero Gamma (${zero_gamma}).")
    st.markdown("* **Mecânica:** Market Makers compram nas quedas e vendem nas altas para manter o hedge estável.")
    st.markdown(f"* **Put Wall (${put_wall}):** É o suporte institucional mais forte do dia.")

else:
    st.error("Erro ao carregar os dados. Verifique a conexão.")
