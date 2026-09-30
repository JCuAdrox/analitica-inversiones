"""Consultas SQL base de la aplicacion. Se cargan en la tabla ConsultaSQL."""

CONSULTAS = [
    {
        "slug": "clientes",
        "nombre": "Lista de clientes",
        "descripcion": "Clientes validos ordenados por total consolidado, para el selector.",
        "visualizacion": "tabla",
        "sql": """
            SELECT id_cliente, id_tipo, banca, perfil_riesgo, tiene_usd
            FROM app.resumen_cliente
            ORDER BY total_consolidado_cop DESC NULLS LAST, aba_cop DESC
        """,
    },
    {
        "slug": "resumen_cliente",
        "nombre": "Resumen del cliente",
        "descripcion": "Totales local, internacional y consolidado de un cliente.",
        "visualizacion": "tabla",
        "sql": """
            SELECT *
            FROM app.resumen_cliente
            WHERE id_cliente = %(id_cliente)s
        """,
    },
    {
        "slug": "cop_por_clase",
        "nombre": "Portafolio local por macroactivo (COP)",
        "descripcion": "Composicion del portafolio local a la ultima fecha del cliente.",
        "visualizacion": "dona",
        "sql": """
            SELECT macroactivo AS clase,
                   SUM(aba) AS valor,
                   ROUND(100 * SUM(aba) / MAX(aba_total), 2) AS pct
            FROM app.portafolio_cop_actual
            WHERE id_cliente = %(id_cliente)s
            GROUP BY macroactivo
            ORDER BY valor DESC
        """,
    },
    {
        "slug": "cop_detalle",
        "nombre": "Posiciones locales (COP)",
        "descripcion": "Detalle por activo del portafolio local.",
        "visualizacion": "barras",
        "sql": """
            SELECT activo, macroactivo, aba, pct
            FROM app.portafolio_cop_actual
            WHERE id_cliente = %(id_cliente)s
            ORDER BY aba DESC
        """,
    },
    {
        "slug": "usd_por_tipo",
        "nombre": "Portafolio internacional por tipo de activo (USD)",
        "descripcion": "Composicion del portafolio internacional a la ultima fecha.",
        "visualizacion": "dona",
        "sql": """
            SELECT tipo_activo AS clase,
                   SUM(valor_usd) AS valor,
                   ROUND(100 * SUM(valor_usd) / MAX(valor_total_usd), 2) AS pct
            FROM app.portafolio_usd_actual
            WHERE id_cliente = %(id_cliente)s
            GROUP BY tipo_activo
            ORDER BY valor DESC
        """,
    },
    {
        "slug": "usd_detalle",
        "nombre": "Posiciones internacionales (USD)",
        "descripcion": "Detalle por activo del portafolio internacional.",
        "visualizacion": "barras",
        "sql": """
            SELECT nombre_activo, tipo_activo, cantidad, valor_usd, pct,
                   fecha_vencimiento, tasa_cupon
            FROM app.portafolio_usd_actual
            WHERE id_cliente = %(id_cliente)s
            ORDER BY valor_usd DESC
        """,
    },
        {
        "slug": "modelo_clientes",
        "nombre": "Modelo: resumen por cliente",
        "descripcion": "Perfil inferido, coherencia, segmento y oportunidades de cada cliente.",
        "visualizacion": "tabla",
        "sql": """
            SELECT * FROM app.modelo_cliente ORDER BY total_cop DESC
        """,
    },
    {
        "slug": "modelo_segmentos",
        "nombre": "Modelo: resumen por segmento",
        "descripcion": "Promedios y valor total de cada segmento de clientes.",
        "visualizacion": "tabla",
        "sql": """
            SELECT segmento, COUNT(*) AS clientes,
                   ROUND(AVG(riesgo_mercado)::numeric, 1)    AS riesgo,
                   ROUND(AVG(pct_internacional)::numeric, 1) AS pct_intl,
                   ROUND(AVG(hhi)::numeric, 2)               AS hhi,
                   SUM(total_cop)                            AS total_cop,
                   SUM(n_oportunidades)                      AS oportunidades
            FROM app.modelo_cliente
            GROUP BY segmento
            ORDER BY total_cop DESC
        """,
    },
    {
        "slug": "oportunidades",
        "nombre": "Modelo: oportunidades priorizadas",
        "descripcion": "Todas las oportunidades comerciales, por prioridad y monto.",
        "visualizacion": "tabla",
        "sql": """
            SELECT * FROM app.oportunidades
            ORDER BY orden_prioridad, monto_cop DESC
        """,
    },
    {
        "slug": "modelo_cliente",
        "nombre": "Modelo: diagnostico de un cliente",
        "descripcion": "Resultado del modelo para el cliente seleccionado.",
        "visualizacion": "tabla",
        "sql": """
            SELECT * FROM app.modelo_cliente WHERE id_cliente = %(id_cliente)s
        """,
    },
    {
        "slug": "oportunidades_cliente",
        "nombre": "Modelo: oportunidades de un cliente",
        "descripcion": "Oportunidades del cliente seleccionado.",
        "visualizacion": "tabla",
        "sql": """
            SELECT id_cliente, segmento, tipo, prioridad, monto_cop, detalle
            FROM app.oportunidades
            WHERE id_cliente = %(id_cliente)s
            ORDER BY orden_prioridad, monto_cop DESC
        """,
    },
]