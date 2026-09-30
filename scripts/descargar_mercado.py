"""Descarga precios de mercado (Yahoo Finance) de acciones, ETFs y referencias."""
import os
from pathlib import Path

import psycopg
import yfinance as yf
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SALIDA = ROOT / "mercado" / "mercado_precios.csv"
INICIO, FIN = "2023-06-01", "2024-06-15"

# nombre interno: tickers candidatos en Yahoo (se usa el primero que funcione)
LOCALES = {
    "ECOPETROL": ["ECOPETROL.CL"], "ISA": ["ISA.CL"], "CELSIA": ["CELSIA.CL"],
    "CEMARGOS": ["CEMARGOS.CL"], "ETB": ["ETB.CL"], "GRUBOLIVAR": ["GRUBOLIVAR.CL"],
    "PFBCOLOM": ["PFBCOLOM.CL"], "PFCEMARGOS": ["PFCEMARGOS.CL"],
    "PFCORFICOL": ["PFCORFICOL.CL"], "PFGRUPSURA": ["PFGRUPSURA.CL"],
}
REFERENCIAS = {
    "TRM": ["COP=X"],
    "COLCAP": ["ICOLCAP.CL", "^COLCAP"],
    "CIB": ["CIB"],
    "AGG": ["AGG"], "SHY": ["SHY"], "EMB": ["EMB"], "ACWI": ["ACWI"], "SPY": ["SPY"], "QQQ": ["QQQ"]
}
ALIAS = {"SQ": ["XYZ", "SQ"]}


def simbolos_internacionales():
    load_dotenv(ROOT / ".env")
    with psycopg.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    ) as conn:
        filas = conn.execute(
            "SELECT DISTINCT simbolo FROM stg.intl_limpio "
            "WHERE tipo_activo IN ('Accion', 'ETF') AND simbolo IS NOT NULL"
        ).fetchall()
    return {f[0]: ALIAS.get(f[0], [f[0].replace(" ", "-")]) for f in filas}


def main():
    mapa = {**LOCALES, **REFERENCIAS, **simbolos_internacionales()}
    tickers = sorted({t for cands in mapa.values() for t in cands})
    precios = yf.download(
        tickers, start=INICIO, end=FIN, auto_adjust=True,
        progress=False, threads=False,
    )["Close"]

    series, fallidas = {}, []
    for nombre, candidatos in mapa.items():
        for t in candidatos:
            if t in precios and precios[t].dropna().size >= 20:
                series[nombre] = precios[t].dropna()
                break
        else:
            fallidas.append(nombre)

    # respaldo: PFBCOLOM aproximada con el ADR de Bancolombia convertido a pesos
    if "PFBCOLOM" in fallidas and "CIB" in series and "TRM" in series:
        series["PFBCOLOM"] = (series["CIB"] * series["TRM"]).dropna()
        fallidas.remove("PFBCOLOM")
        print("Aviso: PFBCOLOM aproximada con CIB por TRM (respaldo)")

    import pandas as pd

    tabla = pd.DataFrame(series)
    tabla.index.name = "fecha"
    SALIDA.parent.mkdir(exist_ok=True)
    tabla.to_csv(SALIDA)

    print(f"Series descargadas: {len(series)}  |  fallidas: {len(fallidas)}")
    print("OK:", ", ".join(sorted(series)))
    print("FALLIDAS:", ", ".join(fallidas) if fallidas else "ninguna")
    print(f"Rango: {tabla.index.min().date()} a {tabla.index.max().date()}  ->  {SALIDA}")


if __name__ == "__main__":
    main()