INSERT INTO stg.param_trm (fecha, trm)
VALUES ('2024-05-30', 3867.02)
ON CONFLICT (fecha) DO UPDATE SET trm = EXCLUDED.trm;