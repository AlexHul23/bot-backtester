# Bot Backtester MVP

Backtester web tipo StrategyQuant pero gratis, sin descargas, con data integrada
y un modo de exploración automática de estrategias.

## Qué incluye esta versión
- **Data integrada**: los históricos viven en `data/*.parquet` dentro del repo.
  El usuario ya no necesita subir un CSV cada vez.
- **Modo manual**: eliges regla y parámetros tú mismo (cruce EMA, RSI reversion,
  breakout Donchian), con una explicación corta de cuándo funciona cada una.
- **Modo "no sé qué usar"**: grid search automático — prueba decenas de
  combinaciones de parámetros y las rankea por Profit Factor, Sharpe y
  Drawdown. Punto de partida basado en datos, no en intuición.
- SL/TP dinámico basado en ATR, position sizing por % de riesgo.
- Exportar trades a CSV.

## Estructura de archivos
```
backtester_app/
├── app.py            <- interfaz web (Streamlit), 2 tabs: manual y explorar
├── engine.py          <- motor de backtest (simulación trade-by-trade)
├── indicators.py       <- EMA, RSI, ATR, MACD, Donchian
├── metrics.py          <- cálculo de métricas de robustez
├── optimizer.py         <- grid search automático de parámetros
├── data_loader.py       <- parser de CSV de Dukascopy + lector de datasets integrados
├── prepare_data.py       <- script para convertir tus CSVs a data/*.parquet
├── requirements.txt
└── data/              <- (creas esta carpeta) tus históricos en formato parquet
```

## Cómo agregar data integrada (una sola vez por instrumento)

### Opción recomendada: Hugging Face Hub (gratis, hasta ~5TB en repos públicos)

1. Crea cuenta gratis en https://huggingface.co/join
2. Ve a https://huggingface.co/settings/tokens → "Create new token" con permiso **Write**.
   Cópialo — nunca lo subas a GitHub, solo úsalo en tu terminal local.
3. Descarga el CSV desde https://www.dukascopy.com/swiss/english/marketwatch/historical/
4. En tu computadora, dentro de la carpeta del proyecto:
   ```bash
   pip install -r requirements.txt
   export HF_TOKEN="hf_tu_token_aqui"
   python prepare_data.py --csv XAUUSD_H1.csv --symbol XAUUSD --timeframe H1 \
       --upload --repo-id TU_USUARIO/dukascopy-data
   ```
   Esto crea el dataset repo en Hugging Face automáticamente (si no existe) y sube el parquet.
5. En `app.py`, cambia la constante `HF_REPO_ID` (al inicio del archivo) por
   `"TU_USUARIO/dukascopy-data"` y haz commit/push a GitHub.
6. Repite el paso 4 por cada instrumento/timeframe que quieras — XAUUSD H1,
   USDJPY M15, EURUSD H1, etc. No hace falta volver a tocar `app.py` ni redeployar,
   la app lista los archivos disponibles del dataset automáticamente.

**Quién puede ver esa data:** el dataset queda público (requisito para el tier
gratis grande de Hugging Face), pero ahí solo vive la data de precios —
información de mercado que cualquiera puede descargar gratis de Dukascopy.
No expone tu código, tu cuenta de Streamlit, ni resultados de trading real.

### Opción alternativa: parquet dentro del propio repo de GitHub
Útil si prefieres no depender de Hugging Face, pero limitado por el tamaño
razonable de un repo de GitHub (unos cientos de MB cómodos).
```bash
python prepare_data.py --csv XAUUSD_H1.csv --symbol XAUUSD --timeframe H1
```
Sube el `.parquet` resultante a la carpeta `data/` de tu repo, y en la app
elige "Data local del repo" como fuente.

**Nota sobre actualizar la data:** esto es un histórico estático (bueno para
investigar y validar estrategias). Si quieres data más reciente, vuelve a
descargar el rango nuevo de Dukascopy y repite el proceso.

## Modo "No sé qué estrategia usar"
En la pestaña "🔍 Explorar", eliges qué familias de reglas probar (o las tres)
y cuántas combinaciones máximo. La app corre el backtest de cada combinación
y las ordena por un score que combina:
- Profit Factor (ganancia bruta / pérdida bruta)
- Sharpe aproximado (retorno ajustado a volatilidad)
- Max Drawdown (penaliza configuraciones con caídas grandes)

Puedes tomar la fila #0 (la mejor) y ver su curva de equity completa antes
de decidir si la quieres llevar a MT5.

**Importante:** esto es un punto de partida, no una garantía. Una configuración
que rankea bien en el histórico puede fallar en datos nuevos — por eso el
roadmap incluye walk-forward y Monte Carlo (ver abajo), que son los filtros
que de verdad separan un bot robusto de uno sobre-ajustado (overfit).

## Cómo correrlo localmente (para probar antes de subirlo)
```bash
pip install -r requirements.txt
streamlit run app.py
```
Abre http://localhost:8501

## Cómo hostearlo gratis (Streamlit Community Cloud)
1. Cuenta gratis en https://share.streamlit.io (login con GitHub)
2. Repo en GitHub con todos estos archivos (incluida la carpeta `data/` con tus parquet)
3. "New app" → tu repo → main file: `app.py` → Deploy

## Siguientes pasos sugeridos (post-MVP)
1. Walk-forward analysis (in-sample / out-of-sample) — filtra el overfitting
   que el grid search por sí solo no detecta
2. Monte Carlo (shuffle de trades) para ver distribución de drawdowns posibles
3. Motor genético completo para generar reglas nuevas, no solo ajustar parámetros
4. Exportar la estrategia ganadora directo a código MQL5 para MT5
