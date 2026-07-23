"""
data_loader.py
Parser flexible para los CSV que exporta Dukascopy Historical Data Feed
(https://www.dukascopy.com/swiss/english/marketwatch/historical/).

Dukascopy exporta columnas con nombres que varían un poco según la versión:
  "Gmt time", "Local time", "Open", "High", "Low", "Close", "Volume"
Este loader detecta la columna de tiempo automáticamente y normaliza
todo a un DataFrame con index datetime y columnas Open/High/Low/Close/Volume.
"""
import pandas as pd


TIME_COL_CANDIDATES = ["Gmt time", "Local time", "Time", "Date", "Datetime", "timestamp"]
OHLC_MAP = {
    "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
}


def load_dukascopy_csv(file_or_path) -> pd.DataFrame:
    df = pd.read_csv(file_or_path)

    # normalizar nombres de columnas OHLC (case-insensitive)
    rename_map = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in OHLC_MAP:
            rename_map[col] = OHLC_MAP[key]
    df = df.rename(columns=rename_map)

    # detectar columna de tiempo
    time_col = None
    for cand in TIME_COL_CANDIDATES:
        if cand in df.columns:
            time_col = cand
            break
    if time_col is None:
        # fallback: primera columna
        time_col = df.columns[0]

    # Dukascopy suele usar formato "DD.MM.YYYY HH:MM:SS.mmm GMT+0000"
    df["__dt__"] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    if df["__dt__"].isna().all():
        # intenta con dayfirst
        df["__dt__"] = pd.to_datetime(df[time_col], errors="coerce", dayfirst=True)

    df = df.dropna(subset=["__dt__"])
    df = df.set_index("__dt__").sort_index()
    df.index.name = "time"

    required = ["Open", "High", "Low", "Close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Faltan columnas OHLC en el CSV: {missing}. "
            f"Columnas encontradas: {list(df.columns)}"
        )

    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float, errors="ignore")
    return df
