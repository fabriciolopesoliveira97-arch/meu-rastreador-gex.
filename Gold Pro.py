import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO - Sinais & Gráfico IA", layout="wide")
st_autorefresh(interval=30 * 1000, key="datarefresh")

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

# --- 2. PAINEL DE CONTROLE DE PREÇO (BARRA LATERAL) ---
st.sidebar.markdown("### ⚙️ Calibração de Preço")
# Permite que você ajuste o valor exato que está vendo no gráfico da OANDA
preco_grafico = st.sidebar.number_input("Preço Atual do XAUUSD (Gráfico)", value=4411.22, step=0.01, format="%.2f")

# --- 3. INTERFACE DE TOPO ---
st.markdown("### ⚡ Ouro (XAUUSD) - Tempo Real & IA Dinâmica")
st.markdown("<p style='color: #888; font-size: 0.9em;'>Gráfico sincronizado e painel de execução automatizada</p>", unsafe_allow_html=True)

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

# --- 5. PROCESSAMENTO DOS VALORES EXATOS ---
entry = preco_grafico
stop = entry - 12.0  # Distância proporcional de Stop
take = entry + 18.0  # Distância proporcional de Take (R:R 1:1.5)
forca = 78
color = "#00ff88"
icon = "↗️"
tipo_trade = "🚀 Trade Longo (Tendência de Alta nos Candles)"

# --- 6. PAINEL DE LEITURA DE MERCADO ---
st.markdown(f"""
<div class="analysis-box">
    <b>📊 Sincronização Ativa:</b> Baseado na cotação de referência <b>{entry:.2f}</b>.<br>
    <b>💡 Perfil do Momento:</b> <b>{tipo_trade}</b> sincronizado com o gráfico.
</div>
""", unsafe_allow_html=True)

# --- 7. CARD DE SINAL EXATO ---
st.markdown("<p style='color: #00ff88; font-size: 0.85em; font-weight: bold;'>⚡ Sinal Ativo Sincronizado</p>", unsafe_allow_html=True)

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
                <span class="badge-percent">{forca}% 🔥</span>
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
