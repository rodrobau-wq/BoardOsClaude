-- 0005_sales_fact.sql — Fato de venda no grao CUPOM/ITEM (silver) + lotes de ingestao.
-- Chave natural garante idempotencia: reenviar substitui, nao duplica.

-- Controle de lote de ingestao (para reprocessamento por recorte).
CREATE TABLE ingest_batch (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  origem      text,                    -- nome do arquivo / conector
  loja_id     uuid REFERENCES loja(id),
  data_de     date,
  data_ate    date,
  linhas      bigint NOT NULL DEFAULT 0,
  status      text NOT NULL DEFAULT 'processando',
  criado_em   timestamptz NOT NULL DEFAULT now()
);

-- Fato item de venda (grao minimo).
CREATE TABLE item_venda (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tenant_id      uuid NOT NULL REFERENCES platform.tenant(id) ON DELETE CASCADE,
  loja_id        uuid NOT NULL REFERENCES loja(id),
  data           date NOT NULL,
  data_hora      timestamptz,
  cupom_id       text NOT NULL,
  seq_item       int  NOT NULL,        -- sequencia do item no cupom (desambigua SKU repetido)
  cliente_id     text,                 -- quando ha identificacao/fidelidade
  sku_id         uuid REFERENCES sku(id),
  categoria_id   uuid REFERENCES categoria(id),
  qtd            numeric(14,3) NOT NULL DEFAULT 0,
  valor_bruto    numeric(14,2) NOT NULL DEFAULT 0,
  desconto       numeric(14,2) NOT NULL DEFAULT 0,
  valor_liquido  numeric(14,2) NOT NULL DEFAULT 0,
  custo          numeric(14,2) NOT NULL DEFAULT 0,
  margem         numeric(14,2) GENERATED ALWAYS AS (valor_liquido - custo) STORED,
  batch_id       uuid REFERENCES ingest_batch(id),
  origem         text,
  ingerido_em    timestamptz NOT NULL DEFAULT now(),
  -- CHAVE NATURAL (idempotencia)
  CONSTRAINT item_venda_nk UNIQUE (tenant_id, loja_id, data, cupom_id, seq_item)
);

CREATE INDEX item_venda_scope_ix ON item_venda (tenant_id, data, loja_id);
CREATE INDEX item_venda_cat_ix   ON item_venda (tenant_id, categoria_id, data);

-- Cupom derivado (para cesta / itens por cupom).
CREATE VIEW v_cupom AS
SELECT tenant_id, loja_id, data, cupom_id,
       max(cliente_id)               AS cliente_id,
       count(*)                      AS itens,
       sum(qtd)                      AS qtd_total,
       sum(valor_liquido)            AS valor_liquido
FROM item_venda
GROUP BY tenant_id, loja_id, data, cupom_id;
