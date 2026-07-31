"""
app.py
Bot Backtester — versión con navegación de páginas (Home, Estrategia,
Backtester, Optimizador, Configuración) para simplificar la experiencia.

El visualizador de velas de la página Backtester usa zoom/pan nativo de
Plotly (como un broker real) en vez de sliders manuales.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_option_menu import option_menu

from data_loader import (
    load_dukascopy_csv, list_local_datasets, load_local_dataset,
    list_hf_datasets, load_hf_dataset,
)
import smc as smc_module

st.set_page_config(page_title="Bot Backtester", layout="wide", initial_sidebar_state="expanded")

HF_REPO_ID = "AlexGus1/dukascopy-data"
PAGES = ["Home", "Estrategia", "Backtester", "Optimizador"]

# ============================================================
# ESTADO
# ============================================================
if "page" not in st.session_state:
    st.session_state.page = "Home"
if "user_name" not in st.session_state:
    st.session_state.user_name = "Trader"
if "language" not in st.session_state:
    st.session_state.language = "Español"
if "theme" not in st.session_state:
    st.session_state.theme = "Oscuro"

THEMES = {
    "Claro": {
        "bg": "linear-gradient(180deg, #F3F7FD 0%, #E7EEFA 100%)",
        "card": "#FFFFFF", "text": "#14151A", "text_soft": "#6B7280",
        "border": "rgba(20,21,26,0.08)", "shadow": "0 8px 24px rgba(20,21,26,0.06)",
        "sidebar_bg": "#FFFFFF", "sidebar_text": "#14151A",
        "chart_bg": "#FFFFFF", "chart_grid": "rgba(20,21,26,0.06)", "chart_font": "#6B7280",
    },
    "Oscuro": {
        "bg": "linear-gradient(180deg, #14151A 0%, #0E0F13 100%)",
        "card": "#1C1D24", "text": "#F5F6F8", "text_soft": "#9CA3AF",
        "border": "rgba(255,255,255,0.08)", "shadow": "0 8px 24px rgba(0,0,0,0.35)",
        "sidebar_bg": "#0E0F13", "sidebar_text": "#F5F6F8",
        "chart_bg": "#14151A", "chart_grid": "rgba(255,255,255,0.06)", "chart_font": "#9CA3AF",
    },
}
ACCENT = "#D6FF3F"
GREEN = "#3ECF8E"
RED = "#F87171"

T = THEMES[st.session_state.theme]

STRINGS = {
    "Español": {
        "nav": ["Home", "Estrategia", "Backtester", "Optimizador"],
        "settings": "Configuración",
        "home_title": "Bienvenido de vuelta",
        "home_sub": "Aquí vas a ver el rendimiento de tus bots guardados.",
        "home_empty": "Todavía no tienes ninguna estrategia guardada. Cuando termines de validar una en Backtester u Optimizador y la guardes, su rendimiento va a aparecer aquí.",
        "strategy_empty": "La página de Estrategia está en construcción. Aquí vas a poder armar y combinar reglas de entrada paso a paso.",
        "optimizer_empty": "La página de Optimizador está en construcción. Aquí vas a poder correr búsquedas automáticas de parámetros, walk-forward y Monte Carlo.",
        "backtester_title": "Visualizador de velas",
        "backtester_sub": "Navega el histórico como en tu plataforma — arrastra para mover, rueda del mouse para zoom.",
    },
    "English": {
        "nav": ["Home", "Strategy", "Backtester", "Optimizer"],
        "settings": "Settings",
        "home_title": "Welcome back",
        "home_sub": "Your saved bots' performance will show up here.",
        "home_empty": "You don't have any saved strategy yet. Once you validate one in Backtester or Optimizer and save it, its performance will appear here.",
        "strategy_empty": "The Strategy page is under construction. Here you'll be able to build and combine entry rules step by step.",
        "optimizer_empty": "The Optimizer page is under construction. Here you'll run automatic parameter search, walk-forward and Monte Carlo.",
        "backtester_title": "Candle viewer",
        "backtester_sub": "Navigate the history like in your platform — drag to pan, scroll to zoom.",
    },
}
L = STRINGS[st.session_state.language]


# ============================================================
# ESTILOS
# ============================================================
def inject_css():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
    .stApp {{ background: {T['bg']}; }}
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    /* mantener el header presente (ahí vive la flecha para reabrir el sidebar
       colapsado) pero transparente y sin la barra de herramientas de Streamlit */
    header[data-testid="stHeader"] {{ background: transparent !important; box-shadow: none !important; }}
    [data-testid="stToolbar"] {{ visibility: hidden; }}
    [data-testid="collapsedControl"] {{ visibility: visible !important; color: {T['text']} !important; }}
    [data-testid="collapsedControl"] svg {{ fill: {T['text']} !important; }}

    /* sidebar como columna flex real: así el botón de Configuración se pega
       abajo en cualquier tamaño de pantalla, sin trucos de altura fija */
    [data-testid="stSidebarUserContent"] {{
        display: flex; flex-direction: column; min-height: 92vh;
    }}
    .sidebar-spacer {{ flex: 1 1 auto; }}

    /* ---------- RESPONSIVE: tablet (iPad) y móvil ---------- */
    @media (max-width: 1024px) {{
        .block-container {{ padding-left: 1rem; padding-right: 1rem; max-width: 100%; }}
    }}
    @media (max-width: 768px) {{
        .app-title {{ font-size: 26px !important; }}
        .app-sub {{ font-size: 13.5px !important; }}
        .stat-card {{ padding: 14px 16px; }}
        .stat-value {{ font-size: 20px !important; }}
        .stat-label {{ font-size: 10.5px !important; }}
        .empty-card {{ padding: 28px 18px; font-size: 14px; }}
        .block-container {{ padding-top: 1rem; }}
    }}
    @media (max-width: 480px) {{
        .app-title {{ font-size: 22px !important; }}
        .pill {{ font-size: 10.5px; padding: 3px 9px; margin-bottom: 4px; }}
    }}
    .block-container {{ padding-top: 1.5rem; max-width: 1180px; }}
    h1, h2, h3 {{ font-family: 'Space Grotesk', sans-serif; color: {T['text']}; }}
    p, span, div, label {{ color: {T['text']}; }}

    section[data-testid="stSidebar"] {{
        background: {T['sidebar_bg']} !important;
        border-right: 1px solid {T['border']};
    }}
    section[data-testid="stSidebar"] * {{ color: {T['sidebar_text']} !important; }}

    .app-title {{ font-size:32px; font-weight:700; color:{T['text']}; margin:0 0 4px 0; }}
    .app-sub {{ color:{T['text_soft']}; font-size:15px; margin:0 0 24px 0; }}

    .stat-card {{
      background:{T['card']}; border-radius:18px; padding:20px 22px;
      box-shadow:{T['shadow']}; border:1px solid {T['border']}; height:100%;
    }}
    .stat-label{{font-size:12px;color:{T['text_soft']};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px;font-weight:600;}}
    .stat-value{{font-size:24px;font-weight:700;color:{T['text']};font-family:'Space Grotesk',sans-serif;}}

    .empty-card {{
      background:{T['card']}; border-radius:20px; padding:40px 32px;
      box-shadow:{T['shadow']}; border:1px dashed {T['border']}; text-align:center;
      color:{T['text_soft']}; font-size:15px; line-height:1.6;
    }}

    .pill {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; background:{T['border']}; color:{T['text_soft']}; margin-right:6px;}}
    .pill.accent {{ background:{ACCENT}; color:#14151A; }}

    div.stButton > button {{ border-radius: 12px !important; font-weight:600 !important; }}
    </style>
    """, unsafe_allow_html=True)


