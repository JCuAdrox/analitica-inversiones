/* Capa staging: vistas limpias sobre las tablas crudas */
CREATE SCHEMA IF NOT EXISTS stg;

/* Activos: corrige 1115 a 1015 y convierte el codigo a entero */
CREATE OR REPLACE VIEW stg.dim_activo AS
SELECT DISTINCT
    (CASE WHEN TRIM(cod_activo) = '1115' THEN '1015'
          ELSE TRIM(cod_activo) END)::int AS cod_activo,
    TRIM(activo) AS activo
FROM catalogo_activos;

/* Banca: elimina el duplicado PR */
CREATE OR REPLACE VIEW stg.dim_banca AS
SELECT DISTINCT
    TRIM(cod_banca) AS cod_banca,
    TRIM(banca)     AS banca
FROM catalogo_banca;

/* Perfil de riesgo: codigo entero y nombre limpio */
CREATE OR REPLACE VIEW stg.dim_perfil_riesgo AS
SELECT DISTINCT
    TRIM(cod_perfil_riesgo)::int AS cod_perfil_riesgo,
    TRIM(perfil_riesgo)          AS perfil_riesgo
FROM cat_perfil_riesgo;