# BoardOS — Escopo de Telas do MVP (Fase 1)

Telas concretas do produto para a Fase 1: o que o CEO e os gerentes veem, com
propósito, público, elementos-chave e estados (vazio/carregando/erro). Serve como
base para design e desenvolvimento.

> Data: 2026-08-01 · relacionado a [PLANO.md](PLANO.md), [ROTEIRO-ENTREVISTA.md](ROTEIRO-ENTREVISTA.md), [BIBLIOTECA-KPIS.md](BIBLIOTECA-KPIS.md)

**Escopo:** foca no **app do cliente (tenant)**. Painel Super-Admin e site de
produto têm docs próprios ([PLANO.md](PLANO.md) 3.11, [SITE-PRODUTO.md](SITE-PRODUTO.md)).

---

## 1. Mapa de navegação (IA)

```
Login (com organização)
└── App do tenant
    ├── Onboarding (primeira vez)
    │   ├── 1. Entrevista de Descoberta
    │   ├── 2. Cadastro da Rede e Lojas
    │   └── 3. Importar dados de venda (CSV)
    ├── 🏠 Início / Painel Estratégico (1 página)
    ├── 📊 Indicadores (dashboards por nível)
    │   ├── Executivo
    │   ├── Tático (loja/categoria)
    │   └── Operacional
    ├── 🎯 Plano
    │   ├── Direção Estratégica
    │   ├── Diagnóstico (SWOT + Radar)
    │   └── Metas (OKRs)
    ├── 🤖 Advisor (insights / perguntas)
    ├── ⚙️ Configuração
    │   ├── Minha Rede (lojas, concorrentes)
    │   ├── Calendário (feriados/sazonalidade, civil↔varejo)
    │   ├── Dados (importações, mapeador)
    │   └── Usuários e papéis
    └── perfil / sair
```

**Shell comum:** menu lateral, seletor de **período** (com toggle **Civil ↔
Varejo**, ver 3.12) e **escopo** (rede → loja → categoria) no topo, sempre
visíveis. O escopo e o período escolhidos valem para todas as telas de dados.

---

## 2. Onboarding (primeiro acesso)

### 2.1 Entrevista de Descoberta
- **Quem:** CEO/admin do tenant. **Propósito:** capturar negócio + expectativas.
- **Formato:** conversa com o **Advisor**, **uma pergunta por vez** (chat guiado),
  barra de progresso, botão "pular e voltar depois". Segue o [ROTEIRO-ENTREVISTA.md](ROTEIRO-ENTREVISTA.md).
- **Fim:** tela de **validação** (resumo para confirmar/ajustar) → gera o
  **documento de expectativas** que pré-preenche Direção, Diagnóstico e Metas.
- **Estados:** retomável (salva a cada resposta); editável depois em Config.

### 2.2 Cadastro da Rede e Lojas
- **Campos da rede:** nome, formato predominante.
- **Loja:** nome, **endereço** (geocodifica → lat/long + município), formato,
  área de vendas. Ao salvar, mostra os **dados IBGE do entorno** já puxados
  (população, renda) como confirmação de que a loja "ganhou contexto".
- **Estado vazio:** CTA "Adicionar primeira loja". Import em lote via planilha.

### 2.3 Importar dados de venda (mapeador)
- **Upload CSV/Excel** → **mapeador de colunas** guiado (aponte qual coluna é
  data, loja, cupom, SKU, qtd, valor, custo…). Preview das primeiras linhas.
- **Validação:** avisa linhas com erro, datas fora do intervalo, SKUs novos.
- **Confirmação:** mostra nº de registros que serão processados (liga ao medidor).
- **Estados:** progresso da ingestão; "concluído — seus dados estão prontos".

---

## 3. Início / Painel Estratégico (1 página)

- **Quem:** CEO/board. **Propósito:** a rede numa tela.
- **Blocos:**
  - **Faixa de KPIs macro** (faturamento, margem, ruptura, ticket) com **farol**,
    tendência e variação **bruta e ajustada por calendário**.
  - **Progresso das Metas (OKRs)** com status semafórico e % de avanço.
  - **Iniciativas-chave** e seus donos (quando existirem — Fase 2).
  - **Alertas / desvios** que precisam de atenção (vermelhos).
  - **Resumo do Advisor** (2–3 frases: o que está acontecendo e por quê).
- **Interações:** clicar em qualquer bloco → drill-down na tela detalhada.
- **Estado vazio (sem dados ainda):** mostra o passo que falta do onboarding.

---

## 4. Indicadores (dashboards por nível)

Todos herdam o **período (Civil/Varejo)** e **escopo** do topo. Cada KPI segue a
[BIBLIOTECA-KPIS.md](BIBLIOTECA-KPIS.md): valor, meta, farol, tendência, e comparações **YoY / MoM /
semana / dia** com valor **bruto e ajustado por composição de calendário**.