def stat_card(label, value):
    return f'<div class="stat-card"><div class="stat-label">{label}</div><div class="stat-value">{value}</div></div>'


inject_css()


# ============================================================
# CARGA DE DATOS (compartida, usada por Backtester)
# ============================================================
@st.cache_data(show_spinner=False)
def _cached_hf_list(repo_id: str):
    return list_hf_datasets(repo_id)


@st.cache_data(show_spinner=False)
def _cached_hf_load(repo_id: str, filename: str):
    return load_hf_dataset(repo_id, filename)


def data_source_picker():
    """Selector de datos compacto. Devuelve (df, label) o (None, None)."""
    df, label = None, None
    with st.spinner("Cargando instrumentos disponibles..."):
        hf_files = _cached_hf_list(HF_REPO_ID)

    col1, col2 = st.columns([2, 1])
    with col1:
        if hf_files:
            key = st.selectbox("Instrumento", hf_files, key="bt_instrument")
            with st.spinner("Descargando (se cachea)..."):
                df = _cached_hf_load(HF_REPO_ID, key)
            label = key
        else:
            st.warning(f"No hay datos en Hugging Face (`{HF_REPO_ID}`). Usa la fuente alterna →")
    with col2:
        with st.expander("Otra fuente"):
            mode = st.radio("Fuente", ["Data local", "Subir CSV"], key="bt_alt_mode", label_visibility="collapsed")
            if mode == "Data local":
                local = list_local_datasets()
                if local:
                    k = st.selectbox("Instrumento local", list(local.keys()), key="bt_local_key")
                    df = load_local_dataset(local[k])
                    label = k
            else:
                up = st.file_uploader("CSV de Dukascopy", type=["csv"], key="bt_upload")
                if up is not None:
                    try:
                        df = load_dukascopy_csv(up)
                        label = up.name
                    except Exception as e:
                        st.error(f"No pude leer el CSV: {e}")
    return df, label


