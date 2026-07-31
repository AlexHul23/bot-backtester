"""
app.py
MVP de backtester web - inspirado en StrategyQuant pero simple, gratis y sin descargas.
Corre con: streamlit run app.py
Hosting gratuito recomendado: Streamlit Community Cloud (share.streamlit.io)
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from data_loader import (
    load_dukascopy_csv, list_local_datasets, load_local_dataset,
    list_hf_datasets, load_hf_dataset,
)
from engine import StrategyConfig, run_backtest
from metrics import compute_metrics, trades_to_dataframe
from optimizer import run_grid_search, PARAM_GRIDS

st.set_page_config(page_title="Bot Backtester MVP", layout="wide")

st.title("🤖 Bot Backtester — MVP")
st.caption("Backtesting de estrategias para MT5, con data integrada. Sin instalar nada.")

# Cambia esto por el repo de dataset que crees en Hugging Face, ej:
# "alexhul23/dukascopy-data". No requiere token para leer si el repo es público.
HF_REPO_ID = "AlexGus1/dukascopy-data"

RULE_LABELS = {
    "ema_cross": "Cruce de EMAs",
    "rsi_reversion": "Reversión por RSI",
    "donchian_breakout": "Breakout de canal (Donchian)",
}


@st.cache_data(show_spinner=False)
def _cached_hf_list(repo_id: str):
    return list_hf_datasets(repo_id)


@st.cache_data(show_spinner=False)
def _cached_hf_load(repo_id: str, filename: str):
    return load_hf_dataset(repo_id, filename)


# ============================================================
# 1. FUENTE DE DATOS (compartida por ambos modos)
# ============================================================
st.sidebar.header("1. Datos")

data_mode = st.sidebar.radio(
    "Fuente de datos",
    ["Hugging Face (recomendado)", "Data local del repo", "Subir mi propio CSV (avanzado)"],
    help="Hugging Face: data pesada fuera de GitHub, sin límite práctico de tamaño. Data local: parquet dentro del repo. Upload: solo para pruebas puntuales.",
)

df = None
if data_mode == "Hugging Face (recomendado)":
    with st.spinner("Consultando dataset en Hugging Face..."):
        hf_files = _cached_hf_list(HF_REPO_ID)

    if not hf_files:
        st.sidebar.warning(
            f"No encontré archivos en `{HF_REPO_ID}` (o el repo aún no existe). "
            "Sube data con `prepare_data.py --upload --repo-id TU_USUARIO/dukascopy-data`, "
            "o cambia HF_REPO_ID al inicio de app.py por el tuyo."
        )
    else:
        dataset_key = st.sidebar.selectbox("Instrumento / Timeframe", hf_files)
        with st.spinner("Descargando de Hugging Face (se cachea, solo tarda la primera vez)..."):
            df = _cached_hf_load(HF_REPO_ID, dataset_key)

elif data_mode == "Data local del repo":
    local_datasets = list_local_datasets()
    if not local_datasets:
        st.sidebar.warning(
            "No hay parquet en la carpeta data/ del repo. Corre `prepare_data.py` "
            "y sube el resultado a `data/` en GitHub, o usa Hugging Face en su lugar."
        )
    else:
        dataset_key = st.sidebar.selectbox("Instrumento / Timeframe", list(local_datasets.keys()))
        df = load_local_dataset(local_datasets[dataset_key])

else:
    uploaded_file = st.sidebar.file_uploader("Sube tu CSV de Dukascopy", type=["csv"])
    if uploaded_file is not None:
        try:
            df = load_dukascopy_csv(uploaded_file)
        except Exception as e:
            st.sidebar.error(f"No pude leer el CSV: {e}")

if df is None:
    st.info(
        "👈 Elige una fuente de datos en el panel izquierdo para empezar.\n\n"
        "**Recomendado:** Hugging Face. Descarga el CSV de "
        "[Dukascopy](https://www.dukascopy.com/swiss/english/marketwatch/historical/), "
        "corre `python prepare_data.py --csv archivo.csv --symbol XAUUSD --timeframe H1 "
        "--upload --repo-id TU_USUARIO/dukascopy-data` en tu computadora, y listo — "
        "la app lo detecta solo, nadie tiene que subir nada de nuevo."
    )
    st.stop()

st.success(f"Data cargada: {len(df):,} velas, de {df.index.min()} a {df.index.max()}")

# ============================================================
# 2. DOS MODOS: manual (si ya sabes qué probar) vs explorar (si no sabes)
# ============================================================
tab_manual, tab_explorar = st.tabs(["🎯 Backtest manual", "🔍 No sé qué estrategia usar — Explorar"])

# --------- Config de riesgo compartida (aplica a ambos modos) ---------
with st.sidebar:
    st.header("2. Gestión de riesgo")
    atr_period = st.number_input("Periodo ATR", 2, 100, 14)
    risk_pct = st.number_input("Riesgo por trade (%)", 0.1, 20.0, 1.0, step=0.1)
    allow_shorts = st.checkbox("Permitir shorts", value=True)
    initial_balance = st.number_input("Balance inicial", 100.0, 10_000_000.0, 10000.0, step=100.0)
    point_value = st.number_input(
        "Valor monetario por unidad de precio", 0.0001, 100000.0, 1.0,
        help="Para XAUUSD normalmente 1.0 con lotes en onzas; para forex ajusta según tu tamaño de lote."
    )

base_cfg_kwargs = dict(
    atr_period=atr_period,
    risk_per_trade_pct=risk_pct,
    allow_shorts=allow_shorts,
    initial_balance=initial_balance,
    point_value=point_value,
)


def show_results(trades, equity, cfg_initial_balance):
    stats = compute_metrics(trades, equity, cfg_initial_balance)
    trades_df = trades_to_dataframe(trades)

    st.subheader("📊 Resultados")
    cols = st.columns(4)
    for i, (k, v) in enumerate(stats.items()):
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


# ============================================================
# TAB 1: Backtest manual (tú eliges los parámetros)
# ============================================================
with tab_manual:
    st.markdown("Elige una regla y sus parámetros a mano. Útil si ya sabes lo que quieres probar.")

    c1, c2 = st.columns([1, 2])
    with c1:
        entry_rule = st.selectbox(
            "Regla de entrada", list(RULE_LABELS.keys()),
            format_func=lambda x: RULE_LABELS[x], key="manual_rule",
        )
    with c2:
        st.caption({
            "ema_cross": "Sigue tendencia: entra cuando una EMA rápida cruza una lenta. Funciona mejor en mercados con tendencia clara.",
            "rsi_reversion": "Reversión: entra cuando el precio está sobrevendido/sobrecomprado, apostando a que rebota. Funciona mejor en rangos, no en tendencias fuertes.",
            "donchian_breakout": "Breakout: entra cuando el precio rompe el máximo/mínimo de N velas. Funciona bien al inicio de tendencias nuevas.",
        }[entry_rule])

    with st.expander("Parámetros de la regla", expanded=True):
        params = {}
        if entry_rule == "ema_cross":
            params["fast_period"] = st.number_input("EMA rápida", 2, 200, 12)
            params["slow_period"] = st.number_input("EMA lenta", 2, 400, 26)
        elif entry_rule == "rsi_reversion":
            params["rsi_period"] = st.number_input("Periodo RSI", 2, 100, 14)
            params["rsi_oversold"] = st.number_input("RSI sobreventa", 1, 50, 30)
            params["rsi_overbought"] = st.number_input("RSI sobrecompra", 50, 99, 70)
        elif entry_rule == "donchian_breakout":
            params["donchian_period"] = st.number_input("Periodo Donchian", 2, 200, 20)

    c3, c4 = st.columns(2)
    with c3:
        sl_atr_mult = st.number_input("SL (múltiplo de ATR)", 0.1, 20.0, 1.5, step=0.1, key="manual_sl")
    with c4:
        tp_atr_mult = st.number_input("TP (múltiplo de ATR)", 0.1, 20.0, 3.0, step=0.1, key="manual_tp")

    if st.button("▶ Correr backtest", type="primary", key="run_manual"):
        cfg = StrategyConfig(
            entry_rule=entry_rule, sl_atr_mult=sl_atr_mult, tp_atr_mult=tp_atr_mult,
            **params, **base_cfg_kwargs,
        )
        with st.spinner("Corriendo backtest..."):
            trades, equity, final_balance = run_backtest(df, cfg)
        show_results(trades, equity, cfg.initial_balance)

# ============================================================
# TAB 2: Explorar automáticamente (grid search)
# ============================================================
with tab_explorar:
    st.markdown(
        "No necesitas saber de trading para empezar aquí: elige una familia de reglas "
        "(o corre las tres) y la app prueba automáticamente varias combinaciones de "
        "parámetros, rankeadas por Profit Factor, Sharpe y control de Drawdown — "
        "los mismos criterios que usarías para validar un bot de prop firm."
    )

    rules_to_test = st.multiselect(
        "Reglas a explorar",
        list(RULE_LABELS.keys()),
        default=list(RULE_LABELS.keys()),
        format_func=lambda x: RULE_LABELS[x],
    )
    max_combos = st.slider("Combinaciones máximas por regla (más = más lento, más completo)", 10, 150, 50, step=10)

    if st.button("🔍 Buscar mejores configuraciones", type="primary"):
        all_results = []
        with st.spinner("Probando combinaciones... esto puede tardar unos segundos"):
            for rule in rules_to_test:
                res = run_grid_search(df, rule, base_cfg_kwargs, max_combos=max_combos)
                if not res.empty:
                    res.insert(0, "rule", RULE_LABELS[rule])
                    all_results.append(res)

        if not all_results:
            st.warning("Ninguna combinación generó suficientes trades para evaluar. Prueba con más data o más combinaciones.")
        else:
            combined = pd.concat(all_results, ignore_index=True).sort_values("score", ascending=False).reset_index(drop=True)
            st.session_state["explorer_results"] = combined
            st.session_state["explorer_df_key"] = id(df)

    if "explorer_results" in st.session_state:
        combined = st.session_state["explorer_results"]
        st.subheader(f"🏆 Top {min(20, len(combined))} configuraciones encontradas")
        st.caption("Ordenadas por score (combina Profit Factor, Sharpe y Drawdown). No garantizan resultados futuros — valida siempre con walk-forward antes de operar en real.")
        st.dataframe(combined.head(20), use_container_width=True)

        st.markdown("**Corre el backtest completo de una fila específica:**")
        row_idx = st.number_input("Índice de la fila (0 = la mejor)", 0, len(combined) - 1, 0)

        if st.button("▶ Ver curva de equity de esta configuración"):
            chosen = combined.iloc[int(row_idx)]
            rule_key = [k for k, v in RULE_LABELS.items() if v == chosen["rule"]][0]
            rule_param_names = list(PARAM_GRIDS.get(rule_key, {}).keys())

            cfg_kwargs = dict(base_cfg_kwargs)
            cfg_kwargs["entry_rule"] = rule_key
            cfg_kwargs["sl_atr_mult"] = chosen["sl_atr_mult"]
            cfg_kwargs["tp_atr_mult"] = chosen["tp_atr_mult"]
            for p in rule_param_names:
                cfg_kwargs[p] = chosen[p]

            cfg = StrategyConfig(**cfg_kwargs)
            with st.spinner("Corriendo backtest completo..."):
                trades, equity, final_balance = run_backtest(df, cfg)
            show_results(trades, equity, cfg.initial_balance)
