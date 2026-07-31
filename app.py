"""
app.py
Bot Backtester — MVP con flujo simple para personas sin experiencia en trading.
Hugging Face es la fuente de datos por defecto. El modo experto (parámetros
manuales) queda disponible pero colapsado al fondo.
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

st.set_page_config(page_title="Bot Backtester", layout="wide", initial_sidebar_state="collapsed")

# Cambia esto por tu dataset de Hugging Face.
HF_REPO_ID = "AlexGus1/dukascopy-data"

RULE_LABELS = {
    "ema_cross": "Sigue la tendencia",
    "rsi_reversion": "Aprovecha rebotes",
    "donchian_breakout": "Rompe máximos y mínimos",
    "smc_confluence": "Smart Money (estructura + liquidez)",
}
RULE_DESCRIPTIONS = {
    "ema_cross": "Entra cuando el precio arranca un movimiento claro en una dirección, y se queda montado mientras dura.",
    "rsi_reversion": "Entra cuando el precio se movió demasiado rápido y es probable que rebote en la dirección contraria.",
    "donchian_breakout": "Entra cuando el precio rompe un máximo o mínimo reciente, apostando a que sigue rompiendo.",
    "smc_confluence": "Entra en el retroceso posterior a un rompimiento de estructura: precio en zona barata (discount), tocando una zona de order block o Fair Value Gap, confirmado con una vela de rechazo.",
}


@st.cache_data(show_spinner=False)
def _cached_hf_list(repo_id: str):
    return list_hf_datasets(repo_id)


@st.cache_data(show_spinner=False)
def _cached_hf_load(repo_id: str, filename: str):
    return load_hf_dataset(repo_id, filename)


# ============================================================
# ESTILOS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: linear-gradient(180deg, #F3F7FD 0%, #E7EEFA 100%); }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 1180px; }

h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; color: #14151A; }

.app-eyebrow {
  display:inline-block; padding:5px 14px; border-radius:999px;
  background:#14151A; color:#D6FF3F; font-size:12px; font-weight:600;
  letter-spacing:.04em; text-transform:uppercase; margin-bottom:14px;
}
.app-title { font-size:36px; font-weight:700; color:#14151A; margin:0 0 6px 0; line-height:1.1; }
.app-sub { color:#6B7280; font-size:15.5px; margin:0 0 28px 0; max-width:640px; }

.stat-card {
  background:#FFFFFF; border-radius:18px; padding:20px 22px;
  box-shadow:0 8px 24px rgba(20,21,26,0.06); border:1px solid rgba(20,21,26,0.06);
  height:100%;
}
.stat-label{font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px;font-weight:600;}
.stat-value{font-size:25px;font-weight:700;color:#14151A;font-family:'Space Grotesk',sans-serif;}
.stat-value.positive{color:#2F9E52;}
.stat-value.negative{color:#E1523D;}

.rank-card {
  background:#14151A; border-radius:20px; padding:8px; margin-bottom:18px;
}
.rank-row {
  display:flex; justify-content:space-between; align-items:center;
  padding:16px 18px; border-radius:14px; margin-bottom:4px;
}
.rank-row.winner { background:#D6FF3F; }
.rank-row:not(.winner) { background:transparent; }
.rank-name { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:16px; color:#FFFFFF; }
.rank-row.winner .rank-name { color:#14151A; }
.rank-sub { font-size:12.5px; color:rgba(255,255,255,0.55); margin-top:2px; }
.rank-row.winner .rank-sub { color:rgba(20,21,26,0.65); }
.rank-metric { text-align:right; font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:17px; color:#FFFFFF; }
.rank-row.winner .rank-metric { color:#14151A; }
.rank-badge {
  display:inline-block; font-size:11px; font-weight:700; padding:3px 9px; border-radius:999px;
  background:rgba(255,255,255,0.12); color:#fff; margin-right:8px;
}
.rank-row.winner .rank-badge { background:rgba(20,21,26,0.12); color:#14151A; }

.detail-card {
  background:#FFFFFF; border-radius:22px; padding:28px 30px;
  box-shadow:0 8px 24px rgba(20,21,26,0.06); border:1px solid rgba(20,21,26,0.06);
}
.detail-headline { font-size:20px; font-family:'Space Grotesk',sans-serif; font-weight:700; color:#14151A; margin-bottom:6px; }
.detail-copy { color:#4B5563; font-size:14.5px; line-height:1.55; margin-bottom:18px; }

.pill { display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; background:rgba(20,21,26,.06); color:#6B7280; margin-right:6px;}
.pill.accent { background:#D6FF3F; color:#14151A; }

div.stButton > button {
  border-radius: 999px !important; font-weight:600 !important; font-family:'Inter',sans-serif !important;
}
div.stButton > button[kind="primary"] {
  background:#14151A !important; color:#D6FF3F !important; border:none !important;
  padding:0.65rem 1.8rem !important; font-family:'Space Grotesk',sans-serif !important; font-size:15px !important;
}
div.stButton > button[kind="primary"]:hover { background:#000000 !important; }
</style>
""", unsafe_allow_html=True)


