import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# ============================================================
# GEX PRO — ANÁLISE REAL DO XAUUSD
# ============================================================
# Dados:
# 1) Twelve Data, se TWELVEDATA_API_KEY estiver em st.secrets
# 2) Yahoo Finance como fallback (XAUUSD=X)
#
# IMPORTANTE:
# O TradingView incorporado é apenas visual. O painel NÃO "lê"
# os candles do iframe. Os valores do painel são calculados a
# partir da mesma ideia de ativo/timeframe usando uma fonte de
# dados externa.
# ============================================================

st.set_page_config(page_title="GEX PRO — XAUUSD Real", layout="wide")
st_autorefresh(interval=30_000, key="datarefresh")

# ---------------- CSS ----------------
st.markdown("""
<style>
.stApp { background:#0e1117; color:#fff; }
.signal-card,.analysis-box {
    background:#161922; border:1px solid #262a34;
    border-radius:12px; padding:16px; margin-bottom:12px;
}
.analysis-box { border-left:4px solid #3b82f6; }
.badge {
    display:inline-block; padding:4px 9px; border-radius:7px;
    font-size:.78rem; font-weight:700; margin-right:5px;
}
.green { background:#123523; color:#00ff88; }
.red { background:#3a171b; color:#ff5c6c; }
.gray { background:#20242d; color:#b8c0cc; }
.blue { background:#162b46; color:#60a5fa; }
.small { color:#87909f; font-size:.78rem; }
</style>
""", unsafe_allow_html=True)

# ---------------- Configuração ----------------
st.sidebar.markdown("### ⚙️ Configuração")

symbol_tv = st.sidebar.selectbox(
    "Ativo no TradingView",
    ["OANDA:XAUUSD", "FX_IDC:XAUUSD"],
    index=0
)

timeframe = st.sidebar.selectbox(
    "Timeframe",
    ["1min", "5min", "15min", "30min", "1h", "4h"],
    index=1
)

tv_interval = {
    "1min": "1", "5min": "5", "15min": "15",
    "30min": "30", "1h": "60", "4h": "240"
}[timeframe]

periods = st.sidebar.slider(
    "Quantidade de candles para análise",
    min_value=100, max_value=1000, value=300, step=50
)

# API key opcional via Streamlit Secrets
api_key = ""
try:
    api_key = st.secrets.get("TWELVEDATA_API_KEY", "")
except Exception:
    api_key = ""

st.sidebar.markdown("---")
st.sidebar.markdown("### 📡 Dados reais")
st.sidebar.info(
    "Com TWELVEDATA_API_KEY: usa XAU/USD via Twelve Data. "
    "Sem chave: tenta Yahoo Finance."
)
st.sidebar.caption(
    "Para dados de mercado via Twelve Data, coloque "
    "`TWELVEDATA_API_KEY` em `.streamlit/secrets.toml`."
)

