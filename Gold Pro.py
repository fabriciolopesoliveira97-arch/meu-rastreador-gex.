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
st.set_page_config(page_title="GEX PRO Gold - Real Time", layout="wide")
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
    except Exception as e:
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
st.title("GEX PRO Gold - Real Time 🏆")

# Novos inputs na barra lateral para o sistema de conversão
st.sidebar.header("⚙️ Configurações de Escala")
ticker_symbol = st.sidebar.text_input("Ticker Opções (Liquidez)", value="GLD").upper()
spot_ticker = st.sidebar.text_input("Ticker Spot (Referência)", value="XAUUSD=X").upper()
converter_escala = st.sidebar.checkbox("Sincronizar com gráfico do celular (Spot)", value=True)

calls_data, puts_data, current_price, df_price, current_expiry = get_gamma_data_v2(ticker_symbol)

if current_expiry and not calls_data.empty and not puts_data.empty:
    
    # --- SISTEMA DE CONVERSÃO SPOT ---
    multiplier = 1.0
    if converter_escala:
        try:
            tk_spot = yf.Ticker(spot_ticker)
            spot_hist = tk_spot.history(period="1d", interval="5m")
            if spot_hist.empty: 
                spot_hist = tk_spot.history(period="1d")
            
            if not spot_hist.empty:
                spot_price = spot_hist['Close'].iloc[-1]
                multiplier = spot_price / current_price
                st.sidebar.success(f"Conversão Ativa! Escala multiplicada por: {multiplier:.2f}x")
            else:
                st.sidebar.warning("Sem dados do Spot. Usando escala padrão.")
        except:
            st.sidebar.error("Erro ao buscar Spot. Verifique o ticker.")
            
    # Escalonando os dados
    current_price = current_price * multiplier
    calls_data['strike'] = calls_data['strike'] * multiplier
    puts_data['strike'] = puts_data['strike'] * multiplier
    df_price['Open'] = df_price['Open'] * multiplier
    df_price['High'] = df_price['High'] * multiplier
    df_price['Low'] = df_price['Low'] * multiplier
    df_price['Close'] = df_price['Close'] * multiplier

    # Calculando os níveis já com a escala ajustada
    levels = get_gamma_levels(calls_data, puts_data, current_price)
    
    fuso_br = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso_br)
    now_time = agora.strftime("%H:%M:%S")
    now_date = agora.strftime("%d/%m/%Y") 
    st.info(f"🕒 **Atualizado em:** {now_date} às {now_time} | 📅 **Vencimento das Opções:** {current_expiry} | 🔍 **Ativo Foco:** {spot_ticker if converter_escala else ticker_symbol}")
    
    total_abs_gex = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['Força'] = (calls_data['GEX'] / total_abs_gex * 100).round(2)
    puts_data['Força'] = (puts_data['GEX'].abs() / total_abs_gex * 100).round(2)
    
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    
    if current_price < levels['put']:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']:.2f})")
    if current_price < levels['zero']:
        st.warning(f"🔥 RISCO: GAMA NEGATIVO - Nível Crítico: ${levels['zero']:.2f}")
    else:
        st.success(f"✅ ESTABILIDADE: GAMA POSITIVO - Pivô: ${levels['zero']:.2f}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço Atual", f"${current_price:.2f}")
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta="Positivo" if net_gex_total > 0 else "Negativo", delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']:.2f}")
    c4.metric("Put Wall", f"${levels['put']:.2f}")
    c5.metric("Call Wall", f"${levels['call']:.2f}")

    st.divider()
    if net_gex_total > 0 and current_price > levels['zero']:
        prob_desc = "ALTA (Estabilidade no Ouro)"
        sentimento = "Os Market Makers estão provendo suporte. O cenário favorece a continuidade da alta ou lateralização."
        cor_alerta = "success"
    elif net_gex_total < 0 and current_price < levels['zero']:
        prob_desc = "BAIXA (Aceleração de Queda)"
        sentimento = "O ouro entrou em 'Gamma Negativo'. Há risco de vendas automáticas acelerarem correções de preço."
        cor_alerta = "error"
    elif current_price < levels['zero'] and net_gex_total > 0:
        prob_desc = "RECUPERAÇÃO (Transição)"
        sentimento = "O preço está em zona perigosa, mas o saldo total de Gamma ainda é positivo. Chance de repique no curto prazo."
        cor_alerta = "warning"
    else:
        prob_desc = "NEUTRA / INDEFINIDA"
        sentimento = "O mercado está testando níveis críticos. Aguarde o distanciamento do Zero Gamma para confirmar a tendência."
        cor_alerta = "info"

    st.subheader("🎯 Análise Probabilística de Curto Prazo")
    if cor_alerta == "success": st.success(f"**Direção Provável:** {prob_desc}\n\n{sentimento}")
    elif cor_alerta == "error": st.error(f"**Direção Provável:** {prob_desc}\n\n{sentimento}")
    elif cor_alerta == "warning": st.warning(f"**Direção Provável:** {prob_desc}\n\n{sentimento}")
    else: st.info(f"**Direção Provável:** {prob_desc}\n\n{sentimento}")

    st.markdown(f"### Cenário Atual: **{'SUPRESSÃO (Baixa Volatilidade)' if current_price > levels['zero'] else 'EXPANSÃO (Alta Volatilidade)'}**")

    col_main, col_side = st.columns([7, 3])

    with col_main:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#ffd700', hovertemplate="Strike: %{x:.2f}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>", customdata=calls_data['Força']))
        fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b', hovertemplate="Strike: %{x:.2f}<br>GEX: %{y:,.0f}<br>Força: %{customdata}%<extra></extra>", customdata=puts_data['Força']))
        fig_hist.add_vline(x=current_price, line_dash="dash", line_color="white", annotation_text=f"SPOT: ${current_price:.2f}")
        
        all_gex = pd.concat([calls_data['GEX'], puts_data['GEX'].abs()])
        limit_y = all_gex.quantile(0.95) * 1.5
        fig_hist.update_layout(template="plotly_dark", barmode='relative', height=350, hovermode="x unified", yaxis=dict(range=[-limit_y, limit_y]), margin=dict(t=10, b=10))
        st.plotly_chart(fig_hist, use_container_width=True)

        fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'], name="Preço")])
        fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="ZERO GAMMA")
        fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="PUT WALL")
        fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="CALL WALL")
        fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_candle, use_container_width=True)

    with col_side:
        st.subheader("Maiores Mudanças de GEX")
        all_data = pd.concat([calls_data[['strike', 'GEX']], puts_data[['strike', 'GEX']]])
        changes = all_data.groupby('strike')['GEX'].sum().sort_values(key=abs, ascending=False).head(15)
        for strike, val in changes.items():
            color = "#ffd700" if val > 0 else "#ff4b4b"
            col_s1, col_s2 = st.columns([1, 1])
            col_s1.write(f"**${strike:.2f}**")
            col_s2.markdown(f"<span style='color:{color}'>{val/10**6:,.2f}M</span>", unsafe_allow_html=True)
