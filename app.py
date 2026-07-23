"""
app.py
MVP de backtester web - inspirado en StrategyQuant pero simple, gratis y sin descargas.
Corre con: streamlit run app.py
Hosting gratuito recomendado: Streamlit Community Cloud (share.streamlit.io)
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data_loader import load_dukascopy_csv
from engine import StrategyConfig, run_backtest
from metrics import compute_metrics, trades_to_dataframe

st.set_page_config(page_title="Bot Backtester MVP", layout="wide")

st.title("🤖 Bot Backtester — MVP")
st.caption("Sube tu CSV de Dukascopy, configura una estrategia y corre el backtest. Todo en el navegador, sin instalar nada.")

# ---------------- Sidebar: carga de datos y configuración ----------------
st.sidebar.header("1. Datos")
uploaded_file = st.sidebar.file_uploader(
    "Sube tu CSV de Dukascopy",
    type=["csv"],
    help="Descárgalo desde dukascopy.com/swiss/english/marketwatch/historical/ y súbelo aquí. No necesitas tocar el código.",
)

st.sidebar.header("2. Estrategia")
entry_rule = st.sidebar.selectbox(
    "Regla de entrada",
    ["ema_cross", "rsi_reversion", "donchian_breakout"],
    format_func=lambda x: {
        "ema_cross": "Cruce de EMAs",
        "rsi_reversion": "Reversión por RSI",
        "donchian_breakout": "Breakout de canal (Donchian)",
    }[x],
)

with st.sidebar.expander("Parámetros de la regla", expanded=True):
    fast_period = st.number_input("EMA rápida", 2, 200, 12)
    slow_period = st.number_input("EMA lenta", 2, 400, 26)
    rsi_period = st.number_input("Periodo RSI", 2, 100, 14)
    rsi_oversold = st.number_input("RSI sobreventa", 1, 50, 30)
    rsi_overbought = st.number_input("RSI sobrecompra", 50, 99, 70)
    donchian_period = st.number_input("Periodo Donchian", 2, 200, 20)

st.sidebar.header("3. Gestión de riesgo")
atr_period = st.sidebar.number_input("Periodo ATR", 2, 100, 14)
sl_atr_mult = st.sidebar.number_input("SL (múltiplo de ATR)", 0.1, 20.0, 1.5, step=0.1)
tp_atr_mult = st.sidebar.number_input("TP (múltiplo de ATR)", 0.1, 20.0, 3.0, step=0.1)
risk_pct = st.sidebar.number_input("Riesgo por trade (%)", 0.1, 20.0, 1.0, step=0.1)
allow_shorts = st.sidebar.checkbox("Permitir shorts", value=True)
initial_balance = st.sidebar.number_input("Balance inicial", 100.0, 10_000_000.0, 10000.0, step=100.0)
point_value = st.sidebar.number_input(
    "Valor monetario por unidad de precio (point_value)", 0.0001, 100000.0, 1.0,
    help="Para XAUUSD normalmente 1.0 con lotes en onzas; para forex ajusta según tu tamaño de lote."
)

run_button = st.sidebar.button("▶ Correr backtest", type="primary", use_container_width=True)

# ---------------- Área principal ----------------
if uploaded_file is None:
    st.info(
        "👈 Sube un CSV de Dukascopy en el panel izquierdo para empezar.\n\n"
        "**Dónde conseguir la data:** ve a "
        "[dukascopy.com Historical Data Feed](https://www.dukascopy.com/swiss/english/marketwatch/historical/), "
        "elige tu instrumento (ej. XAUUSD), timeframe y rango de fechas, y descarga el CSV. "
        "Luego súbelo aquí — no necesitas poner nada en el código."
    )
    st.stop()

try:
    df = load_dukascopy_csv(uploaded_file)
except Exception as e:
    st.error(f"No pude leer el CSV: {e}")
    st.stop()

st.success(f"Data cargada: {len(df):,} velas, de {df.index.min()} a {df.index.max()}")

if run_button:
    cfg = StrategyConfig(
        entry_rule=entry_rule,
        fast_period=fast_period,
        slow_period=slow_period,
        rsi_period=rsi_period,
        rsi_oversold=rsi_oversold,
        rsi_overbought=rsi_overbought,
        donchian_period=donchian_period,
        atr_period=atr_period,
        sl_atr_mult=sl_atr_mult,
        tp_atr_mult=tp_atr_mult,
        risk_per_trade_pct=risk_pct,
        allow_shorts=allow_shorts,
        initial_balance=initial_balance,
        point_value=point_value,
    )

    with st.spinner("Corriendo backtest..."):
        trades, equity, final_balance = run_backtest(df, cfg)
        stats = compute_metrics(trades, equity, cfg.initial_balance)
        trades_df = trades_to_dataframe(trades)

    st.subheader("📊 Resultados")
    cols = st.columns(4)
    metric_items = list(stats.items())
    for i, (k, v) in enumerate(metric_items):
        cols[i % 4].metric(k, v)

    st.subheader("Curva de Equity")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity.index, y=equity.values, mode="lines", name="Equity"))
    fig.update_layout(height=400, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Trades")
    st.dataframe(trades_df, use_container_width=True)

    if not trades_df.empty:
        csv = trades_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Descargar trades (CSV)", csv, "trades.csv", "text/csv")
else:
    st.info("Configura la estrategia en el panel izquierdo y pulsa **Correr backtest**.")