# ---------------- Indicadores ----------------
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def adx(df, period=14):
    """
    ADX / +DI / -DI (Wilder).
    ADX mede a FORÇA da tendência (não a direção) — é o filtro de
    volatilidade/ruído: abaixo de ~20-25 o mercado está de lado e
    cruzamentos de médias tendem a ser "sinais falsos".
    +DI/-DI mostram QUEM está no comando (compradores vs vendedores),
    usado como confirmação de direção do sinal.
    """
    high, low, close = df["high"], df["low"], df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr_w = tr.ewm(alpha=1/period, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr_w.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr_w.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx_val, plus_di, minus_di


def load_twelve_data(interval, outputsize):
    """Obtém candles reais do Twelve Data."""
    if not api_key:
        return None, None

    interval_map = {
        "1min": "1min",
        "5min": "5min",
        "15min": "15min",
        "30min": "30min",
        "1h": "1h",
        "4h": "4h"
    }

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": "XAU/USD",
        "interval": interval_map[interval],
        "outputsize": min(outputsize, 5000),
        "apikey": api_key,
        "format": "JSON",
        "order": "ASC"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if "values" not in data:
            return None, data.get("message", "Resposta inválida da API.")

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "volume" not in df.columns:
            df["volume"] = np.nan

        return df.set_index("datetime"), "Twelve Data"

    except Exception as e:
        return None, f"Erro Twelve Data: {e}"

def load_yahoo_data(interval, outputsize):
    """Fallback público. Pode ter atraso e não é necessariamente a cotação OANDA."""
    try:
        import yfinance as yf

        period_map = {
            "1min": "5d",
            "5min": "1mo",
            "15min": "1mo",
            "30min": "1mo",
            "1h": "3mo",
            "4h": "1y"
        }

        # Yahoo não oferece 4h diretamente; baixa 1h e agrega.
        yahoo_interval = "1h" if interval == "4h" else interval

        df = yf.download(
            "XAUUSD=X",
            period=period_map[interval],
            interval=yahoo_interval,
            auto_adjust=False,
            progress=False
        )

        if df is None or df.empty:
            return None, "Yahoo Finance sem dados."

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        cols = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]].dropna(subset=["close"])

        if interval == "4h":
            df = df.resample("4h").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum"
            }).dropna()

        return df.tail(outputsize), "Yahoo Finance (fallback)"

    except Exception as e:
        return None, f"Erro Yahoo Finance: {e}"

@st.cache_data(ttl=20)
def get_market_data(interval, outputsize):
    # Prioridade: fonte de mercado configurada pelo usuário.
    if api_key:
        df, source = load_twelve_data(interval, outputsize)
        if df is not None and not df.empty:
            return df, source

    return load_yahoo_data(interval, outputsize)

# ---------------- Carrega mercado ----------------
df, source = get_market_data(timeframe, periods)

st.markdown("### ⚡ Ouro (XAUUSD) — Análise baseada em mercado")
st.markdown(
    "<p style='color:#888;font-size:.9rem;'>"
    "Preço, indicadores, entrada, stop e alvo são recalculados pelos candles recebidos."
    "</p>",
    unsafe_allow_html=True
)

if df is None or df.empty:
    st.error(
        "Não foi possível obter os candles reais.\n\n"
        f"**Motivo reportado pela fonte de dados:** {source}"
    )
    st.markdown(
        """
        <div class="analysis-box small">
        Causas mais comuns quando isso acontece só no Streamlit Cloud (e não local):<br>
        • <b>yfinance ausente do requirements.txt</b> — sem TWELVEDATA_API_KEY,
        o app depende 100% do yfinance; se o pacote não estiver listado,
        o import falha silenciosamente e cai aqui.<br>
        • <b>Yahoo Finance bloqueando o IP do servidor</b> — datacenters
        (como o do Streamlit Cloud) são frequentemente limitados/bloqueados
        pelo Yahoo, mesmo funcionando normalmente no seu computador.<br>
        • <b>Sem TWELVEDATA_API_KEY configurada</b> em Settings → Secrets do app.
        </div>
        """,
        unsafe_allow_html=True
    )
    st.stop()

