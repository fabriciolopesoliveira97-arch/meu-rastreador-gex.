import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime
import pytz
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

# --- NOVA FUNÇÃO: OPTIONS INVENTORY ---
def render_options_inventory(calls_df, puts_df, current_price):
    st.markdown("---")
    st.subheader("📊 Options Inventory (Professional GEX Profile)")
    
    df_inv = pd.concat([calls_df, puts_df]).sort_values('strike')
    fig_inv = go.Figure()

    fig_inv.add_trace(go.Bar(
        y=df_inv['strike'],
        x=df_inv['GEX'],
        orientation='h',
        marker_color=np.where(df_inv['GEX'] > 0, '#00ffcc', '#ff4b4b'),
        name='Exposição Gamma',
        hovertemplate="Strike: %{y}<br>GEX: %{x:,.0f}<extra></extra>"
    ))

    fig_inv.add_hline(
        y=current_price, 
        line_dash="dot", 
        line_color="yellow", 
        line_width=2,
        annotation_text=f"SPOT: {current_price:.2f}",
        annotation_position="top right"
    )

    fig_inv.update_layout(
        template="plotly_dark",
        height=800,
        xaxis_title="← VENDA (Short Gamma) | COMPRA (Long Gamma) →",
        yaxis_title="Strike Price ($)",
        hovermode="y unified",
        xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.05)', dtick=1)
    )
    st.plotly_chart(fig_inv, use_container_width=True)

# --- 4. INTERFACE ---
st.title("GEX PRO - Real Time")
ticker_symbol = st.sidebar.text_input("Ticker", value="QQQ").upper()
calls_data, puts_data, current_price, df_price, current_expiry = get_gamma_data_v2(ticker_symbol)

if current_expiry:
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_br)
    now_time = agora.strftime("%H:%M:%S")
    now_date = agora.strftime("%d/%m/%Y") 
    st.info(f"🕒 **Atualizado em:** {now_date} às {now_time} | 📅 **Vencimento:** {current_expiry} | 🔍 **Ticker:** {ticker_symbol}")

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
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta="Positivo" if net_gex_total > 0 else "Negativo", delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    st.markdown(f"### Cenário Atual: **{'SUPRESSÃO' if current_price > levels['zero'] else 'EXPANSÃO'}**")

    col_main, col_side = st.columns([7, 3])

    with col_main:
        # 1. Histograma Original
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc', hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>", customdata=calls_data['Força']))
        fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b', hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>", customdata=puts_data['Força']))
        fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", annotation_text=f"SPOT: ${current_price:.2f}")
        
        all_gex = pd.concat([calls_data['GEX'], puts_data['GEX'].abs()])
        limit_y = all_gex.quantile(0.95) * 1.5
        fig_hist.update_layout(template="plotly_dark", barmode='relative', height=350, hovermode="x unified", yaxis=dict(range=[-limit_y, limit_y]), margin=dict(t=10, b=10))
        st.plotly_chart(fig_hist, use_container_width=True)

        # 2. Candlestick Original
        fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
        fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
        fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="PUT WALL")
        fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="CALL WALL")
        fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_candle, use_container_width=True)

        # 3. CHAMADA DO NOVO INDICADOR (OPTIONS INVENTORY)
        render_options_inventory(calls_data, puts_data, current_price)

    with col_side:
        st.subheader("Maiores Mudanças de GEX")
        all_data = pd.concat([calls_data[['strike', 'GEX']], puts_data[['strike', 'GEX']]])
        changes = all_data.groupby('strike')['GEX'].sum().sort_values(key=abs, ascending=False).head(15)
        for strike, val in changes.items():
            color = "#00ffcc" if val > 0 else "#ff4b4b"
            col_s1, col_s2 = st.columns([1, 1])
            col_s1.write(f"**${strike:.2f}**")
            col_s2.markdown(f"<span style='color:{color}'>{val/10**6:,.2f}M</span>", unsafe_allow_html=True)
else:
    st.warning("Aguardando dados... Verifique se o mercado está aberto.")

# --- 5. GUIA DE OPERAÇÃO PROFISSIONAL ---
st.divider()
with st.expander("📖 GUIA GEX PRO: Domine a Dinâmica do Mercado"):
    st.markdown("""
    Este aplicativo monitora a **Exposição de Gama (GEX)** dos Market Makers (MM). O comportamento deles para proteger suas posições é o que move o preço nos pontos críticos.

    ### 🟢 1. As Métricas Principais (Top Bar)
    * **Net GEX:** É o saldo total de Gama. 
        * **Positivo (Verde):** MM seguram o preço. Volatilidade baixa.
        * **Negativo (Vermelho):** MM vendem na queda e compram na alta. Volatilidade explosiva.
    * **Zero Gamma (O Pivô):** A "fronteira". Abaixo dele, o mercado entra em modo de pânico/aceleração. Acima dele, o mercado tende a ser calmo.
    * **Put Wall & Call Wall:** São os limites psicológicos e técnicos. A Put Wall é o "chão de ferro" e a Call Wall é o "teto de vidro".

    ### 📊 2. Options Inventory (Barras Horizontais)
    * **Lado Direito (Compra/Long Gamma):** Zonas de liquidez compradora. Se o preço está acima, funcionam como suporte imã.
    * **Lado Esquerdo (Venda/Short Gamma):** Zonas onde o MM precisa vender para se proteger. Se o preço rompe um nível aqui, ele tende a acelerar rápido para o próximo strike de volume (vácuo de liquidez).
    * **Polaridade:** Se o preço passa de um strike e volta, a função de suporte/resistência inverte devido ao ajuste de hedge do MM.

    ### 🕯️ 3. Candlestick & Níveis GEX
    * Aqui você vê o preço em tempo real cruzando as linhas de **Zero Gamma**, **Put Wall** e **Call Wall**.
    * **Trade de Reversão:** Se o preço toca a Put Wall em cenário de Gama Positivo, há alta probabilidade de repique.
    * **Trade de Rompimento:** Se o preço perde o Zero Gamma com Net GEX negativo, o movimento tende a ser rápido e forte para baixo.

    ---
    **Resumo do Sentimento:**
    * **SPOT > Zero Gamma:** Buy the Dip (Compre a correção).
    * **SPOT < Zero Gamma:** Sell the Rally (Venda o repique).
    """)

st.caption("Dados via Yahoo Finance (BS Model). Atualização automática a cada 60s.")
