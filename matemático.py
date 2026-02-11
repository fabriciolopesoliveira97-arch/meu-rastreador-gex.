import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime
import time

# --- 1. CONFIGURAÇÃO E AUTO-REFRESH ---
st.set_page_config(page_title="GEX PRO - Real Time", layout="wide")

# Faz a página atualizar automaticamente a cada 60 segundos
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=60 * 1000, key="datarefresh")

# --- 2. FUNÇÕES MATEMÁTICAS ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

# --- 3. BUSCA DE DADOS (CORRIGIDA) ---
@st.cache_data(ttl=30) # Cache reduzido para 30 segundos para ser "quase" real-time
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        # Puxa o preço atual exato (Price Action)
        df_hist = tk.history(period="1d", interval="1m")
        if df_hist.empty:
            return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
            
        S = df_hist['Close'].iloc[-1]
        
        # Seleciona o vencimento mais próximo (Geralmente 0DTE para QQQ)
        available_expirations = tk.options
        if not available_expirations:
            return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
        
        expiry_date = available_expirations[0] 
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days, 0.5) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility']].copy()

        # Limpeza de dados (IV zero quebra o cálculo)
        calls = calls[calls['impliedVolatility'] > 0.001]
        puts = puts[puts['impliedVolatility'] > 0.001]

        calls['GEX'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01, axis=1)
        puts['GEX'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01 * -1, axis=1)
        
        return calls, puts, S, df_hist
    except Exception as e:
        st.error(f"Erro na API: {e}")
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
    
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # Cálculo preciso do Zero Gamma (onde a soma cruza o eixo 0)
    df_total = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    df_net = df_total.groupby('strike').sum().reset_index()
    zero_gamma = df_net.iloc[(df_net['GEX']).abs().argsort()[:1]]['strike'].values[0]
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- 4. INTERFACE ---
ticker_symbol = "QQQ"
calls_data, puts_data, current_price, df_price = get_gamma_data_v2(ticker_symbol)

if not calls_data.empty:
    levels = get_gamma_levels(calls_data, puts_data)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    
    # Lógica de Status (Baseada no Preço Spot vs Zero Gamma)
    status = "SUPRESSÃO (🛡️ MM Comprados)" if current_price > levels['zero'] else "EXPANSÃO (🔥 MM Vendidos)"
    status_color = "#00ffcc" if current_price > levels['zero'] else "#ff4b4b"

    st.title(f"📊 {ticker_symbol} - Monitor de Liquidez")
    st.write(f"Atualizado em: {datetime.now().strftime('%H:%M:%S')}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço Atual", f"${current_price:.2f}")
    c2.metric("Net GEX", f"{net_gex_total:.2f}M")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall (Suporte)", f"${levels['put']}")
    c5.metric("Call Wall (Resistência)", f"${levels['call']}")

    # Gráfico Principal
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="PUT WALL")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="CALL WALL")
    fig_candle.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

    st.info(f"O mercado está em zona de **{status}**. O suporte institucional está em **${levels['put']}**.")

else:
    st.warning("Aguardando dados da API da Nasdaq... (Verifique se o mercado está aberto)")
