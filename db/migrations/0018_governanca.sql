-- 0018_governanca.sql — jornada de planejamento estratégico (handoff v2).
-- Rituais de gestão, sala do conselho (reuniões/pauta/deliberações/membros),
-- iniciativas do plano tático, jornadas guiadas do Advisor e coordenadas de loja.

-- Rituais de gestão (DIA/SEM/MES/TRI)
CREATE TABLE ritual (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  freq       text NOT NULL,               -- DIA | SEM | MES | TRI
  nome       text NOT NULL,
  quem       text,
  objetivo   text,
  proxima    text,                        -- texto livre: "ter 26/ago 9h"
  ordem      int  NOT NULL DEFAULT 0
);

-- Diretoria e conselho
CREATE TABLE governanca_membro (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  nome       text NOT NULL,
  papel      text,                        -- "CEO · fundador", "Conselheira · finanças"
  tag        text NOT NULL DEFAULT 'diretoria',  -- diretoria | conselho
  ordem      int  NOT NULL DEFAULT 0
);

-- Reuniões do conselho + pauta
CREATE TABLE conselho_reuniao (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  titulo     text NOT NULL DEFAULT 'Reunião trimestral do conselho',
  data       date,
  hora       text,                        -- "14h–17h"
  local      text,
  status     text NOT NULL DEFAULT 'agendada',  -- agendada | realizada
  assinada   boolean NOT NULL DEFAULT false,
  criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE conselho_pauta (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  reuniao_id  uuid NOT NULL REFERENCES conselho_reuniao(id) ON DELETE CASCADE,
  item        text NOT NULL,
  tempo       text,                       -- "30 min"
  material    text,                       -- "Painel Estratégico", "Ciclo FCA"…
  ordem       int NOT NULL DEFAULT 0
);

-- Deliberações do conselho
CREATE TABLE deliberacao (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  texto      text NOT NULL,
  data       date,
  status     text NOT NULL DEFAULT 'em_pauta',  -- em_pauta | aprovada | concluida
  follow     text
);

-- Iniciativas do plano tático (agrupam ações 5W2H)
CREATE TABLE iniciativa (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  nome         text NOT NULL,
  objetivo_id  uuid REFERENCES okr_objetivo(id) ON DELETE SET NULL,
  dono         text,
  orcamento    numeric(14,2)
);
ALTER TABLE acao_5w2h ADD COLUMN iniciativa_id uuid REFERENCES iniciativa(id) ON DELETE SET NULL;

-- Jornadas guiadas do Advisor (cultura, posicionamento) — mesmo padrão da descoberta
CREATE TABLE jornada (
  tenant_id      uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  jornada        text NOT NULL,           -- cultura | posicionamento
  respostas      jsonb NOT NULL DEFAULT '{}',
  resumo         text,
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, jornada)
);

-- Mapa da rede: coordenadas da loja (geocodificadas ou manuais)
ALTER TABLE loja ADD COLUMN lat double precision;
ALTER TABLE loja ADD COLUMN lng double precision;

-- Essência: competência central da direção estratégica
ALTER TABLE direcao_estrategica ADD COLUMN competencia text;

SELECT apply_tenant_rls('ritual');
SELECT apply_tenant_rls('governanca_membro');
SELECT apply_tenant_rls('conselho_reuniao');
SELECT apply_tenant_rls('conselho_pauta');
SELECT apply_tenant_rls('deliberacao');
SELECT apply_tenant_rls('iniciativa');
SELECT apply_tenant_rls('jornada');
