"""Carga automatica de los CSV a Postgres, como texto crudo (sin limpiar)."""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.types import Text

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

TABLAS = [
    "cat_perfil_riesgo",
    "catalogo_activos",
    "catalogo_banca",
    "historico_aba_macroactivos",
    "historico_aba_usd_internacional",
]


def get_engine():
    load_dotenv(ROOT / ".env")
    url = (
        f"postgresql+psycopg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    return create_engine(url)


def leer_csv(ruta: Path) -> pd.DataFrame:
    """Lee todo como texto y conserva valores como 'None' o vacios tal cual."""
    return pd.read_csv(
        ruta,
        dtype=str,
        keep_default_na=False,
        na_values=[],
        encoding="utf_8_sig",
    )


def cargar_tabla(engine, nombre: str) -> tuple[int, int]:
    ruta = DATA_DIR / f"{nombre}.csv"
    if not ruta.exists():
        raise FileNotFoundError(f"No encuentro {ruta}")

    df = leer_csv(ruta)
    df.columns = [c.strip().lower() for c in df.columns]

    df.to_sql(
        nombre,
        engine,
        if_exists="replace",
        index=False,
        dtype={col: Text() for col in df.columns},
        chunksize=2000,
    )

    with engine.connect() as conn:
        en_bd = conn.execute(text(f"SELECT COUNT(*) FROM {nombre}")).scalar()
    return len(df), en_bd


def main():
    engine = get_engine()
    print("Conectado a Postgres. Cargando tablas...\n")
    for nombre in TABLAS:
        filas_csv, filas_bd = cargar_tabla(engine, nombre)
        estado = "OK" if filas_csv == filas_bd else "REVISAR"
        print(f"{nombre:<36} csv={filas_csv:>6}  bd={filas_bd:>6}  {estado}")
    print("\nCarga terminada.")


if __name__ == "__main__":
    main()