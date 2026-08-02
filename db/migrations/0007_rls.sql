-- 0007_rls.sql — Row-Level Security por tenant.
-- A app conecta como role boardos_app e faz `SET app.current_tenant = '<uuid>'`
-- no inicio de cada requisicao (ver boardos/db.py). Se nao setar, nada e visivel.

-- Role da aplicacao (nao-superuser => sujeita a RLS).
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'boardos_app') THEN
    CREATE ROLE boardos_app LOGIN PASSWORD 'change-me';
  END IF;
END $$;

GRANT USAGE ON SCHEMA public, platform TO boardos_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public   TO boardos_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA platform TO boardos_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public, platform TO boardos_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO boardos_app;

-- Aplica RLS de tenant a uma tabela.
CREATE OR REPLACE FUNCTION apply_tenant_rls(tbl regclass) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', tbl);
  EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', tbl);
  EXECUTE format($f$
    CREATE POLICY tenant_isolation ON %s
      USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
      WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)
  $f$, tbl);
END $$;

SELECT apply_tenant_rls('app_user');
SELECT apply_tenant_rls('loja');
SELECT apply_tenant_rls('categoria');
SELECT apply_tenant_rls('sku');
SELECT apply_tenant_rls('concorrente');
SELECT apply_tenant_rls('ingest_batch');
SELECT apply_tenant_rls('item_venda');
SELECT apply_tenant_rls('gold_venda_diaria');

-- dim_calendario e as tabelas de platform.* NAO tem RLS de tenant
-- (calendario e dado publico; platform e do super-admin).
