# BoardOS — Biblioteca de KPIs de Varejo Alimentar

Catálogo dos indicadores que o BoardOS acompanha, com **fórmula**, **unidade**,
**tipo** (leading/lagging/saúde/risco), **nível** de quem consome, **frequência**
e **faróis** (verde/amarelo/vermelho). Serve como especificação da biblioteca
inicial do produto.

> Data: 2026-08-01 · relacionado a [PLANO.md](PLANO.md) seção 3.6

**Legenda de tipo**
- **Lagging** — resultado, medido depois que aconteceu (ex.: faturamento).
- **Leading** — ação/antecedente que puxa o resultado (ex.: nº de itens em ruptura).
- **Saúde** — indica que a operação está sadia (ex.: fluxo de caixa).
- **Risco** — antecipa problema (ex.: % validade curta).

**Sobre os faróis:** os limites abaixo são **defaults sugeridos** para
vizinhança/supermercado médio. São **parametrizáveis por rede, formato e loja**
— o número "bom" de margem num atacarejo é diferente de um premium. O default
serve para o sistema já nascer com farol; o cliente ajusta na configuração.

---

## 1. Vendas e Faturamento

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 Verde | 🟡 Amarelo | 🔴 Vermelho |
|-----|---------|-------|------|-------|-------|---------|-----------|------------|
| Faturamento (venda líquida) | Σ valor líquido das vendas | R$ | Lagging | Todos | Diária | ≥ meta | 90–100% da meta | < 90% da meta |
| Crescimento vs. período anterior | (Vendas atual − anterior) / anterior | % | Lagging | Estratégico | Mensal | ≥ +5% | 0 a +5% | negativo |
| Vendas mesmas lojas (SSS) | Cresc. só de lojas com ≥12 meses | % | Lagging | Estratégico | Mensal | ≥ +3% | 0 a +3% | negativo |
| Venda por m² | Venda líquida / área de vendas | R$/m² | Lagging | Tático | Mensal | ≥ benchmark rede | −10% do bench | < −10% |
| Venda por colaborador | Venda líquida / nº colaboradores | R$ | Lagging | Tático | Mensal | ≥ benchmark | −10% | < −10% |
| Participação por categoria | Venda categoria / venda total | % | Lagging | Tático | Mensal | dentro do plano | ±desvio leve | fora da faixa |

---

## 2. Ticket e Cesta

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| Ticket médio | Faturamento / nº de cupons | R$ | Lagging | Todos | Diária | ≥ meta | 95–100% | < 95% |
| Itens por cupom (cesta) | Σ itens / nº de cupons | un | Leading | Tático | Semanal | ≥ meta | 95–100% | < 95% |
| Nº de cupons (fluxo) | Contagem de cupons | un | Leading | Todos | Diária | ≥ meta | 95–100% | < 95% |
| Preço médio por item | Faturamento / total de itens | R$ | Lagging | Tático | Semanal | dentro da faixa | ±leve | fora |

> Ticket médio = itens por cupom × preço médio por item. Útil para o Advisor
> explicar *por que* o ticket caiu (menos itens na cesta? ou downgrade de mix?).

---

## 3. Margem e Rentabilidade

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| Margem bruta | (Venda líq. − CMV) / venda líq. | % | Lagging | Todos | Diária | ≥ meta | −1pp da meta | < −1pp |
| Margem bruta R$ | Venda líquida − CMV | R$ | Lagging | Estratégico | Mensal | ≥ meta | 95–100% | < 95% |
| Mix de margem por seção | Margem % por seção | % | Lagging | Tático | Mensal | dentro do plano | ±leve | fora |
| Markup médio | Preço venda / custo | × | Leading | Tático | Semanal | dentro da faixa | ±leve | fora |
| Margem de contribuição | Venda líq. − custos variáveis | R$/% | Saúde | Estratégico | Mensal | ≥ meta | 95–100% | < 95% |

---

## 4. Estoque e Abastecimento

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| **Ruptura (out-of-stock)** | SKUs sem estoque / SKUs ativos | % | Risco | Todos | Diária | ≤ 3% | 3–5% | > 5% |
| Cobertura de estoque | Estoque atual / venda média diária | dias | Saúde | Tático | Semanal | 15–30 dias | 30–45 ou 10–15 | >45 ou <10 |
| Giro de estoque | CMV período / estoque médio | ×/ano | Saúde | Tático | Mensal | ≥ meta setor | −20% | < −20% |
| GMROI | Margem bruta R$ / estoque médio a custo | × | Saúde | Estratégico | Mensal | ≥ 3,0 | 2,0–3,0 | < 2,0 |
| Estoque parado (sem giro) | SKUs sem venda em N dias / SKUs | % | Risco | Tático | Semanal | ≤ 5% | 5–10% | > 10% |
| Acuracidade de inventário | \|estoque sistema − físico\| / sistema | % erro | Saúde | Tático | Mensal | ≤ 2% | 2–5% | > 5% |

> Ruptura e cobertura são os principais **leading/risco** para o forecast: alta
> ruptura hoje explica queda de venda amanhã.

---

## 5. Perdas e Quebra

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| Quebra operacional | Valor de perdas / venda líquida | % | Risco | Todos | Semanal | ≤ 1,5% | 1,5–3% | > 3% |
| Perda por validade | Valor vencido / venda perecíveis | % | Risco | Tático | Semanal | ≤ 1% | 1–2% | > 2% |
| % SKUs com validade curta | SKUs a vencer em N dias / SKUs perecíveis | % | Risco | Operacional | Diária | ≤ 5% | 5–10% | > 10% |
| Perda desconhecida (furto/erro) | Diferença de inventário não justificada | % | Risco | Estratégico | Mensal | ≤ 0,8% | 0,8–1,5% | > 1,5% |

