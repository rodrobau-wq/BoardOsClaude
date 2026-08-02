-- 0017_loja_ibge.sql — enriquecimento IBGE no cadastro de loja (3.14 parcial).

ALTER TABLE loja ADD COLUMN IF NOT EXISTS ibge_id bigint;
ALTER TABLE loja ADD COLUMN IF NOT EXISTS populacao bigint;
ALTER TABLE loja ADD COLUMN IF NOT EXISTS populacao_ano int;
ALTER TABLE loja ADD COLUMN IF NOT EXISTS pib_per_capita numeric(14,2);
ALTER TABLE loja ADD COLUMN IF NOT EXISTS pib_ano int;
ALTER TABLE loja ADD COLUMN IF NOT EXISTS ibge_atualizado_em timestamptz;
