-- 0016_feriados.sql — Feriados e datas sazonais por tenant (3.4).
-- Alimenta o contexto do Advisor e a leitura do calendário comercial.

CREATE TABLE feriado (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  data       date NOT NULL,
  nome       text NOT NULL,
  tipo       text NOT NULL DEFAULT 'feriado'
               CHECK (tipo IN ('feriado','sazonal')),   -- feriado ou data comercial
  criado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, data, nome)
);
CREATE INDEX feriado_tenant_ix ON feriado (tenant_id, data);

SELECT apply_tenant_rls('feriado');
