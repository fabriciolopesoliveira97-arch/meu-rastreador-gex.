import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX & VANNA PRO 2026", layout="wide")

# --- 2. MOTOR MATEMÁTICO ---
def calculate_greeks(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0, 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vanna = norm.pdf(d1) * (d2 / sigma)
    return gamma, vanna

@st.cache_data(ttl=300)
def get_data(ticker_symbol):
    tk = yf.Ticker(ticker_symbol)
    df_hist = tk.history(period="1d", interval="2m")
    S = df_hist['Close'].iloc[-1]
    options = tk.option_chain(tk.options[0])
    T, r = 1/365.0, 0.045
    
    # Filtro de Strikes para evitar erro de visualização
    calls = options.calls[(options.calls['strike'] > S * 0.92) & (options.calls['strike'] < S * 1.08)].copy()
    puts = options.puts[(options.puts['strike'] > S * 0.92) & (options.puts['strike'] < S * 1.08)].copy()

    for df, multip in [(calls, 1), (puts, -1)]:
        res = df.apply(lambda x: calculate_greeks(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        df['GEX'] = [r[0] for r in res] * df['openInterest'] * 100 * S**2 * 0.01 * multip
        df['VEX'] = [r[1] for r in res] * df['openInterest'] * 100 * multip
    return calls, puts, S, df_hist

# --- 3. EXECUÇÃO ---
ticker = "QQQ"
calls, puts, spot, hist = get_data(ticker)

if not calls.empty:
    # Cálculos de Níveis
    total_gex = calls['GEX'].sum() + puts['GEX'].sum()
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    
    # --- 4. EXIBIÇÃO DE STATUS E AVISOS (CONFORME IMAGEM) ---
    st.write(f"### Status do Mercado: {datetime.now().strftime('%d/%m/%Y')}")
    
    if total_gex > 0:
        st.markdown(f"<h1 style='color: #00ffcc;'>SUPRESSÃO</h1>", unsafe_allow_html=True)
        st.success(f"🛡️ GAMA POSITIVO: Mercado está em zona de estabilidade.")
    else:
        st.markdown(f"<h1 style='color: #ff4b4b;'>EXPANSÃO</h1>", unsafe_allow_html=True)
        st.error(f"🔥 GAMA NEGATIVO: Risco de movimentos explosivos abaixo do Spot.")

    if spot < put_wall:
        st.warning(f"⚠️ ALERTA: Preço furou a Put Wall (${put_wall})")

    # --- 5. MÉTRICAS ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço SPOT", f"${spot:.2f}")
    c2.metric("Net GEX (M)", f"{total_gex/10**6:.2f}M")
    c3.metric("Put Wall", f"${put_wall}")
    c4.metric("Call Wall", f"${call_wall}")

    # --- 6. HISTOGRAMA COM PORCENTAGENS NO MOUSE ---
    st.subheader("📊 Histograma de Gamma Exposure")
    
    # Cálculo de porcentagem do peso de cada strike
    total_abs_gex = calls['GEX'].abs().sum() + puts['GEX'].abs().sum()
    calls['weight'] = (calls['GEX'].abs() / total_abs_gex * 100).round(2)
    puts['weight'] = (puts['GEX'].abs() / total_abs_gex * 100).round(2)

    fig_hist = go.Figure()
    
    # Barras de Calls
    fig_hist.add_trace(go.Bar(
        x=calls['strike'], y=calls['GEX'], name='Calls (Alta)',
        marker_color='#00ffcc',
        hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}<br>Peso: %{customdata}%<extra></extra>",
        customdata=calls['weight']
    ))
    
    # Barras de Puts
    fig_hist.add_trace(go.Bar(
        x=puts['strike'], y=puts['GEX'], name='Puts (Baixa)',
        marker_color='#ff4b4b',
        hovertemplate="Strike: %{x}<br>GEX: %{y:.2f}<br>Peso: %{customdata}%<extra></extra>",
        customdata=puts['weight']
    ))

    fig_hist.add_vline(x=spot, line_dash="dash", line_color="yellow", annotation_text=f"SPOT: ${spot:.2f}")
    fig_hist.update_layout(template="plotly_dark", barmode='relative', height=500, hovermode="x unified")
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- 7. GRÁFICO DE VANNA (VEX) ---
    st.subheader("🌊 Vanna Exposure (VEX) - Sensibilidade à Volatilidade")
    fig_vex = go.Figure()
    fig_vex.add_trace(go.Scatter(x=calls['strike'], y=calls['VEX'] + puts['VEX'].values[:len(calls)], 
                                 mode='lines', name='Net Vanna', line=dict(color='orange', width=3)))
    fig_vex.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig_vex, use_container_width=True)

    # --- 8. DICIONÁRIO ---
    st.divider()
    st.markdown("""
    ### 🧠 Guia de Leitura
    * **Peso (%):** Mostra qual strike tem mais 'força' para segurar ou empurrar o preço.
    * **Vanna (VEX):** Se estiver positivo e a volatilidade cair, o mercado sobe.
    """)

else:
    st.error("Erro ao carregar dados.")
