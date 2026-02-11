import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX & VANNA PRO", layout="wide")

# --- 2. MOTOR MATEMÁTICO (GREEKS) ---
def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    # Gamma
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    # Vanna
    vanna = norm.pdf(d1) * (d2 / sigma)
    
    return gamma, vanna

@st.cache_data(ttl=300)
def get_institutional_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        S = df_hist['Close'].iloc[-1]
        
        expiry = tk.options[0]
        options = tk.option_chain(expiry)
        T = 1/365.0 # Foco em 0DTE/Curto Prazo
        r = 0.045 # Taxa 2026

        # FILTRO DE LIQUIDEZ REAL (Evita erros como o Zero Gamma em $525)
        # Foca apenas em strikes próximos ao preço atual
        calls = options.calls[(options.calls['strike'] > S * 0.85) & (options.calls['strike'] < S * 1.15)].copy()
        puts = options.puts[(options.puts['strike'] > S * 0.85) & (options.puts['strike'] < S * 1.15)].copy()

        # Cálculos de Gamma e Vanna
        for df, multip in [(calls, 1), (puts, -1)]:
            greeks = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
            df['Gamma'] = [g[0] for g in greeks]
            df['Vanna'] = [g[1] for g in greeks]
            # Exposições Financeiras
            df['GEX'] = df['Gamma'] * df['openInterest'] * 100 * S**2 * 0.01 * multip
            df['VEX'] = df['Vanna'] * df['openInterest'] * 100 * multip

        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

# --- 3. PROCESSAMENTO ---
ticker = "QQQ"
calls, puts, current_price, df_price = get_institutional_data(ticker)

if not calls.empty:
    # Níveis de Inflexão
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
    net_vex = (calls['VEX'].sum() + puts['VEX'].sum()) / 10**6

    # --- 4. INTERFACE VISUAL ---
    st.title(f"🛡️ {ticker} Institutional Risk Tracker")
    
    # Cores Dinâmicas para Net GEX e Net VEX
    col1, col2, col3, col4, col5 = st.columns(5)
    
    col1.metric("Preço Spot", f"${current_price:.2f}")
    
    # NET GEX com cor dinâmica
    c_gex = "normal" if net_gex > 0 else "inverse"
    col2.metric("Net GEX", f"{net_gex:.2f}M", delta=f"{'Bullish' if net_gex > 0 else 'Bearish'}", delta_color=c_gex)
    
    # NET VEX (Vanna)
    c_vex = "normal" if net_vex > 0 else "inverse"
    col3.metric("Net Vanna", f"{net_vex:.2f}M", delta="Vol Sens", delta_color=c_vex)
    
    col4.metric("Zero Gamma", f"${zero_gamma}")
    col5.metric("Put Wall", f"${put_wall}")

    # --- HISTOGRAMA GEX ---
    st.subheader("📊 Perfil de Exposição (Gamma & Vanna)")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls['strike'], y=calls['GEX'], name='GEX Calls', marker_color='#00ffcc'))
    fig_hist.add_trace(go.Bar(x=puts['strike'], y=puts['GEX'], name='GEX Puts', marker_color='#ff4b4b'))
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="yellow", annotation_text="SPOT")
    fig_hist.update_layout(template="plotly_dark", barmode='relative', xaxis=dict(range=[current_price*0.95, current_price*1.05]))
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- DICIONÁRIO ESTRATÉGICO ---
    st.divider()
    st.header("🧠 Dicionário de Inteligência 2026")
    exp1, exp2 = st.columns(2)
    with exp1:
        st.markdown(f"""
        ### 🟢 VANNA POSITIVO ({net_vex:.2f}M)
        * **Efeito:** Se a volatilidade (VIX) cair, o mercado sobe por recompras forçadas.
        * **Zero Gamma (${zero_gamma}):** O preço está acima, indicando regime de supressão de volatilidade.
        """)
    with exp2:
        st.markdown(f"""
        ### 🧱 Níveis Chave
        * **Put Wall (${put_wall}):** Suporte Institucional máximo.
        * **Call Wall (${call_wall}):** Resistência Institucional máxima.
        """)

else:
    st.error("Erro ao processar dados. Verifique a conexão.")
