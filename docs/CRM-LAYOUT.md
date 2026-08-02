# Integração com o CRM — layout assumido (provisório)

O CRM do cliente tem **base de empresas** e **vendas por empresa**, acessível por
**CSV, API e banco**. Enquanto não temos o export real, o BoardOS trabalha com o
**layout assumido** abaixo. Quando vier o real, muda-se só o **mapeamento** em
[boardos/crm.py](../boardos/crm.py) (`MAP_EMPRESAS` / `MAP_VENDAS`) — o resto é igual.

## Mapeamento CRM → BoardOS
- cada **empresa** do CRM → um **tenant** (rede) no BoardOS
- cada **loja** nas vendas → uma **loja** do tenant
- **vendas diárias** → camada **gold** (comparação civil-vs-varejo funciona)

## Layout assumido

### empresas.csv (a base de empresas)
```
id_externo;nome;cidade;uf;formato
EMP-1001;Supermercados Aurora;Campinas;SP;vizinhanca
```
| campo | uso |
|-------|-----|
| id_externo | chave da empresa no CRM (liga vendas ↔ empresa) |
| nome | vira o nome do tenant |
| cidade/uf | contexto (e futura geolocalização) |
| formato | vizinhanca/atacarejo/hiper… |

### vendas.csv (vendas por empresa)
```
data;empresa_id;loja;faturamento;cupons;itens
2026-08-01;EMP-1001;C01;168400,00;2890;23700
```
| campo | uso |
|-------|-----|
| data | dia da venda (grão diário) |
| empresa_id | = id_externo da empresa |
| loja | código da loja dentro da empresa |
| faturamento | venda líquida do dia (R$) |
| cupons | nº de cupons (para ticket médio) |
| itens | nº de itens (para cesta) |

## Sobre o GRÃO
- **Diário** (assumido): comparação civil↔varejo, ticket, tendência — tudo funciona.
- **Se o CRM tiver cupom/item**: melhor ainda — habilita cesta, ruptura e margem
  por SKU (usa o pipeline `boardos/ingestion.py`, não o daily do `crm.py`).
- **Se só tiver mensal**: funciona no grão mensal, mas perde o ajuste de
  calendário (que precisa de dado diário). Bom confirmar cedo.

## Três modos de acesso
- **CSV** — implementado: `crm.onboard_empresas_csv` + `crm.import_vendas_diarias_csv`.
- **API** — stub `crm.onboard_empresas_api` / `import_vendas_api` (implementar com o
  endpoint/schema real; mesma escrita no gold).
- **Banco** — ler direto as tabelas do CRM e reutilizar o mesmo import.

## Como trocar pelo CRM real (passos)
1. Exportar/consultar uma amostra e conferir as colunas reais.
2. Ajustar `MAP_EMPRESAS` / `MAP_VENDAS` em `boardos/crm.py`.
3. Rodar `python scripts/onboard_crm_demo.py` (ou um script equivalente apontando
   para os arquivos reais) — cria tenants + importa vendas.
4. Abrir o painel e escolher a empresa no seletor.