else:
    st.warning("Aguardando dados... Verifique se o mercado está aberto ou se o ticker possui opções líquidas.")

# --- 5. GUIA DE OPERAÇÃO PROFISSIONAL ---
st.divider()
with st.expander("📖 GUIA GEX PRO: Como Ler e Operar os Dados de Ouro"):
    st.markdown("""
    ### 🧠 O que é GEX (Gamma Exposure) no Ouro?
    O GEX mede a exposição dos **Market Makers (MM)** que fornecem liquidez para as opções de ouro. Para se manterem neutros, eles precisam comprar ou vender o ativo conforme o preço se move. O comportamento deles dita o ritmo do mercado de metais preciosos no curto prazo.

    ---

    ### 🟢 1. Indicadores do Topo (Métricas em Tempo Real)
    * **Preço Atual (SPOT):** O valor sincronizado com seu gráfico de negociação.
    * **Net GEX:** O saldo total de exposição.
        * **Positivo (Verde):** O mercado está em "Zona de Estabilidade". MM compram quedas e vendem altas, reduzindo a volatilidade.
        * **Negativo (Vermelho):** O mercado está em "Zona de Aceleração". MM vendem quedas e compram altas, gerando movimentos rápidos e explosivos no ouro.
    * **Zero Gamma (O Divisor de Águas):** É o preço onde o sentimento muda. Acima dele é alta probabilidade de calma; abaixo dele é alta probabilidade de pânico/volatilidade.
    * **Put Wall (Muralha de Puts):** O strike com maior exposição negativa. Funciona como o suporte mais forte do dia para o ouro.
    * **Call Wall (Muralha de Calls):** O strike com maior exposição positiva. Funciona como a resistência principal.
    """)

st.caption("Dados de Opções via GLD convertidos para a escala de Ouro Spot. Atualização automática a cada 60s.")
