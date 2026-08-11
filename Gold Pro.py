import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX PRO - Sinais & Gráfico", layout="wide")
st_autorefresh(interval=60 * 1000, key="datarefresh")

# CSS personalizado idêntico ao layout escuro de referência
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
</style>
""", unsafe_allow_html=True)

# --- 2. INTERFACE DE TOPO ---
st.markdown("### ⚡ Ouro (XAUUSD) - Tempo Real")
st.markdown("<p style='color: #888; font-size: 0.9em;'>Gráfico profissional integrado e sinal de IA</p>", unsafe_allow_html=True)

# --- 3. GRÁFICO DO TRADINGVIEW (ESTILO MT5) ---
# Este componente embuti o gráfico interativo de velas (candles) em tempo real do Ouro
tradingview_widget = """
<!-- TradingView Widget BEGIN -->
<div class="tradingview-widget-container" style="height:450px;width:100%">
  <div id="tradingview_chart" style="height:100%;width:100%"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget(
  {
  "width": "100%",
  "height": 450,
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
  "details": true,
  "hotlist": true,
  "calendar": false,
  "studies": [
    "RSI@tv-basicstudies",
    "MACD@tv-basicstudies"
  ],
  "container_id": "tradingview_chart"
  }
  );
  </script>
</div>
<!-- TradingView Widget END -->
"""
components.html(tradingview_widget, height=470)

# --- 4. CARD DE SINAL DO XAUUSD ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("<p style='color: #00ff88; font-size: 0.85em; font-weight: bold;'>⚡ Sinais Ativos (1)</p>", unsafe_allow_html=True)

sinal_xau = {
    "par": "XAUUSD", "tipo": "COMPRA", "tf": "5m", "forca": "77%", "rr": "1:1.5",
    "entrada": 4426.95, "stop": 4402.95, "take": 4462.95, "hora": "10/08 22:50"
}

color = "#00ff88" if sinal_xau["tipo"] == "COMPRA" else "#ff4b4b"
icon = "↗️" if sinal_xau["tipo"] == "COMPRA" else "↘️"

with st.container():
    st.markdown(f"""
    <div class="signal-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <span style="font-size: 1.1em; font-weight: bold; color: {color}">{icon} {sinal_xau['par']}</span>
                <span style="color: #888; font-size: 0.8em; margin-left: 5px;">{sinal_xau['tf']}</span>
                <span class="badge-ativo" style="margin-left: 8px;">Ativo</span>
            </div>
            <div>
                <span class="badge-percent">{sinal_xau['forca']} 🔥</span>
                <span class="badge-rr" style="margin-left: 5px;">{sinal_xau['rr']}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("ENTRADA", f"{sinal_xau['entrada']:.2f}")
    with col2:
        st.metric("STOP", f"{sinal_xau['stop']:.2f}")
    with col3:
        st.metric("TAKE", f"{sinal_xau['take']:.2f}")
        
    st.markdown(f'<div class="time-stamp" style="margin-bottom: 15px;">{sinal_xau["hora"]}</div>', unsafe_allow_html=True)
