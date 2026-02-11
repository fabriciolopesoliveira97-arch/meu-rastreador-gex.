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
        
        # Cálculo institucional: 100 ações por contrato
        calls['GEX'] = calls['openInterest'] * calls['lastPrice'] * 100
        puts['GEX'] = puts['openInterest'] * puts['lastPrice'] * -100
        
        return calls, puts
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return pd.DataFrame(), pd.DataFrame()

def get_gamma_levels(calls, puts):
    if calls.empty or puts.empty:
        return {"zero": 0, "put": 0, "call": 0}
    
    # CORREÇÃO DO ERRO DE SINTAXE: Suffixes agora é uma tupla ('_c', '_p')
    df_total = pd.merge(calls, puts, on='strike', suffixes=('_c', '_p'))
    df_total['net_gex'] = df_total['GEX_c'] + df_total['GEX_p']
    
    zero_gamma = df_total.iloc[(df_total['net_gex']).abs().argsort()[:1]]['strike'].values[0]
    put_wall = puts.iloc[puts['GEX'].abs().idxmax()]['strike']
    call_wall = calls.iloc[calls['GEX'].abs().idxmax()]['strike']
    
    return {"zero": zero_gamma, "put": put_wall, "call": call_wall}

# --- PROCESSAMENTO ---
ticker = yf.Ticker("QQQ")
df_price = ticker.history(period="1d", interval="5m")

if not df_price.empty:
    current_price = df_price['Close'].iloc[-1]
    calls_data, puts_data = get_gamma_data("QQQ")
    levels = get_gamma_levels(calls_data, puts_data)

    # --- INTERFACE ---
    st.title("🛡️ Nasdaq 100 Institutional Tracker")

    c1, c2, c3, c4, c5 = st.columns(5)
    net_gex_total = (calls_data['GEX'].sum() + puts_data['GEX'].sum()) / 10**6
    status = "SUPRESSÃO" if current_price > levels['zero'] else "EXPANSÃO"

    c1.metric("Status Mercado", status)
    c2.metric("Net GEX", f"{net_gex_total:.2f}M")
    c3.metric("Zero Gamma", f"${levels['zero']}")
    c4.metric("Put Wall", f"${levels['put']}")
    c5.metric("Call Wall", f"${levels['call']}")

    # --- HISTOGRAMA DE GAMMA ---
    st.subheader("📊 Histograma de Gamma Exposure")

    fig_hist = go.Figure()

    # Barras de Calls
    fig_hist.add_trace(go.Bar(
        x=calls_data['strike'], 
        y=calls_data['GEX'], 
        name='Calls (Alta)', 
        marker_color='#00ffcc'
    ))

    # Barras de Puts
    fig_hist.add_trace(go.Bar(
        x=puts_data['strike'], 
        y=puts_data['GEX'], 
        name='Puts (Baixa)', 
        marker_color='#ff4b4b'
    ))

    # --- LINHA E ETIQUETA DO PREÇO SPOT ---
    # Linha vertical
    fig_hist.add_vline(
        x=current_price, 
        line_dash="solid", 
        line_color="yellow", 
        line_width=3,
        layer="above"
    )

    # Etiqueta flutuante (Anotação)
    max_gex = max(calls_data['GEX'].max(), puts_data['GEX'].abs().max())
    fig_hist.add_annotation(
        x=current_price,
        y=max_gex,
        text=f"PREÇO ATUAL: ${current_price:.2f}",
        showarrow=True,
        arrowhead=2,
        ax=0,
        ay=-50,
        font=dict(color="black", size=14, family="Arial Black"),
        bgcolor="yellow",
        bordercolor="black",
        borderwidth=2,
        opacity=1
    )

    fig_hist.update_layout(
        template="plotly_dark", 
        barmode='relative',
        hovermode="x unified",
        xaxis_title="Strike Price ($)",
        yaxis_title="GEX Estimado ($)",
        xaxis=dict(range=[current_price * 0.96, current_price * 1.04]), # Zoom de 4%
        height=600,
        showlegend=True
    )

    st.plotly_chart(fig_hist, use_container_width=True)

else:
    st.error("Não foi possível carregar os dados de preço do QQQ.")
