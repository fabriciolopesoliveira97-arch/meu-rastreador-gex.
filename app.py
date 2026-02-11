import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX Tracker Nasdaq", layout="wide")

# --- FUNÇÕES DE DADOS (COM CACHE) ---
@st.cache_data(ttl=300)
def get_gamma_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        expiry = tk.options[0]
        options = tk.option_chain(expiry)
        calls = options.calls[['strike', 'openInterest', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'lastPrice']].copy()
        
        # Cálculo institucional: 1 contrato = 100 ações
        calls['GEX'] = calls['openInterest'] * calls['lastPrice'] * 100
        puts['GEX'] = puts['openInterest'] * puts['lastPrice'] * -100
        return calls, puts
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return pd.DataFrame(), pd.DataFrame()

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    put_wall = puts.iloc[puts['GEX'].abs().idxmax()]['strike']
    call_wall = calls.iloc[calls['GEX'].abs().idxmax()]['strike']
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- PROCESSAMENTO PRINCIPAL ---
ticker_symbol = "QQQ"
ticker = yf.Ticker(ticker_symbol)
df_price = ticker.history(period="1d", interval="5m")

if not df_price.empty:
    current_price = df_price['Close'].iloc[-1]
    calls_data, puts_data = get_gamma_data(ticker_symbol)
    levels = get_gamma_levels(calls_data, puts_data)

    # 1. Cálculos Métricos
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    # Define se o cenário é Supressão (Verde) ou Expansão (Vermelho)
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    status_color = "#00ffcc" if status == "SUPRESSÃO" else "#ff4b4b"

    # --- INTERFACE VISUAL: MÉTRICAS ---
    st.title(f"🛡️ {ticker_symbol} Institutional Tracker")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta=f"{net_gex_total:.2f}M", delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # --- MENSAGEM DE CENÁRIO ATUAL (IGUAL À IMAGEM) ---
    st.markdown(f"## Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

    # Gráfico de Preço (Candlestick)
    fig = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
    fig.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
    fig.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
    fig.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # Medidores de Alerta
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
            st.warning("🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos/Rápidos)")
        else:
            st.info("🟢 RISCO BAIXO: GAMA POSITIVO (Mercado Estável)")

    # --- HISTOGRAMA GEX ---
    st.subheader("📊 Histograma de Gamma Exposure")
    total_abs = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['peso'] = (calls_data['GEX'] / total_abs) * 100
    puts_data['peso'] = (puts_data['GEX'].abs() / total_abs) * 100

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls (Alta)', marker_color='#00ffcc', customdata=calls_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts (Baixa)', marker_color='#ff4b4b', customdata=puts_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="yellow", line_width=2)
    fig_hist.update_layout(template="plotly_dark", barmode='relative', hovermode="x unified", xaxis=dict(range=[current_price * 0.97, current_price * 1.03]), height=500, hoverlabel=dict(bgcolor="black", font_size=13))
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- SEÇÃO EDUCATIVA DETALHADA ---
    st.divider()
    with st.expander("📚 Entenda os Indicadores Institucionais (Dicionário Técnico)"):
        st.markdown("""
        ### 🧱 Put Wall (Parede de Puts)
        É o nível de preço onde existe a **maior concentração de Gamma de Puts**. No mercado financeiro, isso funciona como o **suporte psicológico e financeiro mais forte**. 
        * **Por que importa?** Quando o preço atinge esse nível, os *Market Makers* (grandes instituições) geralmente precisam comprar o ativo para proteger suas posições, o que tende a empurrar o preço para cima, criando um "piso".

        ### 🏰 Call Wall (Parede de Calls)
        É o strike com a **maior concentração de Gamma de Calls**. Representa a **resistência máxima** do dia ou período.
        * **Por que importa?** É o teto onde o mercado encontra dificuldade de subir. Se o preço ultrapassar esse nível com muita força, pode gerar um "Gamma Squeeze", forçando altas ainda mais rápidas.

        ### ⚖️ Zero Gamma (Ponto de Inflexão)
        É o ponto onde a exposição líquida dos Market Makers muda de sinal. Ele divide o mercado em dois estados de "humor":
        1. **Acima do Zero Gamma (Cenário de Supressão):** A volatilidade é baixa. O mercado se move devagar e as quedas são usadas como oportunidade de compra. É um ambiente "seguro".
        2. **Abaixo do Zero Gamma (Cenário de Expansão):** A volatilidade aumenta drasticamente. Os robôs institucionais começam a vender conforme o preço cai, o que acelera as quedas e gera movimentos explosivos e perigosos.

        ### 📊 Peso %
        Indica a relevância financeira de cada nível de preço. Strikes com pesos altos (ex: acima de 10%) são "ímãs" ou barreiras que o preço terá muita dificuldade de ignorar.
        """)
else:
    st.error("Não foi possível carregar os dados. Verifique a conexão com o Yahoo Finance.")
