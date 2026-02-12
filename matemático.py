import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO E AUTO-REFRESH ---
st.set_page_config(page_title="GEX PRO - Real Time", layout="wide")

# Atualiza a página a cada 60 segundos
st_autorefresh(interval=60 * 1000, key="datarefresh")

# --- 2. FUNÇÕES MATEMÁTICAS ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

# --- 3. FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty:
            df_hist = tk.history(period="1d")
        
        if df_hist.empty:
            return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
            
        S = df_hist['Close'].iloc[-1]
        
        vencimentos = tk.options
        if not vencimentos:
            return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
            
        expiry_date = vencimentos[0]
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days + 1, 1) / 365.0
        r = 0.045 

        # Margem de 5% para focar na liquidez próxima ao preço atual
        margin = 0.05 
        calls = options.calls[(options.calls['strike'] > S*(1-margin)) & 
                              (options.calls['strike'] < S*(1+margin)) & 
                              (options.calls['openInterest'] > 50) & 
                              (options.calls['impliedVolatility'] > 0.001)].copy()
        
        puts = options.puts[(options.puts['strike'] > S*(1-margin)) & 
                            (options.puts['strike'] < S*(1+margin)) & 
                            (options.puts['openInterest'] > 50) & 
                            (options.puts['impliedVolatility'] > 0.001)].copy()

        calls['GEX'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01, axis=1)
        puts['GEX'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01 * -1, axis=1)
        
        return calls, puts, S, df_hist
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
    
    # CALL WALL: Strike com maior GEX positivo (Resistência)
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # PUT WALL: Strike com maior GEX negativo (Suporte)
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    
    # ZERO GAMMA: Localiza o ponto onde a exposição líquida inverte o sinal (Cruzamento real)
    df_total = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    df_net = df_total.groupby('strike')['GEX'].sum().reset_index().sort_values('strike')
    
    df_net['prev_GEX'] = df_net['GEX'].shift(1)
    # Procura onde o GEX cruza de negativo para positivo ou vice-versa
    crossing = df_net[((df_net['GEX'] > 0) & (df_net['prev_GEX'] < 0)) | 
                       ((df_net['GEX'] < 0) & (df_net['prev_GEX'] > 0))]
    
    if not crossing.empty:
        zero_gamma = crossing.iloc[0]['strike']
    else:
        # Fallback para o valor mais próximo de zero caso não haja cruzamento
        zero_gamma = df_net.iloc[(df_net['GEX']).abs().argsort()[:1]]['strike'].values[0]
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- 4. INTERFACE ---
ticker_symbol = st.sidebar.text_input("Ticker", value="QQQ").upper()
calls_data, puts_data, current_price, df_price = get_gamma_data_v2(ticker_symbol)

if not calls_data.empty and not puts_data.empty:
    levels = get_gamma_levels(calls_data, puts_data)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    
    status = "SUPRESSÃO (🛡️ MM Comprados)" if current_price > levels['zero'] else "EXPANSÃO (🔥 MM Vendidos)"
    gex_color = "normal" if net_gex_total > 0 else "inverse"

    st.title(f"📊 {ticker_symbol} - Monitor de Liquidez")
    st.write(f"Última atualização: {datetime.now().strftime('%H:%M:%S')}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço Atual", f"${current_price:.2f}")
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta=f"{'Positivo' if net_gex_total > 0 else 'Negativo'}", delta_color=gex_color)
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    fig_candle = go.Figure(data=[go.Candlestick(
        x=df_price.index, open=df_price['Open'], high=df_price['High'], 
        low=df_price['Low'], close=df_price['Close'], name="Preço"
    )])
    
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
    fig_candle.add_hline(y=levels['put'], line_color="#00ff00", line_width=2, annotation_text="PUT WALL")
    fig_candle.add_hline(y=levels['call'], line_color="#ff4b4b", line_width=2, annotation_text="CALL WALL")
    
    fig_candle.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

    st.info(f"O mercado está em zona de **{status}**. Nível crítico em **${levels['zero']}**.")

else:
    st.warning("Aguardando dados... Verifique o ticker ou o horário do mercado.")
