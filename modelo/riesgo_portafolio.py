"""Hito 2: volatilidad y metricas de riesgo de cada portafolio (local e internacional en COP)."""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent
MERCADO = ROOT / "data" / "mercado_precios.csv"
MAPEO = ROOT / "modelo" / "mapeo_riesgo.csv"
FECHA_REF = "2024-05-30"
DIAS = 252
LOCALES = {
    "ECOPETROL", "ISA", "CELSIA", "CEMARGOS", "ETB", "GRUBOLIVAR",
    "PFBCOLOM", "PFCEMARGOS", "PFCORFICOL", "PFGRUPSURA", "COLCAP",
}


def engine_bd():
    load_dotenv(ROOT / ".env")
    url = (
        f"postgresql+psycopg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    return create_engine(url)


def cargar_precios():
    px = pd.read_csv(MERCADO, index_col="fecha", parse_dates=True).sort_index()
    return px.loc[:FECHA_REF]


def retornos_en_pesos(px):
    """Retornos diarios logaritmicos. Los activos en dolares suman la variacion de la TRM."""
    ret = np.log(px.ffill()).diff().iloc[1:]
    ret_cop = ret.copy()
    for c in ret.columns:
        if c not in LOCALES and c != "TRM":
            ret_cop[c] = ret[c] + ret["TRM"]
    return ret_cop


def revisar_series(px, usadas):
    """Detecta series con pocos datos o con precios que casi no cambian (posibles series ilquidas)."""
    filas = []
    for s in sorted(usadas):
        if s not in px:
            continue
        p = px[s].dropna()
        ceros = float((p.diff().iloc[1:] == 0).mean()) if len(p) > 1 else 1.0
        if len(p) < 150 or ceros > 0.2:
            filas.append((s, len(p), round(100 * ceros, 1)))
    return pd.DataFrame(filas, columns=["serie", "observaciones", "pct_dias_sin_cambio"])


def cargas(proxy, universo):
    """Convierte 'ACWI:0.6|AGG:0.4' en {'ACWI': 0.6, 'AGG': 0.4}."""
    if isinstance(proxy, str) and proxy:
        salida = {}
        for parte in proxy.split("|"):
            nombre, _, peso = parte.partition(":")
            salida[nombre] = float(peso) if peso else 1.0
        return salida
    return {"TRM": 1.0} if universo == "USD" else {}


def familia(clase, clave):
    c, k = str(clase), str(clave).upper()
    if c.startswith("Liquidez"):
        return "liquidez"
    if c == "Fondo mixto":
        return "mixto"
    if c == "Nota estructurada":
        return "estructurado"
    if "TREAS" in k or "BOND" in k:
        return "renta_fija"
    if c.startswith(("Renta variable", "Fondo de renta variable")) or c in ("Accion", "ETF"):
        return "renta_variable"
    return "renta_fija"


def calcular(pos, ret_cop):
    """pos: una fila por posicion con id_cliente, universo, clave, clase_riesgo, proxy,
    vol_anual_supuesta, fuente, valor_cop. Devuelve una fila por cliente."""
    pos = pos.copy()
    pos["cargas"] = [cargas(p, u) for p, u in zip(pos.proxy, pos.universo)]
    pos["idio"] = pos.vol_anual_supuesta.fillna(0.0)
    pos["familia"] = [familia(c, k) for c, k in zip(pos.clase_riesgo, pos.clave)]
    pos["sin_id"] = pos.clave.str.upper().str.startswith(("SIN CODIGO", "SIN CATALOGO"))

    tickers = sorted({t for c in pos.cargas for t in c})
    faltan = [t for t in tickers if t not in ret_cop.columns]
    if faltan:
        raise ValueError(f"Series sin datos de mercado: {faltan}")
    cov = (ret_cop[tickers].cov() * DIAS).fillna(0.0).values
    idx = {t: i for i, t in enumerate(tickers)}

    filas = []
    for cliente, g in pos.groupby("id_cliente"):
        total = float(g.valor_cop.sum())
        w = (g.valor_cop / total).values
        e = np.zeros(len(tickers))
        for wi, c in zip(w, g.cargas):
            for t, k in c.items():
                e[idx[t]] += wi * k
        var_mercado = max(float(e @ cov @ e), 0.0)
        var_idio = float(np.sum((w * g.idio.values) ** 2))
        fila = {
            "id_cliente": cliente,
            "total_cop": round(total),
            "n_posiciones": len(g),
            "vol_anual_pct": round(100 * np.sqrt(var_mercado + var_idio), 2),
            "hhi": round(float(np.sum(w ** 2)), 4),
            "pct_internacional": round(100 * float(w[(g.universo == "USD").values].sum()), 2),
            "pct_sin_identificar": round(100 * float(w[g.sin_id.values].sum()), 2),
        }
        for fam in ["liquidez", "renta_fija", "renta_variable", "mixto", "estructurado"]:
            fila[f"pct_{fam}"] = round(100 * float(w[(g.familia == fam).values].sum()), 2)
        for fuente, nombre in [("serie directa", "serie"), ("proxy", "proxy"), ("supuesto", "supuesto")]:
            fila[f"pct_dato_{nombre}"] = round(100 * float(w[(g.fuente == fuente).values].sum()), 2)
        filas.append(fila)
    return pd.DataFrame(filas)


def main():
    eng = engine_bd()
    px = cargar_precios()
    ret_cop = retornos_en_pesos(px)
    mapeo = pd.read_csv(MAPEO).drop_duplicates(["universo", "clave"])

    cop = pd.read_sql(
        "SELECT id_cliente, activo || '|' || macroactivo AS clave, aba AS valor_cop "
        "FROM stg.portafolio_cop_actual", eng)
    cop["universo"] = "COP"
    usd = pd.read_sql(
        "SELECT p.id_cliente, p.nombre_activo AS clave, p.valor_usd * r.trm AS valor_cop "
        "FROM stg.portafolio_usd_actual p JOIN stg.resumen_cliente r USING (id_cliente)", eng)
    usd["universo"] = "USD"
    pos = pd.concat([cop, usd], ignore_index=True)
    pos["valor_cop"] = pos.valor_cop.astype(float)

    pos = pos.merge(mapeo, on=["universo", "clave"], how="left")
    sin_mapeo = pos[pos.clase_riesgo.isna()]
    if len(sin_mapeo):
        raise ValueError(f"Posiciones sin mapeo: {sorted(set(sin_mapeo.clave))}")

    usadas = {t for p, u in zip(pos.proxy, pos.universo) for t in cargas(p, u)}
    dudosas = revisar_series(px, usadas)
    print("Series con pocos datos o precios casi sin cambio:")
    print(dudosas.to_string(index=False) if len(dudosas) else "  ninguna")

    res = calcular(pos, ret_cop)
    attrs = pd.read_sql(
        "SELECT id_cliente, id_tipo, banca, perfil_riesgo FROM stg.resumen_cliente", eng)
    res = attrs.merge(res, on="id_cliente")
    res.to_sql("features_cliente", eng, schema="stg", if_exists="replace", index=False)

    print(f"\nTabla stg.features_cliente creada con {len(res)} clientes.\n")
    cols = ["id_cliente", "perfil_riesgo", "vol_anual_pct", "hhi", "pct_internacional",
            "pct_renta_variable", "pct_dato_supuesto"]
    print(res.sort_values("vol_anual_pct", ascending=False)[cols].to_string(index=False))


if __name__ == "__main__":
    main()