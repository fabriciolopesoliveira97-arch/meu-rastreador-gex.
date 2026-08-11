import streamlit as st
from datetime import datetime
import os
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
    api_key = str(st.secrets.get("TWELVEDATA_API_KEY", "") or "").strip()
except Exception:
    api_key = ""

# Também aceita variável de ambiente (útil no Streamlit Cloud/Docker).
if not api_key:
    api_key = os.getenv("TWELVEDATA_API_KEY", "").strip()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📡 Dados reais")
st.sidebar.info(
    "Com TWELVEDATA_API_KEY: tenta Twelve Data primeiro. "
    "Sem chave ou se a API falhar: usa GC=F (ouro futuro) apenas como fallback."
)
st.sidebar.caption(
    "Para XAU/USD spot exato, coloque `TWELVEDATA_API_KEY` em `.streamlit/secrets.toml`. "
    "Sem chave, o app usa GC=F (ouro futuro) como fallback de emergência."
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
        return None, "Twelve Data: API key não configurada."

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
        "outputsize": min(int(outputsize), 5000),
        "apikey": api_key,
        "format": "JSON",
        "order": "ASC"
    }

    try:
        r = requests.get(
            url,
            params=params,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r.raise_for_status()
        data = r.json()

        if "values" not in data:
            msg = data.get("message") or data.get("code") or "Resposta inválida da API."
            return None, f"Twelve Data: {msg}"

        df = pd.DataFrame(data["values"])
        if df.empty:
            return None, "Twelve Data retornou zero candles."

        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "volume" not in df.columns:
            df["volume"] = np.nan

        df = df.dropna(subset=["open", "high", "low", "close"])
        return df.set_index("datetime").sort_index(), "Twelve Data"

    except requests.RequestException as e:
        return None, f"Twelve Data — erro de conexão: {e}"
    except Exception as e:
        return None, f"Twelve Data — erro: {e}"


def load_yahoo_data(interval, outputsize):
    """
    Fallback de emergência para ouro via Yahoo Finance.

    IMPORTANTE: o Yahoo deixou de responder corretamente para XAUUSD=X em
    alguns ambientes (HTTP 400). Por isso usamos GC=F (ouro futuro COMEX)
    apenas como proxy de ouro quando o XAU/USD spot via Twelve Data não
    estiver disponível. O painel identifica explicitamente a fonte.
    """
    try:
        range_map = {
            "1min": "7d",
            "5min": "60d",
            "15min": "60d",
            "30min": "60d",
            "1h": "730d",
            "4h": "365d"
        }

        yahoo_interval = "1h" if interval == "4h" else interval
        params = {
            "range": range_map[interval],
            "interval": yahoo_interval,
            "events": "history",
            "includeAdjustedClose": "true"
        }

        # XAUUSD=X está retornando HTTP 400 em alguns ambientes.
        # GC=F é o contrato futuro de ouro e serve somente como fallback.
        symbols = ["GC=F"]
        errors = []

        for symbol in symbols:
            for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
                try:
                    url = f"https://{host}/v8/finance/chart/{symbol}"
                    r = requests.get(
                        url,
                        params=params,
                        timeout=15,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                          "AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
                            "Accept": "application/json,text/plain,*/*"
                        }
                    )
                    r.raise_for_status()
                    payload = r.json()
                    result = (payload.get("chart") or {}).get("result")
                    if result:
                        result = result[0]
                        timestamps = result.get("timestamp", [])
                        quote = (result.get("indicators") or {}).get("quote", [{}])[0]
                        if timestamps and quote:
                            df = pd.DataFrame({
                                "datetime": pd.to_datetime(timestamps, unit="s", utc=True),
                                "open": quote.get("open", []),
                                "high": quote.get("high", []),
                                "low": quote.get("low", []),
                                "close": quote.get("close", []),
                                "volume": quote.get("volume", [])
                            })
                            for col in ["open", "high", "low", "close", "volume"]:
                                df[col] = pd.to_numeric(df[col], errors="coerce")
                            df = (
                                df.dropna(subset=["open", "high", "low", "close"])
                                  .set_index("datetime")
                                  .sort_index()
                            )
                            if not df.empty:
                                if interval == "4h":
                                    df = df.resample("4h").agg({
                                        "open": "first",
                                        "high": "max",
                                        "low": "min",
                                        "close": "last",
                                        "volume": "sum"
                                    }).dropna(subset=["open", "high", "low", "close"])
                                return df.tail(int(outputsize)), "Yahoo Finance — GC=F (ouro futuro, fallback)"
                    errors.append(f"{symbol}/{host}: resposta sem candles")
                except Exception as e:
                    errors.append(f"{symbol}/{host}: {e}")

        return None, "Yahoo Finance: " + " | ".join(errors[-2:])

    except Exception as e:
        return None, f"Yahoo Finance — erro: {e}"