def stat_card(label, value, css_class=""):
    return f"""<div class="stat-card"><div class="stat-label">{label}</div>
    <div class="stat-value {css_class}">{value}</div></div>"""


def plain_summary(stats: dict, initial_balance: float) -> str:
    net_pct = stats["Net Profit %"]
    dd = abs(stats["Max Drawdown %"])
    trades = stats["Total Trades"]
    tono = "positive" if net_pct > 0 else "negative"
    signo = "+" if net_pct > 0 else ""
    return (
        f'Con ${initial_balance:,.0f} de balance inicial, esta estrategia habría terminado con '
        f'<span class="{tono}" style="font-weight:700;">{signo}{net_pct:.1f}%</span> en el periodo probado, '
        f'a lo largo de {trades} operaciones. En el peor momento, la cuenta llegó a caer <b>{dd:.1f}%</b> desde su punto más alto.'
    )


def plot_equity(equity: pd.Series):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity.index, y=equity.values, mode="lines", name="Balance",
        line=dict(color="#14151A", width=2.5),
        fill="tozeroy", fillcolor="rgba(214,255,63,0.25)",
    ))
    fig.update_layout(
        height=320, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#6B7280"),
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor="rgba(20,21,26,0.06)"),
    )
    return fig


# ============================================================
# HEADER
# ============================================================
st.markdown('<div class="app-eyebrow">Bot Backtester</div>', unsafe_allow_html=True)
st.markdown('<div class="app-title">Encuentra una estrategia que funcione</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-sub">No necesitas saber de trading. Elige un instrumento, '
    'presiona un botón, y probamos automáticamente decenas de configuraciones '
    'sobre datos históricos reales — te mostramos las que mejor se comportaron.</div>',
    unsafe_allow_html=True,
)

# ============================================================
# FUENTE DE DATOS — Hugging Face por defecto, todo lo demás oculto
# ============================================================
df = None
dataset_label = None

with st.spinner("Cargando instrumentos disponibles..."):
    hf_files = _cached_hf_list(HF_REPO_ID)

col_sel, col_adv = st.columns([3, 2])
with col_sel:
    if hf_files:
        dataset_key = st.selectbox("Instrumento", hf_files, label_visibility="visible")
        with st.spinner("Descargando datos (solo la primera vez)..."):
            df = _cached_hf_load(HF_REPO_ID, dataset_key)
        dataset_label = dataset_key
    else:
        st.warning(f"No encontré datos en Hugging Face (`{HF_REPO_ID}`). Usa la fuente avanzada →")

with col_adv:
    with st.expander("Usar otra fuente de datos"):
        alt_mode = st.radio("Fuente", ["Data local del repo", "Subir mi propio CSV"], label_visibility="collapsed")
        if alt_mode == "Data local del repo":
            local_datasets = list_local_datasets()
            if local_datasets:
                key = st.selectbox("Instrumento (local)", list(local_datasets.keys()))
                df = load_local_dataset(local_datasets[key])
                dataset_label = key
            else:
                st.caption("No hay parquet en data/ del repo.")
        else:
            uploaded_file = st.file_uploader("CSV de Dukascopy", type=["csv"])
            if uploaded_file is not None:
                try:
                    df = load_dukascopy_csv(uploaded_file)
                    dataset_label = uploaded_file.name
                except Exception as e:
                    st.error(f"No pude leer el CSV: {e}")

if df is None:
    st.stop()

# ============================================================
# CONFIG DE RIESGO — valores por defecto sensatos, ocultos
# ============================================================
with st.expander("⚙️ Ajustes avanzados (opcional — valores por defecto ya son razonables)"):
    c1, c2, c3 = st.columns(3)
    with c1:
        initial_balance = st.number_input("Balance inicial", 100.0, 10_000_000.0, 10000.0, step=100.0)
        risk_pct = st.number_input("Riesgo por operación (%)", 0.1, 20.0, 1.0, step=0.1)
    with c2:
        atr_period = st.number_input("Periodo ATR", 2, 100, 14)
        allow_shorts = st.checkbox("Permitir operaciones en corto", value=True)
    with c3:
        point_value = st.number_input("Valor monetario por punto", 0.0001, 100000.0, 1.0)
        max_combos = st.slider("Combinaciones a probar por estrategia", 10, 150, 50, step=10)

