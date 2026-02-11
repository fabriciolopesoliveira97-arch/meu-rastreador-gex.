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

# --- 2. FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES + VANNA) ---
def calculate_greeks(S, K, T, r, sigma):
    """Calcula Gamma e Vanna"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = (norm.pdf(d1) * (d2 / sigma)) * -1 
    return gamma, vanna

# --- 3. FUNÇÕES DE DADOS ---
@st.cache_data(ttl=60)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="1m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        
        S = df_hist['Close'].iloc[-1]
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days, 1) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility']].copy()

        for df, is_put in [(calls, False), (puts, True)]:
            res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
            df['Gamma_Puro'] = res.apply(lambda x: x[0])
            df['Vanna_Pura'] = res.apply(lambda x: x[1])
            mult = 1 if not is_put else -1
            df['GEX'] = df['Gamma_Puro'] * df['openInterest'] * 100 * S * mult
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
    
    st.title(f"🛡️ {ticker_symbol} Institutional Tracker")
    
    # --- GRÁFICO GEX (SEU ORIGINAL COM LINHA SPOT) ---
    st.subheader("📊 Gamma Exposure (GEX)")
    fig_gex = go.Figure()
    fig_gex.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc'))
    fig_gex.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b'))
    fig_gex.add_vline(x=current_price, line_dash="dash", line_color="white", line_width=2)
    fig_gex.update_layout(template="plotly_dark", barmode='relative', xaxis=dict(range=[current_price*0.96, current_price*1.04]))
    st.plotly_chart(fig_gex, use_container_width=True)

    # --- NOVO GRÁFICO VANNA (SOLICITADO) ---
    st.subheader("🔮 Vanna Exposure (VEX) - Sensibilidade à Volatilidade")
    
    # Unindo dados para o gráfico de Vanna único
    vanna_df = pd.concat([
        calls_data[['strike', 'VEX']].assign(Tipo='Call'),
        puts_data[['strike', 'VEX']].assign(Tipo='Put')
    ]).groupby('strike').sum().reset_index()

    # Cores dinâmicas: Verde se VEX > 0, Vermelho se VEX < 0
    vanna_df['color'] = np.where(vanna_df['VEX'] > 0, '#00ffcc', '#ff4b4b')

    fig_vanna = go.Figure()
    fig_vanna.add_trace(go.Bar(
        x=vanna_df['strike'], 
        y=vanna_df['VEX'],
        marker_color=vanna_df['color'],
        hovertemplate="<b>Strike: %{x}</b><br>Vanna: %{y:.2f}<extra></extra>"
    ))
    
    fig_vanna.add_vline(x=current_price, line_dash="dash", line_color="white", line_width=2)
    fig_vanna.update_layout(
        template="plotly_dark", 
        xaxis=dict(title="Strike ($)", range=[current_price*0.96, current_price*1.04]),
        yaxis=dict(title="Vanna Exposure"),
        showlegend=False
    )
    st.plotly_chart(fig_vanna, use_container_width=True)

    # --- GRÁFICO CANDLESTICK ---
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)
else:
    st.error("Erro ao carregar dados.")
