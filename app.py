import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

st.set_page_config(page_title="GEX PRO - Quantum Tracker", layout="wide")

# --- MATEMÁTICA BLACK-SCHOLES ---
def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = (norm.pdf(d1) * (d2 / sigma)) * -1 
    return gamma, vanna

# --- COLETA DE DADOS REAL-TIME ---
@st.cache_data(ttl=60)
def get_market_data(ticker_symbol):
    tk = yf.Ticker(ticker_symbol)
    df_hist = tk.history(period="1d", interval="1m")
    if df_hist.empty: df_hist = tk.history(period="2d", interval="5m")
    S = df_hist['Close'].iloc[-1]
    
    expiry_date = tk.options[0]
    options = tk.option_chain(expiry_date)
    d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
    T = max((d_exp - datetime.now()).days, 0.5) / 365.0
    r = 0.045 

    calls = options.calls[['strike', 'openInterest', 'impliedVolatility']].copy()
    puts = options.puts[['strike', 'openInterest', 'impliedVolatility']].copy()

    for df, is_put in [(calls, False), (puts, True)]:
        res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        df['Gamma_Puro'] = res.apply(lambda x: x[0])
        df['Vanna_Pura'] = res.apply(lambda x: x[1])
        mult = -1 if is_put else 1
        df['GEX'] = df['Gamma_Puro'] * df['openInterest'] * 100 * S * mult
        df['VEX'] = df['Vanna_Pura'] * df['openInterest'] * 100 * mult
    
    return calls, puts, S, df_hist, expiry_date

# --- ANÁLISE DE NÍVEIS ---
def get_levels(calls, puts):
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    df_total = pd.merge(calls[['strike', 'GEX']], puts[['strike', 'GEX']], on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- INTERFACE ---
ticker = "QQQ"
c_data, p_data, spot, df_p, expiry = get_market_data(ticker)

if not c_data.empty:
    lvl = get_levels(c_data, p_data)
    net_gex = (c_data['GEX'].sum() + p_data['GEX'].sum()) / 10**6
    
    st.title(f"🛡️ {ticker} Institutional Dashboard")
    st.subheader(f"Vencimento: {expiry} | Spot: ${spot:.2f}")

    cols = st.columns(5)
    cols[0].metric("Net GEX", f"{net_gex:.2f}M")
    cols[1].metric("Zero Gamma", f"${lvl['zero']}")
    cols[2].metric("Call Wall (Teto)", f"${lvl['call']}")
    cols[3].metric("Put Wall (Chão)", f"${lvl['put']}")
    cols[4].metric("Trend", "BULLISH" if spot > lvl['zero'] else "BEARISH")

    # --- HISTOGRAMA DE GEX COM HOVER PERSONALIZADO ---
    st.markdown("### 📊 Gamma Exposure Profile")
    
    # Cálculo de porcentagem de dominância para o Hover
    total_abs_gex = c_data['GEX'].abs().sum() + p_data['GEX'].abs().sum()
    c_data['dominancia'] = (c_data['GEX'].abs() / total_abs_gex) * 100
    p_data['dominancia'] = (p_data['GEX'].abs() / total_abs_gex) * 100

    fig_hist = go.Figure()
    
    # Calls (Compradores de Gamma / Vendedores de Vol)
    fig_hist.add_trace(go.Bar(
        x=c_data['strike'], y=c_data['GEX'],
        name='Call GEX (Dominância de Alta)',
        marker_color='#00ffcc',
        customdata=c_data['dominancia'],
        hovertemplate="<b>Strike: %{x}</b><br>GEX: %{y:.2f}<br>Dominância: %{customdata:.2f}%<br>Status: Market Makers Comprados<extra></extra>"
    ))

    # Puts (Vendedores de Gamma / Hedging de Baixa)
    fig_hist.add_trace(go.Bar(
        x=p_data['strike'], y=p_data['GEX'],
        name='Put GEX (Proteção de Baixa)',
        marker_color='#ff4b4b',
        customdata=p_data['dominancia'],
        hovertemplate="<b>Strike: %{x}</b><br>GEX: %{y:.2f}<br>Dominância: %{customdata:.2f}%<br>Status: Market Makers Vendidos (Risco)<extra></extra>"
    ))

    # Linha do Spot
    fig_hist.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="PREÇO SPOT")

    fig_hist.update_layout(
        template="plotly_dark", barmode='relative',
        xaxis=dict(title="Strike Price", range=[spot*0.95, spot*1.05]),
        yaxis=dict(title="Financial Exposure"),
        height=500
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- CANDLESTICK ---
    fig_candle = go.Figure(data=[go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'])])
    fig_candle.add_hline(y=lvl['call'], line_color="green", line_dash="dot", annotation_text="CALL WALL")
    fig_candle.add_hline(y=lvl['put'], line_color="red", line_dash="dot", annotation_text="PUT WALL")
    fig_candle.update_layout(template="plotly_dark", height=400, showlegend=False)
    st.plotly_chart(fig_candle, use_container_width=True)

else:
    st.error("Erro ao carregar dados. Verifique a conexão.")