# ---------------- Widget TradingView (referência visual) ----------------
# Isso é só o gráfico visual da corretora/TradingView, para conferência
# manual. Ele NÃO alimenta os cálculos do painel — os candles reais
# usados no score, entrada, stop e take vêm de get_market_data()
# (Twelve Data / Yahoo) e são plotados separadamente no gráfico Plotly
# logo abaixo, para não haver dúvida de qual fonte gerou cada nível.
st.markdown("#### 📺 TradingView")
tv_widget_html = f"""
<div class="tradingview-widget-container">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "width": "100%",
    "height": 500,
    "symbol": "{symbol_tv}",
    "interval": "{tv_interval}",
    "timezone": "Etc/UTC",
    "theme": "dark",
    "style": "1",
    "locale": "br",
    "toolbar_bg": "#0e1117",
    "enable_publishing": false,
    "hide_top_toolbar": false,
    "allow_symbol_change": true,
    "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(tv_widget_html, height=520)
st.caption(
    "Gráfico do TradingView é apenas visual/conferência. "
    "O painel abaixo (score, entrada, stop, take) usa os candles reais "
    "obtidos por API, não os do iframe."
)

# ---------------- Cálculos ----------------
df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
df["rsi"] = rsi(df["close"], 14)
df["atr"] = atr(df, 14)
df["adx"], df["plus_di"], df["minus_di"] = adx(df, 14)

# VWAP intraday (reset por sessão UTC) e Bandas de Bollinger
typical = (df["high"] + df["low"] + df["close"]) / 3
if not df["volume"].isna().all():
    session = df.index.floor("D")
    pv = typical * df["volume"].fillna(0)
    df["vwap"] = pv.groupby(session).cumsum() / df["volume"].fillna(0).groupby(session).cumsum().replace(0, np.nan)
else:
    df["vwap"] = df["close"].rolling(20).mean()

bb_mid = df["close"].rolling(20).mean()
bb_std = df["close"].rolling(20).std()
df["bb_mid"] = bb_mid
df["bb_upper"] = bb_mid + 2 * bb_std
df["bb_lower"] = bb_mid - 2 * bb_std

# Estrutura de mercado: pivôs locais e rompimento do range recente.
pivot_window = 3
df["pivot_high"] = df["high"].where(
    (df["high"] == df["high"].rolling(2 * pivot_window + 1, center=True).max())
)
df["pivot_low"] = df["low"].where(
    (df["low"] == df["low"].rolling(2 * pivot_window + 1, center=True).min())
)


# MACD
ema12 = df["close"].ewm(span=12, adjust=False).mean()
ema26 = df["close"].ewm(span=26, adjust=False).mean()
df["macd"] = ema12 - ema26
df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
df["macd_hist"] = df["macd"] - df["macd_signal"]
df["macd_hist_slope"] = df["macd_hist"].diff()  # momentum acelerando (+) ou perdendo força (-)

# Volume relativo
vol_ma = df["volume"].rolling(20).mean()
if df["volume"].isna().all() or (vol_ma.iloc[-1] == 0):
    volume_ratio = np.nan
else:
    volume_ratio = df["volume"].iloc[-1] / vol_ma.iloc[-1]

# Suportes/resistências simples por janela recente
lookback = min(50, len(df))
recent = df.tail(lookback)

support = float(recent["low"].min())
resistance = float(recent["high"].max())

last = df.iloc[-1]
prev = df.iloc[-2]

price = float(last["close"])
atr_value = float(last["atr"])
rsi_value = float(last["rsi"])

structure_lookback = min(30, len(df))
structure_high = float(df["high"].iloc[-structure_lookback:-1].max())
structure_low = float(df["low"].iloc[-structure_lookback:-1].min())
# Rompimento exige fechamento além do nível por um buffer de ATR
# (não apenas um pavio) e que o candle anterior já estivesse próximo
# do nível — filtra "fakeouts" de 1 candle isolado.
breakout_buffer = atr_value * 0.15
close_prev = float(df["close"].iloc[-2]) if len(df) > 1 else price
breakout_up = (price > structure_high + breakout_buffer) and (close_prev > structure_high - breakout_buffer)
breakout_down = (price < structure_low - breakout_buffer) and (close_prev < structure_low + breakout_buffer)

# ---------------- Score de tendência ----------------
# Correção do modelo anterior: EMA9>EMA21, EMA21>EMA50 e Preço>EMA50
# são quase sempre a MESMA informação (alinhamento de médias), então
# somar 20+20+20 para isso triplicava o peso de um único fato e fazia
# o score oscilar junto com o menor ruído de preço. Aqui esse bloco
# vira UM componente (peso 25), e o espaço restante vai para filtros
# de qualidade (ADX, DI, persistência) em vez de "mais um cruzamento".

adx_value = float(last["adx"]) if not np.isnan(last["adx"]) else np.nan
plus_di_value = float(last["plus_di"]) if not np.isnan(last["plus_di"]) else np.nan
minus_di_value = float(last["minus_di"]) if not np.isnan(last["minus_di"]) else np.nan
macd_hist_slope = float(last["macd_hist_slope"]) if not np.isnan(last["macd_hist_slope"]) else 0.0

score = 0

# 1) Estrutura de médias — peso único (não triplicado)
if last["ema9"] > last["ema21"] > last["ema50"]:
    score += 25
elif last["ema9"] < last["ema21"] < last["ema50"]:
    score -= 25
elif last["ema9"] > last["ema21"]:
    score += 10  # alinhamento parcial de alta
elif last["ema9"] < last["ema21"]:
    score -= 10  # alinhamento parcial de baixa

# 2) Momentum: cruzamento do MACD + aceleração do histograma
if last["macd"] > last["macd_signal"]:
    score += 15
    if macd_hist_slope > 0:
        score += 5  # momentum ganhando força, não só cruzado
else:
    score -= 15
    if macd_hist_slope < 0:
        score -= 5

# 3) RSI — zona de momentum, com desconto em extremos (risco de exaustão)
if 50 <= rsi_value < 70:
    score += 15
elif rsi_value >= 70:
    score += 5   # sobrecomprado: a favor da alta, mas risco de reversão
elif 30 < rsi_value <= 50:
    score -= 15
elif rsi_value <= 30:
    score -= 5   # sobrevendido: a favor da baixa, mas risco de reversão

# 4) Preço vs VWAP (referência de valor justo intradiário)
if not np.isnan(last.get("vwap", np.nan)):
    if price > last["vwap"]:
        score += 10
    else:
        score -= 10

# 5) Rompimento estrutural já confirmado por fechamento (ver bloco acima)
if breakout_up:
    score += 15
elif breakout_down:
    score -= 15

score = max(-100, min(100, score))
raw_direction = 1 if score > 0 else (-1 if score < 0 else 0)

# ---------------- Filtro 1: ADX (força de tendência / regime de mercado) ----------------
# Este é o filtro central contra ruído: cruzamentos de médias e RSI
# geram sinais falsos constantes quando o mercado está de lado. Só
# deixamos o sinal "passar" quando o ADX mostra que existe tendência
# de fato — e exigimos score mais alto quando a tendência é fraca.
adx_threshold_score = 40
if np.isnan(adx_value):
    adx_regime = "indisponível (poucos candles)"
    trend_ok = True
elif adx_value < 18:
    adx_regime = "lateralizado — mercado sem tendência"
    trend_ok = False
elif adx_value < 25:
    adx_regime = "tendência fraca"
    trend_ok = True
    adx_threshold_score = 55
else:
    adx_regime = "tendência confirmada"
    trend_ok = True

# ---------------- Filtro 2: confirmação de fluxo via DI+/DI- ----------------
# O +DI/-DI mostra quem está no controle do fluxo de ordens. Se o
# score aponta para compra mas o -DI ainda domina (ou vice-versa),
# tratamos como sinal ainda não confirmado pelo fluxo real.
if not np.isnan(plus_di_value) and not np.isnan(minus_di_value) and raw_direction != 0:
    di_direction = 1 if plus_di_value > minus_di_value else -1
    di_agrees = di_direction == raw_direction
else:
    di_agrees = True  # dado insuficiente: não bloqueia sozinho

# ---------------- Filtro 3: persistência entre candles ----------------
# Exige que o viés (médias + MACD) já estivesse na mesma direção nos
# últimos candles fechados, não só no candle atual — reduz o
# "flip-flop" de sinal causado por 1 candle isolado de ruído
# (importante aqui porque o painel se autoatualiza a cada 30s).
persist_window = min(3, len(df))
persist_dirs = []
for i in range(-persist_window, 0):
    row = df.iloc[i]
    d = (1 if row["ema9"] > row["ema21"] else -1) + (1 if row["macd"] > row["macd_signal"] else -1)
    persist_dirs.append(1 if d > 0 else (-1 if d < 0 else 0))
persistence_ok = raw_direction != 0 and all(d == raw_direction for d in persist_dirs)

# ---------------- Decisão final ----------------
if trend_ok and di_agrees and persistence_ok and score >= adx_threshold_score:
    signal = "COMPRA"
    color = "#00ff88"
    icon = "↗️"
elif trend_ok and di_agrees and persistence_ok and score <= -adx_threshold_score:
    signal = "VENDA"
    color = "#ff5c6c"
    icon = "↘️"
else:
    signal = "NEUTRO"
    color = "#f5c451"
    icon = "⏸️"

# Confiança agora reflete não só a magnitude do score, mas também a
# força real da tendência (ADX) e a participação de volume — um
# score alto em mercado lateralizado ou com volume fraco não deveria
# gerar a mesma confiança que um score alto em tendência forte.
adx_factor = 0.5 if np.isnan(adx_value) else min(1.0, adx_value / 40)
volume_factor = 1.0 if np.isnan(volume_ratio) else min(1.1, max(0.85, volume_ratio))
confidence = (50 + abs(score) * 0.45) * (0.7 + 0.3 * adx_factor) * volume_factor
confidence = min(95, max(30, confidence))

# ---------------- Entrada / SL / TP ----------------
# O risco é derivado do ATR, e não de um número fixo.
# Stop usa a combinação de ATR + estrutura recente.
# O alvo usa o próximo múltiplo de risco e evita ficar "preso" a valores fixos.
atr_buffer = atr_value * 0.25

if signal == "COMPRA":
    entry = price
    structural_stop = support - atr_buffer
    stop = min(entry - atr_value * 1.2, structural_stop)
    risk_distance = max(entry - stop, atr_value * 0.8)
    take = entry + risk_distance * 1.8

elif signal == "VENDA":
    entry = price
    structural_stop = resistance + atr_buffer
    stop = max(entry + atr_value * 1.2, structural_stop)
    risk_distance = max(stop - entry, atr_value * 0.8)
    take = entry - risk_distance * 1.8

else:
    entry = price
    risk_distance = atr_value * 1.2
    stop = price - risk_distance
    take = price + risk_distance * 1.8

rr = abs(take - entry) / abs(entry - stop)

# ---------------- Gráfico técnico sincronizado com os dados reais ----------------
# Este gráfico usa exatamente o dataframe que alimenta os cálculos do painel.
# Assim, entrada/SL/TP e suporte/resistência são desenhados sobre os mesmos candles.

chart_df = df.tail(min(180, len(df))).copy()

fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=chart_df.index,
    open=chart_df["open"],
    high=chart_df["high"],
    low=chart_df["low"],
    close=chart_df["close"],
    name="XAUUSD"
))

fig.add_trace(go.Scatter(
    x=chart_df.index, y=chart_df["ema9"],
    mode="lines", name="EMA 9",
    line=dict(width=1.5)
))

fig.add_trace(go.Scatter(
    x=chart_df.index, y=chart_df["ema21"],
    mode="lines", name="EMA 21",
    line=dict(width=1.5)
))

fig.add_trace(go.Scatter(
    x=chart_df.index, y=chart_df["ema50"],
    mode="lines", name="EMA 50",
    line=dict(width=1.7)
))

if "vwap" in chart_df.columns:
    fig.add_trace(go.Scatter(
        x=chart_df.index, y=chart_df["vwap"],
        mode="lines", name="VWAP",
        line=dict(width=1.5, dash="dot")
    ))

if "bb_upper" in chart_df.columns and "bb_lower" in chart_df.columns:
    fig.add_trace(go.Scatter(
        x=chart_df.index, y=chart_df["bb_upper"],
        mode="lines", name="BB superior",
        line=dict(width=1, dash="dash")
    ))
    fig.add_trace(go.Scatter(
        x=chart_df.index, y=chart_df["bb_lower"],
        mode="lines", name="BB inferior",
        line=dict(width=1, dash="dash")
    ))

# Níveis calculados no mesmo dataset.
fig.add_hline(
    y=entry, line_dash="solid",
    annotation_text=f"ENTRADA {entry:.2f}",
    annotation_position="top left"
)
fig.add_hline(
    y=stop, line_dash="dash",
    annotation_text=f"STOP {stop:.2f}",
    annotation_position="bottom left"
)
fig.add_hline(
    y=take, line_dash="dash",
    annotation_text=f"TAKE {take:.2f}",
    annotation_position="top right"
)
fig.add_hline(
    y=support, line_dash="dot",
    annotation_text=f"SUPORTE {support:.2f}",
    annotation_position="bottom right"
)
fig.add_hline(
    y=resistance, line_dash="dot",
    annotation_text=f"RESISTÊNCIA {resistance:.2f}",
    annotation_position="top right"
)

fig.update_layout(
    height=620,
    template="plotly_dark",
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis_rangeslider_visible=False,
    legend=dict(orientation="h", y=1.02, x=0),
    title=f"XAUUSD — {timeframe} — dados usados na análise"
)

st.plotly_chart(fig, use_container_width=True)

# ---------------- Status da fonte ----------------

st.markdown(
    f"""
    <div class="analysis-box">
        <b>📡 Fonte:</b> {source}<br>
        <b>🕐 Timeframe:</b> {timeframe} &nbsp; | &nbsp;
        <b>📊 Candles:</b> {len(df)} &nbsp; | &nbsp;
        <b>💰 Último preço recebido:</b> {price:.2f}<br>
        <span class="small">
        Última atualização dos dados: {df.index[-1]}
        </span>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------- Painel principal ----------------
