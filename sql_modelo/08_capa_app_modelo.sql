/* capa de presentacion materializada para la app (modelo y oportunidades) */
CREATE SCHEMA IF NOT EXISTS app;

DROP TABLE IF EXISTS app.modelo_cliente, app.oportunidades;

CREATE TABLE app.oportunidades  AS SELECT * FROM stg.oportunidades;
CREATE TABLE app.modelo_cliente AS SELECT * FROM stg.modelo_cliente;

CREATE INDEX ON app.oportunidades (id_cliente);
CREATE INDEX ON app.modelo_cliente (id_cliente);

ANALYZE app.oportunidades;
ANALYZE app.modelo_cliente;