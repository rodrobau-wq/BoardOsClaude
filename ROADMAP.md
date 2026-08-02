# BoardOS — Roadmap Total (para aprovação)

> Data: 2026-08-02 · Este é o plano completo do que falta para o SaaS.
> Status: aguardando aprovação do fundador.

## ✅ Já entregue (no ar em produção)

| Bloco | Itens |
|-------|-------|
| Fundação (M0) | Multi-tenant + RLS, grão cupom/item, calendário duplo, ingestão idempotente, medidor de uso |
| Motor (M1) | Comparação YoY civil-vs-varejo com ajuste de calendário + testes |
| Painel (M2) | Painel visual ao vivo, toggle Civil↔Varejo, gráfico alinhado, multiempresa |
| Plano (M3 parcial) | Metas/OKRs com **edição na tela** (1.1 ✅) e KR automático do dado real |
| Plano (completo) | **Aba Plano**: Entrevista de Descoberta com resumo IA (1.2 ✅), Direção Estratégica (1.3 ✅), SWOT + Radar de Maturidade (1.4 ✅), Ações 5W2H (1.5 ✅) |
| Execução | **Ciclo FCA + alertas** calculados do dado real (1.6 ✅) |
| IA | **Advisor com Claude** + fallback estatístico (2.1 ✅ — ativa ao setar ANTHROPIC_API_KEY no Render) |
| Operação | **Gestão de usuários** — convites, papéis, troca de senha (4.1 ✅) |
| Segurança | Login JWT, senha hash, tenant do token, super-admin, **rate-limit no login + CORS restrito** (5.1 parcial ✅) |
| Qualidade | **Smoke test de produção** — scripts/test_api_live.py, 15 checagens (5.2 ✅) |
| Operação SaaS | **Painel super-admin** — cadastrar/suspender/excluir clientes, MRR e uso (4.2 ✅) |
| Drill-down | Resumo por loja (civil/varejo) + **por categoria com participação** (3.2 ✅) |
| KPIs | **Margem bruta e itens por cupom** no painel (3.1 parcial ✅) |
| Forecast | **Projeção do restante do mês** (média por dia-da-semana) no gráfico + card (3.3 ✅) |
| Deploy | Render (API + painel + Postgres pago), GitHub CI por push |
| CRM | Conector com layout assumido + onboarding demo (aguarda amostra real) |

---

## 📋 O que falta — em 6 blocos, na ordem proposta

### BLOCO 1 — Completar o módulo de Plano (o coração do produto)
| # | Item | O que entrega |
|---|------|---------------|
| 1.1 | **Edição de OKRs na tela** | CEO cria/edita objetivos e KRs (hoje só visualiza o seed) |
| 1.2 | **Entrevista de Descoberta** | Advisor guiado captura expectativas do CEO (roteiro pronto) e pré-preenche o plano |
| 1.3 | **Direção Estratégica** | Tela de propósito/visão/valores/objetivo de longo prazo |
| 1.4 | **Diagnóstico** | SWOT editável + Radar de Maturidade 360 por área |
| 1.5 | **Plano de Ação (5W2H)** | Iniciativas e ações com responsável/prazo/status ligadas às metas |
| 1.6 | **Ciclo FCA + alertas** | Desvio detectado → Fato/Causa/Ação registrado → mede se a ação funcionou; alertas de KPI vermelho |

### BLOCO 2 — IA de verdade (BoardOS Advisor)
| # | Item | O que entrega |
|---|------|---------------|
| 2.1 | **Insights com Claude API** | Advisor gera análise narrativa real dos desvios (hoje o texto é do motor estatístico) |
| 2.2 | **Converse com seus dados** | Pergunta livre ("por que a margem caiu na loja 3?") respondida com base nos números |
| 2.3 | **Resumo executivo automático** | Briefing semanal/mensal do board gerado pela IA |

### BLOCO 3 — Mais dados e previsão
| # | Item | O que entrega |
|---|------|---------------|
| 3.1 | **Dashboards por nível** | Executivo / tático / operacional com a biblioteca de KPIs (margem, cesta, ruptura…) |
| 3.2 | **Drill-down categoria/SKU** | Aprofundar da loja para categoria e item (schema já suporta) |
| 3.3 | **Forecast à frente** | Projeção do restante do mês/ano no gráfico (estatístico + calendário) |
| 3.4 | **Feriados e sazonalidade** | Cadastro por região/loja alimentando comparação e forecast |
| 3.5 | **Fatores externos** | Concorrentes geolocalizados + IBGE/trade area, clima, inflação (fase mais longa) |

### BLOCO 4 — Operação SaaS (vender e operar)
| # | Item | O que entrega |
|---|------|---------------|
| 4.1 | **Gestão de usuários** | Admin do tenant convida usuários, troca senha, papéis por nível |
| 4.2 | **Painel super-admin** | Cadastrar cliente pela tela (sem seed), suspender, ver uso/MRR |
| 4.3 | **Billing** | Medidor de uso → fatura (base + por registro) + gateway (Stripe/Asaas) |
| 4.4 | **Onboarding self-service** | Upload de CSV com mapeador de colunas na tela |
| 4.5 | **Site de produto** | Landing de venda (plano já escrito em SITE-PRODUTO.md) |
| 4.6 | **Conector CRM real** | Plugar sua base de empresas + vendas (aguarda amostra sua) |

### BLOCO 5 — Qualidade e segurança (antes de cliente real)
| # | Item | O que entrega |
|---|------|---------------|
| 5.1 | **Endurecer produção** | Remover SEED_DEMO, trocar senha do admin, CORS restrito, rate-limit no login |
| 5.2 | **Testes de API** | Suíte automatizada dos endpoints (hoje só o motor tem testes) |
| 5.3 | **Plano pago do web service** | Sem cold start (hoje o serviço grátis dorme) — ação sua no Render |
| 5.4 | **Backup/observabilidade** | Rotina de backup do Postgres + logs/alertas de erro |

### BLOCO 6 — Escala (depois dos primeiros clientes)
| # | Item | O que entrega |
|---|------|---------------|
| 6.1 | **App React** | Migrar o painel de HTML único para app estruturado (quando a UI crescer) |
| 6.2 | **Conectores ERP** | SAP/TOTVS/Linx direto (além do CRM) |
| 6.3 | **Benchmarking entre redes** | Comparativos anônimos entre clientes (com consentimento) |
| 6.4 | **Módulo de Inovação** | Canvas + MVPs de ciclo curto |

---

## Ordem de execução proposta

**1.1 → 1.6 → 2.1 → 4.1 → 5.1/5.2 → 1.2–1.5 → 3.1–3.3 → 4.2–4.4 → 2.2/2.3 → 3.4/3.5 → 4.5/4.6 → Bloco 6**

Racional: primeiro fechar o ciclo *meta → desvio → ação* (1.1, 1.6) e dar IA real ao Advisor (2.1) — é o que demonstra o produto completo numa venda. Depois operação (usuários) e endurecimento, então o restante do Plano e dos dados, e por fim a máquina comercial (billing/site).

## Dependências suas (não bloqueiam o resto)
- Amostra do CRM (4.6) · Upgrade do plano Render (5.3) · Gateway de pagamento a escolher (4.3) · Chave da API Claude para a IA (2.1).
