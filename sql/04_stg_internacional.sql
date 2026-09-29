/* 04: staging del portafolio internacional (USD) */

/* Paso 1: normaliza texto. No elimina duplicados */
CREATE OR REPLACE VIEW stg.intl_norm AS
SELECT
    NULLIF(NULLIF(TRIM(ingestion_year),     ''), 'None') AS ing_year,
    NULLIF(NULLIF(TRIM(ingestion_month),    ''), 'None') AS ing_month,
    NULLIF(NULLIF(TRIM(ingestion_day),      ''), 'None') AS ing_day,
    NULLIF(NULLIF(TRIM(id_sistema_cliente), ''), 'None') AS id_cliente,
    NULLIF(NULLIF(TRIM(simbol),             ''), 'None') AS simbolo,
    NULLIF(NULLIF(TRIM(cusip),              ''), 'None') AS cusip,
    NULLIF(NULLIF(TRIM(isin),               ''), 'None') AS isin,
    NULLIF(NULLIF(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(nombre_activo), 'ISIN#\S*', '', 'g'),
        '\s+', ' ', 'g')), ''), 'None')                  AS nombre_activo,
    NULLIF(NULLIF(TRIM(cantidad),           ''), 'None') AS cantidad,
    NULLIF(NULLIF(TRIM(valor_mercado),      ''), 'None') AS valor_mercado,
    NULLIF(NULLIF(TRIM(fecha_vencimiento),  ''), 'None') AS fecha_vencimiento,
    NULLIF(NULLIF(TRIM(tasa_cupon),         ''), 'None') AS tasa_cupon
FROM historico_aba_usd_internacional;

/* Paso 2: tipos seguros y fechas (mes/dia/anio, 1900 es centinela) */
CREATE OR REPLACE VIEW stg.intl_evaluada AS
WITH p AS (
    SELECT n.*,
        CASE WHEN ing_year  ~ '^\d{4}$'   THEN ing_year::int  END AS y,
        CASE WHEN ing_month ~ '^\d{1,2}$' THEN ing_month::int END AS m,
        CASE WHEN ing_day   ~ '^\d{1,2}$' THEN ing_day::int   END AS d,
        CASE WHEN cantidad      ~ '^-?\d+(\.\d+)?$' THEN cantidad::numeric      END AS cantidad_num,
        CASE WHEN valor_mercado ~ '^-?\d+(\.\d+)?$' THEN valor_mercado::numeric END AS valor_num,
        CASE WHEN tasa_cupon    ~ '^-?\d+(\.\d+)?$' THEN tasa_cupon::numeric    END AS tasa_num,
        CASE WHEN fecha_vencimiento ~ '^\d{1,2}/\d{1,2}/\d{4}$'
             THEN split_part(fecha_vencimiento, '/', 1)::int END AS v_m,
        CASE WHEN fecha_vencimiento ~ '^\d{1,2}/\d{1,2}/\d{4}$'
             THEN split_part(fecha_vencimiento, '/', 2)::int END AS v_d,
        CASE WHEN fecha_vencimiento ~ '^\d{1,2}/\d{1,2}/\d{4}$'
             THEN split_part(fecha_vencimiento, '/', 3)::int END AS v_y
    FROM stg.intl_norm n
), f AS (
    SELECT p.*,
        CASE WHEN y BETWEEN 2000 AND 2100 AND m BETWEEN 1 AND 12 AND d BETWEEN 1 AND 31
             THEN make_date(y, m, 1) + (d - 1) END AS fecha_calc,
        CASE WHEN v_y BETWEEN 1901 AND 2200 AND v_m BETWEEN 1 AND 12 AND v_d BETWEEN 1 AND 31
             THEN make_date(v_y, v_m, 1) + (v_d - 1) END AS venc_calc
    FROM p
)
SELECT f.*,
    CASE WHEN EXTRACT(MONTH FROM f.fecha_calc) = f.m   THEN f.fecha_calc END AS fecha,
    CASE WHEN EXTRACT(MONTH FROM f.venc_calc)  = f.v_m THEN f.venc_calc  END AS fecha_venc
FROM f;

/* Paso 3: diagnostico, la primera regla que falla da el motivo */
CREATE OR REPLACE VIEW stg.intl_diagnostico AS
SELECT e.*,
    CASE
        WHEN e.fecha IS NULL
            THEN 'fecha de ingestion invalida'
        WHEN e.id_cliente IS NULL OR e.id_cliente !~ '^\d{10,11}$'
            THEN 'id de cliente invalido'
        WHEN e.cantidad_num IS NULL
            THEN 'cantidad invalida'
        WHEN e.valor_num IS NULL
            THEN 'valor de mercado invalido'
        WHEN e.tasa_num IS NULL
            THEN 'tasa de cupon invalida'
        WHEN e.fecha_vencimiento IS NOT NULL
         AND e.fecha_vencimiento !~ '^\d{1,2}/\d{1,2}/\d{4}$'
            THEN 'fecha de vencimiento invalida'
    END AS motivo_cuarentena
FROM stg.intl_evaluada e;

CREATE OR REPLACE VIEW stg.intl_cuarentena AS
SELECT * FROM stg.intl_diagnostico WHERE motivo_cuarentena IS NOT NULL;

/* Paso 4: filas limpias con tipo de activo (regla heuristica, se afina luego) */
CREATE OR REPLACE VIEW stg.intl_limpio AS
SELECT
    d.fecha,
    d.id_cliente,
    d.simbolo,
    d.cusip,
    d.isin,
    d.nombre_activo,
    CASE
        WHEN d.isin = 'Liquidez'                                THEN 'Liquidez'
        WHEN d.tasa_num > 0                                     THEN 'Renta Fija'
        WHEN d.nombre_activo ~* '(ETF|ISHARES|SPDR|VANGUARD)'   THEN 'ETF'
        WHEN d.simbolo IS NOT NULL                              THEN 'Accion'
        ELSE 'Fondo'
    END AS tipo_activo,
    d.cantidad_num AS cantidad,
    d.valor_num    AS valor_usd,
    d.fecha_venc   AS fecha_vencimiento,
    d.tasa_num     AS tasa_cupon
FROM stg.intl_diagnostico d
WHERE d.motivo_cuarentena IS NULL;

/* Paso 5: portafolio internacional (USD) en la ultima fecha de cada cliente */
CREATE OR REPLACE VIEW stg.portafolio_usd_actual AS
WITH ult AS (
    SELECT id_cliente, MAX(fecha) AS fecha
    FROM stg.intl_limpio
    GROUP BY id_cliente
)
SELECT
    l.fecha,
    l.id_cliente,
    l.tipo_activo,
    l.nombre_activo,
    l.simbolo,
    l.isin,
    l.cantidad,
    l.valor_usd,
    l.fecha_vencimiento,
    l.tasa_cupon,
    SUM(l.valor_usd) OVER (PARTITION BY l.id_cliente) AS valor_total_usd,
    ROUND(100 * l.valor_usd
          / NULLIF(SUM(l.valor_usd) OVER (PARTITION BY l.id_cliente), 0), 2) AS pct
FROM stg.intl_limpio l
JOIN ult u
  ON u.id_cliente = l.id_cliente
 AND u.fecha      = l.fecha;