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

    # Cálculos Métricos
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    status_color = "#00ffcc" if status == "SUPRESSÃO" else "#ff4b4b"

    # --- INTERFACE VISUAL ---
    st.title(f"🛡️ {ticker_symbol} Institutional Tracker")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M", delta=f"{net_gex_total:.2f}M", delta_color="normal" if net_gex_total > 0 else "inverse")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    st.markdown(f"## Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

    # Gráfico de Preço (Candlestick)
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
    fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

    # --- HISTOGRAMA GEX ---
    st.subheader("📊 Histograma de Gamma Exposure")
    total_abs = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['peso'] = (calls_data['GEX'] / total_abs) * 100
    puts_data['peso'] = (puts_data['GEX'].abs() / total_abs) * 100

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls (Alta)', marker_color='#00ffcc', 
                              customdata=calls_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts (Baixa)', marker_color='#ff4b4b', 
                              customdata=puts_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    
    # Linha e Etiqueta do Spot
    fig_hist.add_vline(x=current_price, line_dash="dash", line_color="yellow", line_width=2, layer="above")
    max_y = max(calls_data['GEX'].max(), puts_data['GEX'].abs().max())
    fig_hist.add_annotation(x=current_price, y=max_y * 1.05, text=f"Preço Spot: ${current_price:.2f}", 
                            showarrow=False, font=dict(color="white", size=12), bgcolor="rgba(0,0,0,0.5)")

    fig_hist.update_layout(template="plotly_dark", barmode='relative', hovermode="x unified", 
                          xaxis=dict(title="Strike Price ($)", range=[current_price * 0.97, current_price * 1.03]), height=500,
                          hoverlabel=dict(bgcolor="black", font_size=13))
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- SEÇÃO EDUCATIVA ESTRATÉGICA ---
    st.divider()
    st.header("🧠 Guia Estratégico: Como ler os Cenários")
    
    col_edu1, col_edu2 = st.columns(2)

    with col_edu1:
        st.markdown(f"""
        ### 🟢 SUPRESSÃO (Gama Positivo)
        **Quando ocorre:** O preço está **acima** do Zero Gamma (${levels['zero']}).
        * **Comportamento:** O mercado age como se estivesse "dentro de uma piscina". Os movimentos são lentos e amortecidos.
        * **Ação Institucional:** Market Makers vendem nas altas e compram nas baixas para manter o preço estável.
        * **Sentimento:** Quedas são geralmente curtas e vistas como oportunidade de compra (*Buy the Dip*).
        
        ### 🧱 Put Wall (${levels['put']})
        * É o suporte máximo. Se o preço chegar aqui, a pressão de compra institucional é enorme.
        """)

    with col_edu2:
        st.markdown(f"""
        ### 🔴 EXPANSÃO (Gama Negativo)
        **Quando ocorre:** O preço está **abaixo** do Zero Gamma (${levels['zero']}).
        * **Comportamento:** O mercado entra em "modo pânico". A volatilidade explode e o preço pode cair (ou subir) muito rápido.
        * **Ação Institucional:** Market Makers são forçados a vender conforme o preço cai, o que acelera a queda.
        * **Sentimento:** Medo e movimentos irracionais. Evite posições pesadas sem proteção.

        ### 🏰 Call Wall (${levels['call']})
        * É a resistência máxima. O preço tem muita dificuldade de passar desse nível, pois há muita venda institucional protegendo o topo.
        """)

    with st.expander("⚖️ O que é o Zero Gamma?"):
        st.info(f"""
        O **Zero Gamma** (${levels['zero']}) é o divisor de águas. Imagine que é a linha que separa o mar calmo de uma tempestade. 
        Sempre que o preço cruza essa linha para baixo, o risco de uma queda forte aumenta drasticamente porque o mercado perde seu "amortecedor" natural.
        """)

else:
    st.error("Dados indisponíveis.")