base_cfg_kwargs = dict(
    atr_period=atr_period, risk_per_trade_pct=risk_pct, allow_shorts=allow_shorts,
    initial_balance=initial_balance, point_value=point_value,
)

# ============================================================
# BÚSQUEDA PRINCIPAL
# ============================================================
st.markdown(f'<span class="pill">📊 {len(df):,} velas cargadas</span>'
            f'<span class="pill">🗓 {df.index.min().date()} → {df.index.max().date()}</span>',
            unsafe_allow_html=True)
st.write("")

if st.button("🔍 Buscar la mejor estrategia para mí", type="primary"):
    all_results = []
    with st.spinner("Probando configuraciones sobre el histórico... esto tarda unos segundos"):
        for rule in RULE_LABELS.keys():
            res = run_grid_search(df, rule, base_cfg_kwargs, max_combos=max_combos)
            if not res.empty:
                res.insert(0, "rule", rule)
                all_results.append(res)

    if not all_results:
        st.warning("Ninguna configuración generó suficientes operaciones para evaluar con este instrumento y periodo.")
    else:
        combined = pd.concat(all_results, ignore_index=True).sort_values("score", ascending=False).reset_index(drop=True)
        st.session_state["results"] = combined
        st.session_state["selected_idx"] = 0
        st.session_state["results_dataset"] = dataset_label

