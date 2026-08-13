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

# API key: mantém suporte ao Streamlit Secrets e permite
# inserir a chave diretamente pela barra lateral.
secret_api_key = ""
try:
    secret_api_key = st.secrets.get("TWELVEDATA_API_KEY", "")
except Exception:
    secret_api_key = ""

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔑 Twelve Data")
api_key_input = st.sidebar.text_input(
    "TWELVEDATA API KEY",
    value=secret_api_key,
    type="password",
    help="Cole aqui sua chave da Twelve Data. A chave também pode ficar em .streamlit/secrets.toml."
)
api_key = api_key_input.strip() or secret_api_key

st.sidebar.markdown("### 📡 Dados reais")
st.sidebar.info(
    "Com TWELVEDATA_API_KEY: usa XAU/USD via Twelve Data. "
    "Sem chave: tenta Yahoo Finance."
)
st.sidebar.caption(
    "Você pode colocar a chave nesta caixa ou em "
    "`.streamlit/secrets.toml`."
)


# ---------------- TradingView — gráfico visual ----------------
# Mantido separado do cálculo da estratégia:
# o TradingView serve para visualização, enquanto os sinais continuam
# sendo calculados pelos candles recebidos pela fonte de dados.
st.markdown("### 📈 Gráfico TradingView")

tv_symbol_js = symbol_tv.replace(":", "%3A")
tv_embed_url = (
    "https://www.tradingview.com/widgetembed/?"
    f"symbol={tv_symbol_js}"
    f"&interval={tv_interval}"
    "&hidesidetoolbar=0"
    "&symboledit=1"
    "&saveimage=1"
    "&toolbarbg=f1f3f6"
    "&studies=[]"
    "&theme=dark"
    "&style=1"
    "&timezone=America%2FSao_Paulo"
    "&withdateranges=1"
    "&hideideas=1"
)

components.html(
    f"""
    <div style="width:100%;height:620px;">
        <iframe
            src="{tv_embed_url}"
            style="width:100%;height:100%;border:0;"
            allowtransparency="true"
            frameborder="0"
            scrolling="no">
        </iframe>
    </div>
    """,
    height=620,
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
        "Não foi possível obter os candles reais. "
        "Configure TWELVEDATA_API_KEY ou verifique a conexão/instalação do yfinance."
    )
    st.stop()

# ---------------- Cálculos ----------------
df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
df["rsi"] = rsi(df["close"], 14)
df["atr"] = atr(df, 14)

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
breakout_up = price > structure_high
breakout_down = price < structure_low

# ---------------- Filtros adicionais da V2 ----------------
def adx_calc(data, period=14):
    high, low, close = data["high"], data["low"], data["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(
        np.where((up > down) & (up > 0), up, 0.0),
        index=data.index
    )
    minus_dm = pd.Series(
        np.where((down > up) & (down > 0), down, 0.0),
        index=data.index
    )
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr_n = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_n.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_n.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False).mean(), plus_di, minus_di

df["adx"], df["plus_di"], df["minus_di"] = adx_calc(df, 14)

# Recarrega a última linha após adicionar os indicadores da V2.
# O objeto `last` criado anteriormente é uma cópia da linha e não
# recebe automaticamente as novas colunas.
last = df.iloc[-1]

def price_action_flags(data):
    if len(data) < 3:
        return {"bullish": False, "bearish": False}

    a, b = data.iloc[-2], data.iloc[-1]
    a_body = abs(a["close"] - a["open"])
    b_body = abs(b["close"] - b["open"])
    b_range = max(b["high"] - b["low"], 1e-9)

    bull_pin = (
        b["close"] > b["open"]
        and (min(b["open"], b["close"]) - b["low"]) >= b_body * 1.5
        and (b["high"] - max(b["open"], b["close"])) <= b_range * 0.35
    )
    bear_pin = (
        b["close"] < b["open"]
        and (b["high"] - max(b["open"], b["close"])) >= b_body * 1.5
        and (min(b["open"], b["close"]) - b["low"]) <= b_range * 0.35
    )
    bull_engulf = (
        a["close"] < a["open"] and b["close"] > b["open"]
        and b["open"] <= a["close"] and b["close"] >= a["open"]
        and b_body >= a_body
    )
    bear_engulf = (
        a["close"] > a["open"] and b["close"] < b["open"]
        and b["open"] >= a["close"] and b["close"] <= a["open"]
        and b_body >= a_body
    )
    return {
        "bullish": bool(bull_pin or bull_engulf),
        "bearish": bool(bear_pin or bear_engulf)
    }

