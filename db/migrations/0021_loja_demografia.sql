-- 0021_loja_demografia.sql — demografia por área de influência da loja.
-- Agregado dos setores censitários (Censo IBGE 2022) cujo centroide cai nos
-- anéis primário (1,0 km), secundário (2,0 km) e terciário (3,5 km).
-- Calculado pelo scripts/demografia_ibge.py e gravado via API.

CREATE TABLE loja_demografia (
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  loja_id       uuid NOT NULL REFERENCES loja(id) ON DELETE CASCADE,
  anel          text NOT NULL,           -- primaria | secundaria | terciaria
  raio_km       numeric(4,1) NOT NULL,
  populacao     bigint NOT NULL DEFAULT 0,
  domicilios    bigint NOT NULL DEFAULT 0,   -- particulares ocupados
  setores       int    NOT NULL DEFAULT 0,   -- nº de setores agregados
  potencial_ano numeric(16,2),               -- domicílios × gasto alimentar/mês × 12
  fonte         text,                        -- ex.: "Censo IBGE 2022 + POF"
  calculado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, loja_id, anel)
);

SELECT apply_tenant_rls('loja_demografia');
