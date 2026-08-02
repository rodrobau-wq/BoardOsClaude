-- 0015_assinatura_unica.sql — corrige duplicação de assinaturas.
-- platform.assinatura não tinha UNIQUE(tenant_id); o "ON CONFLICT DO NOTHING"
-- do seed nunca conflitava e cada boot inseria uma assinatura nova, inflando o
-- JOIN das métricas (72 linhas p/ 3 tenants). Dedupe + constraint.

DELETE FROM platform.assinatura a
 USING platform.assinatura b
 WHERE a.tenant_id = b.tenant_id AND a.ctid < b.ctid;

ALTER TABLE platform.assinatura
  ADD CONSTRAINT assinatura_tenant_uk UNIQUE (tenant_id);
