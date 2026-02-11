import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX & VANNA PRO - High Precision", layout="wide")

# CSS para métricas dinâmicas e alertas
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 42px !important; font-weight: bold; }
    .status-box { padding: 15px; border-radius: 8px; margin-bottom: 15px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES) ---
def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = norm.pdf(d1) * (d2 / sigma)
    return gamma, vanna

# --- 3. FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def get_market_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="2m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        S = df_hist['Close'].iloc[-1]
        
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        T = max(((datetime.strptime(expiry_date, '%Y-%m-%d') - datetime.now()).days + 1), 1) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility']].copy()

        # Cálculo de Gamma e Vanna
        for df, multip in [(calls, 1), (puts, -1)]:
            res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
            df['GEX'] = [r[0] for r in res] * df['openInterest'] * 100 * S**2 * 0.01 * multip
            df['VEX'] = [r[1] for r in res] * df['openInterest'] * 100 * multip
        
        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

# --- 4. EXECUÇÃO ---
ticker = "QQQ" # Representando Nasdaq 100
calls, puts, spot, hist = get_market_data(ticker)

if not calls.empty:
    # Agregação para Zero Gamma
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    df_total['net_vex'] = df_total['VEX_c'] + df_total['VEX_p']
    
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    net_gex_total = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    net_vex_total = (calls['VEX'].sum() + puts['VEX'].sum()) / 10**6

    # Definição de Cores Dinâmicas
    cor_gex = "#00ffcc" if net_gex_total > 0 else "#ff4b4b"
    cor_vex = "#00ffcc" if net_vex_total > 0 else "#ff4b4b"
    cor_zero = "#00ffcc" if spot > zero_gamma else "#ff4b4b"
    status = "SUPRESSÃO" if spot > zero_gamma else "EXPANSÃO"

    st.title(f"🛡️ {ticker} Institutional Tracker")
    
    # Injeção de cores nas métricas
    st.markdown(f"""<style>
        div[data-testid="column"]:nth-child(1) [data-testid="stMetricValue"] {{ color: {cor_gex} !important; }}
        div[data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] {{ color: {cor_vex} !important; }}
        div[data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] {{ color: {cor_zero} !important; }}
        </style>""", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net GEX", f"{net_gex_total:.2f}M")
    c2.metric("Net Vanna", f"{net_vex_total:.2f}M")
    c3.metric("Zero Gamma", f"${zero_gamma}")
    c4.metric("Put Wall", f"${put_wall}")
    c5.metric("Spot Price", f"${spot:.2f}")

    # Alertas Visuais
    if spot < put_wall:
        st.markdown(f"<div class='status-box' style='background-color: #411b1b; color: #ff4b4b; border: 1px solid #ff4b4b;'>⚠️ ABAIXO DO SUPORTE: Put Wall em ${put_wall} rompida!</div>", unsafe_allow_html=True)

    # --- ABAS ---
    tab_gex, tab_vanna, tab_price = st.tabs(["📊 Gamma Profile", "🌊 Vanna Exposure", "📈 Price Action"])

    with tab_gex:
        total_abs = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
        fig_g = go.Figure()
        fig_g.add_trace(go.Bar(x=calls['strike'], y=calls['GEX'], name='Calls', marker_color='#00ffcc',
                               customdata=(calls['GEX'].abs()/total_abs*100).round(2),
                               hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"))
        fig_g.add_trace(go.Bar(x=puts['strike'], y=puts['GEX'], name='Puts', marker_color='#ff4b4b',
                               customdata=(puts['GEX'].abs()/total_abs*100).round(2),
                               hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}M<br>Peso: %{customdata}%<extra></extra>"))
        
        fig_g.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text=f"SPOT: ${spot:.2f}")
        fig_g.add_vline(x=call_wall, line_color="#00ffcc", line_dash="dot", annotation_text="Call Wall")
        fig_g.update_layout(template="plotly_dark", barmode='relative', height=500, hovermode="x unified")
        st.plotly_chart(fig_g, use_container_width=True)

    with tab_vanna:
        st.subheader("Vanna Exposure (Sensibilidade à Volatilidade)")
        fig_v = go.Figure()
        # Linha bicolor para o Vanna
        fig_v.add_trace(go.Scatter(x=df_total['strike'], y=df_total['net_vex'].where(df_total['net_vex'] >= 0),
                                   mode='lines+markers', name='Vanna Bullish', line=dict(color='#00ffcc', width=3)))
        fig_v.add_trace(go.Scatter(x=df_total['strike'], y=df_total['net_vex'].where(df_total['net_vex'] < 0),
                                   mode='lines+markers', name='Vanna Bearish', line=dict(color='#ff4b4b', width=3)))
        fig_v.add_hline(y=0, line_color="gray", line_dash="dash")
        fig_v.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_v, use_container_width=True)

    with tab_price:
        fig_p = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Preço")])
        fig_p.add_hline(y=zero_gamma, line_dash="dash", line_color=cor_zero, annotation_text="Zero Gamma")
        fig_p.add_hline(y=put_wall, line_color="red", annotation_text="Put Wall")
        fig_p.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_p, use_container_width=True)

    # Dicionário Estratégico (resumido para caber)
    st.divider()
    st.markdown(f"### 🧠 Cenário: <span style='color:{cor_zero}'>{status}</span>", unsafe_allow_html=True)
    st.write(f"O Zero Gamma (${zero_gamma}) atua como o pivô de volatilidade. Atualmente, o mercado está em regime de {status}.")

else:
    st.error("Dados não disponíveis para o ticker selecionado.")
