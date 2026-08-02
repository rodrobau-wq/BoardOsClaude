-- 0010_auth.sql — credenciais de login (nível plataforma, sem RLS).
-- Login precisa achar o usuário por e-mail ANTES de saber o tenant, por isso
-- fica em platform.* (sem RLS de tenant). A senha é sempre hash (pbkdf2).

CREATE TABLE platform.usuario_login (
  email       text PRIMARY KEY,
  senha_hash  text NOT NULL,
  nome        text,
  tenant_id   uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  papel       text NOT NULL DEFAULT 'estrategico'
                CHECK (papel IN ('super_admin','admin_tenant','estrategico','tatico','operacional')),
  criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX usuario_login_tenant_ix ON platform.usuario_login (tenant_id);
