import pandas as pd
import plotly.express as px
from django.shortcuts import render

from . import servicios


def _fmt(numero, decimales=0):
    """Formato colombiano: punto para miles y coma para decimales."""
    if numero is None:
        return "N/D"
    texto = f"{numero:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _html(fig, con_js):
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), height=380)
    return fig.to_html(
        full_html=False, include_plotlyjs="cdn" if con_js else False
    )


def _dona(filas, titulo, con_js=False):
    df = pd.DataFrame(filas)
    fig = px.pie(df, names="clase", values="valor", hole=0.5, title=titulo)
    fig.update_traces(textinfo="percent+label")
    return _html(fig, con_js)


def _barras(filas, columna_y, columna_x, columna_pct, titulo):
    df = pd.DataFrame(filas).head(10)
    df[columna_y] = df[columna_y].astype(str).str.slice(0, 38)
    fig = px.bar(
        df, x=columna_x, y=columna_y, orientation="h", title=titulo, text=columna_pct
    )
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_traces(texttemplate="%{text} %", textposition="outside")
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
            cop_det, "activo", "aba", "pct", "Principales posiciones locales (COP)"
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