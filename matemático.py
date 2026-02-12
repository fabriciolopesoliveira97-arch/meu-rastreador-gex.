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
st_autorefresh(interval=60 * 1000, key="datarefresh")

# --- 2. FUNÇÕES MATEMÁTICAS ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

# --- 3. FUNÇÕES DE DADOS ---
@st.cache_data(ttl=300)
def get_gamma_data_v2(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        if df_hist.empty: return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
        
        S = df_hist['Close'].iloc[-1]
        vencimentos = tk.options
        if not vencimentos: return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()
            
        expiry_date = vencimentos[0]
        options = tk.option_chain(expiry_date)
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days + 1, 1) / 365.0
        r = 0.045 

        # FOCO TOTAL NA LIQUIDEZ: Reduzi a margem para 8% para limpar o "lixo" de strikes distantes
        margin = 0.08 
        calls = options.calls[(options.calls['strike'] > S*(1-margin)) & (options.calls['strike'] < S*(1+margin)) & (options.calls['openInterest'] > 5)].copy()
        puts = options.puts[(options.puts['strike'] > S*(1-margin)) & (options.puts['strike'] < S*(1+margin)) & (options.puts['openInterest'] > 5)].copy()

        calls['GEX'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01, axis=1)
        puts['GEX'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01 * -1, axis=1)
        
        return calls, puts, S, df_hist
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame()

def get_gamma_levels(calls, puts, S):
    if calls.empty or puts.empty: return {"zero": 0, "put": 0, "call": 0}
    
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    
    df_total = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    df_net = df_total.groupby('strike')['GEX'].sum().reset_index().sort_values('strike')
    
    # --- A "TRAVA DE SEGURANÇA" ---
    # Só aceitamos o Zero Gamma se ele estiver a menos de 1.5% de distância do preço atual
    # Isso impede que ele fuja para o 603 enquanto o preço está em 615
    df_focado = df_net[(df_net['strike'] >= S * 0.985) & (df_net['strike'] <= S * 1.015)]
    
    if df_focado.empty: # Se não houver nada no 1.5%, tentamos 3%
        df_focado = df_net[(df_net['strike'] >= S * 0.97) & (df_net['strike'] <= S * 1.03)]

    # Procura a inversão de sinal no miolo do preço
    df_focado['prev_GEX'] = df_focado['GEX'].shift(1)
    crossing = df_focado[((df_focado['GEX'] > 0) & (df_focado['prev_GEX'] < 0)) | 
                         ((df_focado['GEX'] < 0) & (df_focado['prev_GEX'] > 0))]
    
    if not crossing.empty:
        # Interpolação para achar o ponto exato
        idx = crossing.index[0]
        s1, g1 = df_focado.loc[idx-1, 'strike'], df_focado.loc[idx-1, 'GEX']
        s2, g2 = df_focado.loc[idx, 'strike'], df_focado.loc[idx, 'GEX']
        zero_gamma = s1 - g1 * (s2 - s1) / (g2 - g1)
    else:
        # Se não houver cruzamento, o strike mais equilibrado PERTO do preço
        zero_gamma = df_focado.iloc[(df_focado['GEX']).abs().argsort()[:1]]['strike'].values[0]
        
    return {"zero": round(zero_gamma, 2), "put": put_wall, "call": call_wall}

# --- 4. INTERFACE ---
ticker_symbol = st.sidebar.text_input("Ticker", value="QQQ").upper()
calls_data, puts_data, current_price, df_price = get_gamma_data_v2(ticker_symbol)

if not calls_data.empty and not puts_data.empty:
    levels = get_gamma_levels(calls_data, puts_data, current_price)
    
    # Cálculo de Força % para o Hover
    total_abs_gex = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['Força'] = (calls_data['GEX'] / total_abs_gex * 100).round(2)
    puts_data['Força'] = (puts_data['GEX'].abs() / total_abs_gex * 100).round(2)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    
    # STATUS DE CENÁRIO (Alertas das imagens)
    if current_price < levels['zero']:
        st.warning(f"🔥 ZONA DE EXPANSÃO (GAMA NEGATIVO) - Pivô Crítico: ${levels['zero']}")
    else:
        st.success(f"🛡️ ZONA DE SUPRESSÃO (GAMA POSITIVO) - Pivô de Suporte: ${levels['zero']}")

    # MÉTRICAS
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço Atual", f"${current_price:.2f}")
    c2.metric("Net GEX", f"{net_gex_total:.2f}M")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # HISTOGRAMA DE FORÇA
    st.subheader("📊 Histograma de Força Institucional (GEX)")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc',
                             hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>",
                             customdata=calls_data['Força']))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b',
                             hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>",
                             customdata=puts_data['Força']))
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", annotation_text=f"PREÇO: ${current_price:.2f}")
    fig_hist.update_layout(template="plotly_dark", barmode='relative', height=350, hovermode="x unified")
    st.plotly_chart(fig_hist, use_container_width=True)

    # GRÁFICO CANDLESTICK COM WALLS
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="PUT WALL")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="CALL WALL")
    fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

else:
    st.warning("Aguardando dados da API...")
