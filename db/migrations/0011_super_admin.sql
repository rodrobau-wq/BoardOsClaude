-- 0011_super_admin.sql — super-admin da plataforma não pertence a um tenant.
-- usuario_login.tenant_id passa a aceitar NULL (apenas para papel super_admin).

ALTER TABLE platform.usuario_login ALTER COLUMN tenant_id DROP NOT NULL;
ALTER TABLE platform.usuario_login
  ADD CONSTRAINT usuario_login_tenant_chk
  CHECK (papel = 'super_admin' OR tenant_id IS NOT NULL);
