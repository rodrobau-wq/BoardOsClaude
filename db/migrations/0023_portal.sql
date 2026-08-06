-- 0023_portal.sql — fundações do Portal BoardOS (protótipo v3).
-- Framework MERCADO (7 pilares × 3 jornadas), Fatos Relevantes, catálogo de
-- PIs, riscos, maturidade de gestão, chat persistido do Conselheiro e as
-- extensões de reunião/deliberação que destravam a taxa de execução.

-- Fato Relevante: evento interno/externo registrado por qualquer usuário;
-- a IA propõe classificação e propagação, nada se grava sem confirmação.
CREATE TABLE fato_relevante (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  texto         text NOT NULL,
  autor         text,
  loja_id       uuid REFERENCES loja(id) ON DELETE SET NULL,
  pilar         text,                          -- M|E|R|C|A|D|O
  tags          text[],                        -- concorrência, clima, fornecedor, preço…
  classificacao text,                          -- proposta da IA (texto curto)
  propagacao    jsonb NOT NULL DEFAULT '{}',   -- {forecast:bool, fca:bool, swot:bool, war_room:bool}
  confirmado    boolean NOT NULL DEFAULT false,
  fca_id        uuid REFERENCES fca_ciclo(id) ON DELETE SET NULL,
  criado_em     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX fato_relevante_ix ON fato_relevante (tenant_id, criado_em DESC);

-- Catálogo de PIs: os indicadores oficiais do ciclo (nome + pilar + jornada
-- + meta + fonte). O valor realizado continua derivado do gold.
CREATE TABLE pi (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  chave     text NOT NULL,                     -- venda|margem|ruptura|quebra|ticket|itens_cupom…
  nome      text NOT NULL,
  pilar     text,                              -- M|E|R|C|A|D|O
  jornada   text,                              -- produto|cliente|financeira
  direcao   text NOT NULL DEFAULT 'up',
  meta      numeric(16,4),
  fonte     text,                              -- "Planilha · carga de …" / "CRM"
  oficial   boolean NOT NULL DEFAULT true,
  ordem     int NOT NULL DEFAULT 0,
  UNIQUE (tenant_id, chave)
);

-- Riscos monitorados (tela Estratégia)
CREATE TABLE risco (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  titulo        text NOT NULL,
  probabilidade text NOT NULL DEFAULT 'medio',   -- baixo|medio|alto
  impacto       text NOT NULL DEFAULT 'medio',
  status        text NOT NULL DEFAULT 'ativo',   -- ativo|mitigado|encerrado
  revisao       text,                            -- "revisão mensal"
  ordem         int NOT NULL DEFAULT 0
);

-- Maturidade de Gestão (6 dimensões, nota 1–5 + alvo) — instrumento distinto
-- do Radar MERCADO.
CREATE TABLE maturidade_gestao (
  tenant_id uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  dimensao  text NOT NULL,
  nota      numeric(3,1),
  alvo      numeric(3,1),
  PRIMARY KEY (tenant_id, dimensao)
);

-- Chat persistido do Conselheiro
CREATE TABLE conversa_msg (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  autor     text NOT NULL,                     -- email do usuário ou 'conselheiro'
  papel     text NOT NULL DEFAULT 'user',      -- user|ia
  texto     text NOT NULL,
  fontes    text[],                            -- chips de fonte citada
  criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conversa_msg_ix ON conversa_msg (tenant_id, criado_em);

-- Pilar MERCADO nas entidades existentes
ALTER TABLE okr_objetivo ADD COLUMN pilar text;
ALTER TABLE fca_ciclo    ADD COLUMN pilar text;
ALTER TABLE iniciativa   ADD COLUMN pilar text;
ALTER TABLE iniciativa   ADD COLUMN marco text;            -- "obra 70% · go-live set/26"
ALTER TABLE iniciativa   ADD COLUMN marco_prazo date;      -- regra: atraso ≥2 sem → pauta

-- Reuniões: tipo de ritual, participantes e origem em fato relevante
ALTER TABLE conselho_reuniao ADD COLUMN tipo text NOT NULL DEFAULT 'conselho';
  -- conselho|diretoria|fechamento|one_on_one|calibracao|war_room
ALTER TABLE conselho_reuniao ADD COLUMN participantes text[];
ALTER TABLE conselho_reuniao ADD COLUMN origem_fato_id uuid REFERENCES fato_relevante(id) ON DELETE SET NULL;

-- Deliberações com dono e prazo → taxa de execução de decisões
ALTER TABLE deliberacao ADD COLUMN dono text;
ALTER TABLE deliberacao ADD COLUMN prazo date;

SELECT apply_tenant_rls('fato_relevante');
SELECT apply_tenant_rls('pi');
SELECT apply_tenant_rls('risco');
SELECT apply_tenant_rls('maturidade_gestao');
SELECT apply_tenant_rls('conversa_msg');
