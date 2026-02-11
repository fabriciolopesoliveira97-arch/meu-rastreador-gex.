import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO Terminal", layout="wide")

# Estilização Dark
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { color: #00ffcc; }
    </style>
    """, unsafe_allow_html=True)

# --- MATEMÁTICA ---
def calc_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0.0001: return 0
    d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

# --- BUSCA DE DADOS ---
@st.cache_data(ttl=300)
def fetch_data(symbol="QQQ"):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d")
    if hist.empty: return None
    current_price = hist['Close'].iloc[-1]
    
    expirations = ticker.options
    target_expiry = expirations[0] # 0DTE / Próxima semanal
    
    opts = ticker.option_chain(target_expiry)
    calls, puts = opts.calls, opts.puts
    
    return current_price, calls, puts, target_expiry

try:
    spot, calls, puts, expiry = fetch_data("QQQ")
    r = 0.045 # Taxa de juros aproximada
    T = 1/252 # Tempo para expiração (diário)

    def process_gex(df, is_call=True):
        # Filtramos apenas o que é necessário para o cálculo para evitar erro de soma de datas
        df_clean = df[['strike', 'openInterest', 'impliedVolatility']].copy()
        df_clean['iv'] = df_clean['impliedVolatility'].replace(0, 0.25)
        
        df_clean['gamma'] = df_clean.apply(lambda x: calc_gamma(spot, x['strike'], T, r, x['iv']), axis=1)
        
        side = 1 if is_call else -1
        # Cálculo GEX Notional em Milhões
        df_clean['GEX_Dollar'] = (df_clean['openInterest'] * df_clean['gamma'] * (spot**2) * 0.01 * 100 * side) / 1_000_000
        return df_clean[['strike', 'GEX_Dollar']]

    calls_gex = process_gex(calls, True)
    puts_gex = process_gex(puts, False)

    # Agrupando apenas os valores numéricos (Strike e GEX)
    all_data = pd.concat([calls_gex, puts_gex]).groupby('strike')['GEX_Dollar'].sum().reset_index()

    # Níveis Críticos
    zero_gamma = np.interp(0, all_data['GEX_Dollar'], all_data['strike'])
    put_wall = all_data.loc[all_data['GEX_Dollar'].idxmin(), 'strike']
    call_wall = all_data.loc[all_data['GEX_Dollar'].idxmax(), 'strike']
    
    # Cenário
    scenario = "SUPRESSÃO" if spot > zero_gamma else "EXPANSÃO"
    color = "#00ffcc" if scenario == "SUPRESSÃO" else "#ff4b4b"

    # --- UI ---
    st.title(f"📊 QQQ GEX PRO - {expiry}")
    
    st.markdown(f"""
        <div style="background-color: #161b22; padding: 15px; border-radius: 10px; border-left: 5px solid {color};">
            <h2 style="margin:0; color: {color};">Cenário: {scenario}</h2>
            <p style="color: gray;">Preço {'acima' if spot > zero_gamma else 'abaixo'} do Zero Gamma. Volatilidade {'suprimida' if spot > zero_gamma else 'acelerada'}.</p>
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net GEX", f"{all_data['GEX_Dollar'].sum():.1f}M")
    c2.metric("Zero Gamma", f"${zero_gamma:.2f}")
    c3.metric("Put Wall", f"${put_wall:.2f}")
    c4.metric("Call Wall", f"${call_wall:.2f}")

    # --- GRÁFICO IGUAL À IMAGEM ---
    fig = go.Figure()

    # Barras de Gamma
    fig.add_trace(go.Bar(
        x=all_data['strike'],
        y=all_data['GEX_Dollar'],
        marker_color=np.where(all_data['GEX_Dollar'] >= 0, '#00cc96', '#ef553b'),
        name="GEX"
    ))

    # Linhas Verticais (Estilo a imagem enviada)
    fig.add_vline(x=spot, line_width=3, line_dash="solid", line_color="#00ffff", 
                 annotation_text=f"SPOT: ${spot:.2f}", annotation_font_color="#00ffff")
    
    fig.add_vline(x=zero_gamma, line_width=2, line_dash="dash", line_color="yellow", 
                 annotation_text=f"Zero Gamma: ${zero_gamma:.2f}", annotation_font_color="yellow")
    
    fig.add_vline(x=put_wall, line_width=2, line_dash="dash", line_color="#00ff00", 
                 annotation_text=f"Put Wall: ${put_wall:.2f}", annotation_font_color="#00ff00")

    fig.add_vline(x=call_wall, line_width=2, line_dash="dash", line_color="#ff0000", 
                 annotation_text=f"Call Wall: ${call_wall:.2f}", annotation_font_color="#ff0000")

    fig.update_layout(
        template="plotly_dark",
        height=600,
        xaxis_title="Strike Price ($)",
        yaxis_title="Gamma Exposure (Milhões $)",
        xaxis_range=[spot*0.97, spot*1.03], # Zoom em volta do Spot
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Erro nos dados: {e}")
