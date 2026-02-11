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

# --- 3. FUNÇÕES DE DADOS (CORRIGIDA) ---
@st.cache_data(ttl=300)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        
        # Tenta pegar dados intradiários (5min) para o gráfico de velas
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty:
            df_hist = tk.history(period="1d")
        
        if df_hist.empty:
            return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
            
        S = df_hist['Close'].iloc[-1]
        
        # Pega opções do vencimento mais próximo
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        d_now = datetime.now()
        days_to_expiry = (d_exp - d_now).days + 1
        T = max(days_to_expiry, 1) / 365.0
        r = 0.045 # Taxa de juros livre de risco

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()

        # Cálculo da Gamma Pura e GEX Financeiro
        calls['Gamma_Puro'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        puts['Gamma_Puro'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)

        calls['GEX'] = calls['Gamma_Puro'] * calls['openInterest'] * 100 * S**2 * 0.01
        puts['GEX'] = puts['Gamma_Puro'] * puts['openInterest'] * 100 * S**2 * 0.01 * -1
        
        return calls, puts, S, df_hist

    except Exception as e:
        # GARANTIA: Sempre retorna 4 valores para evitar o erro de ValueError
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

# --- 4. EXECUÇÃO E INTERFACE VISUAL ---
ticker_symbol = "QQQ"
calls_data, puts_data, current_price, df_price = get_gamma_data_v2(ticker_symbol)

if not calls_data.empty:
    levels = get_gamma_levels(calls_data, puts_data)
    
    # Cálculos de Métricas
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    status_color = "#00ffcc" if status == "SUPRESSÃO" else "#ff4b4b"

    # --- TÍTULO E MÉTRICAS ---
    st.title(f"🛡️ {ticker_symbol} Institutional Tracker")
    st.markdown(f"**Cálculo:** Matemática Black-Scholes Precision")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    st.markdown(f"## Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

    # --- GRÁFICO CANDLESTICK ---
    fig_candle = go.Figure(data=[go.Candlestick(
        x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço"
    )])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
    fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

    # --- ALERTAS DE RISCO ---
    st.divider()
    col_alerta1, col_alerta2 = st.columns(2)
    distancia_put = ((current_price - levels['put']) / levels['put']) * 100

    with col_alerta1:
        if current_price < levels['put']:
            st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']})")
        else:
            st.success(f"🛡️ ACIMA DO SUPORTE: Preço {distancia_put:.2f}% acima da Put Wall.")

    with col_alerta2:
        if status == "EXPANSÃO":
            st.warning("🔥 RISCO: GAMA NEGATIVO (Volatilidade Explosiva)")
        else:
            st.info("🟢 REGIME ESTÁVEL: GAMA POSITIVO (Volatilidade Comprimida)")

    # --- HISTOGRAMA GEX (ESTILIZADO COM HOVER DETALHADO) ---
    st.subheader("📊 Perfil de Exposição Financeira (GEX por Strike)")
    
    # Cálculo de pesos para o hover
    total_abs_gex = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['peso'] = (calls_data['GEX'] / total_abs_gex) * 100
    puts_data['peso'] = (puts_data['GEX'].abs() / total_abs_gex) * 100

    fig_hist = go.Figure()

    # Trace de Calls
    fig_hist.add_trace(go.Bar(
        x=calls_data['strike'], 
        y=calls_data['GEX'], 
        name='Calls (Gamma +)', 
        marker_color='#00ffcc',
        customdata=calls_data['peso'],
        hovertemplate="<b>Strike:</b> $%{x}<br><b>GEX:</b> %{y:.2f}<br><b>Peso:</b> %{customdata:.2f}%<extra></extra>"
    ))

    # Trace de Puts
    fig_hist.add_trace(go.Bar(
        x=puts_data['strike'], 
        y=puts_data['GEX'], 
        name='Puts (Gamma -)', 
        marker_color='#ff4b4b',
        customdata=puts_data['peso'],
        hovertemplate="<b>Strike:</b> $%{x}<br><b>GEX:</b> %{y:.2f}<br><b>Peso:</b> %{customdata:.2f}%<extra></extra>"
    ))
    
    # Linha do Preço Spot (Preço Atual)
    fig_hist.add_vline(
        x=current_price, 
        line_dash="dash", 
        line_color="yellow", 
        line_width=2,
        annotation_text=f"SPOT: ${current_price:.2f}",
        annotation_position="top left"
    )

    fig_hist.update_layout(
        template="plotly_dark", 
        barmode='relative',
        hovermode="x unified", # Agrupa o hover se houver call e put no mesmo strike
        xaxis=dict(
            title="Strike Price ($)", 
            range=[current_price * 0.95, current_price * 1.05] # Zoom de 5% em volta do preço
        ),
        yaxis=dict(title="Exposição Financeira (GEX)"),
        height=550,
        showlegend=True
    )
    
    st.plotly_chart(fig_hist, use_container_width=True)
