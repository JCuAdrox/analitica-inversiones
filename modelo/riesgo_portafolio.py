"""volatilidad y metricas de riesgo de cada portafolio (local e internacional en COP)."""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
MERCADO = ROOT / "mercado" / "mercado_precios.csv"
MAPEO = ROOT / "modelo" / "mapeo_riesgo.csv"
FECHA_REF = "2024-05-30"
LOCALES = {
    "ECOPETROL", "ISA", "CELSIA", "CEMARGOS", "ETB", "GRUBOLIVAR",
    "PFBCOLOM", "PFCEMARGOS", "PFCORFICOL", "PFGRUPSURA", "COLCAP",
}
# series con muy pocos datos: se sustituyen por un proxy mas robusto
SUSTITUTOS = {"ISQWF": "ACWI"}


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


def retornos(px, frecuencia="D"):
    """Retornos logaritmicos diarios (D) o semanales (W)."""
    precios = px.ffill()
    if frecuencia == "W":
        precios = precios.resample("W-FRI").last()
    return np.log(precios).diff().iloc[1:]


def a_pesos(ret):
    """Los activos en dolares suman la variacion de la TRM."""
    ret_cop = ret.copy()
    for c in ret.columns:
        if c not in LOCALES and c != "TRM":
            ret_cop[c] = ret[c] + ret["TRM"]
    return ret_cop


def diagnostico(px, usadas):
    """Series con pocos datos, precios que casi no cambian o volatilidad diaria muy distinta a la semanal."""
    diaria, semanal = retornos(px, "D"), retornos(px, "W")
    filas = []
    for s in sorted(usadas):
        if s not in px:
            continue
        p = px[s].dropna()
        ceros = float((p.diff().iloc[1:] == 0).mean()) if len(p) > 1 else 1.0
        vd = float(diaria[s].std() * np.sqrt(252))
        vs = float(semanal[s].std() * np.sqrt(52))
        salto = diaria[s].abs().idxmax()
        if len(p) < 150 or ceros > 0.2 or abs(vd - vs) / max(vs, 1e-9) > 0.3:
            filas.append((s, len(p), round(100 * ceros, 1), round(100 * vd, 1),
                          round(100 * vs, 1),
                          f"{salto.date()} ({100 * diaria[s].loc[salto]:.0f} %)"))
    return pd.DataFrame(filas, columns=[
        "serie", "obs", "pct_sin_cambio", "vol_diaria", "vol_semanal", "mayor_salto"])


def cargas(proxy, universo, con_fx=True):
    """Convierte 'ACWI:0.6|AGG:0.4' en {'ACWI': 0.6, 'AGG': 0.4}."""
    if isinstance(proxy, str) and proxy:
        salida = {}
        for parte in proxy.split("|"):
            nombre, _, peso = parte.partition(":")
            nombre = SUSTITUTOS.get(nombre, nombre)
            salida[nombre] = salida.get(nombre, 0.0) + (float(peso) if peso else 1.0)
        return salida
    return {"TRM": 1.0} if (universo == "USD" and con_fx) else {}


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


def volatilidad(pos, ret, dias, con_fx=True):
    """Volatilidad anual (en %) de cada portafolio. ret debe estar en la moneda que corresponda."""
    cg = [cargas(p, u, con_fx) for p, u in zip(pos.proxy, pos.universo)]
    tickers = sorted({t for c in cg for t in c})
    faltan = [t for t in tickers if t not in ret.columns]
    if faltan:
        raise ValueError(f"Series sin datos de mercado: {faltan}")
    cov = (ret[tickers].cov() * dias).fillna(0.0).values
    idx = {t: i for i, t in enumerate(tickers)}
    idio = pos.vol_anual_supuesta.fillna(0.0).values
    valores = pos.valor_cop.values
    clientes = pos.id_cliente.values
    salida = {}
    for cliente in pd.unique(clientes):
        m = clientes == cliente
        w = valores[m] / valores[m].sum()
        e = np.zeros(len(tickers))
        for wi, i in zip(w, np.where(m)[0]):
            for t, k in cg[i].items():
                e[idx[t]] += wi * k
        var = max(float(e @ cov @ e), 0.0) + float(np.sum((w * idio[m]) ** 2))
        salida[cliente] = round(100 * np.sqrt(var), 2)
    return pd.Series(salida)


def calcular(pos, px):
    """Una fila por cliente con volatilidades y metricas de composicion."""
    pos = pos.copy()
    pos["familia"] = [familia(c, k) for c, k in zip(pos.clase_riesgo, pos.clave)]
    pos["sin_id"] = pos.clave.str.upper().str.startswith(("SIN CODIGO", "SIN CATALOGO"))

    diaria, semanal = retornos(px, "D"), retornos(px, "W")
    vol_cop = volatilidad(pos, a_pesos(diaria), 252, con_fx=True)
    vol_sem = volatilidad(pos, a_pesos(semanal), 52, con_fx=True)
    vol_sin_fx = volatilidad(pos, semanal, 52, con_fx=False)

    filas = []
    for cliente, g in pos.groupby("id_cliente"):
        w = (g.valor_cop / g.valor_cop.sum()).values
        fila = {
            "id_cliente": cliente,
            "total_cop": round(float(g.valor_cop.sum())),
            "n_posiciones": len(g),
            "vol_anual_pct": vol_cop[cliente],
            "vol_semanal_pct": vol_sem[cliente],
            "vol_sin_fx_pct": vol_sin_fx[cliente],
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
    print("Series a revisar (pocos datos, precios casi sin cambio o volatilidad inestable):")
    dudosas = diagnostico(px, usadas)
    print(dudosas.to_string(index=False) if len(dudosas) else "  ninguna")

    res = calcular(pos, px)
    attrs = pd.read_sql(
        "SELECT id_cliente, id_tipo, banca, perfil_riesgo FROM stg.resumen_cliente", eng)
    res = attrs.merge(res, on="id_cliente")
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stg.features_cliente CASCADE"))
    res.to_sql("features_cliente", eng, schema="stg", if_exists="fail", index=False)

    print(f"\nTabla stg.features_cliente creada con {len(res)} clientes.\n")
    cols = ["id_cliente", "perfil_riesgo", "vol_anual_pct", "vol_semanal_pct",
            "vol_sin_fx_pct", "pct_internacional", "pct_renta_variable", "pct_dato_supuesto"]
    print(res.sort_values("vol_anual_pct", ascending=False)[cols].to_string(index=False))


if __name__ == "__main__":
    main()