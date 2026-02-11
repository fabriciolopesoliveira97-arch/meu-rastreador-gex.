import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm

# --- CONFIGURAÇÃO DE TELA ---
st.set_page_config(page_title="GEX PRO - Deep Analysis", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# --- ENGINE MATEMÁTICA ---
def calc_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0.0001: return 0
    d1 = (np.log(S/K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

@st.cache_data(ttl=300)
def get_data(symbol="QQQ"):
    tk = yf.Ticker(symbol)
    spot = tk.history(period="1d")['Close'].iloc[-1]
    exp = tk.options[0] # 0DTE / Próxima semanal
    chain = tk.option_chain(exp)
    return spot, chain.calls, chain.puts, exp

try:
    spot_price, calls, puts, expiry_date = get_data("QQQ")
    T, r = 1/252, 0.045 # Premissas padrão intraday

    def process_df(df, is_call=True):
        # Limpeza rigorosa para evitar erro datetime64
        data = df[['strike', 'openInterest', 'impliedVolatility']].copy()
        data['iv'] = data['impliedVolatility'].replace(0, 0.25)
        data['gamma'] = data.apply(lambda x: calc_gamma(spot_price, x['strike'], T, r, x['iv']), axis=1)
        
        # GEX Notional (MM View: Long Calls / Long Puts)
        # Para o gráfico espelhado: Calls (+), Puts (-)
        mult = 1 if is_call else -1
        data['GEX'] = data['openInterest'] * data['gamma'] * (spot_price**2) * 0.01 * 100 * mult
        return data[['strike', 'GEX']]

    df_calls = process_df(calls, True)
    df_puts = process_df(puts, False)

    # Agrupamento por Strike
    df_calls = df_calls.groupby('strike').sum().reset_index()
    df_puts = df_puts.groupby('strike').sum().reset_index()
    
    # Cálculo de "Força" (Percentual sobre a maior exposição)
    total_abs_max = max(df_calls['GEX'].max(), abs(df_puts['GEX'].min()))
    df_calls['forca'] = (df_calls['GEX'] / total_abs_max) * 100
    df_puts['forca'] = (abs(df_puts['GEX']) / total_abs_max) * 100

    # Níveis de Preço
    all_gex = pd.merge(df_calls, df_puts, on='strike', suffixes=('_c', '_p'))
    all_gex['total'] = all_gex['GEX_c'] + all_gex['GEX_p']
    zero_gamma = np.interp(0, all_gex['total'], all_gex['strike'])
    call_wall = df_calls.loc[df_calls['GEX'].idxmax(), 'strike']
    put_wall = df_puts.loc[df_puts['GEX'].idxmin(), 'strike']

    # --- DASHBOARD UI ---
    st.subheader(f"📊 Histograma de Gamma Exposure (Força por Strike) - {expiry_date}")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("SPOT", f"${spot_price:.2f}")
    m2.metric("ZERO GAMMA", f"${zero_gamma:.2f}")
    m3.metric("CALL WALL", f"${call_wall:.2f}")
    m4.metric("PUT WALL", f"${put_wall:.2f}")

    # --- GRÁFICO ESPELHADO (EXATAMENTE COMO A IMAGEM) ---
    fig = go.Figure()

    # Barras de Calls (Verde - para cima)
    fig.add_trace(go.Bar(
        x=df_calls['strike'], y=df_calls['GEX'],
        name="Calls", marker_color='#00f2c3',
        customdata=df_calls['forca'],
        hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata:.2f}%<extra></extra>"
    ))

    # Barras de Puts (Vermelho - para baixo)
    fig.add_trace(go.Bar(
        x=df_puts['strike'], y=df_puts['GEX'],
        name="Puts", marker_color='#ff5858',
        customdata=df_puts['forca'],
        hovertemplate="Strike: %{x}<br>GEX: %{y:,.0f}<br>Força: %{customdata:.2f}%<extra></extra>"
    ))

    # Linha do SPOT (Branca tracejada como na imagem)
    fig.add_vline(x=spot_price, line_width=3, line_dash="dash", line_color="white")
    fig.add_annotation(x=spot_price, y=total_abs_max*1.1, text=f"SPOT: ${spot_price:.2f}", 
                       showarrow=False, bgcolor="white", font_color="black")

    fig.update_layout(
        template="plotly_dark",
        barmode='relative',
        height=700,
        xaxis=dict(title="Strike Price ($)", range=[spot_price*0.96, spot_price*1.04]),
        yaxis=dict(title="Gamma Exposure (Notional)", gridcolor="#222"),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Erro ao processar: {e}")
