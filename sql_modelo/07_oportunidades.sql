/* oportunidades comerciales por cliente.
   Depende de stg.perfil_cliente (06), stg.features_cliente, stg.segmento_cliente
   y del portafolio internacional actual */

CREATE OR REPLACE VIEW stg.oportunidades AS
WITH base AS (
    SELECT p.*, f.pct_liquidez, f.pct_sin_identificar
    FROM stg.perfil_cliente p
    JOIN stg.features_cliente f USING (id_cliente)
),
venc AS (
    SELECT u.id_cliente, u.nombre_activo, u.fecha_vencimiento,
           (u.fecha_vencimiento - u.fecha) AS dias,
           u.valor_usd * r.trm AS valor_cop
    FROM stg.portafolio_usd_actual u
    JOIN stg.resumen_cliente r USING (id_cliente)
    WHERE u.fecha_vencimiento IS NOT NULL
      AND u.fecha_vencimiento <= u.fecha + 180
),
todas AS (
    /* 1. Perfilamiento pendiente */
    SELECT id_cliente, 'Perfilamiento pendiente' AS tipo, total_cop AS monto_cop,
           'Sin perfil declarado. Perfil sugerido por el riesgo del portafolio: '
           || perfil_inferido AS detalle,
           CASE WHEN total_cop >= 1e9 THEN 1 WHEN total_cop >= 1e8 THEN 2 ELSE 3 END AS prioridad
    FROM base WHERE coherencia = 'SIN PERFIL DECLARADO'

    UNION ALL /* 2. Idoneidad: asume mas riesgo del declarado */
    SELECT id_cliente, 'Revisar idoneidad', total_cop,
           'Perfil ' || perfil_declarado || ' con riesgo de mercado de '
           || ROUND(riesgo_mercado::numeric, 1) || ' %, propio de un perfil ' || perfil_inferido,
           1
    FROM base WHERE coherencia = 'MAS RIESGO QUE SU PERFIL'

    UNION ALL /* 3. Capacidad de riesgo sin usar */
    SELECT id_cliente, 'Capacidad de riesgo sin usar', total_cop,
           'Perfil ' || perfil_declarado || ' con portafolio de riesgo '
           || perfil_inferido || ' (' || ROUND(riesgo_mercado::numeric, 1)
           || ' %). Proponer productos acordes a su perfil',
           CASE WHEN total_cop >= 1e9 THEN 1 ELSE 2 END
    FROM base WHERE coherencia = 'MENOS RIESGO QUE SU PERFIL'

    UNION ALL /* 4. Vencimientos proximos: reinversion */
    SELECT id_cliente, 'Vencimiento proximo', valor_cop,
           nombre_activo || ' vence en ' || dias || ' dias',
           CASE WHEN dias <= 90 THEN 1 ELSE 2 END
    FROM venc

    UNION ALL /* 5. Concentracion alta */
    SELECT id_cliente, 'Concentracion alta', total_cop,
           'Indice de concentracion HHI de ' || ROUND(hhi::numeric, 2)
           || ' en ' || n_posiciones || ' posicion(es)',
           CASE WHEN total_cop >= 1e8 THEN 2 ELSE 3 END
    FROM base WHERE hhi >= 0.6

    UNION ALL /* 6. Liquidez ociosa */
    SELECT id_cliente, 'Liquidez ociosa', ROUND(total_cop * pct_liquidez / 100),
           ROUND(pct_liquidez::numeric, 1) || ' % del portafolio en liquidez',
           CASE WHEN total_cop * pct_liquidez / 100 >= 1e8 THEN 2 ELSE 3 END
    FROM base WHERE pct_liquidez >= 20

    UNION ALL /* 7. Baja diversificacion internacional (solo IDs completos, los truncados no se cruzan) */
    SELECT id_cliente, 'Diversificacion internacional', total_cop,
           'Solo ' || ROUND(pct_internacional::numeric, 1)
           || ' % en el exterior con un portafolio relevante',
           2
    FROM base
    WHERE id_tipo = 'COMPLETO' AND pct_internacional < 20 AND total_cop >= 1e8

    UNION ALL /* 8. Calidad de datos: posiciones sin identificar */
    SELECT id_cliente, 'Posiciones sin identificar', ROUND(total_cop * pct_sin_identificar / 100),
           ROUND(pct_sin_identificar::numeric, 1)
           || ' % del portafolio sin codigo de activo o fuera del catalogo',
           CASE WHEN total_cop * pct_sin_identificar / 100 >= 1e8 THEN 2 ELSE 3 END
    FROM base WHERE pct_sin_identificar > 0
)
SELECT t.id_cliente, s.segmento, t.tipo,
       CASE t.prioridad WHEN 1 THEN 'ALTA' WHEN 2 THEN 'MEDIA' ELSE 'BAJA' END AS prioridad,
       t.prioridad AS orden_prioridad,
       t.monto_cop, t.detalle
FROM todas t
LEFT JOIN stg.segmento_cliente s USING (id_cliente);

/* Vista resumen para la app: un registro por cliente con todo el modelo */
CREATE OR REPLACE VIEW stg.modelo_cliente AS
SELECT p.id_cliente, p.id_tipo, p.banca, p.perfil_declarado, p.perfil_inferido,
       p.coherencia, p.accion_sugerida, p.clasificacion_estable, p.confianza_dato,
       p.riesgo_mercado, p.riesgo_total_con_fx, p.hhi, p.pct_internacional,
       p.total_cop, s.segmento, s.pc1, s.pc2,
       COUNT(o.tipo) AS n_oportunidades,
       COUNT(o.tipo) FILTER (WHERE o.prioridad = 'ALTA') AS n_alta
FROM stg.perfil_cliente p
LEFT JOIN stg.segmento_cliente s USING (id_cliente)
LEFT JOIN stg.oportunidades o USING (id_cliente)
GROUP BY p.id_cliente, p.id_tipo, p.banca, p.perfil_declarado, p.perfil_inferido,
         p.coherencia, p.accion_sugerida, p.clasificacion_estable, p.confianza_dato,
         p.riesgo_mercado, p.riesgo_total_con_fx, p.hhi, p.pct_internacional,
         p.total_cop, s.segmento, s.pc1, s.pc2;