import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX Tracker Nasdaq", layout="wide")

# --- FUNÇÕES DE DADOS ---
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
ticker_name = "QQQ"
ticker = yf.Ticker(ticker_name)
df_price = ticker.history(period="1d", interval="5m")

if not df_price.empty:
    current_price = df_price['Close'].iloc[-1]
    calls_data, puts_data = get_gamma_data(ticker_name)
    levels = get_gamma_levels(calls_data, puts_data)

    # Cálculo Métrico
    net_gex_val = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    gex_delta_color = "normal" if net_gex_val >= 0 else "inverse"

    # --- INTERFACE: MÉTRICAS ---
    st.title(f"🛡️ {ticker_name} Institutional Tracker")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX Total", f"{net_gex_val:.2f}M", 
              delta=f"{'POSITIVO' if net_gex_val > 0 else 'NEGATIVO'}", 
              delta_color=gex_delta_color)
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # --- GRÁFICO CANDLESTICK ---
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
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
            st.success(f"🛡️ ACIMA DO SUPORTE: Preço {distancia_suporte:.2f}% acima da proteção.")

    with col_alerta2:
        if status == "EXPANSÃO":
            st.warning("🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)")
        else:
            st.info("🟢 REGIME ESTÁVEL: GAMA POSITIVO (Volatilidade Baixa)")

    # --- HISTOGRAMA GEX ---
    st.subheader("📊 Histograma de Gamma Exposure")
    total_abs = calls_data['GEX'].abs().sum() + puts_data['GEX'].abs().sum()
    calls_data['peso'] = (calls_data['GEX'].abs() / total_abs) * 100
    puts_data['peso'] = (puts_data['GEX'].abs() / total_abs) * 100

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc', 
                              customdata=calls_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b', 
                              customdata=puts_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    
    # Linha Spot no Histograma
    fig_hist.add_vline(x=current_price, line_dash="solid", line_color="yellow", line_width=3, layer="above")
    max_y = max(calls_data['GEX'].max(), puts_data['GEX'].abs().max())
    fig_hist.add_annotation(x=current_price, y=max_y, text=f"SPOT: ${current_price:.2f}", showarrow=True, arrowhead=2, bgcolor="yellow", font=dict(color="black"))

    fig_hist.update_layout(template="plotly_dark", barmode='relative', xaxis=dict(range=[current_price * 0.97, current_price * 1.03]), height=500)
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- SEÇÃO EDUCATIVA ---
    st.divider()
    with st.expander("📚 Dicionário de Indicadores Institucionais"):
        st.markdown("""
        ### 🧱 Put Wall (Parede de Puts)
        É o strike com a maior concentração de Gamma de Puts. Atua como o **suporte mais importante** do dia. Market Makers defendem este nível comprando o ativo.

        ### 🏰 Call Wall (Parede de Calls)
        É o strike com a maior concentração de Gamma de Calls. Atua como a **resistência principal**. Se rompida com volume, pode gerar um 'Gamma Squeeze'.

        ### ⚖️ Zero Gamma (Ponto de Inflexão)
        O divisor de águas entre o mercado calmo e o caos:
        * **Acima do Zero Gamma (Gama Positivo):** O mercado tende a ser estável e as quedas são compradas rapidamente (**Supressão de Volatilidade**).
        * **Abaixo do Zero Gamma (Gama Negativo):** O mercado entra em **Expansão de Volatilidade**. Os movimentos de queda são acelerados porque os Market Makers precisam vender para proteger suas posições.
        """)

else:
    st.error("Dados indisponíveis no momento.")
