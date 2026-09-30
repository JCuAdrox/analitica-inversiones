"""Construye el mapeo de riesgo: a cada activo le asigna serie propia, proxy o supuesto."""
import os
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SALIDA = ROOT / "modelo" / "mapeo_riesgo.csv"
MERCADO = ROOT / "data" / "mercado_precios.csv"
FECHA_REF = date(2024, 5, 30)

ACCIONES_LOCALES = {
    "ECOPETROL", "ISA", "CELSIA", "CEMARGOS", "ETB", "GRUBOLIVAR",
    "PFBCOLOM", "PFCEMARGOS", "PFCORFICOL", "PFGRUPSURA",
}


def regla_cop(activo, macro):
    a = activo.upper()
    if a == "PFBCOLOM":
        return ("Renta variable local", "PFBCOLOM", None, "proxy",
                "Serie aproximada con el ADR CIB por la TRM, porque Yahoo no tiene la local")
    if a in ACCIONES_LOCALES:
        return ("Renta variable local", a, None, "serie directa",
                "Precio de mercado de la accion en la Bolsa de Valores de Colombia")
    if a.startswith("CDT"):
        return ("Deposito a plazo", None, 0.0, "supuesto",
                "Tasa fija mantenida a vencimiento, sin volatilidad de mercado relevante")
    if a in ("FIDUCUENTA", "RENTA LIQUIDEZ"):
        return ("Liquidez (FIC)", None, 0.005, "supuesto",
                "Fondo de liquidez con volatilidad muy baja, validar con rentabilidades publicadas")
    if macro == "Renta Variable":
        return ("Renta variable local sin identificar", "COLCAP", None, "proxy",
                "Activo sin codigo, se asume el comportamiento del indice local")
    return ("Renta fija (FIC)", None, 0.02, "supuesto",
            "Fondo de renta fija con volatilidad supuesta de 2 % anual, validar")


def regla_fondo(n):
    if "SHORT DURATION" in n:
        return ("Fondo de renta fija corto plazo", "SHY", "proxy",
                "Fondo de bonos de corta duracion, ETF de Tesoros a 1 a 3 anos")
    if any(k in n for k in ("FIXED INCOME", "INCOME OPTIMISER", "PIMCO", "JPMORGAN INCOME")):
        return ("Fondo de renta fija", "AGG", "proxy",
                "Fondo de renta fija global, se usa el indice agregado de bonos de EEUU")
    if "MANAGED INDEX" in n:
        mezcla = "ACWI:0.5|AGG:0.5" if "MODERATE" in n else "ACWI:0.8|AGG:0.2"
        return ("Fondo mixto", mezcla, "proxy",
                "Fondo de portafolios indexados, mezcla segun su perfil moderado o de crecimiento")
    if "MULTI" in n or "ALLOCATION" in n:
        return ("Fondo mixto", "ACWI:0.6|AGG:0.4", "proxy",
                "Fondo multiactivo, mezcla estandar de 60 % acciones y 40 % bonos")
    if "TECHNOLOGY" in n:
        return ("Fondo de renta variable tecnologia", "QQQ", "proxy",
                "Fondo tecnologico, se usa el Nasdaq 100")
    if "EMERGING" in n or "ASIA" in n:
        return ("Fondo de renta variable emergente", "EEM", "proxy",
                "Fondo de acciones de Asia o emergentes, se usa el ETF de mercados emergentes")
    if "EUROPE" in n:
        return ("Fondo de renta variable Europa", "VGK", "proxy",
                "Fondo de acciones europeas, se usa el ETF de Europa")
    if "U.S." in n or " US " in n:
        return ("Fondo de renta variable EEUU", "SPY", "proxy",
                "Fondo de acciones estadounidenses, se usa el S&P 500")
    return ("Fondo de renta variable global", "ACWI", "proxy",
            "Fondo de acciones globales, se usa el indice mundial de acciones")


