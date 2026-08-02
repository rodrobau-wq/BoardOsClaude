-- 0014_plano_completo.sql — Módulo de Plano (1.2–1.5):
-- Entrevista de Descoberta, Diagnóstico (SWOT + Radar) e Ações 5W2H.
-- (Direção Estratégica já existe: direcao_estrategica em 0009.)

-- 1.2 Entrevista de Descoberta: respostas por chave + resumo executivo gerado.
CREATE TABLE descoberta (
  tenant_id     uuid PRIMARY KEY REFERENCES platform.tenant(id) ON DELETE CASCADE,
  respostas     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {"A1": "...", "B3": "..."}
  resumo        text,                                  -- documento da Etapa 3
  atualizado_em timestamptz NOT NULL DEFAULT now()
);

-- 1.4 SWOT
CREATE TABLE swot_item (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  quadrante  text NOT NULL CHECK (quadrante IN ('forca','fraqueza','oportunidade','ameaca')),
  texto      text NOT NULL,
  ordem      int  NOT NULL DEFAULT 0,
  criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX swot_tenant_ix ON swot_item (tenant_id, quadrante, ordem);

-- 1.4 Radar de Maturidade (nota 0–10 por área de gestão)
CREATE TABLE radar_nota (
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  area       text NOT NULL,
  nota       int  NOT NULL CHECK (nota BETWEEN 0 AND 10),
  PRIMARY KEY (tenant_id, area)
);

-- 1.5 Ações no formato 5W2H, opcionalmente ligadas a uma meta (OKR)
CREATE TABLE acao_5w2h (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  objetivo_id  uuid REFERENCES okr_objetivo(id) ON DELETE SET NULL,
  oque         text NOT NULL,       -- What
  porque       text,                -- Why
  onde         text,                -- Where
  quando       date,                -- When
  quem         text,                -- Who
  como         text,                -- How
  quanto       numeric(14,2),       -- How much (R$)
  status       text NOT NULL DEFAULT 'planejada'
                 CHECK (status IN ('planejada','em_andamento','concluida','cancelada')),
  criado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX acao_tenant_ix ON acao_5w2h (tenant_id, status);

SELECT apply_tenant_rls('descoberta');
SELECT apply_tenant_rls('swot_item');
SELECT apply_tenant_rls('radar_nota');
SELECT apply_tenant_rls('acao_5w2h');
