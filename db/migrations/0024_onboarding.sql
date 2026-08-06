-- 0024_onboarding.sql — onboarding self-service: trial com prazo, segmento de
-- varejo e origem do cadastro; unicidade case-insensitive de e-mail; e o
-- Primeiro Modelo de Ação proposto pela IA (pré-confirmação) na jornada.

ALTER TABLE platform.tenant ADD COLUMN trial_expira_em timestamptz;
ALTER TABLE platform.tenant ADD COLUMN segmento text;           -- supermercado|farmacia|moda|...
ALTER TABLE platform.tenant ADD COLUMN origem text NOT NULL DEFAULT 'manual';
  -- manual (criado pelo super-admin) | self_service (cadastro público)

-- O login sempre buscou por lower(email); normaliza o PK e trava a unicidade
-- case-insensitive (fecha a corrida do cadastro público).
-- Guarda: se existirem contas que só diferem por maiúsculas/minúsculas, aborta
-- com mensagem acionável em vez de estourar violação de chave no boot.
DO $$
DECLARE dups int;
BEGIN
  SELECT count(*) INTO dups FROM (
    SELECT lower(email) FROM platform.usuario_login GROUP BY 1 HAVING count(*) > 1
  ) d;
  IF dups > 0 THEN
    RAISE EXCEPTION
      'Migração 0024: % e-mail(is) duplicado(s) por maiúsculas em platform.usuario_login. '
      'Decida qual conta fica (SELECT email, tenant_id FROM platform.usuario_login '
      'WHERE lower(email) IN (SELECT lower(email) FROM platform.usuario_login '
      'GROUP BY 1 HAVING count(*)>1)) e remova a outra antes de implantar.', dups;
  END IF;
END $$;

UPDATE platform.usuario_login SET email = lower(email) WHERE email <> lower(email);
CREATE UNIQUE INDEX usuario_login_email_lower_ux ON platform.usuario_login (lower(email));

-- Onboarding reusa a tabela jornada (linha jornada='onboarding'):
-- respostas jsonb já existe; faltam a proposta da IA e o carimbo de aprovação.
ALTER TABLE jornada ADD COLUMN modelo jsonb;
ALTER TABLE jornada ADD COLUMN confirmado_em timestamptz;
