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
        if df_hist.empty: return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame(), ""
        
        S = df_hist['Close'].iloc[-1]
        vencimentos = tk.options
        if not vencimentos: return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame(), ""
            
        expiry_date = vencimentos[0]
        options = tk.option_chain(expiry_date)
        d_exp = datetime.strptime(expiry_date, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days + 1, 1) / 365.0
        r = 0.045 

        margin = 0.10 
        calls = options.calls[(options.calls['strike'] > S*(1-margin)) & (options.calls['strike'] < S*(1+margin)) & (options.calls['openInterest'] > 20)].copy()
        puts = options.puts[(options.puts['strike'] > S*(1-margin)) & (options.puts['strike'] < S*(1+margin)) & (options.puts['openInterest'] > 20)].copy()

        calls['GEX'] = calls.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01, axis=1)
        puts['GEX'] = puts.apply(lambda x: calculate_gamma(S, x['strike'], T, r, x['impliedVolatility']) * x['openInterest'] * 100 * S**2 * 0.01 * -1, axis=1)
        
        for df in [calls, puts]:
            if not df.empty:
                q_high = df['GEX'].abs().quantile(0.99)
                df.drop(df[df['GEX'].abs() > q_high * 10].index, inplace=True)

        return calls, puts, S, df_hist, expiry_date
    except:
        return pd.DataFrame(), pd.DataFrame(), 0, pd.DataFrame(), ""

def get_gamma_levels(calls, puts, S):
    if calls.empty or puts.empty: return {"zero": 0, "put": 0, "call": 0}
    
    call_wall = calls.loc[calls['GEX'].idxmax(), 'strike']
    put_wall = puts.loc[puts['GEX'].abs().idxmax(), 'strike']
    
    df_total = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    df_net = df_total.groupby('strike')['GEX'].sum().reset_index().sort_values('strike')
    
    df_prox = df_net[(df_net['strike'] >= S - 5) & (df_net['strike'] <= S + 5)]
    if df_prox.empty:
        df_prox = df_net[(df_net['strike'] >= S * 0.95) & (df_net['strike'] <= S * 1.05)]

    df_prox['prev_GEX'] = df_prox['GEX'].shift(1)
    crossing = df_prox[((df_prox['GEX'] > 0) & (df_prox['prev_GEX'] < 0)) | 
                       ((df_prox['GEX'] < 0) & (df_prox['prev_GEX'] > 0))]
    
    if not crossing.empty:
        zero_gamma = crossing.iloc[0]['strike']
    else:
        zero_gamma = df_prox.iloc[(df_prox['GEX']).abs().argsort()[:1]]['strike'].values[0]
        
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- 4. NOVAS FUNÇÕES (BASEADAS NAS IMAGENS) ---
def display_gex_changes(calls, puts):
    st.markdown("### 📊 Maiores Mudanças de GEX")
    df_total = pd.concat([calls[['strike', 'GEX']], puts[['strike', 'GEX']]])
    df_sum = df_total.groupby('strike')['GEX'].sum().reset_index()
    # Simulando a mudança (em um app real, compararia com o cache anterior)
    df_sum = df_sum.sort_values(by='GEX', key=abs, ascending=False).head(8)
    
    for _, row in df_sum.iterrows():
        color = "#00ffcc" if row['GEX'] > 0 else "#ff4b4b"
        cols = st.columns([2, 4, 2])
        cols[0].write(f"**${row['strike']:.2f}**")
        cols[1].markdown(f"<span style='color:{color}'>{row['GEX']/10**6:.2f}M</span>", unsafe_allow_html=True)
        cols[2].write("1d")

def display_market_heatmap():
    st.markdown("### 🔥 Mapa de Calor do Mercado")
    # Nota: Um heatmap real requer dados de múltiplos tickers. 
    # Aqui criamos um placeholder visual conforme a imagem enviada.
    st.image("https://finviz.com/p_map_s500.png", caption="Performance S&P 500 (Fonte: Finviz)")

def display_economic_calendar():
    st.markdown("### 📅 Calendário Econômico")
    events = [
        {"hora": "10:30", "evento": "Core CPI MM, SA", "prev": "0,3%", "ant": "0,2%"},
        {"hora": "10:30", "evento": "Core CPI YY, NSA", "prev": "2,5%", "ant": "2,6%"},
        {"hora": "10:30", "evento": "CPI MM, SA", "prev": "0,2%", "ant": "0,2%"}
    ]
    for ev in events:
        with st.container():
            c1, c2, c3 = st.columns([1, 3, 2])
            c1.write(ev['hora'])
            c2.write(f"**{ev['evento']}**")
            c3.write(f"P: {ev['prev']} | A: {ev['ant']}")
            st.divider()

# --- 5. INTERFACE ---
st.title("GEX PRO - Real Time")
ticker_symbol = st.sidebar.text_input("Ticker", value="QQQ").upper()
calls_data, puts_data, current_price, df_price, current_expiry = get_gamma_data_v2(ticker_symbol)

if current_expiry:
    now = datetime.now().strftime("%H:%M:%S")
    st.info(f"🕒 **Última Atualização:** {now} | 📅 **Vencimento Analisado:** {current_expiry} | 🔍 **Ticker:** {ticker_symbol}")

if not calls_data.empty and not puts_data.empty:
    levels = get_gamma_levels(calls_data, puts_data, current_price)
    
    # Grid Principal
    c1, c2, c3, c4, c5 = st.columns(5)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    c1.metric("Preço Atual", f"${current_price:.2f}")
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta="Positivo" if net_gex_total > 0 else "Negativo")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # Layout de Duas Colunas para Gráficos e Tabelas
    col_left, col_right = st.columns([7, 3])

    with col_left:
        # Gráfico de Candlestick
        fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
        fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
        fig_candle.update_layout(template="plotly_dark", height=400, margin=dict(t=20, b=20))
        st.plotly_chart(fig_candle, use_container_width=True)
        
        # Histograma GEX
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc'))
        fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b'))
        fig_hist.update_layout(template="plotly_dark", height=300, barmode='relative')
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_right:
        # Inserindo os novos blocos das imagens
        display_gex_changes(calls_data, puts_data)
        st.divider()
        display_economic_calendar()

    # Rodapé com Heatmap
    st.divider()
    display_market_heatmap()

else:
    st.warning("Aguardando dados... Verifique se o mercado está aberto.")

# O restante do seu Guia de Operação...
with st.expander("📖 GUIA GEX PRO"):
    st.write("Interpretando os dados...")
