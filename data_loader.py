"""
data_loader.py
Parser flexible para los CSV que exporta Dukascopy Historical Data Feed
(https://www.dukascopy.com/swiss/english/marketwatch/historical/).

Dukascopy exporta columnas con nombres que varían un poco según la versión:
  "Gmt time", "Local time", "Open", "High", "Low", "Close", "Volume"
Este loader detecta la columna de tiempo automáticamente y normaliza
todo a un DataFrame con index datetime y columnas Open/High/Low/Close/Volume.
"""
import os
import re
import glob
import pandas as pd


TIME_COL_CANDIDATES = ["gmt time", "local time", "time", "date", "datetime", "timestamp"]
OHLC_MAP = {
    "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
}


def _read_csv_any_delimiter(file_or_path) -> pd.DataFrame:
    """Lee un CSV detectando el separador automáticamente (coma, punto y coma, tab)."""
    try:
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        df = pd.read_csv(file_or_path, sep=None, engine="python")
    except Exception:
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        df = pd.read_csv(file_or_path)

    # si la detección de separador falló, terminamos con una sola columna gigante
    if df.shape[1] == 1:
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        for sep in [",", ";", "\t"]:
            try:
                candidate = pd.read_csv(file_or_path, sep=sep)
                if candidate.shape[1] > 1:
                    df = candidate
                    break
            except Exception:
                pass
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(0)
    return df


def _parse_datetime_column(raw: pd.Series) -> pd.Series:
    """Prueba varias estrategias de parseo de fecha, en orden, hasta que una funcione."""
    attempts = [
        dict(utc=True, errors="coerce"),
        dict(dayfirst=True, errors="coerce"),
        dict(format="mixed", errors="coerce"),
    ]
    best = None
    for kwargs in attempts:
        try:
            parsed = pd.to_datetime(raw, **kwargs)
        except Exception:
            continue
        valid = parsed.notna().sum()
        if best is None or valid > best.notna().sum():
            best = parsed
        if valid == len(raw):
            return parsed

    # última opción: quitar sufijos de zona horaria en texto (ej. "GMT-0500", "America/New_York")
    # antes de parsear, por si están confundiendo al parser.
    stripped = raw.astype(str).str.replace(r"\s*(GMT|UTC)[+-]?\d{0,4}\s*$", "", regex=True)
    stripped = stripped.str.replace(r"\s*[A-Za-z]+/[A-Za-z_]+\s*$", "", regex=True)
    try:
        parsed = pd.to_datetime(stripped, errors="coerce", format="mixed")
        if best is None or parsed.notna().sum() > best.notna().sum():
            best = parsed
    except Exception:
        pass

    return best if best is not None else pd.Series([pd.NaT] * len(raw), index=raw.index)


def load_dukascopy_csv(file_or_path) -> pd.DataFrame:
    df = _read_csv_any_delimiter(file_or_path)
    df.columns = [str(c).strip() for c in df.columns]

    # normalizar nombres de columnas OHLC (case-insensitive, admite espacios extra)
    rename_map = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in OHLC_MAP:
            rename_map[col] = OHLC_MAP[key]
    df = df.rename(columns=rename_map)

    # detectar columna de tiempo: primero por nombre exacto conocido,
    # si no, cualquier columna que contenga "time" o "date" en el nombre
    time_col = None
    cols_lower = {c: c.strip().lower() for c in df.columns}
    for cand in TIME_COL_CANDIDATES:
        for orig, low in cols_lower.items():
            if low == cand:
                time_col = orig
                break
        if time_col:
            break
    if time_col is None:
        for orig, low in cols_lower.items():
            if "time" in low or "date" in low:
                time_col = orig
                break
    if time_col is None:
        time_col = df.columns[0]

    parsed = _parse_datetime_column(df[time_col])
    original_columns = list(df.columns)
    df["__dt__"] = parsed
    n_total = len(df)
    df_clean = df.dropna(subset=["__dt__"])

    if df_clean.empty:
        sample = df[time_col].astype(str).head(3).tolist()
        raise ValueError(
            f"No pude interpretar las fechas del CSV. Columna de tiempo detectada: "
            f"'{time_col}'. Primeros valores crudos: {sample}. "
            f"Columnas encontradas en el archivo: {original_columns}. "
            f"Revisa que el archivo no esté vacío y que la columna de tiempo tenga "
            f"un formato de fecha reconocible."
        )
    if len(df_clean) < n_total:
        dropped = n_total - len(df_clean)
        # no se detiene la carga, pero queda registro de cuántas filas no se pudieron leer
        df_clean.attrs["rows_dropped_unparsable_date"] = dropped

    df = df_clean.set_index("__dt__").sort_index()
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


# ---------------------------------------------------------------------------
# Datasets en Hugging Face Hub (recomendado): la data vive en un dataset
# público en huggingface.co, no en el repo de GitHub ni en tu PC.
# La descarga se cachea localmente en el contenedor, así que solo se baja
# una vez por sesión del hosting, no en cada rerun.
# ---------------------------------------------------------------------------

def list_hf_datasets(repo_id: str) -> list:
    """Lista los archivos .parquet y .csv disponibles en un dataset repo de Hugging Face."""
    try:
        from huggingface_hub import list_repo_files
        files = list_repo_files(repo_id, repo_type="dataset")
        return [f for f in files if f.endswith(".parquet") or f.endswith(".csv")]
    except Exception:
        return []


def load_hf_dataset(repo_id: str, filename: str) -> pd.DataFrame:
    """
    Descarga (con caché local automática) y carga un dataset desde Hugging Face.
    Soporta tanto .parquet (ideal, más liviano) como .csv de Dukascopy sin convertir
    (útil si lo subiste directo desde el sitio web sin usar prepare_data.py).
    """
    from huggingface_hub import hf_hub_download
    local_path = hf_hub_download(repo_id=repo_id, filename=filename, repo_type="dataset")
    if filename.endswith(".parquet"):
        return pd.read_parquet(local_path)
    else:
        return load_dukascopy_csv(local_path)


# ---------------------------------------------------------------------------
# Datasets locales dentro del repo de GitHub (data/*.parquet) - fallback,
# útil si no quieres depender de Hugging Face.
# ---------------------------------------------------------------------------

def list_local_datasets(data_dir: str = "data") -> dict:
    files = sorted(glob.glob(os.path.join(data_dir, "*.parquet")))
    return {os.path.splitext(os.path.basename(f))[0]: f for f in files}


def load_local_dataset(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Nombre limpio de instrumento a partir del nombre de archivo, y resampling
# de temporalidad (el archivo fuente puede venir en M1 y la app arma
# cualquier timeframe mayor bajo demanda).
# ---------------------------------------------------------------------------

def parse_instrument_name(filename: str) -> str:
    """
    'XAU-USD_1Minute_BID_2020-01-01_00_00-23_59_America_New_York.csv' -> 'XAUUSD'
    'XAUUSD_H1.parquet' -> 'XAUUSD'
    """
    base = filename.rsplit(".", 1)[0]
    first_token = base.split("_")[0]
    clean = re.sub(r"[^A-Za-z0-9]", "", first_token).upper()
    return clean or base.upper()


TIMEFRAME_RULES = {
    "M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
    "H1": "1h", "H4": "4h", "D1": "1D",
}


def resample_ohlc(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Reagrupa velas a una temporalidad mayor (ej. de M1 a H1)."""
    rule = TIMEFRAME_RULES.get(timeframe)
    if rule is None:
        raise ValueError(f"Timeframe desconocido: {timeframe}")
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    out = df.resample(rule).agg(agg)
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    return out
