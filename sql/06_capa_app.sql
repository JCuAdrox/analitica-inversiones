/* capa de presentacion materializada para la app (portafolios).
   Las vistas stg recalculan toda la cadena en cada consulta; aqui se guardan
   los resultados una sola vez y la app lee de estas tablas.
   Se reconstruyen cada vez que se ejecuta scripts/run_sql.py */
CREATE SCHEMA IF NOT EXISTS app;

DROP TABLE IF EXISTS app.resumen_cliente, app.portafolio_cop_actual, app.portafolio_usd_actual;

CREATE TABLE app.resumen_cliente       AS SELECT * FROM stg.resumen_cliente;
CREATE TABLE app.portafolio_cop_actual AS SELECT * FROM stg.portafolio_cop_actual;
CREATE TABLE app.portafolio_usd_actual AS SELECT * FROM stg.portafolio_usd_actual;

CREATE INDEX ON app.resumen_cliente (id_cliente);
CREATE INDEX ON app.portafolio_cop_actual (id_cliente);
CREATE INDEX ON app.portafolio_usd_actual (id_cliente);

ANALYZE app.resumen_cliente;
ANALYZE app.portafolio_cop_actual;
ANALYZE app.portafolio_usd_actual;