pa = price_action_flags(df)
adx_value = float(last["adx"])
plus_di_value = float(last["plus_di"])
minus_di_value = float(last["minus_di"])

# Rompimento + reteste.
retest_tolerance = max(atr_value * 0.35, price * 0.00035)
recent6 = df.tail(min(6, len(df)))
bull_retest = bool(
    (recent6["low"] <= structure_high + retest_tolerance).any()
    and price > structure_high
)
bear_retest = bool(
    (recent6["high"] >= structure_low - retest_tolerance).any()
    and price < structure_low
)

# Filtro de preço muito esticado.
ema21_value = float(last["ema21"])
vwap_now = float(last["vwap"])
stretch_ema_atr = abs(price - ema21_value) / max(atr_value, 1e-9)
stretch_vwap_atr = abs(price - vwap_now) / max(atr_value, 1e-9)
stretched = bool(
    stretch_ema_atr >= 2.2
    or stretch_vwap_atr >= 2.5
    or price >= float(last["bb_upper"])
    or price <= float(last["bb_lower"])
)

# Confirmação 15m + 1h.
confirm15_df, confirm15_source = get_market_data("15min", max(periods, 200))
if confirm15_df is not None and len(confirm15_df) >= 60:
    confirm15_df = confirm15_df.copy()
    confirm15_df["ema9"] = confirm15_df["close"].ewm(span=9, adjust=False).mean()
    confirm15_df["ema21"] = confirm15_df["close"].ewm(span=21, adjust=False).mean()
    confirm15_df["ema50"] = confirm15_df["close"].ewm(span=50, adjust=False).mean()
    confirm15_df["macd"] = (
        confirm15_df["close"].ewm(span=12, adjust=False).mean()
        - confirm15_df["close"].ewm(span=26, adjust=False).mean()
    )
    confirm15_df["macd_signal"] = confirm15_df["macd"].ewm(span=9, adjust=False).mean()
    confirm15_df["adx"], confirm15_df["plus_di"], confirm15_df["minus_di"] = adx_calc(confirm15_df, 14)

    c15 = confirm15_df.iloc[-1]
    m15_bull = bool(
        c15["ema9"] > c15["ema21"] > c15["ema50"]
        and c15["macd"] > c15["macd_signal"]
        and c15["adx"] >= 20
    )
    m15_bear = bool(
        c15["ema9"] < c15["ema21"] < c15["ema50"]
        and c15["macd"] < c15["macd_signal"]
        and c15["adx"] >= 20
    )
else:
    m15_bull = m15_bear = False
    confirm15_source = "Indisponível"

confirm1h_df, confirm1h_source = get_market_data("1h", max(periods, 200))
if confirm1h_df is not None and len(confirm1h_df) >= 60:
    confirm1h_df = confirm1h_df.copy()
    confirm1h_df["ema9"] = confirm1h_df["close"].ewm(span=9, adjust=False).mean()
    confirm1h_df["ema21"] = confirm1h_df["close"].ewm(span=21, adjust=False).mean()
    confirm1h_df["ema50"] = confirm1h_df["close"].ewm(span=50, adjust=False).mean()
    confirm1h_df["macd"] = (
        confirm1h_df["close"].ewm(span=12, adjust=False).mean()
        - confirm1h_df["close"].ewm(span=26, adjust=False).mean()
    )
    confirm1h_df["macd_signal"] = confirm1h_df["macd"].ewm(span=9, adjust=False).mean()
    confirm1h_df["adx"], confirm1h_df["plus_di"], confirm1h_df["minus_di"] = adx_calc(confirm1h_df, 14)

    c1h = confirm1h_df.iloc[-1]
    h1_bull = bool(
        c1h["ema9"] > c1h["ema21"] > c1h["ema50"]
        and c1h["macd"] > c1h["macd_signal"]
        and c1h["adx"] >= 20
    )
    h1_bear = bool(
        c1h["ema9"] < c1h["ema21"] < c1h["ema50"]
        and c1h["macd"] < c1h["macd_signal"]
        and c1h["adx"] >= 20
    )
else:
    h1_bull = h1_bear = False
    confirm1h_source = "Indisponível"

# ---------------- Score separado de COMPRA e VENDA ----------------
buy_score = 0
sell_score = 0
buy_reasons = []
sell_reasons = []

def check_buy(condition, points, text):
    global buy_score
    if condition:
        buy_score += points
        buy_reasons.append(f"✅ {text} (+{points})")
    else:
        buy_reasons.append(f"❌ {text}")

def check_sell(condition, points, text):
    global sell_score
    if condition:
        sell_score += points
        sell_reasons.append(f"✅ {text} (+{points})")
    else:
        sell_reasons.append(f"❌ {text}")