st.markdown("#### 📊 Leitura objetiva do mercado")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("PREÇO", f"{price:.2f}", f"{price - float(prev['close']):+.2f}")

with c2:
    st.metric("RSI 14", f"{rsi_value:.1f}")

with c3:
    st.metric("ATR 14", f"{atr_value:.2f}")

with c4:
    st.metric("SCORE", f"{score:+d}/100")

# ---------------- Sinal ----------------
badge_class = "green" if signal == "COMPRA" else "red" if signal == "VENDA" else "gray"

st.markdown(
    f"""
    <div class="signal-card">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <span style="font-size:1.15rem;font-weight:bold;color:{color}">
                    {icon} {signal} — XAUUSD
                </span>
                <span class="badge blue">{timeframe}</span>
                <span class="badge {badge_class}">{confidence:.0f}% confiança</span>
            </div>
            <div class="small">RR 1:{rr:.1f}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

p1, p2, p3 = st.columns(3)

with p1:
    st.metric("ENTRADA", f"{entry:.2f}")

with p2:
    st.metric("STOP", f"{stop:.2f}", f"Risco {abs(entry-stop):.2f}")

with p3:
    st.metric("TAKE", f"{take:.2f}", f"Alvo {abs(take-entry):.2f}")

# ---------------- Indicadores ----------------
st.markdown("#### 🔎 Indicadores")

i1, i2, i3, i4 = st.columns(4)

with i1:
    ema_trend = "Alta" if last["ema9"] > last["ema21"] > last["ema50"] else \
                "Baixa" if last["ema9"] < last["ema21"] < last["ema50"] else "Mista"
    st.metric("Tendência EMA", ema_trend)

with i2:
    macd_status = "Positivo" if last["macd"] > last["macd_signal"] else "Negativo"
    st.metric("MACD", macd_status)

with i3:
    if np.isnan(volume_ratio):
        st.metric("Volume relativo", "N/D")
    else:
        st.metric("Volume relativo", f"{volume_ratio:.2f}x")

with i4:
    adx_display = "N/D" if np.isnan(adx_value) else f"{adx_value:.1f}"
    st.metric("ADX 14 (força)", adx_display, adx_regime.split(" —")[0].split(" (")[0])

# ---------------- Suporte / resistência ----------------
st.markdown("#### 🎯 Níveis técnicos")

structure_status = (
    "Rompimento de alta" if breakout_up else
    "Rompimento de baixa" if breakout_down else
    "Dentro do range"
)

n1, n2, n3 = st.columns(3)

with n1:
    st.metric("Suporte recente", f"{support:.2f}")

with n2:
    st.metric("Preço", f"{price:.2f}")

with n3:
    st.metric("Resistência recente", f"{resistance:.2f}")

n4, n5 = st.columns(2)

with n4:
    st.metric("Topo do range", f"{structure_high:.2f}")

with n5:
    st.metric("Fundo do range", f"{structure_low:.2f}")

st.markdown(
    f'<div class="analysis-box"><b>Estrutura:</b> {structure_status} '
    f'| <b>VWAP:</b> {float(last["vwap"]):.2f} '
    f'| <b>BB:</b> {float(last["bb_lower"]):.2f} — {float(last["bb_upper"]):.2f}</div>',
    unsafe_allow_html=True
)

# ---------------- Diagnóstico ----------------
if signal == "COMPRA":
    perfil = "Viés comprador: médias e momentum favorecem alta."
elif signal == "VENDA":
    perfil = "Viés vendedor: médias e momentum favorecem baixa."
else:
    perfil = "Mercado sem confirmação suficiente para um sinal direcional."

rsi_text = (
    "RSI em região de sobrecompra." if rsi_value >= 70 else
    "RSI em região de sobrevenda." if rsi_value <= 30 else
    "RSI em zona intermediária."
)

filtro_adx_txt = "✅ liberado" if trend_ok else "🚫 bloqueado (mercado lateralizado)"
filtro_di_txt = "✅ fluxo confirma" if di_agrees else "🚫 fluxo (DI) diverge do score"
filtro_persist_txt = "✅ direção estável" if persistence_ok else "🚫 direção mudou recentemente (possível ruído)"

st.markdown(
    f"""
    <div class="analysis-box">
        <b>🧠 Diagnóstico:</b> {perfil}<br>
        <b>RSI:</b> {rsi_text}<br>
        <b>EMA 9:</b> {last['ema9']:.2f} &nbsp; | &nbsp;
        <b>EMA 21:</b> {last['ema21']:.2f} &nbsp; | &nbsp;
        <b>EMA 50:</b> {last['ema50']:.2f}<br>
        <b>MACD:</b> {last['macd']:.4f} &nbsp; | &nbsp;
        <b>Sinal MACD:</b> {last['macd_signal']:.4f}<br>
        <b>Estrutura:</b> {structure_status} &nbsp; | &nbsp;
        <b>VWAP:</b> {float(last['vwap']):.2f}
    </div>
    <div class="analysis-box">
        <b>🧪 Filtros de ruído aplicados ao sinal:</b><br>
        <b>ADX ({adx_regime}):</b> {filtro_adx_txt}<br>
        <b>+DI/-DI:</b> {filtro_di_txt}<br>
        <b>Persistência (últimos candles):</b> {filtro_persist_txt}
    </div>
    """,
    unsafe_allow_html=True
)


# ---------------- Dados utilizados ----------------
with st.expander("📋 Ver candles e valores usados no cálculo"):
    show_cols = ["open", "high", "low", "close", "ema9", "ema21", "ema50", "vwap", "bb_upper", "bb_lower", "rsi", "atr", "macd", "macd_signal"]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(
        df[show_cols].tail(50).round(4),
        use_container_width=True
    )

st.caption(
    "O gráfico técnico acima e o painel usam a mesma série de candles. "
    "Isso evita que o painel mostre níveis calculados de uma fonte diferente do gráfico."
)

st.markdown(
    f'<div class="small">Atualizado em {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}. '
    'Os valores de entrada, stop e take são cálculos técnicos, não garantia de resultado.</div>',
    unsafe_allow_html=True
)
