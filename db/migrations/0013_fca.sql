-- 0013_fca.sql — Ciclo de correção FCA (Fato → Causa → Ação) + resultado.
-- Fecha o loop meta → desvio → ação do BoardOS. Ver PLANO.md 3.7.

CREATE TABLE fca_ciclo (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  titulo        text NOT NULL,
  fato          text,                     -- o dado que evidencia o desvio
  causa         text,                     -- causa-raiz investigada
  acao          text,                     -- ação corretiva definida
  responsavel   text,
  prazo         date,
  status        text NOT NULL DEFAULT 'aberto'
                  CHECK (status IN ('aberto','em_andamento','resolvido','descartado')),
  kpi           text,                     -- KPI de origem (ex.: 'venda_comparavel', 'ruptura')
  origem        text NOT NULL DEFAULT 'manual',   -- manual | alerta
  resultado     text,                     -- a ação funcionou? o que mudou no número
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX fca_tenant_ix ON fca_ciclo (tenant_id, status);

SELECT apply_tenant_rls('fca_ciclo');