check_buy(last["ema9"] > last["ema21"] > last["ema50"], 15, "EMA 9 > 21 > 50")
check_sell(last["ema9"] < last["ema21"] < last["ema50"], 15, "EMA 9 < 21 < 50")
check_buy(adx_value >= 20 and plus_di_value > minus_di_value, 12, f"ADX {adx_value:.1f} + DI comprador")
check_sell(adx_value >= 20 and minus_di_value > plus_di_value, 12, f"ADX {adx_value:.1f} + DI vendedor")
check_buy(price > vwap_now, 10, "Preço acima da VWAP")
check_sell(price < vwap_now, 10, "Preço abaixo da VWAP")
check_buy(
    last["macd"] > last["macd_signal"] and last["macd_hist"] > 0,
    10, "MACD comprador"
)
check_sell(
    last["macd"] < last["macd_signal"] and last["macd_hist"] < 0,
    10, "MACD vendedor"
)
check_buy(50 <= rsi_value <= 68, 8, f"RSI favorável {rsi_value:.1f}")
check_sell(32 <= rsi_value <= 50, 8, f"RSI favorável {rsi_value:.1f}")
check_buy(pa["bullish"], 10, "Price Action bullish")
check_sell(pa["bearish"], 10, "Price Action bearish")
check_buy(breakout_up and bull_retest, 15, "Rompimento + reteste de alta")
check_sell(breakout_down and bear_retest, 15, "Rompimento + reteste de baixa")
check_buy(m15_bull, 8, "Confirmação 15m bullish")
check_sell(m15_bear, 8, "Confirmação 15m bearish")
check_buy(h1_bull, 10, "Confirmação 1h bullish")
check_sell(h1_bear, 10, "Confirmação 1h bearish")

if stretched:
    if price > ema21_value:
        sell_score += 4
        buy_reasons.append("⚠️ Preço esticado na alta")
        sell_reasons.append("✅ Esticamento favorece correção (+4)")
    else:
        buy_score += 4
        buy_reasons.append("✅ Esticamento favorece correção (+4)")
        sell_reasons.append("⚠️ Preço esticado na baixa")
else:
    buy_reasons.append("✅ Preço não está muito esticado")
    sell_reasons.append("✅ Preço não está muito esticado")

buy_score = int(min(100, buy_score))
sell_score = int(min(100, sell_score))
score = buy_score - sell_score

trend_ok = adx_value >= 20
score_gap = abs(buy_score - sell_score)
min_entry_score = 65

if not trend_ok:
    status, signal, status_reason = (
        "EVITAR", "NEUTRO",
        f"ADX {adx_value:.1f} abaixo de 20: mercado sem tendência suficiente."
    )
elif stretched and (
    (price > ema21_value and buy_score > sell_score)
    or (price < ema21_value and sell_score > buy_score)
):
    status, signal, status_reason = (
        "EVITAR", "NEUTRO",
        "Preço excessivamente esticado; aguarde correção."
    )
elif breakout_up and not bull_retest:
    status, signal, status_reason = (
        "AGUARDAR PULLBACK", "COMPRA",
        "Rompimento de alta detectado, aguardando reteste."
    )
elif breakout_down and not bear_retest:
    status, signal, status_reason = (
        "AGUARDAR PULLBACK", "VENDA",
        "Rompimento de baixa detectado, aguardando reteste."
    )
elif buy_score >= min_entry_score and buy_score > sell_score + 8 and m15_bull and h1_bull:
    status, signal, status_reason = (
        "ENTRADA", "COMPRA",
        "Score comprador + 15m + 1h + tendência alinhados."
    )
elif sell_score >= min_entry_score and sell_score > buy_score + 8 and m15_bear and h1_bear:
    status, signal, status_reason = (
        "ENTRADA", "VENDA",
        "Score vendedor + 15m + 1h + tendência alinhados."
    )
elif max(buy_score, sell_score) >= 50 and score_gap < 10:
    status, signal, status_reason = (
        "EVITAR", "NEUTRO",
        "Compra e venda estão sem vantagem clara."
    )
else:
    status = "AGUARDAR PULLBACK"
    signal = "COMPRA" if buy_score > sell_score else "VENDA"
    status_reason = "Há viés, mas ainda falta confirmação para entrada."

if signal == "COMPRA":
    color, icon = "#00ff88", "↗️"
elif signal == "VENDA":
    color, icon = "#ff5c6c", "↘️"
else:
    color, icon = "#f5c451", "⏸️"

confidence = int(min(95, max(50, 50 + abs(score) * 0.45)))

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

i1, i2, i3 = st.columns(3)

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
