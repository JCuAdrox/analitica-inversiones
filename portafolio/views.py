import pandas as pd
import numpy as np
import plotly.express as px
from django.shortcuts import render
from django.db import DatabaseError
from .models import ConsultaSQL
from . import servicios


def _fmt(numero, decimales=0):
    """Formato colombiano: punto para miles y coma para decimales."""
    if numero is None:
        return "N/D"
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _html(fig, con_js):
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=380, separators=",.")
    return fig.to_html(
        full_html=False, include_plotlyjs="cdn" if con_js else False
    )


def _dona(filas, titulo, con_js=False):
    df = pd.DataFrame(filas)
    fig = px.pie(df, names="clase", values="valor", hole=0.5, title=titulo)
    fig.update_traces(textinfo="percent+label")
    return _html(fig, con_js)


def _barras(filas, columna_y, columna_x, columna_pct, titulo, etiqueta_x):
    df = pd.DataFrame(filas).head(10)
    df[columna_y] = df[columna_y].astype(str).str.slice(0, 38)
    df["etiqueta"] = df[columna_pct].map(lambda p: _fmt(p, 1) + " %")
    fig = px.bar(
        df, x=columna_x, y=columna_y, orientation="h", title=titulo,
        text="etiqueta", labels={columna_x: etiqueta_x, columna_y: ""},
    )
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(range=[0, float(df[columna_x].max()) * 1.25])
    fig.update_traces(textposition="outside", cliponaxis=False)
    return _html(fig, False)


def dashboard(request):
    clientes = servicios.ejecutar("clientes")
    if not clientes:
        return render(request, "portafolio/dashboard.html", {"sin_datos": True})

    ids = [c["id_cliente"] for c in clientes]
    seleccionado = request.GET.get("id_cliente")
    if seleccionado not in ids:
        seleccionado = ids[0]
    params = {"id_cliente": seleccionado}

    opciones = []
    for c in clientes:
        etiqueta = f'{c["id_cliente"]} | {c["banca"] or "N/D"} | {c["perfil_riesgo"] or "N/D"}'
        if c["id_tipo"] == "TRUNCADO":
            etiqueta += " | ID truncado"
        if c["tiene_usd"]:
            etiqueta += " | con USD"
        opciones.append({"id": c["id_cliente"], "etiqueta": etiqueta})

    r = servicios.ejecutar("resumen_cliente", params)[0]
    tiene_usd = r["tiene_usd"]
    kpis = [
        ("Banca", r["banca"] or "N/D"),
        ("Perfil de riesgo", r["perfil_riesgo"] or "N/D"),
        ("Portafolio local (COP)", "$ " + _fmt(r["aba_cop"])),
        (
            "Portafolio internacional (USD)",
            "US$ " + _fmt(r["valor_usd"]) if tiene_usd else "Sin portafolio",
        ),
        (
            "Total consolidado (COP)",
            "$ " + _fmt(r["total_consolidado_cop"]),
        ),
        (
            "Exposicion internacional",
            f'{_fmt(r["pct_internacional"], 1)} %' if tiene_usd else "0 %",
        ),
    ]

    cop_clase = servicios.ejecutar("cop_por_clase", params)
    cop_det = servicios.ejecutar("cop_detalle", params)
    contexto = {
        "opciones": opciones,
        "seleccionado": seleccionado,
        "resumen": r,
        "kpis": kpis,
        "tiene_usd": tiene_usd,
        "graf_cop_dona": _dona(
            cop_clase, "Portafolio local por macroactivo (COP)", con_js=True
        ),
        "graf_cop_barras": _barras(
            cop_det, "activo", "aba", "pct",
            "Principales posiciones locales (COP)", "Valor (COP)"
        ),
        "tabla_cop": [
            {
                "activo": f["activo"],
                "clase": f["macroactivo"],
                "valor": _fmt(f["aba"]),
                "pct": _fmt(f["pct"], 2),
            }
            for f in cop_det
        ],
    }
    contexto.update(contexto_modelo_cliente(seleccionado))
    if tiene_usd:
        usd_tipo = servicios.ejecutar("usd_por_tipo", params)
        usd_det = servicios.ejecutar("usd_detalle", params)
        contexto.update(
            {
                "graf_usd_dona": _dona(
                    usd_tipo, "Portafolio internacional por tipo (USD)"
                ),
                "graf_usd_barras": _barras(
                    usd_det,
                    "nombre_activo",
                    "valor_usd",
                    "pct",
                    "Principales posiciones internacionales (USD)",
                    "Valor (USD)",
                ),
                "tabla_usd": [
                    {
                        "nombre": f["nombre_activo"],
                        "tipo": f["tipo_activo"],
                        "cantidad": _fmt(f["cantidad"], 2),
                        "valor": _fmt(f["valor_usd"], 2),
                        "pct": _fmt(f["pct"], 2),
                        "vence": f["fecha_vencimiento"].strftime("%d/%m/%Y")
                        if f["fecha_vencimiento"]
                        else "",
                        "cupon": _fmt(f["tasa_cupon"], 3) if f["tasa_cupon"] else "",
                    }
                    for f in usd_det
                ],
            }
        )

    return render(request, "portafolio/dashboard.html", contexto)

ORDEN_DECLARADO = ["CONSERVADOR", "MODERADO", "AGRESIVO", "SIN DEFINIR", "SIN INFORMACION"]
ORDEN_INFERIDO = ["CONSERVADOR", "MODERADO", "AGRESIVO"]
COLOR_PRIORIDAD = {"ALTA": "#c0392b", "MEDIA": "#e0a800", "BAJA": "#7f8c8d"}


