"""Consultas SQL base de la aplicacion. Se cargan en la tabla ConsultaSQL."""

CONSULTAS = [
    {
        "slug": "clientes",
        "nombre": "Lista de clientes",
        "descripcion": "Clientes validos ordenados por total consolidado, para el selector.",
        "visualizacion": "tabla",
        "sql": """
            SELECT id_cliente, id_tipo, banca, perfil_riesgo, tiene_usd
            FROM stg.resumen_cliente
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
            FROM stg.resumen_cliente
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
            FROM stg.portafolio_cop_actual
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
            FROM stg.portafolio_cop_actual
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
            FROM stg.portafolio_usd_actual
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
            FROM stg.portafolio_usd_actual
            WHERE id_cliente = %(id_cliente)s
            ORDER BY valor_usd DESC
        """,
    },
]