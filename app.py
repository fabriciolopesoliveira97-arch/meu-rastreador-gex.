import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX PRO - High Precision", layout="wide")

# --- 2. FUNÇÕES MATEMÁTICAS ---
def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = (norm.pdf(d1) * (d2 / sigma)) * -1 
    return gamma, vanna

# --- 3. FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        S = df_hist['Close'].iloc[-1]
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max(((d_exp - datetime.now()).days + 1), 1) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility']].copy()

        for df, is_put in [(calls, False), (puts, True)]:
            res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
            df['Gamma_Puro'] = res.apply(lambda x: x[0])
            df['Vanna_Pura'] = res.apply(lambda x: x[1])
            mult = 1 if not is_put else -1
            df['GEX'] = df['Gamma_Puro'] * df['openInterest'] * 100 * S**2 * 0.01 * mult
            df['VEX'] = df['Vanna_Pura'] * df['openInterest'] * 100 * mult
        
        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty: return {"zero": 0, "put": 0, "call": 0}
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- 4. EXECUÇÃO ---
ticker_symbol = "QQQ"
calls_data, puts_data, current_price, df_price = get_gamma_data_v2(ticker_symbol)

if not calls_data.empty:
    levels = get_gamma_levels(calls_data, puts_data)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    
    st.title(f"🛡️ {ticker_symbol} Institutional Tracker")

    # --- ALERTAS VISUAIS ---
    if current_price < levels['put']:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']})")
    if current_price < levels['zero']:
        st.warning(f"🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)")

    # --- MÉTRICAS COM CORES DINÂMICAS ---
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status", "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO")
    
    # COR DINÂMICA DO NET GEX: Verde se > 0, Vermelho se < 0
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", 
              delta=f"{'Bullish' if net_gex_total > 0 else 'Bearish'}", 
              delta_color="normal" if net_gex_total > 0 else "inverse")
    
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # --- HISTOGRAMA GEX COM SPOT LABEL ---
    st.subheader("📊 Gamma Exposure (Força por Strike)")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc'))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b'))
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", line_width=2)
    fig_hist.add_annotation(x=current_price, y=1.05, yref="paper", text=f"SPOT: ${current_price:.2f}", 
                            showarrow=False, font=dict(color="black"), bgcolor="white", borderpad=4)
    fig_hist.update_layout(template="plotly_dark", barmode='relative', hovermode="x unified", xaxis=dict(range=[current_price*0.97, current_price*1.03]))
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- GRÁFICO VANNA ---
    st.subheader("🔮 Vanna Exposure (VEX)")
    vanna_merged = pd.concat([calls_data[['strike', 'VEX']], puts_data[['strike', 'VEX']]]).groupby('strike').sum().reset_index()
    vanna_merged['cor'] = np.where(vanna_merged['VEX'] >= 0, '#00ffcc', '#ff4b4b')
    fig_vanna = go.Figure(go.Bar(x=vanna_merged['strike'], y=vanna_merged['VEX'], marker_color=vanna_merged['cor']))
    fig_vanna.update_layout(template="plotly_dark", xaxis=dict(range=[current_price*0.97, current_price*1.03]))
    st.plotly_chart(fig_vanna, use_container_width=True)

    # --- CANDLESTICK COM NÍVEIS ---
    st.subheader("🕯️ Níveis de Suporte e Resistência")
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.add_hline(y=levels['put'], line_color="#ff4b4b", line_width=2, annotation_text="Put Wall")
    fig_candle.add_hline(y=levels['call'], line_color="#00ffcc", line_width=2, annotation_text="Call Wall")
    fig_candle.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

else:
    st.error("Erro ao carregar dados.")
