# BoardOS

Plataforma SaaS multiempresa de **planejamento estratégico e execução para CEOs
de supermercado**. Do plano à execução: lê os dados de venda da rede, compara
com honestidade (calendário duplo), projeta à frente e explica desvios com IA.

Este repositório está na fase **M0 — Fundação** (multi-tenant + ingestão de
vendas no grão cupom/item → camada gold + calendário duplo). Ver
[PLANO-IMPLEMENTACAO.md](PLANO-IMPLEMENTACAO.md).

---

## Rodar o diferencial agora (sem banco)

O motor de **comparação com calendário duplo** roda só com Python stdlib:

```bash
python3 scripts/demo_local.py
```

Mostra, com a composição **real** de dias da semana do calendário, a diferença
entre a lente **Civil** (mês-calendário, dinheiro) e a lente **Varejo**
(like-for-line por dia da semana, demanda) — o insight central do produto.

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
curl "http://localhost:8000/kpi/diario?data_de=2026-08-01&data_ate=2026-08-31" \
     -H "X-Tenant-Id: <TENANT_ID>"
```

Reingerir o mesmo CSV (`make seed`) **não duplica** linhas — idempotência pela
chave natural.

---

## Estrutura

```
db/migrations/     schema Postgres: platform, tenant, calendário duplo, fato
                   item de venda, gold rollups, RLS por tenant
boardos/           núcleo Python: calendar_gen, mapping, ingestion, db (RLS)
api/               FastAPI mínima com contexto de tenant
scripts/           migrate, seed, demo_local (roda sem banco)
data/              CSV de exemplo (grão cupom/item) + mapa de colunas
```

### Decisões de fundação já implementadas
- **Multi-tenant** com `tenant_id` em toda tabela + **Row-Level Security** (0007).
- **Grão cupom/item** com **chave natural** e **upsert idempotente**.
- **Camada gold** recomputada incrementalmente por (loja, dia).
- **Calendário duplo** (civil + varejo/ISO week) com ajuste de composição.
- **Medidor de uso** para billing (conta itens distintos, não linhas).

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