### 4.1 Dashboard Executivo
- KPIs macro (vendas, margem R$/%, ruptura, ticket, cesta), gráfico de vendas no
  tempo com **linha do ano anterior alinhada (semana de varejo)** e **forecast à
  frente** (faixa de projeção).
- Card "Civil vs. Varejo": o mesmo mês em duas lentes, com a explicação
  ("teve um sábado a menos").

### 4.2 Dashboard Tático (loja / categoria)
- Ranking de lojas e de categorias; participação por categoria; venda por m².
- Drill-down loja → categoria → SKU.
- Tabela comparativa com faróis por linha.

### 4.3 Dashboard Operacional
- Ruptura por SKU, cobertura de estoque, % validade curta, quebra.
- Foco em ação do dia; itens em vermelho no topo.

**Estados comuns:** carregando (skeleton), KPI **indisponível** (falta fonte —
ex.: NPS sem fidelidade, com o pré-requisito para ativar), sem dados no período.

---

## 5. Plano

### 5.1 Direção Estratégica
- Propósito, Valores, Visão, objetivo de longo prazo — **pré-preenchidos** pela
  entrevista, editáveis. Módulo de cultura (guia + manifesto) como opcional.

### 5.2 Diagnóstico
- **SWOT** em 4 quadrantes (editável, itens sugeridos pela IA a partir dos dados).
- **Radar de Maturidade 360** por área (Comercial, Marketing/Fidelização,
  Operação/Pessoas, Inovação, Financeiro) com notas e gargalos destacados.
- Cruzamento com dados reais (ex.: "ruptura alta" vira fraqueza automática).

### 5.3 Metas (OKRs)
- Criar objetivo → resultados-chave (cada KR liga a um **KPI** da biblioteca) →
  desdobrar em cascata (Corp → Área → Loja/Categoria).
- Cada KR mostra **atual vs. alvo**, prazo, responsável e farol.
- Conciliação top-down ↔ bottom-up (a soma bate com a meta da rede?).
- **Estado vazio:** sugestão de OKRs a partir das expectativas da entrevista.

---

## 6. Advisor (insights)

- **Quem:** todos. **Propósito:** conversar com os dados, no tom conselheiro.
- **Feed de insights:** desvios explicados como **Fato → Causa provável →
  Ação sugerida**, sempre citando números.
- **Pergunta livre:** "por que a margem caiu em julho na Loja 3?" → resposta
  fundamentada, com gráfico e a comparação usada (civil/varejo).
- **Ação:** transformar um insight em **iniciativa/ação** (liga à Fase 2).

---

## 7. Configuração

### 7.1 Minha Rede (lojas e concorrentes)
- Lista de lojas com mapa; editar loja (endereço/geo/IBGE).
- **Concorrentes:** cadastrar por endereço (geocodifica); marcar lojas afetadas;
  (importação automática de POIs entra na Fase 3).

### 7.2 Calendário
- Configurar o **calendário de varejo** (ISO week default; 4-4-5 opcional).
- Cadastro de **feriados** (nacional/estadual/municipal por loja) e **datas
  sazonais** com efeito esperado.

### 7.3 Dados
- Histórico de importações (batches), status, reprocessar um recorte.
- Reabrir o **mapeador** para novos arquivos.

### 7.4 Usuários e papéis
- Convidar usuários da rede; atribuir nível (admin/estratégico/tático/operacional)
  e o recorte de visibilidade (quais lojas/áreas cada um vê).

---

## 8. Componentes transversais (design system)

- **Seletor de período** com toggle **Civil ↔ Varejo** e presets (hoje, semana,
  mês, ano, YoY).
- **Seletor de escopo** rede → loja → categoria → SKU (breadcrumb).
- **KPI Card:** valor, meta, farol (🟢🟡🔴), tendência, variação bruta + ajustada.
- **Badge de comparação:** "vs. ano anterior (varejo)", "vs. mês (civil)".
- **Farol** com direção correta (maior é melhor vs. menor é melhor).
- **Estado indisponível** com o pré-requisito de dado.
- **Skeletons** de carregamento; **empty states** que guiam a próxima ação.

---

## 9. O que fica FORA do MVP (Fase 1)

- Forecast avançado com clima/inflação/concorrência (Fase 3).
- Trade area (zonas) e importação automática de concorrentes (Fase 3).
- Gestão de iniciativas/ações e rotinas (ciclo FCA completo) — Fase 2.
- Conectores de ERP — Fase 2. Billing self-service e site — Fase 5.
- Módulo de Inovação — Fase 6.

> No MVP, o cadastro de concorrente e a geocodificação da loja **existem**
> (contexto e dado), mas a **inteligência de trade area** vem depois.
