/* 03: clientes validos y portafolio COP a la ultima fecha */

/* Un registro por cliente, con atributos vigentes y bandera de validez */
CREATE OR REPLACE VIEW stg.dim_cliente AS
SELECT
    id_cliente,
    MIN(id_tipo)          AS id_tipo,
    COUNT(DISTINCT fecha) AS n_fechas,
    MIN(fecha)            AS primera_fecha,
    MAX(fecha)            AS ultima_fecha,
    (ARRAY_AGG(cod_banca ORDER BY fecha DESC)
        FILTER (WHERE cod_banca IS NOT NULL))[1]          AS cod_banca,
    (ARRAY_AGG(cod_perfil_riesgo ORDER BY fecha DESC)
        FILTER (WHERE cod_perfil_riesgo IS NOT NULL))[1]  AS cod_perfil_riesgo,
    COUNT(DISTINCT fecha) >= 30                           AS es_valido
FROM stg.macro_limpio
GROUP BY id_cliente;

/* Portafolio local (COP) de cada cliente en su ultima fecha disponible */
CREATE OR REPLACE VIEW stg.portafolio_cop_actual AS
SELECT
    c.id_cliente,
    c.id_tipo,
    c.ultima_fecha AS fecha,
    b.banca,
    COALESCE(p.perfil_riesgo, 'SIN INFORMACION') AS perfil_riesgo,
    m.macroactivo,
    m.cod_activo,
    m.activo,
    m.aba,
    SUM(m.aba) OVER (PARTITION BY c.id_cliente) AS aba_total,
    ROUND(100 * m.aba / SUM(m.aba) OVER (PARTITION BY c.id_cliente), 2) AS pct
FROM stg.dim_cliente c
JOIN stg.macro_limpio m
  ON m.id_cliente = c.id_cliente
 AND m.fecha      = c.ultima_fecha
LEFT JOIN stg.dim_banca b
  ON b.cod_banca = c.cod_banca
LEFT JOIN stg.dim_perfil_riesgo p
  ON p.cod_perfil_riesgo = c.cod_perfil_riesgo
WHERE c.es_valido;