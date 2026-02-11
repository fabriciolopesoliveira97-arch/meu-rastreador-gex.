import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO Terminal", layout="wide", initial_sidebar_state="collapsed")

# Estilização Dark Mode Customizada
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .metric-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #30363d;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- MATEMÁTICA DAS GREGAS ---
def calc_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0
    d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

# --- BUSCA DE DADOS ---
@st.cache_data(ttl=3600) # Cache de 1 hora para não sobrecarregar
def fetch_data(symbol="QQQ"):
    ticker = yf.Ticker(symbol)
    current_price = ticker.history(period="1d")['Close'].iloc[-1]
    
    # Próxima expiração (foco em 0DTE ou próxima semanal)
    expirations = ticker.options
    target_expiry = expirations[0]
    
    opts = ticker.option_chain(target_expiry)
    calls, puts = opts.calls, opts.puts
    
    # Taxa 10Y aproximada
    r = 0.042 
    T = 1/252 # Foco no intraday/curto prazo
    
    return current_price, calls, puts, T, r, target_expiry

try:
    spot, calls, puts, T, r, expiry = fetch_data("QQQ")

    # --- PROCESSAMENTO DE EXPOSIÇÃO ---
    def process_gex(df, is_call=True):
        df = df[df['openInterest'] > 0].copy()
        df['iv'] = df['impliedVolatility'].replace(0, 0.25)
        df['gamma'] = df.apply(lambda x: calc_gamma(spot, x['strike'], T, r, x['iv']), axis=1)
        
        # GEX em Milhões de Dólares (Notional)
        # Multiplicador 100 contratos * 0.01 (1% move)
        side = 1 if is_call else -1
        df['GEX_Dollar'] = (df['openInterest'] * df['gamma'] * (spot**2) * 0.01 * 100 * side) / 1_000_000
        return df

    calls = process_gex(calls, True)
    puts = process_gex(puts, False)
    all_data = pd.concat([calls, puts]).groupby('strike').sum().reset_index()

    # --- NÍVEIS CRÍTICOS (MÉTRICAS DO APP) ---
    call_wall = calls.loc[calls['GEX_Dollar'].idxmax(), 'strike']
    put_wall = puts.loc[puts['GEX_Dollar'].idxmin(), 'strike']
    net_gex = all_data['GEX_Dollar'].sum()
    
    # Gamma Flip (Interpolação para achar o zero)
    all_data = all_data.sort_values('strike')
    zero_gamma = np.interp(0, all_data['GEX_Dollar'], all_data['strike'])

    # Determinação do Cenário (Igual ao seu app)
    scenario = "SUPRESSÃO" if spot > zero_gamma else "EXPANSÃO"
    scenario_color = "#00ffcc" if scenario == "SUPRESSÃO" else "#ff4b4b"
    sub_text = "Volatilidade suprimida, movimentos limitados." if scenario == "SUPRESSÃO" else "Volatilidade alta, movimentos amplos."

    # --- UI DASHBOARD ---
    st.title(f"🔍 QQQ GEX Analyser - Exp: {expiry}")
    
    # Banner de Cenário
    st.markdown(f"""
        <div style="background-color: #161b22; padding: 20px; border-left: 5px solid {scenario_color}; border-radius: 10px;">
            <h3 style="margin:0; color: {scenario_color};">Cenário Atual: {scenario}</h3>
            <p style="margin:0; color: #8b949e;">{sub_text}</p>
        </div>
    """, unsafe_allow_html=True)
    st.write("")

    # Métricas Principais
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net GEX Total", f"${net_gex:.1f}M")
    col2.metric("Zero Gamma", f"${zero_gamma:.2f}")
    col3.metric("Put Wall (Suporte)", f"${put_wall:.2f}")
    col4.metric("Call Wall (Resistência)", f"${call_wall:.2f}")

    # Gráfico de Histograma
    fig = go.Figure()
    
    # Barras de Gamma
    fig.add_trace(go.Bar(
        x=all_data['strike'], 
        y=all_data['GEX_Dollar'],
        marker_color=np.where(all_data['GEX_Dollar'] >= 0, '#00cc96', '#ef553b'),
        name="Gamma Exposure"
    ))

    # Linhas de Referência
    fig.add_vline(x=spot, line_dash="dash", line_color="cyan", annotation_text=f"SPOT: {spot:.2f}")
    fig.add_vline(x=zero_gamma, line_dash="dot", line_color="yellow", annotation_text="ZERO GAMMA")

    fig.update_layout(
        template="plotly_dark",
        title="Histograma de Gamma Exposure (M$ por Strike)",
        xaxis=dict(range=[spot*0.95, spot*1.05], title="Strike Price"),
        yaxis=dict(title="GEX Notional (Milhões $)"),
        height=600,
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Aguardando abertura do mercado ou erro nos dados: {e}")
