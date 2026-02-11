import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX & VANNA PRO - High Precision", layout="wide")

# --- 2. FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES APRIMORADO) ---
def calculate_greeks(S, K, T, r, sigma):
    """Calcula Gamma e Vanna usando Black-Scholes"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0, 0
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    # Gamma
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    # Vanna: dGamma / dSigma ou dDelta / dSigma
    # Uma aproximação comum para Vanna financeira:
    vanna = (norm.pdf(d1) * (d2 / sigma)) * -1 
    
    return gamma, vanna

# --- 3. FUNÇÕES DE DADOS (AGORA COM AUTO-UPDATE) ---
@st.cache_data(ttl=60) # Atualiza a cada 60 segundos
def get_market_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        # Tenta pegar dados intradiários reais
        df_hist = tk.history(period="1d", interval="1m")
        if df_hist.empty:
            df_hist = tk.history(period="2d", interval="5m")
            
        S = df_hist['Close'].iloc[-1]
        
        # Pega o vencimento mais próximo (0DTE ou próximo disponível)
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days, 0.5) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility']].copy()

        # Cálculo de Gamma e Vanna
        for df, is_put in [(calls, False), (puts, True)]:
            greeks = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
            df['Gamma_Puro'] = greeks.apply(lambda x: x[0])
            df['Vanna_Pura'] = greeks.apply(lambda x: x[1])
            
            mult = -1 if is_put else 1
            df['GEX'] = df['Gamma_Puro'] * df['openInterest'] * 100 * S * mult
            df['VEX'] = df['Vanna_Pura'] * df['openInterest'] * 100 * mult # Vanna Exposure

        return calls, puts, S, df_hist, expiry_date
    except Exception as e:
        st.error(f"Erro na captura: {e}")
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame(), ""

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
    
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # Cruzamento para achar Zero Gamma Real-Time
    df_total = pd.merge(calls[['strike', 'GEX']], puts[['strike', 'GEX']], on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- 4. EXECUÇÃO ---
ticker_symbol = "QQQ"
calls_data, puts_data, current_price, df_price, expiry = get_market_data(ticker_symbol)

if not calls_data.empty:
    levels = get_gamma_levels(calls_data, puts_data)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    net_vanna_total = (calls_data['VEX'].sum() + puts_data['VEX'].sum()) / 10**6
    
    status = "SUPRESSÃO (🛡️)" if current_price > levels['zero'] else "EXPANSÃO (🔥)"
    status_color = "#00ffcc" if current_price > levels['zero'] else "#ff4b4b"

    st.title(f"⚡ {ticker_symbol} Quantum Tracker")
    st.caption(f"Dados em tempo real para o vencimento: {expiry} | Spot: ${current_price:.2f}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta="Bullish" if net_gex_total > 0 else "Bearish")
    c3.metric("Net Vanna", f"{net_vanna_total:.2f}M", help="Sensibilidade à Volatilidade")
    c4.metric("Zero Gamma", f"${levels['zero']}")
    c5.metric("Put Wall", f"${levels['put']}")

    # --- GRÁFICO CANDLESTICK ---
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
    fig_candle.update_layout(template="plotly_dark", height=400, margin=dict(t=10, b=10))
    st.plotly_chart(fig_candle, use_container_width=True)

    # --- GRÁFICO VANNA vs GEX ---
    st.subheader("🔮 Exposure Profile (GEX vs VANNA)")
    fig_vanna = go.Figure()
    fig_vanna.add_trace(go.Scatter(x=calls_data['strike'], y=calls_data['VEX'], fill='tozeroy', name='Vanna (Vol Risk)', line_color='#ab63ff'))
    fig_vanna.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='GEX (Price Risk)', marker_color='#00ffcc'))
    fig_vanna.update_layout(template="plotly_dark", height=400, xaxis=dict(range=[current_price*0.96, current_price*1.04]))
    st.plotly_chart(fig_vanna, use_container_width=True)

    # --- EXPLICAÇÃO DA VANNA ---
    with st.expander("O que é a Vanna adicionada?"):
        st.write("""
        A **Vanna** mede como o Delta de uma opção muda quando a Volatilidade Implícita (IV) se move. 
        - **Vanna Positiva:** Se a IV cair (mercado acalmar), os Market Makers precisam comprar o ativo, empurrando o preço para cima.
        - **Vanna Negativa:** Se a IV subir (medo), gera pressão de venda automática.
        """)
else:
    st.error("Falha ao conectar com Yahoo Finance. Verifique o Ticker.")
