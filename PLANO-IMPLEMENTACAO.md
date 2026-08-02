# BoardOS — Plano de Implementação (Fase 0 e 1)

O que construir, em que ordem, para sair do zero a um MVP que um primeiro
supermercado use de verdade. Complementa [PLANO.md](PLANO.md) (arquitetura) e
[ESCOPO-TELAS-MVP.md](ESCOPO-TELAS-MVP.md) (telas).

> Data: 2026-08-01

---

## 1. Stack (proposta)

| Camada | Escolha | Porquê |
|--------|---------|--------|
| **Frontend app** | React + TypeScript (Vite ou Next.js) | ecossistema, dashboards; tokens do [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md) |
| **Gráficos** | SVG próprio (como no protótipo) ou lib leve | controle do calendário duplo; evita peso |
| **Backend/API** | Python (FastAPI) | forte em dados/ML, forecast na mesma casa |
| **Banco** | PostgreSQL + **PostGIS** + **RLS** | multi-tenant pooled, geo, isolamento |
| **Ingestão/ETL** | jobs Python (fila) | CSV → bronze→silver→gold, upsert idempotente |
| **IA (Advisor)** | modelos Claude mais recentes | insights Fato→Causa→Ação sobre dados do tenant |
| **Auth** | provider com organização (tenant) + RBAC | login por rede; papéis |
| **Infra** | nuvem gerenciada (a definir) | ver decisão nuvem vs. on-prem |

> Decisões ainda abertas (do [PLANO.md](PLANO.md) §8): nuvem vs. on-prem, gateway de
> billing, fontes externas. Não bloqueiam a Fase 0/1.

---

## 2. Multi-tenancy — a fundação inegociável

Fazer **desde o primeiro commit** (retrofit depois é caro):
1. Toda tabela de negócio tem `tenant_id` NOT NULL.
2. **Row-Level Security** no Postgres por `tenant_id` (rede de segurança).
3. Middleware da API injeta o `tenant_id` da sessão em toda query.
4. Usuário pertence a um tenant; super-admin vive fora dos tenants.
5. IA e relatórios **nunca** cruzam tenants.

---

## 3. Fase 0 — Fundação (dados + esqueleto)

Objetivo: um pipeline confiável e o app "de pé", sem features de negócio ainda.

1. **Esqueleto multi-tenant:** auth com organização, `tenant_id` + RLS, papéis
   (admin/estratégico/tático/operacional + super-admin).
2. **Modelo canônico:** `item_venda` (grão cupom/item) + Loja/Categoria/SKU +
   **Dim. Calendário duplo** (civil + varejo, ISO week) semeada.
3. **Ingestão CSV + mapeador:** upload → mapear colunas → validar → bronze →
   silver (item limpo) → gold (rollups dia×loja×categoria).
   - **Chave natural** `tenant_id+loja+data+cupom_id+seq_item` + **upsert**
     idempotente; reprocessamento por lote (`batch_id` + recorte).
   - **Medidor de uso** (conta itens distintos por chave natural — base do billing).
4. **Cadastro mínimo de tenant** (manual pelo super-admin) para rodar o 1º cliente.
5. **Geocodificação básica da loja** (endereço → lat/long + município).

**Pronto quando:** dá para cadastrar uma rede, subir um CSV de vendas e ver os
dados agregados corretos na camada gold (sem UI de dashboard ainda).

---

## 4. Fase 1 — MVP (o cliente usa)

Ordem sugerida (cada item entrega valor visível):

1. **Design system em código:** tokens (light/dark) + componentes base do
   [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md) (Card, KPI Card, Farol, Segmented, seletores, shell).
2. **Motor de Comparação Temporal** (o diferencial): YoY/MoM/semana/dia com
   valor **bruto e ajustado por composição de calendário** (civil ↔ varejo).
   Materializar comparações no gold.
3. **Dashboards de KPI por nível** (executivo/tático/operacional) usando a
   [BIBLIOTECA-KPIS.md](BIBLIOTECA-KPIS.md) — começar pelo **conjunto mínimo** (vendas, ticket,
   cesta, margem, ruptura, giro, quebra) + faróis parametrizáveis.
4. **Painel Estratégico (1 página)** — a tela-herói (já prototipada).
5. **Gráfico de vendas** com ano anterior alinhado + **forecast simples à frente**
   (baseline estatístico; o avançado é Fase 3).
6. **Entrevista de Descoberta** (Advisor guiado) — captura expectativas e
   pré-preenche Direção/Diagnóstico/Metas ([ROTEIRO-ENTREVISTA.md](ROTEIRO-ENTREVISTA.md)).
7. **Direção + Diagnóstico (SWOT + Radar) + Metas (OKRs)** com desdobramento.
8. **Advisor (insights):** narrativa Fato→Causa→Ação sobre os desvios reais.
9. **Config:** Minha Rede (lojas, concorrentes por endereço), Calendário
   (feriados/sazonalidade, ISO/4-4-5), Dados (batches/reprocessar), Usuários.

**Fora do MVP** (ver [ESCOPO-TELAS-MVP.md](ESCOPO-TELAS-MVP.md) §9): forecast com clima/inflação,
trade area, ciclo FCA completo com ações, conectores ERP, billing self-service,
site, inovação.

---

## 5. Ordem de valor (o caminho mais curto até "uau")

O menor caminho para o cliente sentir o diferencial:
**Fase 0 (ingestão) → comparação com calendário duplo → Painel Estratégico +
gráfico.** Com isso já se demonstra o "Civil −2,1% / Varejo +3,4%" com **dados
reais do cliente** — antes mesmo de OKRs e Advisor completos.

Sugestão: rodar um **piloto com 1 rede** logo após esse núcleo, e iterar o resto
(Descoberta, Metas, Advisor) com feedback real.

---

## 6. Marcos (milestones)

| Marco | Entrega | Sinal de pronto |
|-------|---------|-----------------|
| **M0** | Fundação multi-tenant + ingestão | CSV vira gold correto para 1 tenant |
| **M1** | Comparação + Painel + gráfico | "Civil vs. Varejo" com dado real do piloto |
| **M2** | KPIs por nível + Config básica | CEO e gerente navegam seus recortes |
| **M3** | Descoberta + Direção/Diagnóstico/Metas | plano estratégico montado no sistema |
| **M4** | Advisor (insights) | desvios explicados em Fato→Causa→Ação |
| **MVP** | M0–M4 estáveis com o piloto | 1 rede usando na rotina |

---

## 7. Riscos de execução

- **Qualidade do CSV do cliente** (colunas inconsistentes, cupom sem `seq_item`)
  → mapeador tolerante + fallback de chave natural.
- **Composição de calendário** exige acerto fino da Dim. Calendário (ISO week,
  semana partida) — testar cedo com dados reais.
- **Volume no grão de item** → rollups incrementais desde o início (não deixar
  dashboard ler fato cru).
- **Escopo do MVP** → resistir a puxar forecast avançado/trade area para a Fase 1.
