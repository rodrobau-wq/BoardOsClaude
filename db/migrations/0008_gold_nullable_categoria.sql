-- 0008_gold_nullable_categoria.sql — corrige gold_venda_diaria.
-- A linha de TOTAL da loja usa categoria_id = NULL, mas coluna de PRIMARY KEY
-- não aceita NULL. Troca a PK por UNIQUE com NULLS NOT DISTINCT (Postgres 15+),
-- que trata o NULL como valor único e ainda dedupa a linha de total.

ALTER TABLE gold_venda_diaria DROP CONSTRAINT IF EXISTS gold_venda_diaria_pkey;
ALTER TABLE gold_venda_diaria ALTER COLUMN categoria_id DROP NOT NULL;
ALTER TABLE gold_venda_diaria
  ADD CONSTRAINT gold_vd_uk
  UNIQUE NULLS NOT DISTINCT (tenant_id, data, loja_id, categoria_id);
