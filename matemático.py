import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX PRO - Market Real-Time", layout="wide")

# --- 2. FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES) ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0.0001 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def calculate_vanna(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0.0001 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    # Vanna: dDelta / dSigma
    return (norm.pdf(d1) * (d2 / sigma))

# --- 3. OBTENÇÃO DE DADOS ---
@st.cache_data(ttl=300)
def get_market_data(ticker_symbol="QQQ"):
    ticker = yf.Ticker(ticker_symbol)
    
    # Preço Atual
    hist = ticker.history(period="1d")
    if hist.empty: return None
    current_price = hist['Close'].iloc[-1]
    
    # Taxa de Juros (10Y Yield)
    tnx = yf.Ticker("^TNX")
    tnx_hist = tnx.history(period="1d")
    r = tnx_hist['Close'].iloc[-1] / 100 if not tnx_hist.empty else 0.04
    
    # Opções
    expirations = ticker.options
    if not expirations: return None
    selected_expiry = expirations[0] 
    
    opts = ticker.option_chain(selected_expiry)
    
    # Tempo para expiração
    expiry_dt = datetime.strptime(selected_expiry, '%Y-%m-%d')
    T = (expiry_dt - datetime.now()).total_seconds() / (365.25 * 24 * 3600)
    if T <= 0: T = 0.001 # 1 dia p/ evitar erro
    
    return current_price, r, opts.calls, opts.puts, T, selected_expiry

# --- 4. PROCESSAMENTO ---
data = get_market_data("QQQ")

if data:
    current_price, r, calls, puts, T, expiry_date = data

    def process_exposure(df, is_call=True):
        df = df[df['openInterest'] > 0].copy()
        df['iv'] = df['impliedVolatility'].apply(lambda x: x if x > 0 else 0.20)
        
        df['gamma'] = df.apply(lambda x: calculate_gamma(current_price, x['strike'], T, r, x['iv']), axis=1)
        df['vanna'] = df.apply(lambda x: calculate_vanna(current_price, x['strike'], T, r, x['iv']), axis=1)
        
        # GEX Notional (MM View)
        # Call Gamma é positivo, Put Gamma é negativo para o Market Maker (assumindo que o público compra)
        direction = 1 if is_call else -1
        df['GEX'] = df['openInterest'] * df['gamma'] * (current_price**2) * 0.01 * direction * 100
        df['VEX'] = df['openInterest'] * df['vanna'] * 100 * direction
        return df

    calls = process_exposure(calls, is_call=True)
    puts = process_exposure(puts, is_call=False)
    
    # Unificando
    all_strikes = pd.concat([calls, puts])
    gex_total = all_strikes.groupby('strike')['GEX'].sum().reset_index()
    vex_total = all_strikes.groupby('strike')['VEX'].sum().reset_index()

    # Cálculo do Gamma Flip (Onde cruza o zero)
    gex_total = gex_total.sort_values('strike')
    flip_price = np.interp(0, gex_total['GEX'], gex_total['strike'])

    # --- 5. DASHBOARD ---
    st.title(f"📊 GEX PRO - {expiry_date}")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("QQQ Spot", f"${current_price:.2f}")
    c2.metric("Gamma Flip", f"${flip_price:.2f}")
    c3.metric("Risk-Free (10Y)", f"{r*100:.2f}%")
    c4.metric("Total Net GEX", f"${gex_total['GEX'].sum()/1e6:.1f}M")

    # Gráfico GEX
    fig_gex = go.Figure()
    fig_gex.add_trace(go.Bar(
        x=gex_total['strike'], 
        y=gex_total['GEX'],
        marker_color=np.where(gex_total['GEX'] >= 0, '#00CC96', '#EF553B')
    ))
    fig_gex.add_vline(x=current_price, line_dash="dash", line_color="white", annotation_text="SPOT")
    fig_gex.add_vline(x=flip_price, line_dash="dot", line_color="yellow", annotation_text="FLIP")
    
    fig_gex.update_layout(
        title="Net Gamma Exposure por Strike",
        template="plotly_dark",
        xaxis_range=[current_price * 0.90, current_price * 1.10],
        yaxis_title="GEX Notional ($)"
    )
    st.plotly_chart(fig_gex, use_container_width=True)

    # Gráfico VEX
    fig_vex = go.Figure()
    fig_vex.add_trace(go.Bar(x=vex_total['strike'], y=vex_total['VEX'], marker_color="#636EFA"))
    fig_vex.add_vline(x=current_price, line_dash="dash", line_color="white", annotation_text="SPOT")
    
    fig_vex.update_layout(
        title="Vanna Exposure (Sensibilidade à Volatilidade)",
        template="plotly_dark",
        xaxis_range=[current_price * 0.90, current_price * 1.10],
        yaxis_title="Vanna Exposure"
    )
    st.plotly_chart(fig_vex, use_container_width=True)

else:
    st.error("Erro ao carregar dados. Verifique o Ticker ou a conexão.")