# ============================================================
# SIDEBAR — navegación
# ============================================================
with st.sidebar:
    st.markdown(f'<div style="padding:8px 4px 20px 4px;font-family:\'Space Grotesk\',sans-serif;'
                f'font-weight:700;font-size:20px;">🤖 Bot Backtester</div>', unsafe_allow_html=True)

    icons = ["house", "diagram-3", "bar-chart-line", "sliders"]
    current_index = PAGES.index(st.session_state.page) if st.session_state.page in PAGES else 0

    menu_choice = option_menu(
        menu_title=None,
        options=L["nav"],
        icons=icons,
        default_index=current_index,
        styles={
            "container": {"padding": "0", "background-color": "transparent"},
            "icon": {"color": ACCENT, "font-size": "16px"},
            "nav-link": {
                "font-family": "Inter", "font-size": "14.5px", "font-weight": "600",
                "color": T["sidebar_text"], "border-radius": "10px", "margin": "3px 0",
                "padding": "10px 14px",
            },
            "nav-link-selected": {"background-color": ACCENT, "color": "#14151A"},
        },
    )
    if menu_choice in L["nav"]:
        st.session_state.page = PAGES[L["nav"].index(menu_choice)]

    st.markdown('<div class="sidebar-spacer"></div>', unsafe_allow_html=True)
    st.markdown("---")
    if st.button(f"⚙️  {L['settings']}", use_container_width=True):
        st.session_state.page = "Configuración"

page = st.session_state.page


