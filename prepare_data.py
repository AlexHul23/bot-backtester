"""
prepare_data.py
Convierte un CSV de Dukascopy a Parquet y, opcionalmente, lo sube directo
a un dataset de Hugging Face Hub (gratis, hasta ~5TB en repos públicos).

Uso básico (solo conversión local):
    python prepare_data.py --csv XAUUSD_H1.csv --symbol XAUUSD --timeframe H1

Uso con subida automática a Hugging Face:
    export HF_TOKEN="hf_tu_token_aqui"
    python prepare_data.py --csv XAUUSD_H1.csv --symbol XAUUSD --timeframe H1 \
        --upload --repo-id TU_USUARIO/dukascopy-data

Cómo conseguir tu HF_TOKEN:
    1. Crea cuenta gratis en https://huggingface.co/join
    2. Ve a https://huggingface.co/settings/tokens
    3. "Create new token" con permiso de escritura (Write)
    4. Cópialo y ponlo en tu variable de entorno HF_TOKEN (NUNCA lo subas a GitHub)

El repo de dataset (--repo-id) se crea automáticamente si no existe.
"""
import argparse
import os

from data_loader import load_dukascopy_csv


def maybe_upload_to_hf(local_path: str, repo_id: str, filename_in_repo: str):
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("\n⚠  No encontré la variable de entorno HF_TOKEN.")
        print('   Corre esto primero:  export HF_TOKEN="hf_tu_token_aqui"')
        print(f"   O sube el archivo manualmente en https://huggingface.co/new-dataset")
        return

    from huggingface_hub import HfApi
    api = HfApi()

    print(f"Creando/verificando dataset repo: {repo_id} ...")
    api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, token=token)

    print(f"Subiendo {filename_in_repo} ...")
    api.upload_file(
        path_or_fileobj=local_path,
        path_in_repo=filename_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
        token=token,
    )
    print(f"✅ Subido: https://huggingface.co/datasets/{repo_id}/blob/main/{filename_in_repo}")


def main():
    parser = argparse.ArgumentParser(description="Convierte CSV de Dukascopy a Parquet, opcionalmente sube a Hugging Face")
    parser.add_argument("--csv", required=True, help="Ruta al CSV descargado de Dukascopy")
    parser.add_argument("--symbol", required=True, help="Ej: XAUUSD, USDJPY, EURUSD")
    parser.add_argument("--timeframe", required=True, help="Ej: M5, M15, H1, H4, D1")
    parser.add_argument("--outdir", default="data", help="Carpeta de salida local (default: data/)")
    parser.add_argument("--upload", action="store_true", help="Subir automáticamente a Hugging Face")
    parser.add_argument("--repo-id", default=None, help="Ej: tu_usuario/dukascopy-data (requerido si usas --upload)")
    args = parser.parse_args()

    print(f"Leyendo {args.csv} ...")
    df = load_dukascopy_csv(args.csv)
    print(f"  {len(df):,} velas, de {df.index.min()} a {df.index.max()}")

    os.makedirs(args.outdir, exist_ok=True)
    out_name = f"{args.symbol.upper()}_{args.timeframe.upper()}.parquet"
    out_path = os.path.join(args.outdir, out_name)
    df.to_parquet(out_path)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"Guardado localmente: {out_path} ({size_kb:.1f} KB)")

    if args.upload:
        if not args.repo_id:
            print("❌ Falta --repo-id (ej: tu_usuario/dukascopy-data)")
            return
        maybe_upload_to_hf(out_path, args.repo_id, out_name)
    else:
        print("Tip: usa --upload --repo-id TU_USUARIO/dukascopy-data para subirlo directo a Hugging Face.")


if __name__ == "__main__":
    main()
