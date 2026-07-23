# Bot Backtester MVP

Backtester web simple, tipo StrategyQuant pero gratis, sin descargas, corriendo en tu navegador.

## Qué incluye este MVP
- 3 reglas de entrada configurables: cruce de EMAs, reversión por RSI, breakout Donchian
- Gestión de riesgo con SL/TP dinámico basado en ATR (como en tus EAs de MT5)
- Position sizing por % de riesgo del balance
- Métricas: Win rate, Profit Factor, Max Drawdown, Sharpe aproximado, Net Profit
- Curva de equity interactiva
- Exportar trades a CSV

## Estructura de archivos
```
backtester_app/
├── app.py            <- interfaz web (Streamlit)
├── engine.py          <- motor de backtest (simulación trade-by-trade)
├── indicators.py       <- EMA, RSI, ATR, MACD, Donchian
├── metrics.py          <- cálculo de métricas de robustez
├── data_loader.py       <- parser de CSV de Dukascopy
└── requirements.txt
```

## Dónde pones tu data de Dukascopy
**No la pones en el código.** Descárgala y súbela directamente en la app:

1. Ve a https://www.dukascopy.com/swiss/english/marketwatch/historical/
2. Elige instrumento (ej. XAUUSD), timeframe (M5, M15, H1...) y rango de fechas
3. Descarga el CSV
4. Abre la app, en el panel izquierdo usa el botón "Sube tu CSV de Dukascopy"

El `data_loader.py` detecta automáticamente el formato de columnas de Dukascopy
(sea "Gmt time" o "Local time"), así que cualquier export que descargues debería
funcionar sin tocar nada.

## Cómo correrlo localmente (para probar antes de subirlo)
```bash
pip install -r requirements.txt
streamlit run app.py
```
Abre http://localhost:8501

## Cómo hostearlo gratis (Streamlit Community Cloud)
1. Crea una cuenta gratis en https://share.streamlit.io (login con GitHub)
2. Crea un repo nuevo en GitHub (puede ser privado) y sube estos 6 archivos
3. En Streamlit Community Cloud: "New app" → selecciona tu repo → main file: `app.py`
4. Deploy. En ~1-2 minutos tienes una URL pública tipo `tuapp.streamlit.app`

Límites del tier gratuito: 1 app privada + apps públicas ilimitadas, ~1GB RAM.
Suficiente para el MVP; si luego necesitas correr backtests genéticos pesados
(miles de combinaciones) tocará mover el motor a un backend separado (Render,
Railway, o un servidor propio), pero para probar reglas y validar ideas esto
te alcanza de sobra.

## Siguientes pasos sugeridos (post-MVP)
1. Walk-forward analysis (dividir data en ventanas in-sample/out-of-sample)
2. Monte Carlo (shuffle de trades para ver distribución de drawdowns)
3. Motor genético para generar combinaciones de reglas automáticamente
4. Exportar la estrategia ganadora a MQL5 / Pine Script
