import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX PRO - High Precision", layout="wide")

# --- FUNÇÕES MATEMÁTICAS (BLACK-SCHOLES) ---
def calculate_gamma(S, K, T, r, sigma):
    """Calcula a grega Gamma matemática pura"""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

# --- FUNÇÕES DE DADOS (COM CACHE) ---
@st.cache_data(ttl=300)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        hist = tk.history(period="1d")
        if hist.empty: return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
        S = hist['Close'].iloc[-1]
        
        expiry_date = tk.options[0]
        options = tk.option_chain(expiry_date)
        
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        d_now = datetime.now()
        days_to_expiry = (d_exp - d_now).days + 1
        T = max(days_to_expiry, 1) / 365.0
        r = 0.045 

        calls = options.calls[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'impliedVolatility', 'lastPrice']].copy()

        # 1. CÁLCULO DA GAMMA PURA E GEX
        calls['Gamma_Puro'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)
        puts['Gamma_Puro'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']), axis=1)

        # Fórmula de Exposição Financeira
        calls['GEX'] = calls['Gamma_Puro'] * calls['openInterest'] * 100 * S**2 * 0.01
        puts['GEX'] = puts['Gamma_Puro'] * puts['openInterest'] * 100 * S**2 * 0.01 * -1
        
        return calls, puts, S, hist
    except Exception as e:
        st.error(f"Erro no cálculo matemático: {e}")
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

# --- PROCESSAMENTO PRINCIPAL ---
ticker_symbol = "QQQ"
calls_data, puts_data, current_price, df_price = get_gamma_data_v2(ticker_symbol)

if not calls_data.empty:
    levels = get_gamma_levels(calls_data, puts_data)
    
    # Cálculos de Status
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    status_color = "#00ffcc" if status == "SUPRESSÃO" else "#ff4b4b"

    # --- INTERFACE VISUAL: MÉTRICAS ---
    st.title(f"🛡️ {ticker_symbol} High Precision Tracker")
    st.markdown(f"**Modelo:** Black-Scholes Gamma Exposure")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX Total", f"{net_gex_total:.2f}M", delta=f"{net_gex_total:.2f}M", delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    st.markdown(f"## Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

    # --- GRÁFICO DE PREÇO (CANDLESTICK) ---
    fig_candle = go.Figure(data=[go.Candlestick(
        x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço"
    )])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
    fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_candle, use_container_width=True)

    # --- ALERTAS DE RISCO ---
    st.divider()
    col_alerta1, col_alerta2 = st.columns(2)
    distancia_suporte = ((current_price - levels['put']) / levels['put']) * 100

    with col_alerta1:
        if current_price < levels['put']:
            st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']})")
        else:
            st.success(f"🛡️ ACIMA DO SUPORTE: Preço {distancia_suporte:.2f}% acima da Put Wall.")

    with col_alerta2:
        if status == "EXPANSÃO":
            st.warning("🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos/Vulnerabilidade)")
        else:
            st.info("🟢 REGIME ESTÁVEL: GAMA POSITIVO (Volatilidade Comprimida)")

    # --- HISTOGRAMA GEX (ESTILIZADO) ---
    st.subheader("📊 Perfil de Exposição Financeira (GEX por Strike)")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls (Gamma +)', marker_color='#00ffcc'))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts (Gamma -)', marker_color='#ff4b4b'))
    
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", line_width=2)
    fig_hist.update_layout(
        template="plotly_dark", 
        barmode='relative',
        xaxis=dict(title="Strike Price ($)", range=[current_price * 0.92, current_price * 1.08]),
        height=500
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- DICIONÁRIO ESTRATÉGICO ---
    st.divider()
    st.header("🧠 Dicionário Estratégico de Mercado")
    col_edu1, col_edu2 = st.columns(2)

    with col_edu1:
        st.markdown(f"""
        ### 🟢 SUPRESSÃO (Gama Positivo)
        **Cenário:** Preço ACIMA do Zero Gamma (${levels['zero']}).
        * **Mecânica:** Market Makers "amortecem" o mercado. Eles compram quando cai e vendem quando sobe.
        * **Expectativa:** Baixa volatilidade, tendência de alta lenta e gradual ("Grind up").
        
        ### 🧱 Put Wall (${levels['put']})
        * Onde reside a maior defesa dos Touros. Perder este nível pode acelerar quedas violentas.
        """)

    with col_edu2:
        st.markdown(f"""
        ### 🔴 EXPANSÃO (Gama Negativo)
        **Cenário:** Preço ABAIXO do Zero Gamma (${levels['zero']}).
        * **Mecânica:** Efeito cascata. Market Makers precisam vender conforme o preço cai para proteger suas posições.
        * **Expectativa:** Volatilidade alta, velas longas, "gaps" e movimentos erráticos.

        ### 🏰 Call Wall (${levels['call']})
        * O teto institucional. Nível onde investidores tendem a realizar lucros ou onde a pressão vendedora trava a alta.
        """)

else:
    st.error("Erro ao processar dados matemáticos. Verifique a conexão com o Yahoo Finance.")
