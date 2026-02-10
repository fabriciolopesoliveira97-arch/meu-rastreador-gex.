import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# Configuração da página estilo Dark
st.set_page_config(page_title="GEX Tracker Nasdaq", layout="wide")

def get_gamma_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        expiry = tk.options[0]
        options = tk.option_chain(expiry)
        calls = options.calls[['strike', 'openInterest', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'lastPrice']].copy()
        
        calls['GEX'] = calls['openInterest'] * calls['lastPrice'] * 0.1
        puts['GEX'] = puts['openInterest'] * puts['lastPrice'] * -0.1
        return calls, puts
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

def get_gamma_levels():
    try:
        calls, puts = get_gamma_data("QQQ")
        if calls.empty or puts.empty:
            return {"zero": 602.24, "put": 600.17, "call": 610.00}
            
        # Calcula Net GEX por strike para achar o Zero Gamma
        df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
        df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
        
        # Acha o ponto onde a soma dos Gammas cruza o zero
        zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
        
        # Acha as maiores concentrações (Walls)
        put_wall = puts.iloc[puts['GEX'].abs().idxmax()]['strike']
        call_wall = calls.iloc[calls['GEX'].abs().idxmax()]['strike']
        
        return {"zero": zero_gamma, "put": put_wall, "call": call_wall}
    except:
        # Valores de segurança caso a bolsa esteja fechada
        return {"zero": 602.24, "put": 600.17, "call": 610.00}

st.title("🛡️ Nasdaq 100 Institutional Tracker")
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
# Abaixo do seu st.plotly_chart(fig, ...) na linha 46
st.markdown(f"### Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

# Gráfico de Preço com as Linhas
fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
fig.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
fig.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
fig.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")

fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)
with st.expander("📖 Como interpretar este Monitor"):
        st.markdown("""
        ### 🛡️ O que é Supressão vs Expansão?
        * **SUPRESSÃO (Gama Positiva):** O mercado tende a ficar calmo e lateral.
        * **EXPANSÃO (Gama Negativa):** Alerta de volatilidade! Movimentos rápidos.

        ### 🎯 Entendendo os Alvos:
        * **Gama Zero:** É o divisor de águas entre a calmaria e o pânico.
        * **Put Wall:** Funciona como um 'chão' (suporte institucional).
        * **Call Wall:** Funciona como um 'teto' (resistência institucional).
        """)
st.divider()
st.subheader("📊 Histograma de Gamma Exposure")

try:
    # Chamando os dados
    calls_data, puts_data = get_gamma_data('QQQ')
    
    # Cálculo de Força Total para a porcentagem
    total_gex = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    
    fig_hist = go.Figure()

    # Barras de Calls (Verde)
    fig_hist.add_trace(go.Bar(
        x=calls_data['strike'],
        y=calls_data['GEX'],
        name='Calls (Alta)',
        marker_color='#00ffcc',
        customdata=calls_data['GEX'] / total_gex * 100,
        hovertemplate="<b>Strike: %{x}</b><br>Peso: %{customdata:.2f}%<extra></extra>"
    ))

    # Barras de Puts (Vermelho)
    fig_hist.add_trace(go.Bar(
        x=puts_data['strike'],
        y=puts_data['GEX'],
        name='Puts (Baixa)',
        marker_color='#ff4b4b',
        customdata=puts_data['GEX'].abs() / total_gex * 100,
        hovertemplate="<b>Strike: %{x}</b><br>Peso: %{customdata:.2f}%<extra></extra>"
    ))

    # Ajuste do Layout e Zoom
    fig_hist.update_layout(
        template="plotly_dark", 
        barmode='relative',
        xaxis_title="Strike Price ($)",
        yaxis_title="GEX Estimado",
        height=500,
        xaxis=dict(range=[current_price * 0.95, current_price * 1.05]),
        hovermode="x unified"
    )
    
       # Linha do Preço Atual (SPOT)
    fig_hist.add_vline(
        x=current_price, 
        line_width=3, 
        line_dash="dash", 
        line_color="yellow",
        annotation_text=f"Preço Spot: ${current_price:.2f}",
        annotation_position="top left"
    )

    st.plotly_chart(fig_hist, 
use_container_width=True)
except Exception as e:
    st.info(f"Aguardando dados... {e}")
