# BoardOS

Plataforma SaaS multiempresa de **planejamento estratégico e execução para CEOs
de supermercado**. Do plano à execução: lê os dados de venda da rede, compara
com honestidade (calendário duplo), projeta à frente e explica desvios com IA.

Fases entregues:
- **M0 — Fundação:** multi-tenant + ingestão cupom/item → gold + calendário duplo.
- **M1 — Motor de comparação:** `boardos/comparison.py` (YoY civil-vs-varejo com
  ajuste de composição de calendário), testes, e endpoint `GET /comparacao/yoy`.

Ver [PLANO-IMPLEMENTACAO.md](PLANO-IMPLEMENTACAO.md).

---

## Rodar o diferencial agora (sem banco)

O motor de **comparação com calendário duplo** roda só com Python stdlib:

```bash
make demo        # agosto 2026 vs 2025 (composição real do calendário)
make demo-comp   # gera ~3 anos de dados e compara YoY no nível gold
make test        # testes do motor de comparação
```

Mostram, com a composição **real** de dias da semana, a diferença entre a lente
**Civil** (mês-calendário, dinheiro) e a lente **Varejo** (like-for-like por dia
da semana, demanda) — o insight central do produto. Ex.: *Civil +1,7% / Varejo
+2,6%* porque o mês trocou uma sexta (dia forte) por uma segunda (dia fraco).

---

## Subir o ambiente completo (Postgres)

```bash
cp .env.example .env          # ajuste as senhas
docker compose up -d          # Postgres + PostGIS
make install                  # pip install -r requirements.txt
make migrate                  # aplica db/migrations/*.sql (schema + RLS)
make seed                     # cria tenant demo + dim_calendario + ingere CSV exemplo
make api                      # sobe a API (uvicorn)
```

Testar a API (RLS por tenant — use o id impresso pelo seed):

```bash
# KPIs diários (gold, com chaves do calendário duplo)
curl "http://localhost:8000/kpi/diario?data_de=2026-08-01&data_ate=2026-08-31" \
     -H "X-Tenant-Id: <TENANT_ID>"

# Comparação YoY civil-vs-varejo (o número do Painel Estratégico)
curl "http://localhost:8000/comparacao/yoy?ano=2026&mes=8" \
     -H "X-Tenant-Id: <TENANT_ID>"
```

Reingerir o mesmo CSV (`make seed`) **não duplica** linhas — idempotência pela
chave natural.

---

## Estrutura

```
db/migrations/     schema Postgres: platform, tenant, calendário duplo, fato
                   item de venda, gold rollups, RLS por tenant
boardos/           núcleo Python: calendar_gen, mapping, ingestion, db (RLS),
                   comparison (motor de comparação com ajuste de calendário)
api/               FastAPI: KPIs diários + comparação YoY, com contexto de tenant
scripts/           migrate, seed, gen_dataset, demos e testes (rodam sem banco)
data/              CSV item de exemplo + mapa de colunas + série gold gerada
```

### Decisões de fundação já implementadas
- **Multi-tenant** com `tenant_id` em toda tabela + **Row-Level Security** (0007).
- **Grão cupom/item** com **chave natural** e **upsert idempotente**.
- **Camada gold** recomputada incrementalmente por (loja, dia).
- **Calendário duplo** (civil + varejo/ISO week) com ajuste de composição.
- **Medidor de uso** para billing (conta itens distintos, não linhas).
- **Motor de comparação** (M1): YoY civil-vs-varejo com ajuste de composição de
  calendário, com testes e endpoint na API.

---

## Documentos de planejamento

| Doc | Cobre |
|-----|-------|
| [PLANO.md](PLANO.md) | Arquitetura, módulos, dados, roadmap, multi-tenant, billing |
| [ROTEIRO-ENTREVISTA.md](ROTEIRO-ENTREVISTA.md) | Entrevista de descoberta (expectativas do plano) |
| [BIBLIOTECA-KPIS.md](BIBLIOTECA-KPIS.md) | KPIs de varejo com fórmulas e faróis |
| [SITE-PRODUTO.md](SITE-PRODUTO.md) | Site de marketing / conversão |
| [ESCOPO-TELAS-MVP.md](ESCOPO-TELAS-MVP.md) | Telas da Fase 1 |
| [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md) | Tokens + componentes (colhidos do protótipo) |
| [PLANO-IMPLEMENTACAO.md](PLANO-IMPLEMENTACAO.md) | Ordem de construção Fase 0/1 |
| [prototipo-painel.html](prototipo-painel.html) | Protótipo navegável do Painel Estratégico |
