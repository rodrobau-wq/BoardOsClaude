-- 0022_ciclo_resultados.sql — fecha o ciclo resultado → ação → verificação.
-- Toda ação (FCA) pode apontar o KR que quer mover, com o valor do indicador
-- no momento em que nasceu (baseline) — é isso que permite medir eficácia.
-- O squad de agentes grava suas rodadas e vereditos aqui.

ALTER TABLE fca_ciclo ADD COLUMN kr_id uuid REFERENCES okr_kr(id) ON DELETE SET NULL;
ALTER TABLE fca_ciclo ADD COLUMN baseline numeric(16,4);
ALTER TABLE fca_ciclo ADD COLUMN baseline_em date;

-- iniciativa nascida de um desvio; deliberação que acompanha uma iniciativa
ALTER TABLE iniciativa ADD COLUMN fca_id uuid REFERENCES fca_ciclo(id) ON DELETE SET NULL;
ALTER TABLE deliberacao ADD COLUMN iniciativa_id uuid REFERENCES iniciativa(id) ON DELETE SET NULL;

-- rodadas do squad de agentes (Analista, Verificador, Projetista, Relator)
CREATE TABLE agente_rodada (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  executado_em timestamptz NOT NULL DEFAULT now(),
  saida        jsonb NOT NULL DEFAULT '{}',   -- {analise:[], verificacoes:[], projecoes:[]}
  texto        text                            -- Relator: reflexão consolidada
);
CREATE INDEX agente_rodada_ix ON agente_rodada (tenant_id, executado_em DESC);

-- veredito de eficácia de cada ação a cada rodada
CREATE TABLE acao_verificacao (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  fca_id        uuid NOT NULL REFERENCES fca_ciclo(id) ON DELETE CASCADE,
  kr_id         uuid REFERENCES okr_kr(id) ON DELETE CASCADE,
  baseline      numeric(16,4),
  valor_atual   numeric(16,4),
  delta         numeric(16,4),
  veredito      text NOT NULL,                 -- funcionou | sem_efeito | piorou | cedo_demais
  verificado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX acao_verificacao_ix ON acao_verificacao (tenant_id, fca_id, verificado_em DESC);

SELECT apply_tenant_rls('agente_rodada');
SELECT apply_tenant_rls('acao_verificacao');