def _intentar(slug, params=None):
    """Ejecuta una consulta del modelo. Devuelve None si el modelo aun no se ha ejecutado."""
    try:
        return servicios.ejecutar(slug, params)
    except (DatabaseError, ConsultaSQL.DoesNotExist):
        return None


def _filas_oportunidades(filas):
    return [
        {
            "id_cliente": o["id_cliente"],
            "segmento": o.get("segmento") or "N/D",
            "tipo": o["tipo"],
            "prioridad": o["prioridad"],
            "monto": _fmt(o["monto_cop"]),
            "detalle": o["detalle"],
        }
        for o in filas
    ]


def modelo(request):
    clientes = _intentar("modelo_clientes")
    if not clientes:
        return render(request, "portafolio/modelo.html", {"sin_modelo": True})

    df = pd.DataFrame(clientes)
    segmentos = _intentar("modelo_segmentos") or []
    oportunidades = _intentar("oportunidades") or []
    op = pd.DataFrame(oportunidades)

    kpis = [
        ("Clientes analizados", str(len(df))),
        ("Sin perfil declarado", str(int((df.coherencia == "SIN PERFIL DECLARADO").sum()))),
        ("Perfil incoherente", str(int(df.coherencia.isin(
            ["MAS RIESGO QUE SU PERFIL", "MENOS RIESGO QUE SU PERFIL"]).sum()))),
        ("Oportunidades", str(len(op))),
        ("Prioridad alta", str(int((op.prioridad == "ALTA").sum())) if len(op) else "0"),
    ]

    # mapa de segmentos con ejes interpretables
    df["tamano"] = np.log10(df.total_cop.astype(float).clip(lower=10))
    fig = px.scatter(
        df, x="pct_internacional", y="riesgo_mercado", color="segmento", size="tamano",
        hover_name="id_cliente",
        hover_data={"perfil_declarado": True, "perfil_inferido": True, "tamano": False},
        labels={"pct_internacional": "% del portafolio en el exterior",
                "riesgo_mercado": "Riesgo de mercado (% anual, sin TRM)",
                "segmento": "Segmento", "perfil_declarado": "Perfil declarado",
                "perfil_inferido": "Perfil inferido"},
        title="Mapa de segmentos (tamaño del punto según el valor del portafolio)",
    )
    fig.update_layout(legend=dict(orientation="h", y=-0.25))
    graf_segmentos = _html(fig, True)

    # matriz perfil declarado frente a perfil inferido
    cruce = (pd.crosstab(df.perfil_declarado, df.perfil_inferido)
             .reindex(index=ORDEN_DECLARADO, columns=ORDEN_INFERIDO, fill_value=0))
    fig = px.imshow(
        cruce, text_auto=True, color_continuous_scale="Blues", aspect="auto",
        labels=dict(x="Perfil inferido por el modelo", y="Perfil declarado", color="Clientes"),
        title="Perfil declarado frente a perfil inferido",
    )
    graf_coherencia = _html(fig, False)

    # oportunidades por tipo y prioridad
    graf_oportunidades = None
    if len(op):
        conteo = op.groupby(["tipo", "prioridad"]).size().reset_index(name="casos")
        fig = px.bar(
            conteo, x="casos", y="tipo", color="prioridad", orientation="h",
            color_discrete_map=COLOR_PRIORIDAD,
            category_orders={"prioridad": ["ALTA", "MEDIA", "BAJA"]},
            labels={"casos": "Casos", "tipo": "", "prioridad": "Prioridad"},
            title="Oportunidades por tipo y prioridad",
        )
        graf_oportunidades = _html(fig, False)

    tipo = request.GET.get("tipo", "")
    prioridad = request.GET.get("prioridad", "")
    filtradas = [o for o in oportunidades
                 if (not tipo or o["tipo"] == tipo) and (not prioridad or o["prioridad"] == prioridad)]

    contexto = {
        "kpis": kpis,
        "graf_segmentos": graf_segmentos,
        "graf_coherencia": graf_coherencia,
        "graf_oportunidades": graf_oportunidades,
        "segmentos": [
            {"nombre": s["segmento"], "clientes": s["clientes"], "riesgo": _fmt(s["riesgo"], 1),
             "pct_intl": _fmt(s["pct_intl"], 1), "hhi": _fmt(s["hhi"], 2),
             "total": _fmt(s["total_cop"] / 1e6),  "oportunidades": int(s["oportunidades"])}
            for s in segmentos
        ],
        "tipos": sorted({o["tipo"] for o in oportunidades}),
        "tipo": tipo,
        "prioridad": prioridad,
        "oportunidades": _filas_oportunidades(filtradas),
    }
    return render(request, "portafolio/modelo.html", contexto)


def contexto_modelo_cliente(id_cliente):
    """Datos del modelo para la ficha de un cliente. Se usa desde dashboard."""
    params = {"id_cliente": id_cliente}
    m = _intentar("modelo_cliente", params)
    if not m:
        return {"modelo": None}
    m = m[0]
    return {
        "modelo": {
            "segmento": m["segmento"] or "N/D",
            "perfil_declarado": m["perfil_declarado"],
            "perfil_inferido": m["perfil_inferido"],
            "coherencia": m["coherencia"],
            "accion": m["accion_sugerida"],
            "riesgo": _fmt(m["riesgo_mercado"], 1),
            "riesgo_fx": _fmt(m["riesgo_total_con_fx"], 1),
            "confianza": m["confianza_dato"],
            "estable": m["clasificacion_estable"],
        },
        "oport_cliente": _filas_oportunidades(_intentar("oportunidades_cliente", params) or []),
    }