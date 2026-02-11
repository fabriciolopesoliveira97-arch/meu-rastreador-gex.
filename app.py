import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO - Black-Scholes Precision", layout="wide")

# --- MOTOR MATEMÁTICO (BLACK-SCHOLES) ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

@st.cache_data(ttl=300)
def get_market_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        S = df_hist['Close'].iloc[-1]
        
        # Foco no vencimento atual (Crucial para 0DTE em 2026)
        expiry = tk.options[0]
        options = tk.option_chain(expiry)
        
        T = 1/365.0 
        r = 0.045 # Taxa de Juros 2026

        # FILTRO DE RELEVÂNCIA: Focamos em strikes próximos ao preço (Spot +- 10%)
        # Isso elimina o erro de Zero Gamma em $525 quando o preço está em $612
        lower_bound = S * 0.90
        upper_bound = S * 1.10
        
        calls = options.calls[(options.calls['strike'] > lower_bound) & (options.calls['strike'] < upper_bound)].copy()
        puts = options.puts[(options.puts['strike'] > lower_bound) & (options.puts['strike'] < upper_bound)].copy()
        
        # Cálculo Gamma e GEX Real
        calls['Gamma'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        puts['Gamma'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        
        calls['GEX'] = calls['Gamma'] * calls['openInterest'] * 100 * S**2 * 0.01
        puts['GEX'] = puts['Gamma'] * puts['openInterest'] * 100 * S**2 * 0.01 * -1
        
        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

# --- INTERFACE ---
ticker = "QQQ"
calls, puts, price, hist = get_market_data(ticker)

if not calls.empty:
    # Localização dos Níveis Institucionais
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # Cálculo do Zero Gamma sobre o Net GEX filtrado
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6

    # --- MÉTRICAS ---
    st.title(f"🚀 Nasdaq 100 (QQQ) - Institutional Flow")
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço Spot", f"${price:.2f}")
    
    # Net GEX com cor dinâmica
    gex_color = "normal" if net_gex > 0 else "inverse"
    c2.metric("Net GEX (M)", f"{net_gex:.2f}M", delta=f"{'Bullish' if net_gex > 0 else 'Bearish'}", delta_color=gex_color)
    
    # O Zero Gamma agora aparecerá próximo aos $600-$610, não mais em $525
    c3.metric("Zero Gamma", f"${zero_gamma}")
    c4.metric("Put Wall", f"${put_wall}")
    c5.metric("Call Wall", f"${call_wall}")

    # --- GRÁFICO CANDLESTICK ---
    fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Preço")])
    fig.add_hline(y=zero_gamma, line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig.add_hline(y=put_wall, line_color="#ff4b4b", line_width=2, annotation_text="Put Wall")
    fig.add_hline(y=call_wall, line_color="#00ffcc", line_width=2, annotation_text="Call Wall")
    fig.update_layout(template="plotly_dark", height=400, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # --- HISTOGRAMA GEX (FOCADO) ---
    st.subheader("📊 Perfil de Gamma Exposure (Foco Institucional)")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls['strike'], y=calls['GEX'], name='Calls', marker_color='#00ffcc'))
    fig_hist.add_trace(go.Bar(x=puts['strike'], y=puts['GEX'], name='Puts', marker_color='#ff4b4b'))
    fig_hist.update_layout(template="plotly_dark", barmode='relative', hovermode="x unified")
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- DICIONÁRIO ESTRATÉGICO ---
    st.divider()
    st.header("🧠 Dicionário de Trading")
    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**Zero Gamma (${zero_gamma}):** Se o preço cair abaixo deste nível, a volatilidade explode.")
    with col_b:
        st.write(f"**Put Wall (${put_wall}):** Onde os bancos estão 'sentados' comprando para defender o mercado.")

else:
    st.error("Erro ao carregar dados. Verifique a conexão com o Yahoo Finance.")
