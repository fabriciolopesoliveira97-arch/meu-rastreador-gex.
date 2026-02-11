import os
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GEX Tracker Nasdaq", layout="wide")

# --- FUNÇÕES DE DADOS (COM CACHE) ---
@st.cache_data(ttl=300)  # Atualiza os dados a cada 5 minutos
def get_gamma_data(ticker_symbol):
    try:
        tk = yf.Ticker(ticker_symbol)
        # Pega o vencimento mais próximo (0DTE ou o próximo disponível)
        expiry = tk.options[0]
        options = tk.option_chain(expiry)
        calls = options.calls[['strike', 'openInterest', 'lastPrice']].copy()
        puts = options.puts[['strike', 'openInterest', 'lastPrice']].copy()
        
        # AJUSTE DE CÁLCULO: 
        # Cada contrato representa 100 ações. 
        # O GEX nominal é calculado como Open Interest * Last Price * 100.
        # Puts têm sinal negativo pois representam delta negativo para o Market Maker.
        calls['GEX'] = calls['openInterest'] * calls['lastPrice'] * 100
        puts['GEX'] = puts['openInterest'] * puts['lastPrice'] * -100
        
        return calls, puts
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return pd.DataFrame(), pd.DataFrame()

def salvar_historico(p_price, p_gex, p_levels):
    arquivo = 'historico_gex.csv'
    data_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    nova_linha = pd.DataFrame([{
        'Data': data_hora,
        'Preço': p_price,
        'NetGEX': p_gex,
        'ZeroGamma': p_levels['zero'],
        'PutWall': p_levels['put'],
        'CallWall': p_levels['call']
    }])
    
    if not os.path.isfile(arquivo):
        nova_linha.to_csv(arquivo, index=False)
    else:
        df_existente = pd.read_csv(arquivo)
        if not df_existente.empty:
            ultima_data = df_existente['Data'].iloc[-1]
            if ultima_data[:16] == data_hora[:16]:
                return
        nova_linha.to_csv(arquivo, mode='a', header=False, index=False)

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        # Fallback para valores aproximados caso o fetch falhe
        return {"zero": 602.24, "put": 600.17, "call": 610.00}

    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    
    # Zero Gamma: Onde a soma de GEX Calls e Puts é mais próxima de 0
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    
    # Put Wall: Strike com maior concentração de GEX em Puts (Suporte)
    put_wall = puts.iloc[puts['GEX'].abs().idxmax()]['strike']
    
    # Call Wall: Strike com maior concentração de GEX em Calls (Resistência)
    call_wall = calls.iloc[calls['GEX'].abs().idxmax()]['strike']
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- PROCESSAMENTO PRINCIPAL ---
st.title("🛡️ Nasdaq 100 Institutional Tracker")

# 1. Coleta de Preço e Dados de Opções
ticker = yf.Ticker("QQQ")
df_price = ticker.history(period="1d", interval="5m")
current_price = df_price['Close'].iloc[-1]

calls_data, puts_data = get_gamma_data("QQQ")
levels = get_gamma_levels(calls_data, puts_data)

# 2. Cálculos Métricos (Dividido por 1M para facilitar leitura)
net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
status_color = "#00f2ff" if status == "SUPRESSÃO" else "#ff4b4b"

# 3. Registro de Histórico
salvar_historico(current_price, net_gex_total, levels)

# --- INTERFACE VISUAL ---
c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Status Mercado", status)
c2.metric(label="Net GEX", value=f"{net_gex_total:.2f}M", delta=f"{net_gex_total:.2f}M")
c3.metric("Zero Gamma", f"${levels['zero']}")
c4.metric("Put Wall", f"${levels['put']}")
c5.metric("Call Wall", f"${levels['call']}")

st.markdown(f"### Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

# Gráfico de Preço (Candlestick)
fig = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
fig.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
fig.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
fig.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

# Medidor de Risco
st.divider()
col_vix1, col_vix2 = st.columns(2)
distancia_suporte = ((current_price - levels['put']) / levels['put']) * 100

with col_vix1:
    if current_price < levels['put']:
        st.error(f"⚠️ ABAIXO DO SUPORTE: Preço furou a Put Wall (${levels['put']})")
    else:
        st.success(f"🛡️ ACIMA DO SUPORTE: Preço {distancia_suporte:.2f}% acima da proteção.")

with col_vix2:
    if status == "EXPANSÃO":
        st.warning("🔥 RISCO: GAMA NEGATIVO (Movimentos Explosivos)")
    else:
        st.info("🟢 RISCO: GAMA POSITIVO (Mercado Estável)")

# --- HISTOGRAMA DE GAMMA EXPOSURE ---
total_gex_abs = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
calls_data['peso'] = (calls_data['GEX'] / total_gex_abs) * 100
puts_data['peso'] = (puts_data['GEX'].abs() / total_gex_abs) * 100

st.subheader("📊 Histograma de Gamma Exposure")

fig_hist = go.Figure()
fig_hist.add_trace(go.Bar(
    x=calls_data['strike'], 
    y=calls_data['GEX'], 
    name='Calls (Alta)', 
    marker_color='#00ffcc',
    customdata=calls_data['peso'],
    hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"
))

fig_hist.add_trace(go.Bar(
    x=puts_data['strike'], 
    y=puts_data['GEX'], 
    name='Puts (Baixa)', 
    marker_color='#ff4b4b',
    customdata=puts_data['peso'],
    hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"
))

fig_hist.add_vline(x=current_price, line_dash="dash", line_color="yellow", line_width=2)

fig_hist.update_layout(
    template="plotly_dark", 
    barmode='relative',
    hovermode="x unified",
    xaxis_title="Strike Price ($)",
    yaxis_title="GEX Estimado",
    xaxis=dict(range=[current_price * 0.97, current_price * 1.03]),
    legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
    height=550
)

st.plotly_chart(fig_hist, use_container_width=True)

# --- SEÇÃO EDUCATIVA ---
st.divider()
with st.expander("📚 Entenda os Indicadores Institucionais"):
    st.markdown("""
    ### 🧱 Put Wall (Parede de Puts)
    Nível com maior concentração de **GEX de Puts**. Funciona como suporte institucional.

    ### 🏰 Call Wall (Parede de Calls)
    Nível com maior concentração de **GEX de Calls**. Funciona como resistência institucional.

    ### ⚖️ Zero Gamma
    Ponto de equilíbrio. Acima dele (Gama Positivo), o mercado é calmo. Abaixo (Gama Negativo), a volatilidade aumenta drasticamente.
    """)
