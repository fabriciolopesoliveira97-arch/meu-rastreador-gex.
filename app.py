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

# --- 2. FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES) ---
def calculate_gamma(S, K, T, r, sigma):
    """Calcula a grega Gamma matemática pura"""
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
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        d_now = datetime.now()
        days_to_expiry = (d_exp - d_now).days + 1
        T = max(days_to_expiry, 1) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()

        calls['Gamma_Puro'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        puts['Gamma_Puro'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)

        calls['GEX'] = calls['Gamma_Puro'] * calls['openInterest'] * 100 * S**2 * 0.01
        puts['GEX'] = puts['Gamma_Puro'] * puts['openInterest'] * 100 * S**2 * 0.01 * -1
        
        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
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
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    status_color = "#00ffcc" if status == "SUPRESSÃO" else "#ff4b4b"

    st.title(f"🛡️ {ticker_symbol} Institutional Tracker")

    # --- ALERTAS DINÂMICOS (IGUAL À IMAGEM) ---
    st.divider()
    if current_price < levels['put']:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']})")
    
    if status == "EXPANSÃO":
        st.warning(f"🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)")

    # --- MÉTRICAS COM CORES DINÂMICAS ---
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", 
              delta=f"{'Positivo' if net_gex_total > 0 else 'Negativo'}", 
              delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Preço Spot", f"${current_price:.2f}")

    # --- HISTOGRAMA GEX (COM LABEL SPOT) ---
    st.subheader("📊 Histograma de Gamma Exposure")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc'))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b'))
    
    # Etiqueta Spot exata
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", line_width=2)
    fig_hist.add_annotation(x=current_price, y=1.05, yref="paper", text=f"SPOT: ${current_price:.2f}", 
                            showarrow=False, font=dict(color="black"), bgcolor="white", borderpad=4)
    fig_hist.update_layout(template="plotly_dark", barmode='relative', hovermode="x unified", 
                          xaxis=dict(range=[current_price * 0.97, current_price * 1.03]))
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- EXPLICAÇÃO TÉCNICA (DICIONÁRIO) ---
    st.divider()
    st.header("🧠 O que significa cada indicador?")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📌 Níveis de Preço")
        st.write(f"**Zero Gamma (${levels['zero']}):** O 'divisor de águas'. Acima dele, o mercado é calmo; abaixo, a volatilidade explode.")
        st.write(f"**Put Wall (${levels['put']}):** O suporte mais forte. É onde os grandes players param de vender e começam a segurar o preço.")
        st.write(f"**Call Wall (${levels['call']}):** A resistência principal. Marca o 'teto' onde o rali costuma perder força.")
    
    with col2:
        st.subheader("📈 Dinâmica de Mercado")
        st.write(f"**Net GEX (${net_gex_total:.2f}M):** Se positivo, os Market Makers agem como amortecedores. Se negativo, eles aceleram as quedas.")
        st.write(f"**Status {status}:** Indica se o mercado está em fase de compressão (calmo) ou expansão de risco (perigoso).")

else:
    st.error("Erro ao carregar dados.")