# ============================================================
# PÁGINA: HOME
# ============================================================
def render_home():
    st.markdown(f'<div class="app-title">{L["home_title"]}, {st.session_state.user_name} 👋</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-sub">{L["home_sub"]}</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(stat_card("Estrategias guardadas", 0), unsafe_allow_html=True)
    c2.markdown(stat_card("Backtests corridos", "—"), unsafe_allow_html=True)
    c3.markdown(stat_card("Mejor Profit Factor", "—"), unsafe_allow_html=True)
    c4.markdown(stat_card("Bots en producción", 0), unsafe_allow_html=True)

    st.write("")
    st.markdown(f'<div class="empty-card">📊<br><br>{L["home_empty"]}</div>', unsafe_allow_html=True)


# ============================================================
# PÁGINA: ESTRATEGIA (vacía por ahora)
# ============================================================
def render_estrategia():
    st.markdown(f'<div class="app-title">Estrategia</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="empty-card">🧩<br><br>{L["strategy_empty"]}</div>', unsafe_allow_html=True)


# ============================================================
# PÁGINA: OPTIMIZADOR (vacía por ahora)
# ============================================================
def render_optimizador():
    st.markdown(f'<div class="app-title">Optimizador</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="empty-card">⚙️<br><br>{L["optimizer_empty"]}</div>', unsafe_allow_html=True)


# ============================================================
# PÁGINA: BACKTESTER — visualizador de velas estilo broker
# ============================================================
def render_backtester():
    st.markdown(f'<div class="app-title">{L["backtester_title"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-sub">{L["backtester_sub"]}</div>', unsafe_allow_html=True)

    df, label = data_source_picker()
    if df is None:
        return

    st.markdown(f'<span class="pill accent">{label}</span>'
                f'<span class="pill">{len(df):,} velas</span>'
                f'<span class="pill">{df.index.min().date()} → {df.index.max().date()}</span>',
                unsafe_allow_html=True)

    with st.expander("Mostrar conceptos Smart Money sobre el gráfico"):
        show_bos = st.checkbox("BOS / CHoCH", value=False)
        show_ob = st.checkbox("Order Blocks", value=False)
        show_fvg = st.checkbox("Fair Value Gaps", value=False)
        show_sweep = st.checkbox("Liquidity sweeps", value=False)

    n_visible = st.select_slider("Velas iniciales visibles", options=[100, 200, 300, 500, 1000], value=300)
    view_df = df.tail(max(n_visible, 300))  # margen extra para poder hacer scroll hacia atrás con el rangeslider

    need_smc = show_bos or show_ob or show_fvg or show_sweep
    smc_df = None
    if need_smc:
        with st.spinner("Calculando conceptos SMC..."):
            smc_df = smc_module.build_smc_dataframe(df).tail(max(n_visible, 300))

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=view_df.index, open=view_df["Open"], high=view_df["High"],
        low=view_df["Low"], close=view_df["Close"],
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor=GREEN, decreasing_fillcolor=RED,
        name="Precio",
    ))

    if need_smc and smc_df is not None:
        def markers(mask_col, y_col, symbol, color, name):
            sub = smc_df[smc_df[mask_col] == True]
            if sub.empty:
                return
            fig.add_trace(go.Scatter(x=sub.index, y=sub[y_col], mode="markers", name=name,
                                      marker=dict(symbol=symbol, size=10, color=color,
                                                  line=dict(width=1, color=T["chart_bg"]))))
        if show_bos:
            markers("bos_bull", "Low", "triangle-up", GREEN, "BOS alcista")
            markers("bos_bear", "High", "triangle-down", RED, "BOS bajista")
            markers("choch_bull", "Low", "star", ACCENT, "CHoCH alcista")
            markers("choch_bear", "High", "star", "#F97316", "CHoCH bajista")
        if show_sweep:
            markers("liquidity_sweep_high", "High", "x", "#9333EA", "Sweep alto")
            markers("liquidity_sweep_low", "Low", "x", "#9333EA", "Sweep bajo")

        shapes = []
        if show_ob:
            for col_h, col_l, color in [("bull_ob_high", "bull_ob_low", GREEN), ("bear_ob_high", "bear_ob_low", RED)]:
                z = smc_df[[col_h, col_l]].dropna()
                if not z.empty:
                    r = z.iloc[-1]
                    shapes.append(dict(type="rect", x0=view_df.index[0], x1=view_df.index[-1],
                                        y0=r[col_l], y1=r[col_h],
                                        fillcolor=f"rgba({'62,207,142' if color==GREEN else '248,113,113'},0.12)",
                                        line=dict(width=0), layer="below"))
        if show_fvg:
            for col_top, col_bot, color in [("bull_fvg_top", "bull_fvg_bottom", GREEN), ("bear_fvg_top", "bear_fvg_bottom", RED)]:
                z = smc_df[smc_df[col_top].notna()]
                for _, r in z.tail(5).iterrows():
                    shapes.append(dict(type="rect", x0=r.name, x1=view_df.index[-1],
                                        y0=r[col_bot], y1=r[col_top],
                                        fillcolor=f"rgba({'62,207,142' if color==GREEN else '248,113,113'},0.10)",
                                        line=dict(width=0), layer="below"))
        fig.update_layout(shapes=shapes)

    fig.update_layout(
        height=460, margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor=T["chart_bg"], paper_bgcolor=T["chart_bg"],
        font=dict(family="Inter", color=T["chart_font"]),
        xaxis=dict(showgrid=False, rangeslider=dict(visible=True, thickness=0.06), type="date"),
        yaxis=dict(showgrid=True, gridcolor=T["chart_grid"], side="right"),
        legend=dict(orientation="h", y=1.05, font=dict(color=T["chart_font"])),
        dragmode="pan",
    )
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})


# ============================================================
# PÁGINA: CONFIGURACIÓN
# ============================================================
def render_configuracion():
    st.markdown(f'<div class="app-title">{L["settings"]}</div>', unsafe_allow_html=True)
    st.write("")

    with st.container():
        st.markdown("#### Nombre")
        new_name = st.text_input("Cómo quieres que te llamemos", value=st.session_state.user_name)
        if new_name != st.session_state.user_name:
            st.session_state.user_name = new_name
            st.rerun()

        st.markdown("#### Idioma")
        new_lang = st.selectbox("Idioma de la interfaz", ["Español", "English"],
                                 index=["Español", "English"].index(st.session_state.language))
        if new_lang != st.session_state.language:
            st.session_state.language = new_lang
            st.rerun()

        st.markdown("#### Tema")
        new_theme = st.selectbox("Apariencia", ["Oscuro", "Claro"],
                                  index=["Oscuro", "Claro"].index(st.session_state.theme))
        if new_theme != st.session_state.theme:
            st.session_state.theme = new_theme
            st.rerun()

        st.caption("Nota: estas preferencias viven mientras dura tu sesión — al cerrar la pestaña se reinician.")


# ============================================================
# ROUTER
# ============================================================
if page == "Home":
    render_home()
elif page == "Estrategia":
    render_estrategia()
elif page == "Backtester":
    render_backtester()
elif page == "Optimizador":
    render_optimizador()
elif page == "Configuración":
    render_configuracion()
