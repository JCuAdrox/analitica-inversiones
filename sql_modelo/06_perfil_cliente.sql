/* perfil de riesgo inferido y coherencia con el perfil declarado.
   Depende de stg.features_cliente, que crea modelo/riesgo_portafolio.py */

CREATE OR REPLACE VIEW stg.perfil_cliente AS
WITH v AS (
    SELECT f.*,
        f.vol_sin_fx_pct AS riesgo_mercado,
        CASE f.perfil_riesgo
            WHEN 'CONSERVADOR' THEN 1
            WHEN 'MODERADO'    THEN 2
            WHEN 'AGRESIVO'    THEN 3
        END AS nivel_declarado,
        /* umbrales base: menos de 5 % conservador, de 5 a 15 % moderado, desde 15 % agresivo */
        CASE WHEN f.vol_sin_fx_pct < 5  THEN 1
             WHEN f.vol_sin_fx_pct < 15 THEN 2 ELSE 3 END AS nivel_inferido,
        /* sensibilidad: umbrales mas estrictos (3 y 10) y mas laxos (7 y 20) */
        CASE WHEN f.vol_sin_fx_pct < 3  THEN 1
             WHEN f.vol_sin_fx_pct < 10 THEN 2 ELSE 3 END AS nivel_estricto,
        CASE WHEN f.vol_sin_fx_pct < 7  THEN 1
             WHEN f.vol_sin_fx_pct < 20 THEN 2 ELSE 3 END AS nivel_laxo
    FROM stg.features_cliente f
)
SELECT
    v.id_cliente, v.id_tipo, v.banca, v.perfil_riesgo AS perfil_declarado,
    v.total_cop, v.n_posiciones, v.riesgo_mercado, v.vol_semanal_pct AS riesgo_total_con_fx,
    v.hhi, v.pct_internacional, v.pct_dato_supuesto,
    CASE v.nivel_inferido WHEN 1 THEN 'CONSERVADOR' WHEN 2 THEN 'MODERADO' ELSE 'AGRESIVO' END
        AS perfil_inferido,
    (v.nivel_estricto = v.nivel_inferido AND v.nivel_inferido = v.nivel_laxo) AS clasificacion_estable,
    CASE WHEN v.pct_dato_supuesto >= 80 THEN 'BAJA'
         WHEN v.pct_dato_supuesto >= 40 THEN 'MEDIA'
         ELSE 'ALTA' END AS confianza_dato,
    CASE WHEN v.nivel_declarado IS NULL             THEN 'SIN PERFIL DECLARADO'
         WHEN v.nivel_inferido > v.nivel_declarado  THEN 'MAS RIESGO QUE SU PERFIL'
         WHEN v.nivel_inferido < v.nivel_declarado  THEN 'MENOS RIESGO QUE SU PERFIL'
         ELSE 'COHERENTE' END AS coherencia,
    CASE WHEN v.nivel_declarado IS NULL
             THEN 'Completar perfilamiento (perfil sugerido: '
                  || CASE v.nivel_inferido WHEN 1 THEN 'CONSERVADOR' WHEN 2 THEN 'MODERADO'
                                           ELSE 'AGRESIVO' END || ')'
         WHEN v.nivel_inferido > v.nivel_declarado
             THEN 'Revisar idoneidad: el portafolio asume mas riesgo que el declarado'
         WHEN v.nivel_inferido < v.nivel_declarado
             THEN 'Oportunidad: hay capacidad para tomar mas riesgo segun su perfil'
         ELSE 'Mantener' END AS accion_sugerida
FROM v;