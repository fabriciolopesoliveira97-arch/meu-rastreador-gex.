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
        
        # Cálculo institucional (100 ações por contrato)
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
        try:
            df_existente = pd.read_csv(arquivo)
            if not df_existente.empty:
                ultima_data = df_existente['Data'].iloc[-1]
                if ultima_data[:16] == data_hora[:16]: 
                    return
            nova_linha.to_csv(arquivo, mode='a', header=False, index=False)
        except:
            nova_linha.to_csv(arquivo, index=False)

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}

    # CORRIGIDO: Suffixes como tupla
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    put_wall = puts.iloc[puts['GEX'].abs().idxmax()]['strike']
    call_wall = calls.iloc[calls['GEX'].abs().idxmax()]['strike']
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- PROCESSAMENTO PRINCIPAL ---
st.title("🛡️ Nasdaq 100 Institutional Tracker")

ticker = yf.Ticker("QQQ")
df_price = ticker.history(period="1d", interval="5m")

if not df_price.empty:
    current_price = df_price['Close'].iloc[-1]
    calls_data, puts_data = get_gamma_data("QQQ")
    levels = get_gamma_levels(calls_data, puts_data)

    # Métricas
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"
    status_color = "#00f2ff" if status == "SUPRESSÃO" else "#ff4b4b"

    # Salvar histórico
    salvar_historico(current_price, net_gex_total, levels)

    # --- INTERFACE VISUAL ---
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    st.markdown(f"### Cenário Atual: <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)

    # Gráfico Candlestick
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
    fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

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
            st.warning("🔥 RISCO: GAMA NEGATIVO (Alta Volatilidade)")
        else:
            st.info("🟢 RISCO: GAMA POSITIVO (Estabilidade)")

    # --- HISTOGRAMA GEX ---
    st.subheader("📊 Histograma de Gamma Exposure")
    
    total_gex_abs = calls_data['GEX'].abs().sum() + puts_data['GEX'].abs().sum()
    calls_data['peso'] = (calls_data['GEX'].abs() / total_gex_abs) * 100
    puts_data['peso'] = (puts_data['GEX'].abs() / total_gex_abs) * 100

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(x=calls_data['strike'], y=calls_data['GEX'], name='Calls', marker_color='#00ffcc', customdata=calls_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))
    fig_hist.add_trace(go.Bar(x=puts_data['strike'], y=puts_data['GEX'], name='Puts', marker_color='#ff4b4b', customdata=puts_data['peso'], hovertemplate="Strike: %{x}<br>Peso: %{customdata:.2f}%<extra></extra>"))

    # Destaque do Preço Spot
    fig_hist.add_vline(x=current_price, line_dash="solid", line_color="yellow", line_width=3, layer="above")
    max_val = max(calls_data['GEX'].max(), puts_data['GEX'].abs().max())
    fig_hist.add_annotation(x=current_price, y=max_val, text=f"SPOT: ${current_price:.2f}", showarrow=True, arrowhead=2, bgcolor="yellow", font=dict(color="black", size=12))

    fig_hist.update_layout(template="plotly_dark", barmode='relative', xaxis=dict(range=[current_price * 0.96, current_price * 1.04]), height=550)
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- SEÇÃO EDUCATIVA ---
    st.divider()
    with st.expander("📚 Entenda os Indicadores"):
        st.markdown("""
        **Put Wall:** Suporte máximo. **Call Wall:** Resistência máxima. 
        **Zero Gamma:** Se o preço cair abaixo disso, a volatilidade 'explode'.
        """)

else:
    st.error("Erro ao carregar dados do Yahoo Finance.")
