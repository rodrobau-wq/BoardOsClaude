-- 0003_tenant_core.sql — entidades do tenant (isoladas por tenant_id + RLS)
-- Todas as tabelas carregam tenant_id NOT NULL. RLS em 0007.

-- Usuário da rede cliente. Papeis: admin do tenant + niveis de negocio.
CREATE TABLE app_user (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  email      text NOT NULL,
  nome       text,
  papel      text NOT NULL DEFAULT 'operacional'
               CHECK (papel IN ('admin_tenant','estrategico','tatico','operacional')),
  criado_em  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE loja (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  codigo         text NOT NULL,                 -- codigo da loja no ERP do cliente
  nome           text NOT NULL,
  formato        text,                          -- vizinhanca|atacarejo|premium|hiper
  area_vendas_m2 numeric(10,2),
  endereco       text,
  municipio      text,
  uf             char(2),
  geom           geometry(Point, 4326),         -- lat/long (PostGIS)
  criado_em      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, codigo)
);
CREATE INDEX loja_geom_gix ON loja USING gist (geom);

CREATE TABLE categoria (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  codigo     text NOT NULL,
  nome       text NOT NULL,
  secao      text,                              -- mercearia|hortifruti|acougue|bebidas...
  UNIQUE (tenant_id, codigo)
);

CREATE TABLE sku (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  codigo        text NOT NULL,                  -- codigo/EAN
  descricao     text,
  categoria_id  uuid REFERENCES categoria(id),
  perecivel     boolean NOT NULL DEFAULT false,
  UNIQUE (tenant_id, codigo)
);

-- Concorrente cadastrado na area (geolocalizado).
CREATE TABLE concorrente (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  nome           text NOT NULL,
  tipo           text,
  endereco       text,
  geom           geometry(Point, 4326),
  data_abertura  date,
  origem         text NOT NULL DEFAULT 'manual',  -- manual|importado
  criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX concorrente_geom_gix ON concorrente USING gist (geom);
