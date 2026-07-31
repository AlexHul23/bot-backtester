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
import glob
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
