"""segmentacion de clientes por comportamiento (clustering explicable)."""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
VARIABLES = ["riesgo_mercado", "hhi", "pct_internacional", "pct_renta_variable"]
TAM_MIN = 5  # un segmento con menos clientes no se considera util


def engine_bd():
    load_dotenv(ROOT / ".env")
    url = (
        f"postgresql+psycopg://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    return create_engine(url)


def estandarizar(df):
    X = df[VARIABLES].astype(float)
    return ((X - X.mean()) / X.std(ddof=0)).values


def elegir_k(Z, ks=range(2, 7)):
    """Prueba varios k y elige el de mayor silueta cuyos segmentos tengan al menos TAM_MIN clientes."""
    filas = []
    for k in ks:
        etiquetas = KMeans(k, n_init=20, random_state=0).fit_predict(Z)
        filas.append((k, round(float(silhouette_score(Z, etiquetas)), 3),
                      int(np.bincount(etiquetas).min())))
    tabla = pd.DataFrame(filas, columns=["k", "silueta", "segmento_mas_pequeno"])
    validos = tabla[tabla.segmento_mas_pequeno >= TAM_MIN]
    mejor = int(validos.sort_values("silueta", ascending=False).iloc[0].k)
    return mejor, tabla


def nombrar(c):
    """Nombre legible a partir de los promedios del segmento."""
    ambito = "Internacional" if c.pct_internacional >= 50 else "Local"
    conc = "concentrado" if c.hhi >= 0.6 else "diversificado"
    if c.riesgo_mercado >= 20:
        estilo = "renta variable"
    elif c.riesgo_mercado >= 5:
        estilo = "riesgo medio"
    else:
        estilo = "liquidez y renta fija"
    return f"{ambito} {conc}, {estilo}"


def segmentar(df):
    Z = estandarizar(df)
    k, tabla = elegir_k(Z)
    modelo = KMeans(k, n_init=20, random_state=0).fit(Z)
    etiquetas = modelo.labels_

    # estabilidad: cuantas semillas distintas reproducen exactamente la misma particion
    iguales = sum(
        adjusted_rand_score(etiquetas, KMeans(k, n_init=20, random_state=s).fit_predict(Z)) == 1.0
        for s in range(1, 11))

    out = df.copy()
    out["segmento_id"] = etiquetas
    nombres = {}
    for sid, g in out.groupby("segmento_id"):
        nombre = nombrar(g[VARIABLES].mean())
        nombres[sid] = nombre if nombre not in nombres.values() else f"{nombre} ({sid + 1})"
    out["segmento"] = out.segmento_id.map(nombres)

    # coordenadas 2D (componentes principales) para graficar los segmentos en la app
    U, S, _ = np.linalg.svd(Z - Z.mean(axis=0), full_matrices=False)
    out["pc1"], out["pc2"] = (U[:, 0] * S[0]).round(4), (U[:, 1] * S[1]).round(4)
    return out, tabla, k, iguales


def main():
    eng = engine_bd()
    df = pd.read_sql(
        "SELECT id_cliente, perfil_riesgo AS perfil_declarado, "
        "vol_sin_fx_pct AS riesgo_mercado, hhi, pct_internacional, "
        "pct_renta_variable, total_cop FROM stg.features_cliente", eng)
    res, tabla, k, iguales = segmentar(df)

    print("Prueba de numero de segmentos:")
    print(tabla.to_string(index=False))
    print(f"\nSe eligen {k} segmentos. Estabilidad: {iguales} de 10 semillas dan la misma particion.\n")

    resumen = res.groupby("segmento").agg(
        clientes=("id_cliente", "size"),
        riesgo=("riesgo_mercado", "mean"), hhi=("hhi", "mean"),
        pct_intl=("pct_internacional", "mean"), pct_rv=("pct_renta_variable", "mean"),
        total_millones=("total_cop", lambda s: s.sum() / 1e6)).round(1)
    print(resumen.to_string(), "\n")
    for nombre, g in res.groupby("segmento"):
        print(f"{nombre}: {', '.join(g.id_cliente)}")

    salida = res[["id_cliente", "segmento_id", "segmento", "pc1", "pc2"]]
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stg.segmento_cliente CASCADE"))
    salida.to_sql("segmento_cliente", eng, schema="stg", if_exists="fail", index=False)
    print("\nTabla stg.segmento_cliente creada.")


if __name__ == "__main__":
    main()