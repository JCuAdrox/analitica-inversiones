"""Ejecuta en orden todos los archivos de la carpeta sql/ sobre Postgres."""
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "sql")


def main():
    load_dotenv(ROOT / ".env")
    conn = psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        autocommit=True,
    )
    archivos = sorted(SQL_DIR.glob("*.sql"))
    with conn, conn.cursor() as cur:
        for archivo in archivos:
            cur.execute(archivo.read_text(encoding="utf-8"))
            print(f"OK  {archivo.name}")
    print(f"\n{len(archivos)} archivos ejecutados.")


if __name__ == "__main__":
    main()