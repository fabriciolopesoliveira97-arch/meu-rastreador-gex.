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
        
        # Cálculo institucional (100 ações por contrato)
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

# --- PROCESSAMENTO ---
ticker_name = "QQQ"
ticker = yf.Ticker(ticker_name)
df_price = ticker.history(period="1d", interval="5m")

if not df_price.empty:
    current_price = df_price['Close'].iloc[-1]
    calls_data, puts_data = get_gamma_data(ticker_name)
    levels = get_gamma_levels(calls_data, puts_data)

    # Cálculo do Net GEX e Cor
    net_gex_val = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    gex_color = "normal" if net_gex_val >= 0 else "inverse" # Streamlit usa delta para cores

    # --- INTERFACE VISUAL ---
    st.title(f"🛡️ {ticker_name} Institutional Tracker")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status Mercado", "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO")
    
    # Net GEX com cor dinâmica
    c2.metric(
        label="Net GEX Total", 
        value=f"{net_gex_val:.2f}M", 
        delta=f"{'Positivo' if net_gex_val > 0 else 'Negativo'}",
        delta_color=gex_color
    )
    
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # --- HISTOGRAMA GEX COM PESOS ---
    st.subheader("📊 Distribuição de Gamma por Strike (Peso %)")
    
    # Cálculo de pesos para o Hover
    total_abs_exposure = calls_data['GEX'].sum() + puts_data['GEX'].abs().sum()
    calls_data['peso'] = (calls_data['GEX'] / total_abs_exposure) * 100
    puts_data['peso'] = (puts_data['GEX'].abs() / total_abs_exposure) * 100

    fig_hist = go.Figure()

    # Trace de Calls
    fig_hist.add_trace(go.Bar(
        x=calls_data['strike'], 
        y=calls_data['GEX'], 
        name='Calls (Gamma +)', 
        marker_color='#00ffcc',
        customdata=calls_data['peso'],
        hovertemplate="<b>Strike: $%{x}</b><br>GEX: $%{y:,.0f}<br>Peso: %{customdata:.2f}%<extra></extra>"
    ))

    # Trace de Puts
    fig_hist.add_trace(go.Bar(
        x=puts_data['strike'], 
        y=puts_data['GEX'], 
        name='Puts (Gamma -)', 
        marker_color='#ff4b4b',
        customdata=puts_data['peso'],
        hovertemplate="<b>Strike: $%{x}</b><br>GEX: $%{y:,.0f}<br>Peso: %{customdata:.2f}%<extra></extra>"
    ))

    # Destaque do Preço Spot
    fig_hist.add_vline(x=current_price, line_dash="solid", line_color="yellow", line_width=3, layer="above")
    
    max_y = max(calls_data['GEX'].max(), puts_data['GEX'].abs().max())
    fig_hist.add_annotation(
        x=current_price, y=max_y, text=f"PREÇO SPOT: ${current_price:.2f}",
        showarrow=True, arrowhead=2, bgcolor="yellow", font=dict(color="black", size=12, family="Arial Black")
    )

    fig_hist.update_layout(
        template="plotly_dark", 
        barmode='relative',
        hovermode="x unified",
        xaxis=dict(title="Strike Price ($)", range=[current_price * 0.96, current_price * 1.04]),
        yaxis=dict(title="Gamma Exposure ($)"),
        height=600
    )

    st.plotly_chart(fig_hist, use_container_width=True)

    # --- GRÁFICO CANDLESTICK ---
    st.divider()
    st.subheader("📈 Níveis Gráficos")
    fig_candle = go.Figure(data=[go.Candlestick(x=df_price.index, open=df_price['Open'], high=df_price['High'], low=df_price['Low'], close=df_price['Close'])])
    fig_candle.add_hline(y=levels['zero'], line_dash="dash", line_color="yellow", annotation_text="Zero Gamma")
    fig_candle.add_hline(y=levels['put'], line_color="green", line_width=2, annotation_text="Put Wall")
    fig_candle.add_hline(y=levels['call'], line_color="red", line_width=2, annotation_text="Call Wall")
    fig_candle.update_layout(template="plotly_dark", height=450, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_candle, use_container_width=True)

else:
    st.error("Erro ao conectar com Yahoo Finance. Verifique sua conexão.")