---

## 6. Clientes e Fidelização

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| NPS | % promotores − % detratores | −100..100 | Lagging | Estratégico | Mensal | ≥ 50 | 30–50 | < 30 |
| Clientes ativos (base fidelidade) | Clientes com compra no período | un | Leading | Tático | Mensal | ≥ meta | 90–100% | < 90% |
| Churn de clientes | Clientes que pararam de comprar / base | % | Risco | Estratégico | Mensal | ≤ 5% | 5–10% | > 10% |
| Frequência de compra | Nº compras / cliente no período | ×/mês | Leading | Tático | Mensal | ≥ meta | 90–100% | < 90% |
| Recompra (retenção) | Clientes que voltaram / base anterior | % | Saúde | Estratégico | Mensal | ≥ 70% | 50–70% | < 50% |
| LTV (valor do cliente) | Ticket médio × frequência × tempo de vida | R$ | Saúde | Estratégico | Trimestral | ≥ meta | 90–100% | < 90% |
| CAC (custo de aquisição) | Investimento em captação / novos clientes | R$ | Risco | Estratégico | Mensal | ≤ meta | 100–120% | > 120% |
| Relação LTV/CAC | LTV / CAC | × | Saúde | Estratégico | Trimestral | ≥ 3,0 | 1,5–3,0 | < 1,5 |

> NPS, churn, frequência e LTV/CAC só existem se houver **programa de
> fidelidade / identificação do cliente** no cupom. Se a rede não tem, o sistema
> marca esses KPIs como "indisponível" e sugere ativar identificação no caixa.

---

## 7. Operação e Pessoas

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| Tempo médio de fila no caixa | Média de espera | min | Saúde | Operacional | Diária | ≤ 5 | 5–8 | > 8 |
| Produtividade de caixa | Cupons / hora-operador | un/h | Leading | Operacional | Semanal | ≥ meta | 90–100% | < 90% |
| Custo de pessoal / venda | Folha / venda líquida | % | Risco | Estratégico | Mensal | ≤ meta | 100–110% | > 110% |
| Absenteísmo | Faltas / dias planejados | % | Risco | Tático | Mensal | ≤ 3% | 3–6% | > 6% |
| Turnover | Desligamentos / headcount médio | % | Risco | Estratégico | Mensal | ≤ meta | 100–130% | > 130% |

---

## 8. Financeiro e Saúde do Negócio

| KPI | Fórmula | Unid. | Tipo | Nível | Freq. | 🟢 | 🟡 | 🔴 |
|-----|---------|-------|------|-------|-------|----|----|----|
| EBITDA / margem operacional | Resultado operac. / venda líq. | % | Lagging | Estratégico | Mensal | ≥ meta | −1pp | < −1pp |
| Fluxo de caixa livre | Entradas − saídas do período | R$ | Saúde | Estratégico | Semanal | positivo e ≥ meta | positivo < meta | negativo |
| Ciclo financeiro | PMR + PME − PMP | dias | Saúde | Estratégico | Mensal | ≤ meta | 100–120% | > 120% |
| Despesa operacional / venda | Despesas / venda líquida | % | Risco | Estratégico | Mensal | ≤ meta | 100–110% | > 110% |
| Ponto de equilíbrio (break-even) | Custos fixos / margem contribuição % | R$ | Saúde | Estratégico | Mensal | venda ≥ 120% do BE | 100–120% | < 100% |

---

## 9. Regras transversais do sistema

1. **Cada KPI tem:** valor atual, meta, tendência (▲▼—), farol, comparação vs.
   período anterior e vs. plano, e drill-down por rede→loja→categoria→SKU.
   1a. **Comparações sempre disponíveis** (via Motor de Comparação — [PLANO.md](PLANO.md)
   3.12): ano anterior (YoY), mês anterior (MoM), semana do ano, dia do mês e
   mesmo dia da semana. Toda variação mostra o valor **bruto** e o **ajustado por
   composição de calendário** (nº de sábados/domingos etc.), para não confundir
   efeito de calendário com desempenho real.
2. **Faróis parametrizáveis** por rede/formato/loja; o default acima só semeia.
3. **Direção do farol** respeita se "maior é melhor" (faturamento) ou "menor é
   melhor" (ruptura, quebra, churn, CAC).
4. **KPI indisponível** quando falta o dado de origem (ex.: sem fidelidade →
   sem NPS/churn) — o sistema mostra "indisponível" e o pré-requisito para ativar.
5. **Cascata leading→lagging:** o Advisor usa a relação para explicar desvios.
   Ex.: faturamento caiu (lagging) → itens por cupom caíram (leading) → ruptura
   subiu (risco) → **Causa provável: abastecimento**; **Ação:** revisar
   reposição das categorias X e Y.
6. **Cada KPI pode virar Key Result** de um OKR (módulo 3.4) e disparar o ciclo
   Fato→Causa→Ação (3.7) quando fura o farol vermelho.

---

## 10. Conjunto mínimo do MVP (Fase 1)

Para o MVP, começar com o núcleo que só depende dos **dados de venda + estoque**
(sem exigir fidelidade nem financeiro completo):

- Faturamento, Crescimento vs. período anterior, Venda por loja/categoria
- Ticket médio, Itens por cupom, Nº de cupons
- Margem bruta (% e R$), Mix por seção
- Ruptura %, Cobertura de estoque, Giro, GMROI
- Quebra operacional, % SKUs validade curta

Fidelização (seção 6), Operação/Pessoas (7) e Financeiro (8) entram conforme o
cliente disponibiliza as fontes correspondentes.
