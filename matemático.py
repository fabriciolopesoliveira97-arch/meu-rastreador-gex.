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
        
        # Limpeza de outliers para não distorcer o histograma
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

# --- 4. INTERFACE ---
st.title("GEX PRO - Real Time")
ticker_symbol = st.sidebar.text_input("Ticker", value="QQQ").upper()
calls_data, puts_data, current_price, df_price, current_expiry = get_gamma_data_v2(ticker_symbol)

if current_expiry:
    now = datetime.now().strftime("%H:%M:%S")
    st.info(f"🕒 **Última Atualização:** {now} | 📅 **Vencimento Analisado:** {current_expiry} | 🔍 **Ticker:** {ticker_symbol}")

if not calls_data.empty and not puts_data.empty:
    levels = get_gamma_levels(calls_data, puts_data, current_price)
    
    total_abs_gex = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['Força'] = (calls_data['GEX'] / total_abs_gex * 100).round(2)
    puts_data['Força'] = (puts_data['GEX'].abs() / total_abs_gex * 100).round(2)
    
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    
    if current_price < levels['put']:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']})")
    if current_price < levels['zero']:
        st.warning(f"🔥 RISCO: GAMA NEGATIVO - Nível Crítico: ${levels['zero']}")
    else:
        st.success(f"✅ ESTABILIDADE: GAMA POSITIVO - Pivô: ${levels['zero']}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço Atual", f"${current_price:.2f}")
    c2.metric(
        "Net GEX", 
        f"{net_gex_total:.2f}M", 
        delta="Positivo" if net_gex_total > 0 else "Negativo",
        delta_color="normal" if net_gex_total > 0 else "inverse"
    )
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    st.markdown(f"### Cenário Atual: **{'SUPRESSÃO' if current_price > levels['zero'] else 'EXPANSÃO'}**")

    # --- NOVO LAYOUT COM INDICADOR LATERAL ---
    col_main, col_side = st.columns([7, 3])

    with col_main:
        # HISTOGRAMA COM ESCALA CORRIGIDA
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc',
                                 hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>",
                                 customdata=calls_data['Força']))
        fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b',
                                 hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>",
                                 customdata=puts_data['Força']))
        fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", annotation_text=f"SPOT: ${current_price:.2f}")
        
        all_gex = pd.concat([calls_data['GEX'], puts_data['GEX'].abs()])
        limit_y = all_gex.quantile(0.95) * 1.5
        
        fig_hist.update_layout(
            template="plotly_dark", barmode='relative', height=350, hovermode="x unified",
            yaxis=dict(range=[-limit_y, limit_y]), margin=dict(t=10, b=10)
        )
        st.plotly_chart(fig_hist, use_container_width=True)

        fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
        fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
        fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="PUT WALL")
        fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="CALL WALL")
        fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_candle, use_container_width=True)

    with col_side:
        # INDICADOR: MAIORES MUDANÇAS DE GEX (Conforme imagem enviada)
        st.subheader("Maiores Mudanças de GEX")
        
        # Consolidando dados de Calls e Puts por Strike
        df_total = pd.concat([calls_data[['strike', 'GEX']], puts_data[['strike', 'GEX']]])
        df_sum = df_total.groupby('strike')['GEX'].sum().reset_index()
        
        # Ordenando pelos maiores valores absolutos (mais relevantes)
        df_top_changes = df_sum.sort_values(by='GEX', key=abs, ascending=False).head(10)
        
        # Estilização da Tabela
        for _, row in df_top_changes.iterrows():
            strike_val = f"${row['strike']:.2f}"
            gex_val = row['GEX'] / 10**6
            color = "#00ffcc" if gex_val > 0 else "#ff4b4b"
            
            # Criando linhas formatadas para parecer com a imagem
            c_s1, c_s2, c_s3 = st.columns([2, 3, 1])
            c_s1.write(f"**{strike_val}**")
            c_s2.markdown(f"<span style='color:{color}; font-weight:bold;'>{'+' if gex_val > 0 else ''}{gex_val:.2f}M</span>", unsafe_allow_html=True)
            c_s3.write("1d")
            st.divider()

else:
    st.warning("Aguardando dados... Verifique se o mercado está aberto.")

# --- 5. GUIA DE OPERAÇÃO DETALHADO ---
st.divider()
with st.expander("📖 GUIA GEX PRO: Como interpretar as métricas e o cenário"):
    st.markdown("""
    ### 🚦 Indicadores de Topo (Métricas)
    
    * **Net GEX (Exposição Líquida):** É a soma de todo o Gama do mercado. 
        * **Verde (Positivo):** Indica que o mercado está "protegido". Os Market Makers tendem a segurar a volatilidade.
        * **Vermelho (Negativo):** Indica que o mercado está "desprotegido". O risco de quedas rápidas e vácuos de liquidez é alto.
        
    * **Zero Gamma (O Pivô):** É a linha divisória do dia. 
        * Se o preço está **acima**, você está em águas calmas.
        * Se o preço está **abaixo**, você está em águas perigosas (Zona de Expansão).
        
    * **Call Wall & Put Wall:** * **Call Wall:** O "teto" onde a resistência é máxima. Raramente o preço rompe este nível sem um evento muito forte.
        * **Put Wall:** O "chão" técnico. Se o preço cair abaixo disso, o pânico pode acelerar pois os Market Makers precisam vender agressivamente para se proteger.

    ---

    ### 📊 O Gráfico de Barras (Histograma)
    
    * **Barras Verdes (Calls):** Mostram onde os investidores estão otimistas. Quanto maior a barra, mais forte aquele strike atua como um "ímã" que impede o preço de disparar descontroladamente (Resistência).
    * **Barras Vermelhas (Puts):** Mostram onde está a proteção contra quedas. Se as barras de Puts forem muito maiores que as de Calls, a pressão vendedora no dia é dominante.
    * **Força %:** No hover (ao passar o mouse), você vê o peso de cada strike. Strikes com força > 10% dominam a movimentação do dia.

    ---

    ### 🗺️ Definição dos Cenários
    
    * **Cenário de SUPRESSÃO (Preço > Zero Gamma):** * Os Market Makers compram quando cai e vendem quando sobe. 
        * **O que esperar:** Movimentos lentos, reversão à média, dias de "range" lateral. É o cenário ideal para quem vende opções ou faz operações de tiro curto.
        
    * **Cenário de EXPANSÃO (Preço < Zero Gamma):** * Os Market Makers vendem quando cai e compram quando sobe (Hedge Dinâmico). Isso "alimenta" o movimento do preço.
        * **O que esperar:** Volatilidade alta, tendências fortes de queda, movimentos bruscos. É aqui que ocorrem os "Flash Crashes".

    ---
    *Dica: Se o Preço Atual estiver exatamente sobre o Zero Gamma, o mercado está em um momento de decisão. O lado que vencer (rompimento para cima ou para baixo) ditará a direção das próximas horas.*
    """)

st.caption("Dados baseados no modelo Black-Scholes. Atualização via Yahoo Finance. Use para fins educacionais.")
