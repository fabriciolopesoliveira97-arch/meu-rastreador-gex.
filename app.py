import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# Configuração da página estilo Dark
st.set_page_config(page_title="GEX Tracker Nasdaq", layout="wide")

# Níveis institucionais (Conforme as imagens que você me enviou)
def get_gamma_levels():
    return {
        "zero": 602.24,
        "put": 600.17,
        "call": 610.00
    }

st.title("🛡️ Nasdaq 100 Institutional Tracker")
if st.button('🔄 Atualizar Dados'):
    st.rerun()
# Busca preço real do QQQ (Nasdaq ETF)
ticker = yf.Ticker("QQQ")
df = ticker.history(period="1d", interval="5m")
current_price = df['Close'].iloc[-1]
levels = get_gamma_levels()

# Lógica de Status (Supressão/Expansão)
status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
status_color = "#00f2ff" if status == "SUPRESSÃO" else "#ff4b4b"

# Exibição dos Cards Visuais
c1, c2, c3, c4 = st.columns(4)
c1.metric("Status Mercado", status)
c2.metric("Zero Gamma", f"${levels['zero']}")
c3.metric("Put Wall", f"${levels['put']}")
c4.metric("Call Wall", f"${levels['call']}")

st.markdown(f"### Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

# Gráfico de Preço com as Linhas
fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
fig.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
fig.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
fig.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")

fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)
