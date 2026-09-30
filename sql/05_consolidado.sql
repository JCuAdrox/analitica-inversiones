/* consolidado por cliente (COP y USD) */

/* Parametros: TRM (pesos por dolar) por fecha */
CREATE TABLE IF NOT EXISTS stg.param_trm (
    fecha date PRIMARY KEY,
    trm   numeric NOT NULL CHECK (trm > 0)
);

/* Un registro por cliente valido: portafolio local, internacional y totales */
CREATE OR REPLACE VIEW stg.resumen_cliente AS
WITH cop AS (
    SELECT id_cliente,
           MAX(fecha)         AS fecha_cop,
           MAX(banca)         AS banca,
           MAX(perfil_riesgo) AS perfil_riesgo,
           COUNT(*)           AS n_pos_cop,
           MAX(aba_total)     AS aba_cop
    FROM stg.portafolio_cop_actual
    GROUP BY id_cliente
), usd AS (
    SELECT id_cliente,
           MAX(fecha)           AS fecha_usd,
           COUNT(*)             AS n_pos_usd,
           MAX(valor_total_usd) AS valor_usd
    FROM stg.portafolio_usd_actual
    GROUP BY id_cliente
), base AS (
    SELECT c.id_cliente, c.id_tipo, cop.banca, cop.perfil_riesgo,
           cop.fecha_cop, cop.n_pos_cop, cop.aba_cop,
           usd.fecha_usd, usd.n_pos_usd, usd.valor_usd,
           (usd.id_cliente IS NOT NULL) AS tiene_usd,
           (SELECT t.trm FROM stg.param_trm t
             WHERE t.fecha <= usd.fecha_usd
             ORDER BY t.fecha DESC LIMIT 1) AS trm
    FROM stg.dim_cliente c
    JOIN cop ON cop.id_cliente = c.id_cliente
    LEFT JOIN usd ON usd.id_cliente = c.id_cliente
    WHERE c.es_valido
)
SELECT b.*,
    ROUND(b.valor_usd * b.trm, 0) AS valor_usd_en_cop,
    CASE WHEN NOT b.tiene_usd THEN b.aba_cop
         WHEN b.trm IS NULL   THEN NULL
         ELSE ROUND(b.aba_cop + b.valor_usd * b.trm, 0) END AS total_consolidado_cop,
    CASE WHEN NOT b.tiene_usd THEN 0
         WHEN b.trm IS NULL   THEN NULL
         ELSE ROUND(100 * b.valor_usd * b.trm
                    / (b.aba_cop + b.valor_usd * b.trm), 2) END AS pct_internacional
FROM base b;

/* Todas las posiciones actuales en un solo esquema, local e internacional */
CREATE OR REPLACE VIEW stg.posiciones_actuales AS
SELECT id_cliente, fecha, 'COP' AS moneda, 'Local' AS mercado,
       macroactivo AS clase, activo, aba AS valor, pct
FROM stg.portafolio_cop_actual
UNION ALL
SELECT id_cliente, fecha, 'USD', 'Internacional',
       tipo_activo, nombre_activo, valor_usd, pct
FROM stg.portafolio_usd_actual
WHERE id_cliente IN (SELECT id_cliente FROM stg.dim_cliente WHERE es_valido);