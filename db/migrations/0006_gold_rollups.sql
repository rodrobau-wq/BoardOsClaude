-- 0006_gold_rollups.sql — camada GOLD: agregados que os dashboards leem.
-- Recomputados incrementalmente por (tenant, loja, data) a cada ingestao.
-- Dashboards NAO leem item_venda cru.

CREATE TABLE gold_venda_diaria (
  tenant_id          uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  data               date NOT NULL,
  loja_id            uuid NOT NULL REFERENCES loja(id),
  categoria_id       uuid,                       -- NULL = total da loja no dia
  faturamento_bruto  numeric(16,2) NOT NULL DEFAULT 0,
  faturamento_liq    numeric(16,2) NOT NULL DEFAULT 0,
  custo              numeric(16,2) NOT NULL DEFAULT 0,
  margem             numeric(16,2) NOT NULL DEFAULT 0,
  itens              bigint  NOT NULL DEFAULT 0,
  cupons             bigint  NOT NULL DEFAULT 0,
  qtd                numeric(16,3) NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, data, loja_id, categoria_id)
);
CREATE INDEX gold_vd_scope_ix ON gold_venda_diaria (tenant_id, data);

-- View de KPI diario ja com as chaves do calendario duplo (civil + varejo).
-- E aqui que o Motor de Comparacao Temporal (3.12) se apoia.
CREATE VIEW v_kpi_diario AS
SELECT g.*,
       c.ano_civil, c.mes_civil, c.dia_mes, c.dow_iso, c.dow_label,
       c.is_fim_semana, c.qtd_mesmo_dow_no_mes,
       c.retail_year, c.retail_week, c.semana_partida,
       CASE WHEN g.faturamento_liq > 0 THEN g.margem / g.faturamento_liq END AS margem_pct,
       CASE WHEN g.cupons > 0 THEN g.faturamento_liq / g.cupons END          AS ticket_medio,
       CASE WHEN g.cupons > 0 THEN g.itens::numeric / g.cupons END           AS itens_por_cupom
FROM gold_venda_diaria g
JOIN dim_calendario c ON c.data = g.data;

-- Funcao de recomputo incremental do gold para um recorte (tenant, loja, dia).
-- Chamada pelo pipeline apos upsert de item_venda.
CREATE OR REPLACE FUNCTION recompute_gold(p_tenant uuid, p_loja uuid, p_data date)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  DELETE FROM gold_venda_diaria
   WHERE tenant_id = p_tenant AND loja_id = p_loja AND data = p_data;

  -- por categoria
  INSERT INTO gold_venda_diaria
    (tenant_id, data, loja_id, categoria_id, faturamento_bruto, faturamento_liq,
     custo, margem, itens, cupons, qtd)
  SELECT i.tenant_id, i.data, i.loja_id, i.categoria_id,
         sum(i.valor_bruto), sum(i.valor_liquido), sum(i.custo), sum(i.margem),
         count(*), count(DISTINCT i.cupom_id), sum(i.qtd)
  FROM item_venda i
  WHERE i.tenant_id = p_tenant AND i.loja_id = p_loja AND i.data = p_data
  GROUP BY i.tenant_id, i.data, i.loja_id, i.categoria_id;

  -- total da loja (categoria_id NULL)
  INSERT INTO gold_venda_diaria
    (tenant_id, data, loja_id, categoria_id, faturamento_bruto, faturamento_liq,
     custo, margem, itens, cupons, qtd)
  SELECT i.tenant_id, i.data, i.loja_id, NULL,
         sum(i.valor_bruto), sum(i.valor_liquido), sum(i.custo), sum(i.margem),
         count(*), count(DISTINCT i.cupom_id), sum(i.qtd)
  FROM item_venda i
  WHERE i.tenant_id = p_tenant AND i.loja_id = p_loja AND i.data = p_data
  GROUP BY i.tenant_id, i.data, i.loja_id;
END $$;