# ============================================================
# RESULTADOS
# ============================================================
if "results" in st.session_state:
    combined = st.session_state["results"]
    top = combined.head(5)

    st.write("")
    stat_cols = st.columns(4)
    best = top.iloc[0]
    stat_cols[0].markdown(stat_card("Configuraciones probadas", len(combined)), unsafe_allow_html=True)
    stat_cols[1].markdown(stat_card("Mejor Profit Factor", best["Profit Factor"]), unsafe_allow_html=True)
    dd_val = abs(best["Max Drawdown %"])
    stat_cols[2].markdown(stat_card("Caída máxima (la mejor)", f"{dd_val:.1f}%",
                                     "negative" if dd_val > 20 else ""), unsafe_allow_html=True)
    stat_cols[3].markdown(stat_card("Operaciones (la mejor)", int(best["Total Trades"])), unsafe_allow_html=True)

    st.write("")
    col_list, col_detail = st.columns([1, 1.4])

    with col_list:
        st.markdown("#### Mejores configuraciones encontradas")
        st.markdown('<div class="rank-card">', unsafe_allow_html=True)
        for i, row in top.iterrows():
            is_winner = (i == 0)
            css = "rank-row winner" if is_winner else "rank-row"
            badge = "🏆 #1" if is_winner else f"#{i + 1}"
            net_pct = row["Net Profit %"]
            st.markdown(f"""
            <div class="{css}">
              <div>
                <span class="rank-badge">{badge}</span>
                <span class="rank-name">{RULE_LABELS[row['rule']]}</span>
                <div class="rank-sub">PF {row['Profit Factor']} · {int(row['Total Trades'])} operaciones</div>
              </div>
              <div class="rank-metric">{'+' if net_pct > 0 else ''}{net_pct:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Ver detalle #{i + 1}", key=f"select_{i}", use_container_width=True):
                st.session_state["selected_idx"] = i
        st.markdown('</div>', unsafe_allow_html=True)

    with col_detail:
        sel_idx = st.session_state.get("selected_idx", 0)
        chosen = combined.iloc[int(sel_idx)]
        rule_key = chosen["rule"]
        rule_param_names = list(PARAM_GRIDS.get(rule_key, {}).keys())

        cfg_kwargs = dict(base_cfg_kwargs)
        cfg_kwargs["entry_rule"] = rule_key
        cfg_kwargs["sl_atr_mult"] = chosen["sl_atr_mult"]
        cfg_kwargs["tp_atr_mult"] = chosen["tp_atr_mult"]
        for p in rule_param_names:
            cfg_kwargs[p] = chosen[p]

        cfg = StrategyConfig(**cfg_kwargs)
        with st.spinner("Cargando detalle..."):
            trades, equity, final_balance = run_backtest(df, cfg)
        stats = compute_metrics(trades, equity, cfg.initial_balance)

        st.markdown('<div class="detail-card">', unsafe_allow_html=True)
        st.markdown(f'<div class="detail-headline">{RULE_LABELS[rule_key]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="detail-copy">{RULE_DESCRIPTIONS[rule_key]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="detail-copy">{plain_summary(stats, cfg.initial_balance)}</div>', unsafe_allow_html=True)
        st.plotly_chart(plot_equity(equity), use_container_width=True, config={"displayModeBar": False})

        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(stat_card("Profit Factor", stats["Profit Factor"]), unsafe_allow_html=True)
        m2.markdown(stat_card("Sharpe (aprox)", stats["Sharpe (aprox)"]), unsafe_allow_html=True)
        m3.markdown(stat_card("Win rate", f'{stats["Win Rate %"]}%'), unsafe_allow_html=True)
        m4.markdown(stat_card("Operaciones", stats["Total Trades"]), unsafe_allow_html=True)

        with st.expander("Ver todas las operaciones"):
            trades_df = trades_to_dataframe(trades)
            st.dataframe(trades_df, use_container_width=True)
            if not trades_df.empty:
                csv = trades_df.to_csv(index=False).encode("utf-8")
                st.download_button("⬇ Descargar operaciones (CSV)", csv, "trades.csv", "text/csv")
        st.markdown('</div>', unsafe_allow_html=True)

st.write("")
st.write("")

# ============================================================
# REPRODUCTOR DE VELAS — para comprobar visualmente que las señales SMC
# se detectan en el momento correcto, sin look-ahead.
# ============================================================
with st.expander("🎞 Reproductor de velas — comprobar detección SMC vela por vela"):
    st.caption(
        "Avanza vela por vela y revisa que los eventos (BOS, CHoCH, Order Blocks, FVG) "
        "aparecen cuando deberían — no antes. Si ves una señal marcada en una vela y el "
        "patrón que la originó todavía no se ve completo en el gráfico, hay un problema "
        "de look-ahead que hay que corregir antes de confiar en el backtest."
    )

    import smc as smc_module

    @st.cache_data(show_spinner=False)
    def _cached_smc_build(_df, df_key):
        return smc_module.build_smc_dataframe(_df)

    smc_df = _cached_smc_build(df, dataset_label)

    window_size = st.slider("Velas visibles en el gráfico", 40, 300, 120, step=20)
    max_idx = len(smc_df) - 1
    default_start = max(window_size, min(max_idx, window_size * 3))
    current_idx = st.slider("Posición (vela actual)", window_size, max_idx, default_start)

    view = smc_df.iloc[max(0, current_idx - window_size):current_idx + 1]

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=view.index, open=view["Open"], high=view["High"], low=view["Low"], close=view["Close"],
        increasing_line_color="#2F9E52", decreasing_line_color="#E1523D", name="Precio",
    ))

    def _markers(mask_col, y_col, symbol, color, label):
        sub = view[view[mask_col] == True]
        if sub.empty:
            return
        fig.add_trace(go.Scatter(
            x=sub.index, y=sub[y_col], mode="markers", name=label,
            marker=dict(symbol=symbol, size=11, color=color, line=dict(width=1, color="#14151A")),
        ))

    _markers("bos_bull", "Low", "triangle-up", "#2F9E52", "BOS alcista")
    _markers("bos_bear", "High", "triangle-down", "#E1523D", "BOS bajista")
    _markers("choch_bull", "Low", "star", "#D6FF3F", "CHoCH alcista")
    _markers("choch_bear", "High", "star", "#F97316", "CHoCH bajista")
    _markers("liquidity_sweep_high", "High", "x", "#9333EA", "Liquidity sweep (alto)")
    _markers("liquidity_sweep_low", "Low", "x", "#9333EA", "Liquidity sweep (bajo)")

    # zonas activas de OB y FVG dentro de la ventana visible, como rectángulos sombreados
    shapes = []
    last_bull_ob = view[["bull_ob_high", "bull_ob_low"]].dropna()
    if not last_bull_ob.empty:
        r = last_bull_ob.iloc[-1]
        shapes.append(dict(type="rect", x0=view.index[0], x1=view.index[-1],
                            y0=r["bull_ob_low"], y1=r["bull_ob_high"],
                            fillcolor="rgba(47,158,82,0.12)", line=dict(width=0), layer="below"))
    last_bear_ob = view[["bear_ob_high", "bear_ob_low"]].dropna()
    if not last_bear_ob.empty:
        r = last_bear_ob.iloc[-1]
        shapes.append(dict(type="rect", x0=view.index[0], x1=view.index[-1],
                            y0=r["bear_ob_low"], y1=r["bear_ob_high"],
                            fillcolor="rgba(225,82,61,0.12)", line=dict(width=0), layer="below"))
    fig.update_layout(shapes=shapes)

    fig.update_layout(
        height=480, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#6B7280"),
        xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
        yaxis=dict(showgrid=True, gridcolor="rgba(20,21,26,0.06)"),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    current_row = smc_df.iloc[current_idx]
    st.markdown(
        f'<span class="pill">Tendencia: {current_row["trend"] or "sin definir"}</span>'
        f'<span class="pill">Zona: {current_row["zone"] or "sin definir"}</span>'
        f'<span class="pill">{"🟢 Kill zone activa" if current_row["kill_zone"] else "Kill zone inactiva"}</span>',
        unsafe_allow_html=True,
    )

st.write("")
st.write("")

# ============================================================
# MODO EXPERTO — parámetros manuales, colapsado al fondo
# ============================================================
with st.expander("🧪 Modo experto — elegir yo mismo los parámetros"):
    st.caption("Para cuando ya sabes qué quieres probar.")
    c1, c2 = st.columns([1, 2])
    with c1:
        entry_rule = st.selectbox("Regla de entrada", list(RULE_LABELS.keys()),
                                   format_func=lambda x: RULE_LABELS[x], key="manual_rule")
    with c2:
        st.caption(RULE_DESCRIPTIONS[entry_rule])

    params = {}
    pc1, pc2, pc3 = st.columns(3)
    if entry_rule == "ema_cross":
        params["fast_period"] = pc1.number_input("EMA rápida", 2, 200, 12)
        params["slow_period"] = pc2.number_input("EMA lenta", 2, 400, 26)
    elif entry_rule == "rsi_reversion":
        params["rsi_period"] = pc1.number_input("Periodo RSI", 2, 100, 14)
        params["rsi_oversold"] = pc2.number_input("RSI sobreventa", 1, 50, 30)
        params["rsi_overbought"] = pc3.number_input("RSI sobrecompra", 50, 99, 70)
    elif entry_rule == "donchian_breakout":
        params["donchian_period"] = pc1.number_input("Periodo Donchian", 2, 200, 20)
    elif entry_rule == "smc_confluence":
        params["smc_swing_left"] = pc1.number_input("Velas para confirmar swing (izq.)", 1, 10, 2)
        params["smc_swing_right"] = pc2.number_input("Velas para confirmar swing (der.)", 1, 10, 2)
        params["smc_require_choch"] = pc3.checkbox("Solo entrar tras CHoCH (reversión)", value=False)
        sc1, sc2, sc3 = st.columns(3)
        params["smc_require_zone"] = sc1.checkbox("Exigir zona discount/premium", value=True)
        params["smc_require_ob_or_fvg"] = sc2.checkbox("Exigir Order Block o FVG", value=True)
        params["smc_require_confirmation"] = sc3.checkbox("Exigir vela de confirmación", value=True)
        params["smc_require_killzone"] = st.checkbox("Exigir sesión de Londres/Nueva York", value=False)

    rc1, rc2 = st.columns(2)
    sl_atr_mult = rc1.number_input("SL (múltiplo de ATR)", 0.1, 20.0, 1.5, step=0.1, key="manual_sl")
    tp_atr_mult = rc2.number_input("TP (múltiplo de ATR)", 0.1, 20.0, 3.0, step=0.1, key="manual_tp")

    if st.button("▶ Correr backtest manual", key="run_manual"):
        cfg = StrategyConfig(entry_rule=entry_rule, sl_atr_mult=sl_atr_mult, tp_atr_mult=tp_atr_mult,
                              **params, **base_cfg_kwargs)
        with st.spinner("Corriendo backtest..."):
            trades, equity, final_balance = run_backtest(df, cfg)
        stats = compute_metrics(trades, equity, cfg.initial_balance)
        st.plotly_chart(plot_equity(equity), use_container_width=True, config={"displayModeBar": False})
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.markdown(stat_card("Profit Factor", stats["Profit Factor"]), unsafe_allow_html=True)
        mc2.markdown(stat_card("Net Profit %", f'{stats["Net Profit %"]}%'), unsafe_allow_html=True)
        mc3.markdown(stat_card("Max Drawdown %", f'{stats["Max Drawdown %"]}%'), unsafe_allow_html=True)
        mc4.markdown(stat_card("Trades", stats["Total Trades"]), unsafe_allow_html=True)
        trades_df = trades_to_dataframe(trades)
        st.dataframe(trades_df, use_container_width=True)
