-- 0009_plano.sql — Módulo de Plano (M3): Direção Estratégica + Metas (OKRs).
-- Entidades por tenant, isoladas por RLS. Ver PLANO.md 3.2 e 3.4.

-- Direção estratégica (uma por tenant).
CREATE TABLE direcao_estrategica (
  tenant_id     uuid PRIMARY KEY REFERENCES platform.tenant(id) ON DELETE CASCADE,
  proposito     text,
  visao         text,
  valores       text,
  objetivo_lp   text,                     -- objetivo de longo prazo
  atualizado_em timestamptz NOT NULL DEFAULT now()
);

-- Objetivo (o "O" do OKR).
CREATE TABLE okr_objetivo (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  titulo     text NOT NULL,
  periodo    text,                        -- ex.: "2026", "2026-T3"
  nivel      text NOT NULL DEFAULT 'corporativo'
               CHECK (nivel IN ('corporativo','area','loja')),
  owner      text,
  ordem      int NOT NULL DEFAULT 0,
  criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX okr_objetivo_tenant_ix ON okr_objetivo (tenant_id);

-- Resultado-chave (o "KR"). Cada KR é uma métrica com meta e atual.
CREATE TABLE okr_kr (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  objetivo_id  uuid NOT NULL REFERENCES okr_objetivo(id) ON DELETE CASCADE,
  titulo       text NOT NULL,
  unidade      text,                      -- %, R$, un, pp...
  meta         numeric(16,3) NOT NULL,
  atual        numeric(16,3) NOT NULL DEFAULT 0,
  base         numeric(16,3),             -- ponto de partida (para % de avanço)
  direcao      text NOT NULL DEFAULT 'up' -- 'up' = maior é melhor; 'down' = menor é melhor
                 CHECK (direcao IN ('up','down')),
  ordem        int NOT NULL DEFAULT 0
);
CREATE INDEX okr_kr_obj_ix ON okr_kr (objetivo_id);

SELECT apply_tenant_rls('direcao_estrategica');
SELECT apply_tenant_rls('okr_objetivo');
SELECT apply_tenant_rls('okr_kr');
