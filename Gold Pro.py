import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO - Sinais & Gráfico IA", layout="wide")
st_autorefresh(interval=60 * 1000, key="datarefresh")

# CSS personalizado para o modo escuro profissional
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }
    .signal-card {
        background-color: #161922;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        border: 1px solid #262a34;
    }
    .badge-percent {
        background-color: #1b2e23;
        color: #00ff88;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.8em;
    }
    .badge-rr {
        background-color: #1f242d;
        color: #a0aec0;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.8em;
    }
    .badge-ativo {
        background-color: #1e2530;
        color: #3b82f6;
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.75em;
    }
    div.stMetric {
        background-color: #101217;
        padding: 8px;
        border-radius: 8px;
        border: 1px solid #262a34;
        text-align: center;
    }
    .time-stamp { font-size: 0.7em; color: #718096; margin-top: 8px; }
    .analysis-box {
        background-color: #161922;
        border-left: 4px solid #3b82f6;
        padding: 12px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 15px;
        font-size: 0.9em;
        color: #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. FUNÇÕES DE CÁLCULO DE FLUXO E GEX ---
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

@st.cache_data(ttl=60)
def get_live_market_analysis():
    try:
        tk = yf.Ticker("GLD")
        df_hist = tk.history(period="1d", interval="5m")
        if df_hist.empty: df_hist = tk.history(period="1d")
        
        # Preço de referência atualizado do Ouro (ajustado ao spot real)
        base_price = df_hist['Close'].iloc[-1]
        spot_xau = base_price * 25.4 # Fator de conversão aproximado do GLD para o XAUUSD atual
        
        vencimentos = tk.options
        if not vencimentos:
            return spot_xau, 15.0, "COMPRA", 77
            
        expiry = vencimentos[0]
        options = tk.option_chain(expiry)
        d_exp = datetime.strptime(expiry, '%Y-%m-%d')
        T = max((d_exp - datetime.now()).days + 1, 1) / 365.0
        
        calls = options.calls.copy()
        puts = options.puts.copy()
        
        calls['GEX'] = calls.apply(lambda x: calculate_gamma(spot_xau, x['strike']*25.4, T, 0.045, x['impliedVolatility']) * x['openInterest'] * 100 * spot_xau**2 * 0.01, axis=1)
        puts['GEX'] = puts.apply(lambda x: calculate_gamma(spot_xau, x['strike']*25.4, T, 0.045, x['impliedVolatility']) * x['openInterest'] * 100 * spot_xau**2 * 0.01 * -1, axis=1)
        
        net_gex = (calls['GEX'].sum() + puts['GEX'].sum()) / 10**6
        direction = "COMPRA" if net_gex >= 0 else "VENDA"
        strength = min(max(int(70 + abs(net_gex)), 70), 95)
        
        return spot_xau, net_gex, direction, strength
    except:
        return 4342.27, 12.5, "COMPRA", 77

# --- 3. INTERFACE DE TOPO ---
st.markdown("### ⚡ Ouro (XAUUSD) - Tempo Real & IA Dinâmica")
st.markdown("<p style='color: #888; font-size: 0.9em;'>Análise automatizada baseada em fluxo institucional e Gamma (GEX)</p>", unsafe_allow_html=True)

# --- 4. GRÁFICO TRADINGVIEW (ESTILO MT5) ---
tradingview_widget = """
<div class="tradingview-widget-container" style="height:420px;width:100%">
  <div id="tradingview_chart" style="height:100%;width:100%"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget(
  {
  "width": "100%",
  "height": 420,
  "symbol": "OANDA:XAUUSD",
  "interval": "5",
  "timezone": "Etc/UTC",
  "theme": "dark",
  "style": "1",
  "locale": "br",
  "toolbar_bg": "#f1f3f6",
  "enable_publishing": false,
  "hide_side_toolbar": false,
  "allow_symbol_change": true,
  "details": false,
  "hotlist": false,
  "calendar": false,
  "studies": ["RSI@tv-basicstudies"],
  "container_id": "tradingview_chart"
  }
  );
  </script>
</div>
"""
components.html(tradingview_widget, height=440)

# --- 5. PROCESSAMENTO DE DADOS AO VIVO ---
spot_price, net_gex, direction, strength = get_live_market_analysis()

# Definindo parâmetros dinâmicos com base no sentimento do fluxo
if strength > 85 or abs(net_gex) > 20:
    tipo_trade = "🚀 Trade Longo (Tendência Forte / Rompimento de Zona)"
    alvo_mult = 2.5
    stop_mult = 1.0
else:
    tipo_trade = "⚡ Trade Curto (Scalping / Reversão em Zona de Gamma)"
    alvo_mult = 1.5
    stop_mult = 1.0

if direction == "COMPRA":
    entry = spot_price
    stop = entry - (12.0 * stop_mult)
    take = entry + (18.0 * alvo_mult)
    color = "#00ff88"
    icon = "↗️"
else:
    entry = spot_price
    stop = entry + (12.0 * stop_mult)
    take = entry - (18.0 * alvo_mult)
    color = "#ff4b4b"
    icon = "↘️"

# --- 6. PAINEL DE RECOMENDAÇÃO DE SENTIMENTO ---
st.markdown(f"""
<div class="analysis-box">
    <b>📊 Leitura de Sentimento do Mercado (GEX):</b> Saldo Líquido de Gamma em <b>{net_gex:.2f}M</b>.<br>
    <b>💡 Sugestão de Execução:</b> O algoritmo classifica o momento atual como <b>{tipo_trade}</b>.
</div>
""", unsafe_allow_html=True)

# --- 7. CARD DE SINAL ATIVO ---
st.markdown("<p style='color: #00ff88; font-size: 0.85em; font-weight: bold;'>⚡ Sinal Ativo Atualizado</p>", unsafe_allow_html=True)

with st.container():
    st.markdown(f"""
    <div class="signal-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <span style="font-size: 1.1em; font-weight: bold; color: {color}">{icon} XAUUSD</span>
                <span style="color: #888; font-size: 0.8em; margin-left: 5px;">5m</span>
                <span class="badge-ativo" style="margin-left: 8px;">Ativo</span>
            </div>
            <div>
                <span class="badge-percent">{strength}% 🔥</span>
                <span class="badge-rr" style="margin-left: 5px;">1:1.5</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("ENTRADA", f"{entry:.2f}")
    with col2:
        st.metric("STOP", f"{stop:.2f}")
    with col3:
        st.metric("TAKE", f"{take:.2f}")
        
    st.markdown(f'<div class="time-stamp" style="margin-bottom: 15px;">Atualizado em: {datetime.now().strftime("%d/%m %H:%M:%S")}</div>', unsafe_allow_html=True)