def regla_usd(nombre, tipo, simbolo, venc):
    n = nombre.upper()
    if tipo == "Liquidez":
        return ("Liquidez USD", None, 0.0, "supuesto", "Fondo de liquidez en dolares")
    if tipo in ("Accion", "ETF"):
        return (tipo, simbolo, None, "serie directa", "Precio de mercado en Yahoo Finance")
    if tipo == "Renta Fija":
        if n.startswith("UNITED STATES TREAS"):
            anios = (venc - FECHA_REF).days / 365.25 if venc else 3
            proxy = "SHY" if anios <= 3 else "AGG"
            return ("Bono del Tesoro de EEUU", proxy, None, "proxy",
                    "ETF de Tesoros segun el vencimiento restante (hasta 3 anos, SHY; mas, AGG)")
        return ("Bono corporativo emergente", "EMB", None, "proxy",
                "ETF de bonos emergentes en dolares, por ser emisores colombianos y latinoamericanos")
    if tipo == "Nota estructurada":
        return ("Nota estructurada", "SPY", None, "proxy",
                "Ligada a indices accionarios de EEUU, se usa SPY como supuesto conservador "
                "sin modelar barreras ni capital protegido")
    clase, proxy, fuente, just = (lambda r: (r[0], r[1], r[2], r[3]))(regla_fondo(n))
    return (clase, proxy, None, fuente, just)


def tickers_de(proxy):
    if not isinstance(proxy, str):
        return []
    return [p.split(":")[0] for p in proxy.split("|")]


def conectar():
    load_dotenv(ROOT / ".env")
    return psycopg.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def main():
    columnas = set(pd.read_csv(MERCADO, nrows=0).columns)
    filas = []

    with conectar() as conn:
        cop = conn.execute(
            "SELECT activo, macroactivo, SUM(aba) FROM stg.portafolio_cop_actual "
            "GROUP BY activo, macroactivo"
        ).fetchall()
        usd = conn.execute(
            "SELECT nombre_activo, tipo_activo, MAX(simbolo), MAX(fecha_vencimiento), "
            "SUM(valor_usd) FROM stg.portafolio_usd_actual GROUP BY nombre_activo, tipo_activo"
        ).fetchall()

    for activo, macro, valor in cop:
        clase, proxy, vol, fuente, just = regla_cop(activo, macro)
        filas.append(("COP", f"{activo}|{macro}", clase, proxy, vol, fuente, just, float(valor)))
    for nombre, tipo, simbolo, venc, valor in usd:
        clase, proxy, vol, fuente, just = regla_usd(nombre, tipo, simbolo, venc)
        filas.append(("USD", nombre, clase, proxy, vol, fuente, just, float(valor)))

    df = pd.DataFrame(filas, columns=[
        "universo", "clave", "clase_riesgo", "proxy", "vol_anual_supuesta",
        "fuente", "justificacion", "valor"])

    # si una serie no esta disponible, se usa el indice mundial como respaldo
    for i, r in df.iterrows():
        if any(t not in columnas for t in tickers_de(r.proxy)):
            df.at[i, "proxy"] = "ACWI"
            df.at[i, "fuente"] = "proxy"
            df.at[i, "justificacion"] = r.justificacion + " (serie no disponible, se usa ACWI)"

    df.drop(columns="valor").to_csv(SALIDA, index=False, encoding="utf-8")

    print(f"Activos mapeados: {len(df)}  ->  {SALIDA}\n")
    for universo, g in df.groupby("universo"):
        pesos = (g.groupby("fuente").valor.sum() / g.valor.sum() * 100).round(1)
        print(f"Cobertura por valor, {universo}:")
        print(pesos.to_string(), "\n")

    print("Fondos y notas del universo USD, para revisar:")
    rev = df[(df.universo == "USD") & df.clase_riesgo.str.startswith(("Fondo", "Nota"))]
    for _, r in rev.iterrows():
        print(f"  {r.clave[:58]:<58} {r.proxy}")


if __name__ == "__main__":
    main()