@st.cache_data(ttl=20)
def get_market_data(interval, outputsize, api_key_present):
    # Prioridade: Twelve Data quando há chave válida.
    errors = []

    if api_key_present:
        df, source = load_twelve_data(interval, outputsize)
        if df is not None and not df.empty:
            return df, source
        errors.append(source)

    # Fallback independente de yfinance.
    df, source = load_yahoo_data(interval, outputsize)
    if df is not None and not df.empty:
        if errors:
            source = f"{source} | Twelve Data indisponível: {errors[-1]}"
        return df, source

    errors.append(source)
    return None, " | ".join(errors)

# ---------------- Carrega mercado ----------------
df, source = get_market_data(timeframe, periods, bool(api_key))

st.markdown("### ⚡ Ouro (XAUUSD) — Análise baseada em mercado")
st.markdown(
    "<p style='color:#888;font-size:.9rem;'>"
    "Preço, indicadores, entrada, stop e alvo são recalculados pelos candles recebidos."
    "</p>",
    unsafe_allow_html=True
)

if df is None or df.empty:
    st.error("❌ Não foi possível obter candles reais para a análise do ouro.")
    st.warning(
        "O aplicativo tentou o XAU/USD pela Twelve Data e, se não disponível, o ouro futuro GC=F pelo Yahoo Finance. "
        "Veja o detalhe abaixo para saber qual serviço bloqueou a conexão."
    )
    st.code(str(source))
    st.info(
        "Para analisar XAU/USD spot exatamente como no TradingView/OANDA, adicione "
        "TWELVEDATA_API_KEY em Settings → Secrets. Sem a chave, o aplicativo usa "
        "GC=F apenas como fallback e identifica isso na fonte."
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

# ---------------- Score de tendência ----------------
score = 0

if last["ema9"] > last["ema21"]:
    score += 20
else:
    score -= 20

if last["ema21"] > last["ema50"]:
    score += 20
else:
    score -= 20

if last["macd"] > last["macd_signal"]:
    score += 20
else:
    score -= 20

if rsi_value >= 55:
    score += 20
elif rsi_value <= 45:
    score -= 20

if price > last["ema50"]:
    score += 20
else:
    score -= 20

# Estrutura recebe peso adicional sem deixar um único rompimento dominar o sinal.
if breakout_up:
    score += 15
elif breakout_down:
    score -= 15

if not np.isnan(last.get("vwap", np.nan)):
    if price > last["vwap"]:
        score += 5
    else:
        score -= 5

score = max(-100, min(100, score))

if score >= 40:
    signal = "COMPRA"
    color = "#00ff88"
    icon = "↗️"
elif score <= -40:
    signal = "VENDA"
    color = "#ff5c6c"
    icon = "↘️"
else:
    signal = "NEUTRO"
    color = "#f5c451"
    icon = "⏸️"

confidence = min(95, max(50, 50 + abs(score) * 0.45))

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
