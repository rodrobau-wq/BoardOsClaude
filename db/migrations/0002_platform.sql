-- 0002_platform.sql — nível plataforma (compartilhado, NÃO escopado por tenant)
-- Operado pelo super-admin BoardOS. Ver PLANO.md secao 3.11 e 5.

CREATE SCHEMA IF NOT EXISTS platform;

-- Cliente / rede de supermercado = tenant
CREATE TABLE platform.tenant (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome         text NOT NULL,
  slug         text UNIQUE NOT NULL,                 -- identificador em URL/login
  status       text NOT NULL DEFAULT 'trial'         -- trial|ativo|inadimplente|cancelado
                 CHECK (status IN ('trial','ativo','inadimplente','cancelado')),
  criado_em    timestamptz NOT NULL DEFAULT now()
);

-- Plano/assinatura. Billing v0: base mínima + por registro de venda ingerido.
CREATE TABLE platform.assinatura (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  plano             text NOT NULL DEFAULT 'v0',
  base_mensal_cent  bigint NOT NULL DEFAULT 0,        -- preço mínimo mensal (centavos)
  preco_por_1k_cent bigint NOT NULL DEFAULT 0,        -- por 1.000 registros de venda
  status_cobranca   text NOT NULL DEFAULT 'trial',
  gateway_id        text,
  criado_em         timestamptz NOT NULL DEFAULT now()
);

-- Medidor de uso: conta ITENS DISTINTOS (chave natural) por tenant/competência.
-- Reenvio/correcao NAO infla a fatura (ver ingestao idempotente).
CREATE TABLE platform.medidor_uso (
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  competencia   date NOT NULL,                        -- 1o dia do mes de competencia
  registros     bigint NOT NULL DEFAULT 0,            -- itens distintos ingeridos
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, competencia)
);

CREATE TABLE platform.fatura (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  competencia    date NOT NULL,
  valor_base_cent  bigint NOT NULL DEFAULT 0,
  valor_uso_cent   bigint NOT NULL DEFAULT 0,
  status         text NOT NULL DEFAULT 'aberta',
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, competencia)
);

-- Usuários da plataforma (super-admin/suporte), fora de qualquer tenant.
CREATE TABLE platform.platform_user (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email     text UNIQUE NOT NULL,
  nome      text,
  papel     text NOT NULL DEFAULT 'suporte' CHECK (papel IN ('super_admin','suporte')),
  criado_em timestamptz NOT NULL DEFAULT now()
);

-- Auditoria de acoes administrativas (inclui impersonation).
CREATE TABLE platform.audit_log (
  id         bigserial PRIMARY KEY,
  ator       text NOT NULL,
  acao       text NOT NULL,
  tenant_id  uuid,
  detalhe    jsonb,
  criado_em  timestamptz NOT NULL DEFAULT now()
);
