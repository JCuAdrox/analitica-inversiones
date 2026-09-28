/* 02: staging de macroactivos (COP) */

/* Paso 1: normaliza texto (vacio y None pasan a NULL) y elimina duplicados exactos */
CREATE OR REPLACE VIEW stg.macro_norm AS
SELECT DISTINCT
    NULLIF(NULLIF(TRIM(ingestion_year),     ''), 'None') AS ing_year,
    NULLIF(NULLIF(TRIM(ingestion_month),    ''), 'None') AS ing_month,
    NULLIF(NULLIF(TRIM(ingestion_day),      ''), 'None') AS ing_day,
    NULLIF(NULLIF(TRIM(id_sistema_cliente), ''), 'None') AS id_cliente,
    NULLIF(NULLIF(TRIM(macroactivo),        ''), 'None') AS macroactivo,
    NULLIF(NULLIF(TRIM(cod_activo),         ''), 'None') AS cod_activo,
    NULLIF(NULLIF(TRIM(aba),                ''), 'None') AS aba,
    NULLIF(NULLIF(TRIM(cod_perfil_riesgo),  ''), 'None') AS cod_perfil_riesgo,
    NULLIF(NULLIF(TRIM(cod_banca),          ''), 'None') AS cod_banca
FROM historico_aba_macroactivos;

/* Paso 2: relacion codigo de activo a macroactivo, solo si es unica.
   Sirve para recuperar filas con macroactivo vacio */
CREATE OR REPLACE VIEW stg.map_activo_macro AS
SELECT cod_activo, MIN(macroactivo) AS macroactivo
FROM stg.macro_norm
WHERE macroactivo IN ('Renta Variable', 'FICs', 'Renta Fija')
  AND cod_activo ~ '^\d+$'
GROUP BY cod_activo
HAVING COUNT(DISTINCT macroactivo) = 1;

/* Paso 3: convierte tipos de forma segura y calcula la fecha de la foto */
CREATE OR REPLACE VIEW stg.macro_evaluada AS
WITH p AS (
    SELECT n.*,
        CASE WHEN ing_year  ~ '^\d{4}$'   THEN ing_year::int  END AS y,
        CASE WHEN ing_month ~ '^\d{1,2}$' THEN ing_month::int END AS m,
        CASE WHEN ing_day   ~ '^\d{1,2}$' THEN ing_day::int   END AS d,
        CASE WHEN aba ~ '^\d+(\.\d+)?$'   THEN aba::numeric   END AS aba_num
    FROM stg.macro_norm n
), f AS (
    SELECT p.*,
        CASE WHEN y BETWEEN 2000 AND 2100
                  AND m BETWEEN 1 AND 12
                  AND d BETWEEN 1 AND 31
             THEN make_date(y, m, 1) + (d - 1) END AS fecha_calc
    FROM p
)
SELECT f.*,
    CASE WHEN EXTRACT(MONTH FROM f.fecha_calc) = f.m THEN f.fecha_calc END AS fecha,
    COALESCE(f.macroactivo, mm.macroactivo) AS macro_final
FROM f
LEFT JOIN stg.map_activo_macro mm ON mm.cod_activo = f.cod_activo;

/* Paso 4: diagnostico, la primera regla que falla explica el motivo */
CREATE OR REPLACE VIEW stg.macro_diagnostico AS
SELECT e.*,
    CASE
        WHEN e.fecha IS NULL
            THEN 'fecha de ingestion invalida'
        WHEN e.macro_final IS NULL
          OR e.macro_final NOT IN ('Renta Variable', 'FICs', 'Renta Fija')
            THEN 'macroactivo invalido o no recuperable'
        WHEN e.aba_num IS NULL OR e.aba_num <= 0
            THEN 'aba invalido'
        WHEN e.id_cliente IS NULL
          OR NOT (e.id_cliente ~ '^\d+$' OR e.id_cliente ~ '^\d\.\d+E\+\d+$')
            THEN 'id de cliente invalido'
        WHEN e.cod_banca IS NOT NULL
          AND e.cod_banca NOT IN (SELECT cod_banca FROM stg.dim_banca)
            THEN 'cod_banca invalido'
        WHEN e.cod_perfil_riesgo IS NOT NULL
          AND e.cod_perfil_riesgo NOT IN
              (SELECT cod_perfil_riesgo::text FROM stg.dim_perfil_riesgo)
            THEN 'perfil de riesgo invalido'
        WHEN e.cod_activo IS NOT NULL AND e.cod_activo !~ '^\d+$'
            THEN 'cod_activo invalido'
    END AS motivo_cuarentena
FROM stg.macro_evaluada e;

/* Paso 5a: filas danadas, aparte y con su motivo */
CREATE OR REPLACE VIEW stg.macro_cuarentena AS
SELECT * FROM stg.macro_diagnostico
WHERE motivo_cuarentena IS NOT NULL;

/* Paso 5b: filas limpias, tipadas y con nombre de activo.
   Supuesto: el codigo 10007 es un typo de 1007 (Fiducuenta).
   Para desactivarlo, borra esa linea del VALUES */
CREATE OR REPLACE VIEW stg.macro_limpio AS
WITH b AS (
    SELECT d.*,
        (COALESCE(corr.destino, d.cod_activo))::int AS cod_activo_final
    FROM stg.macro_diagnostico d
    LEFT JOIN (VALUES ('10007', '1007')) AS corr(origen, destino)
           ON corr.origen = d.cod_activo
    WHERE d.motivo_cuarentena IS NULL
)
SELECT
    b.fecha,
    b.id_cliente,
    CASE WHEN b.id_cliente ~ '^\d+$' THEN 'COMPLETO' ELSE 'TRUNCADO' END AS id_tipo,
    b.macro_final               AS macroactivo,
    b.cod_activo_final          AS cod_activo,
    COALESCE(a.activo,
             CASE WHEN b.cod_activo_final IS NULL THEN 'SIN CODIGO'
                  ELSE 'SIN CATALOGO' END) AS activo,
    b.aba_num                   AS aba,
    b.cod_perfil_riesgo::int    AS cod_perfil_riesgo,
    b.cod_banca
FROM b
LEFT JOIN stg.dim_activo a ON a.cod_activo = b.cod_activo_final;