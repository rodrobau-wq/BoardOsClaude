# BoardOS — Plano do Projeto

Sistema de planejamento estratégico e execução para CEOs de supermercados.
Do plano à execução: entrevista o CEO para capturar as expectativas, define a
direção, lê os dados de venda da rede, acompanha o realizado, detecta desvios,
sugere ajustes de rota/forecast e gera insights com IA.

> Status: **v3 do plano** — metodologia própria BoardOS.
> Data: 2026-08-01

---

## 0. O que é o BoardOS

**Plataforma SaaS multiempresa (multi-tenant).** O BoardOS é vendido para
várias redes de supermercado; cada cliente é um **tenant** isolado, com seus
dados, usuários, metas e configurações separados dos demais. Há um **painel de
administração** (nível operador BoardOS) para cadastrar novos clientes, gerir
planos/assinaturas e dar suporte — e um **site de produto** para atrair e
converter novos supermercados.

Para cada rede cliente, o BoardOS é um "sistema operacional do board" que roda
um ciclo vivo de gestão estratégica, conectando **estratégia** (onde a rede quer
chegar) com **execução** (o que os dados de venda mostram), fechando o loop
continuamente:

```
DESCOBERTA → DIREÇÃO → DIAGNÓSTICO → METAS → PLANO DE AÇÃO → EXECUÇÃO
     ▲                                                            │
     └────────────────────────────────────────────────────────────┘
                 (o realizado alimenta o próximo ciclo)
```

A **Metodologia BoardOS** usa ferramentas de gestão consagradas e neutras
(entrevista de descoberta, análise SWOT, OKRs, plano de ação 5W2H, ciclo de
correção Fato→Causa→Ação, painel estratégico de uma página, faróis de status),
calibradas para a realidade de um supermercado: lojas, categorias, SKUs,
sazonalidade, ruptura, margem, giro.

Definições do usuário já incorporadas: **3 níveis de usuário** (CEO/board →
diretores/gerentes → gerentes de loja/categoria), **ingestão híbrida** (CSV +
ERP) e **IA no centro** do produto.

---

## 1. Visão do produto

O diferencial é a **IA no centro** — o **BoardOS Advisor**: um conselheiro
digital direto, prático e orientado à ação, que sempre cita os números que
embasam a conclusão. Ele conduz a entrevista de descoberta, explica *por que* o
resultado desviou do plano (Fato → Causa), projeta o forecast e recomenda a
ação corretiva. A IA sugere; o humano decide.

---

## 2. Personas e níveis de acesso

Dois universos: o **operador da plataforma** (você/BoardOS) e os **usuários de
cada rede cliente** (o tenant).

### 2.1 Plataforma (BoardOS)
| Papel | Persona | Foco |
|-------|---------|------|
| **Super-Admin** | Operador BoardOS (você) | Cadastrar/suspender clientes, planos, billing, métricas globais, suporte |
| **Suporte / Onboarding** | Time BoardOS | Configurar o tenant novo, acompanhar ingestão, ajudar no setup |

> O Super-Admin nunca navega dados de negócio do cliente por padrão; acesso a
> dados de tenant exige **impersonation auditada** (log de quem acessou o quê).

### 2.2 Dentro de cada rede cliente (tenant)
Três camadas, o mesmo dado em profundidades diferentes:

| Nível | Persona | Foco | O que decide |
|-------|---------|------|--------------|
| **Admin do tenant** | Dono/TI da rede | Convidar usuários, papéis, integrações, configuração | Quem acessa o quê na rede |
| **Estratégico** | CEO / Board | Direção, diagnóstico, metas corporativas, painel 1 página | Metas, alocação, prioridades |
| **Tático** | Diretores / Gerentes regionais | Plano de ação, metas de área, drill-down loja/categoria | Ajustes de rota, redistribuição de metas |
| **Operacional** | Gerentes de loja / categoria | Execução, ruptura, forecast por SKU, rotinas diárias | Reposição, ações locais |

Visibilidade por linha (row-level security): cada usuário vê seu recorte; o
board vê tudo agregado com drill-down. **Todo dado é escopado por `tenant_id`.**

---

## 3. Módulos funcionais

### 3.1 Entrevista de Descoberta (captura de expectativas)
Ponto de entrada do CEO no sistema. O BoardOS Advisor conduz uma **entrevista
guiada, uma pergunta por vez**, para entender o negócio e, principalmente,
**as expectativas sobre o plano estratégico** antes de qualquer tela de plano.

- **Etapa 1 — Perguntas (uma a uma):** nome e tempo da rede; o que vende e como
  entrega valor; problema real que resolve para o cliente; cliente ideal
  (perfil, região, porte); diferenciais vs. concorrência; principal resultado
  entregue; modelo de receita; onde atua; **visão/objetivo principal do
  negócio**. Se a resposta vier vaga, o Advisor pede exemplos concretos.
  - Perguntas específicas de expectativa do plano: *quais metas o CEO espera
    bater no ano? qual o maior gargalo hoje? o que "sucesso" significa para
    ele em 12 meses? que decisões quer que o sistema o ajude a tomar?*
- **Etapa 2 — Organização estratégica:** o Advisor identifica inconsistências
  ou falta de clareza, sugere ajustes e **valida o entendimento** antes de
  concluir.
- **Etapa 3 — Entrega estruturada:** gera um documento claro e direto:
  1. Resumo executivo (3–5 linhas)
  2. O que a rede faz (descrição objetiva)
  3. Problema que resolve
  4. Público-alvo
  5. Diferenciais competitivos
  6. Como ganha dinheiro (modelo de negócio)
  7. Posicionamento resumido (uma frase)
  8. **Expectativas do plano estratégico** (metas-alvo, gargalos, definição de
     sucesso) — o insumo que alimenta os módulos seguintes.

> Esse artefato vira a "linha de base" do plano: os módulos 3.2–3.4 partem dele.

### 3.2 Direção Estratégica
- Captura de **Propósito, Valores, Visão e objetivo de longo prazo** da rede,
  via fluxo guiado por IA (perguntas uma a uma), reaproveitando o material da
  entrevista de descoberta.
- Módulo de **Cultura**: fluxo guiado que gera um guia interno de valores e
  comportamentos e, opcionalmente, um manifesto para a equipe.

### 3.3 Diagnóstico
- **Análise SWOT** guiada (5–10 itens por quadrante).
- **Radar de Maturidade 360**: nota por área de gestão (Comercial/Vendas,
  Marketing e Fidelização, Operação e Pessoas, Inovação, Financeiro),
  mostrando forças e gargalos da rede — o "check-up estratégico".
- Enriquecido pelos **dados de venda reais** (receita, margem, ruptura, giro),
  não só percepção.

### 3.4 Metas e Objetivos (OKRs)
- **OKRs SMART** por horizonte (ano/trimestre), com desdobramento em cascata:
  Corporativo → Área → Loja/Categoria.
- Cada resultado-chave é uma **métrica** (lagging), ligada a **iniciativas** e a
  **leading indicators** (as ações que puxam o resultado).
- Conciliação top-down ↔ bottom-up (a soma das lojas bate com a meta da rede?).

### 3.5 Plano de Ação
- Desdobra cada meta em **Iniciativas** e **Ações no formato 5W2H**
  (O quê, Por quê, Onde, Quando, Quem, Como, Quanto custa).
- **Painel Estratégico de uma página**: Direção → Metas → Iniciativas →
  Indicadores → Riscos, com responsável por item e status semafórico.

### 3.6 Indicadores (KPIs)
- Biblioteca de KPIs de varejo alimentar pronta, classificados em **lagging**
  (resultado), **leading** (ação), **saúde** e **risco**:
  - Vendas, margem bruta, ticket médio, itens por cupom, GMROI, **ruptura %**,
    quebra/perdas, giro de estoque, venda por m², venda por colaborador,
    participação por categoria, **NPS, churn de clientes, LTV, CAC** (fidelidade).
- Cada KPI: valor atual, meta, tendência, **farol verde/amarelo/vermelho**,
  vs. período anterior e vs. plano.
- Dashboards por nível (executivo / tático / operacional).

### 3.7 Execução e Acompanhamento (ciclo de correção)
- **Plano vs. Realizado** por meta, com detecção automática de desvio.
- **Ciclo Fato → Causa → Ação**: para cada desvio o sistema estrutura o **Fato**
  (o dado), a **Causa** (a IA investiga a raiz cruzando os dados) e a **Ação**
  (plano corretivo com responsável, prazo, status — e depois mede se a ação
  funcionou).
- **Rotinas** embutidas como cadência do produto:

  | Rotina | Frequência | Nível | Objetivo |
  |--------|-----------|-------|----------|
  | Diária | diária | Operacional | remover bloqueios do dia |
  | Semanal | semanal | Tático | progresso das ações |
  | Mensal | mensal | Executivo | revisar metas, desvios, ajustes |
  | Trimestral | trimestral | Board | resultados, aprendizados, re-plano |

- Alertas (e-mail/painel) quando um KPI crítico fura o limite.

### 3.8 Ajustes de rota e forecast (projeção para a frente)
- **Forecast de vendas sempre à frente** por rede/loja/categoria/SKU
  (estatístico + IA): projeta o restante do dia/semana/mês/ano.
- Usa como features: **composição de calendário** (3.12), **sazonalidade e
  feriados** (3.13), e os **fatores externos** — concorrência, inflação, clima
  (3.13).
- Re-forecast contínuo conforme entram novos dados; mantém versões do forecast.
- Quando o forecast indica que a meta não será batida, o sistema roda o ciclo
  de correção e **recomenda o ajuste de rota** priorizado por impacto na meta.

### 3.9 Insights — BoardOS Advisor (IA)
- Narrativa automática de desvios (Fato → Causa provável → Ação sugerida).
- Perguntas em linguagem natural sobre os dados, sempre fundamentadas.
- Resumos executivos periódicos (semanal/mensal) para o board.
- **Tom:** conselheiro direto, sem enrolação, orientado à ação, citando sempre
  os números.

### 3.10 Inovação (fase posterior)
- **Canvas de inovação** + ciclos curtos de MVP para testar iniciativas de
  varejo (nova categoria, formato de loja, ação promocional), com hipótese,
  KPIs de sucesso e decisão (escalar / ajustar / descartar).
- Lógica de foco 80/20: operar o core e explorar o novo.

### 3.11 Painel de Administração da Plataforma (Super-Admin)
Aplicação separada (ou área protegida) para o operador BoardOS gerir o negócio
SaaS. **Nunca é vista pelos clientes.**

- **Clientes (tenants):** cadastrar novo supermercado (cria o tenant isolado),
  editar dados, suspender/reativar, excluir (com retenção/LGPD).
- **Provisionamento/onboarding:** criar o tenant, o admin inicial da rede,
  disparar convite, checklist de setup (ingestão configurada? primeiras metas?).
- **Planos e assinaturas (billing):**
  - **Modelo v0:** **preço mínimo mensal (assinatura base) + cobrança por
    registros de venda processados** (usage-based sobre a quantidade de linhas/
    cupons ingeridos no período). Valores serão refinados depois — a v0 só
    precisa **medir e faturar** esses dois componentes.
  - **Medidor de uso:** o pipeline de ingestão conta registros por tenant/mês
    (idempotente, sem dupla contagem em reprocessamento); esse contador alimenta
    a fatura. Guardar histórico do medidor para auditoria/contestação.
  - Status (trial/ativo/inadimplente/cancelado), cobrança recorrente + parcela
    variável de uso, faturas.
  - Integração com gateway (ex.: Stripe/Iugu/Asaas) — **cobrança nunca é
    processada dentro do app; usa gateway externo.**
- **Métricas do negócio (BoardOS):** MRR, nº de tenants ativos, churn de
  clientes, uso por tenant, contas em risco.
- **Suporte:** impersonation auditada (entrar como um tenant para dar suporte,
  com log), tickets, avisos/broadcast.
- **Feature flags por plano/tenant:** habilitar módulos (ex.: Inovação, ERP
  connector) conforme o plano contratado.
- **Auditoria:** log de ações administrativas (quem cadastrou/suspendeu/acessou).

### 3.12 Motor de Comparação Temporal e Ajuste de Calendário
O coração analítico do BoardOS: **toda venda é sempre comparada** em múltiplos
recortes de tempo, com **correção de calendário** para não enganar o CEO.

#### Calendário duplo (diferencial do produto)
O BoardOS mantém **dois calendários ao mesmo tempo**, ambos ancorados no **dia**
como unidade atômica (cada dia carrega as chaves dos dois):

- **Calendário civil (mês/ano-calendário)** — usado para **dinheiro**:
  faturamento, despesas, margem, fechamento contábil e billing. Fecha sempre no
  mês do calendário (do dia 1 ao último), porque é assim que o financeiro do
  supermercado funciona.
- **Calendário de varejo (semana alinhada)** — usado para **demanda / venda
  comparável**: semanas começam sempre no mesmo dia (padrão **ISO week**, ou
  **4-4-5** opcional por tenant), agrupadas em períodos de varejo. Assim o
  "mesmo período do ano passado" tem **a mesma composição de dias da semana** —
  a comparação YoY fica honesta (não compara 5 sábados contra 4).

**Como os dois se encaixam:** como tudo é somado a partir do dia, uma **semana de
varejo pode cair em dois meses civis** (semana partida). Isso não gera conflito:
- Para **finanças**, os dias da semana partida caem naturalmente em cada mês
  civil (grão diário resolve).
- Para **comparação de demanda**, a semana é tratada inteira, alinhada ao ano
  anterior.
- A tela mostra as duas lentes lado a lado e o Advisor explica qual usar:
  *"No fechamento (civil) o mês caiu 2%; em venda comparável (varejo) cresceu 3% —
  o mês teve um sábado a menos."*

- **Comparações padrão (sempre presentes):**
  - **Ano anterior** (YoY) — comparando **semanas de varejo alinhadas** (e não
    datas civis), além de mês civil YoY para o financeiro.
  - **Mês anterior** (MoM) — civil (dinheiro) e período de varejo (demanda).
  - **Semana do ano** (semana de varejo N vs. N do ano passado).
  - **Dias do mês** (acumulado dia-a-dia: dia 12 vs. dia 12).
  - **Mesmo dia da semana** (este sábado vs. o sábado equivalente).
- **Ajuste de composição de calendário (trading-day):** o sistema conta
  **quantos de cada dia da semana** o período tem (ex.: 5 sábados vs. 4) e
  **normaliza a comparação**. Assim, um mês que vendeu mais só porque teve um
  sábado a mais **não** é lido como crescimento real. Mostra dois números:
  **bruto** e **ajustado por calendário**.
  - Cada dia da semana tem peso próprio (fim de semana costuma vender mais);
    o motor aprende esses pesos por loja a partir do histórico.
- **Efeitos de calendário destacados:** feriados, vésperas, pagamento
  (início/fim de mês), datas comerciais — sinalizados na comparação para
  explicar picos/vales (integra com 3.13).
- **Saída:** variação % bruta e ajustada, contribuição de cada fator (calendário
  vs. desempenho real), e alimentação do forecast (3.8) e dos insights (3.9).

### 3.13 Fatores Externos, Feriados e Sazonalidade (cadastros)
Cadastros e integrações que explicam a venda além da operação — e viram
features do forecast e contexto para o Advisor.

- **Concorrência:** cadastrar **novo concorrente na região** (nome, tipo,
  endereço/raio, data de abertura) e marcar as **lojas afetadas**. O sistema
  mede o impacto na venda das lojas próximas (antes/depois) e alerta.
- **Inflação do período:** puxar índice (ex.: IPCA / IPCA-15, ou índice setorial
  de alimentos) por período/região para **separar crescimento real de
  crescimento por preço** (venda real vs. venda deflacionada).
- **Clima e tempo:** integração com fonte de meteorologia por região/loja
  (histórico + previsão). Chuva, calor, frio mudam a cesta e o fluxo — vira
  feature do forecast e explicação de desvio ("choveu no sábado → fluxo −12%").
- **Feriados e sazonalidade:** calendário cadastrável de **feriados** (nacional,
  estadual, municipal — por loja/região) e **datas sazonais** (Natal, Páscoa,
  volta às aulas, Black Friday, festas regionais), com efeito esperado por
  categoria. Base para forecast e para o ajuste de calendário (3.12).

> Fontes externas (inflação, clima, feriados) são **compartilhadas entre tenants**
> (dado público/regional), mas o **impacto calculado** é por tenant/loja.

### 3.14 Geolocalização e Inteligência de Mercado (IBGE + trade area)
No **cadastro da loja**, o endereço é geocodificado (lat/long) e enriquecido
automaticamente com dados públicos de mercado.

- **Geocodificação:** endereço da loja → coordenadas + município/UF + setor
  censitário (via geocoder — Google/OSM-Nominatim).
- **Dados IBGE do entorno:** ao salvar a loja, puxar do IBGE o que estiver
  disponível para a cidade/região: **população, densidade, renda média
  domiciliar, PIB per capita municipal, nº de domicílios**, faixa etária.
  Usa Censo, PIB dos Municípios e agregados por setor censitário. Vira contexto
  de **potencial de mercado** da loja.
- **Trade area (zonas primária / secundária / terciária):** desenhar as zonas de
  influência da loja por **anéis de distância** (ex.: 0–1 km / 1–3 km / 3–5 km)
  ou, quando possível, por **isócrona de deslocamento** (5 / 10 / 15 min). Para
  cada zona, agregar população, domicílios e renda (do IBGE) → estimativa de
  **consumo potencial** por zona.
  - Regra prática de varejo: a zona **primária** costuma concentrar a maioria dos
    clientes; secundária e terciária são captação decrescente e mais disputadas.
- **Sobreposição de concorrência:** cruzar as zonas da loja com os concorrentes
  cadastrados (3.13) para ver **quais concorrentes caem em cada anel** e a
  pressão competitiva por zona.
- **Cadastro de concorrentes por endereço:** o endereço do concorrente também é
  geocodificado; opção de **importar automaticamente** supermercados da área a
  partir de uma base de POIs/estabelecimentos (ex.: Google Places, OpenStreetMap
  ou base de CNPJ da Receita filtrada por CNAE de comércio de alimentos) — o
  usuário revisa e confirma antes de gravar.
- **Saídas:** ficha de mercado da loja (potencial vs. venda realizada, "share of
  wallet" estimado), mapa de trade area com concorrentes, e features para o
  forecast (3.8) e para o Advisor (ex.: "abertura de concorrente na zona primária
  da Loja 4 explica queda de fluxo").

> Enriquecimento IBGE/POI usa fontes **públicas compartilháveis entre tenants**
> (cacheadas por região); a **loja, suas zonas e concorrentes** são dado do tenant.

---

## 4. Arquitetura de dados e ingestão

Ingestão **híbrida e agnóstica** (CSV + ERP), evoluindo em fases:

```
Fontes                 Ingestão              Armazenamento          Consumo
──────                 ────────              ─────────────          ───────
CSV / Excel  ─┐
              ├─►  Camada de conectores  ─►  Data warehouse    ─►  API  ─►  App
ERP/BD (SAP,  │    + validação/limpeza       (bronze→silver→        (web)
TOTVS, Linx) ─┘    + normalização            gold)                  IA / forecast
```

- **Fase 1 (MVP):** upload de CSV/Excel com mapeador de colunas guiado.
- **Fase 2:** conectores diretos ao ERP/banco (SAP, TOTVS, Linx) com sync agendado.
- **Grão de ingestão: cupom / item** (decidido). Ingerimos a **linha de
  transação** — o nível mais fino — o que habilita cesta (itens por cupom),
  ruptura por SKU, margem por item e churn de cliente (quando há identificação).
  - **Modelo canônico (fato item de venda):** `item_venda(tenant_id, data_hora,
    loja, cupom_id, cliente_id?, sku, categoria, qtd, valor_bruto, valor_liquido,
    desconto, custo, margem, …)`.
  - **Cupom** deriva do agrupamento dos itens (nº de itens, valor total, cliente).
- **Camada de performance (agregados/views):** como o volume no grão de item é
  grande, os dashboards **não** leem o fato cru. Materializamos **rollups** na
  camada gold:
  - por **dia × loja × categoria** (e × SKU quando necessário);
  - já com as chaves do **calendário duplo** (civil + varejo, ver 3.12);
  - KPIs pré-calculados e comparações materializadas (YoY/MoM/semana).
  - Implementação: **views materializadas** (ou tabelas de rollup incrementais)
    atualizadas no pipeline de ingestão; o fato item fica disponível para
    drill-down fino sob demanda.
- Camadas de qualidade: bronze (cru) → silver (item limpo/normalizado) → gold
  (rollups e agregações prontos para KPI, meta, comparação e forecast).

- **Chave natural e reprocessamento idempotente:**
  - **Chave natural do item:** `tenant_id + loja + data + cupom_id + seq_item`
    (a sequência do item dentro do cupom desambigua o mesmo SKU repetido). Se o
    ERP não tiver `seq_item`, cair para `... + sku + ocorrência`.
  - **Upsert:** ingestão faz **insert-or-update** pela chave natural — reenviar
    um dia/cupom **substitui** os registros existentes em vez de duplicar.
  - **Reprocessamento por lote:** cada carga tem um `batch_id` e um recorte
    (loja + intervalo de datas). Reprocessar um recorte roda um
    **delete-and-reload** (ou upsert + tombstone) só daquele recorte — o resto
    fica intacto. Correções do ERP (estorno, ajuste de preço) entram assim.
  - **Rollups incrementais:** ao reprocessar um recorte, só os agregados gold
    daquele dia/loja são recalculados.
  - **Medidor de uso (billing) à prova de duplicidade:** o contador de registros
    conta **itens distintos pela chave natural**, não linhas ingeridas — reenvio
    ou correção **não infla** a fatura. Guardar o snapshot do medidor por período.
  - **Auditoria:** manter `batch_id`, origem, `ingerido_em` e versão em cada
    registro para rastrear o que veio de qual carga.

---

## 5. Modelo de dados (núcleo)

**Nível plataforma (compartilhado):**
- **Tenant (Cliente/Rede)**: id, nome, status, plano, criado_em
- **Assinatura/Plano**: tenant, plano, ciclo, status de cobrança, gateway_id
- **Medidor de Uso**: tenant, período, nº de registros de venda ingeridos (base
  da parcela variável do billing v0)
- **Fatura**: assinatura, valor base + valor por uso, período, status
- **Usuário de Plataforma**: super-admin / suporte (fora de tenant)
- **Log de Auditoria**: ator, ação, tenant alvo, timestamp
- **Fontes externas (regionais/públicas, reusáveis entre tenants):**
  - **Dim. Calendário (calendário duplo, grão = dia)**: data →
    - *civil:* mês/ano-calendário, dia do mês, nº de cada dia da semana no mês
    - *varejo:* semana de varejo (ISO/4-4-5), período de varejo, ano de varejo,
      flag de semana partida entre meses civis
    - *comuns:* dia da semana, útil/fim de semana, período de pagamento, feriado
  - **Feriado**: data, abrangência (nacional/estadual/municipal), região
  - **Evento Sazonal**: nome, janela, efeito esperado por categoria
  - **Índice de Inflação**: índice, período, região
  - **Clima**: região, data, condição, temperatura, chuva (histórico + previsão)
  - **Dados IBGE (por município/setor censitário)**: população, densidade, renda
    média domiciliar, PIB per capita, nº de domicílios, faixa etária

**Nível tenant (isolado por `tenant_id` em todas as tabelas):**
- **Rede** → **Loja** → **Categoria** → **SKU**
  - **Loja** guarda: endereço, **lat/long**, município/UF, setor censitário,
    formato/área de vendas
- **Item de Venda** (fato, grão mínimo): data_hora, loja, cupom_id, cliente_id?,
  sku, categoria, qtd, valor_bruto, valor_liquido, desconto, custo, margem
- **Cupom** (derivado): loja, data_hora, cliente_id?, nº de itens, valor total
- **Cliente** (quando há fidelidade/identificação): id, atributos, histórico
- **Agregados (gold / views materializadas):** rollups por dia × loja ×
  categoria (× SKU opcional), com chaves de calendário duplo, KPIs e comparações
  pré-calculados — fonte dos dashboards
- **Trade Area (zona)**: loja, tipo (primária/secundária/terciária), geometria
  (anel ou isócrona), população/domicílios/renda agregados, consumo potencial
- **Concorrente**: nome, tipo, **endereço + lat/long**, data de abertura, origem
  (manual/importado), lojas e zonas afetadas
- **Impacto Externo (calculado)**: loja, fator (concorrente/clima/feriado/inflação), período, efeito estimado
- **Comparação (materializada)**: entidade, período, base (YoY/MoM/semana/dia),
  valor bruto, valor ajustado por calendário
- **Venda** (fato): data, loja, sku, qtd, valor bruto/líquido, custo, margem
- **Descoberta**: respostas da entrevista + documento de expectativas
- **Direção Estratégica**: propósito, valores, visão, objetivo de longo prazo
- **SWOT / Radar de Maturidade**: itens e notas por área
- **Meta (OKR)**: objetivo, resultados-chave, período, responsável, nível
- **Iniciativa / Ação (5W2H)**: meta de origem, os 7 campos, responsável, prazo, status
- **KPI (medição)**: valor realizado, tipo (leading/lagging/saúde/risco), farol
- **Ciclo de correção**: desvio de origem, fato, causa, ação, resultado da ação
- **Forecast**: entidade, período, valor previsto, versão, intervalo de confiança
- **Rotina**: tipo, cadência, participantes, pauta, decisões
- **Usuário / Papel**: nível de acesso e recorte de visibilidade

---

## 6. Arquitetura técnica (proposta)

- **Multi-tenancy:** modelo **pooled** (banco único, todas as tabelas com
  `tenant_id` + Row-Level Security do Postgres) como default — simples de operar
  e escalar para muitos clientes pequenos/médios. Opção de **schema isolado** ou
  **banco dedicado** para um cliente grande que exija isolamento forte.
  - Toda query passa por um middleware que injeta o `tenant_id` da sessão; RLS no
    banco é a rede de segurança contra vazamento entre clientes.
- **Três superfícies:** (1) **app do cliente** (multi-tenant), (2) **painel
  super-admin** (plataforma), (3) **site de produto** (público). Ver [SITE-PRODUTO.md](SITE-PRODUTO.md).
- **Frontend:** app web (React), dashboards responsivos, painel estratégico 1 página.
- **Backend/API:** Python (bom para dados/ML) ou Node.
- **Dados:** Postgres para começar (com **PostGIS** para geolocalização de lojas,
  zonas de trade area e concorrentes); evoluir para OLAP conforme o volume.
- **Geo/enriquecimento:** serviço de geocodificação + enriquecimento IBGE/POI,
  com cache regional compartilhado entre tenants.
- **Forecast/ML:** serviço dedicado de previsão (série temporal + calendário).
- **IA/LLM:** camada de insights (BoardOS Advisor) usando os modelos Claude mais
  recentes, recebendo os dados **do tenant** (nunca cruzando tenants) como contexto.
- **Auth:** login com organização (tenant) + RBAC + row-level por nível.
  Cada usuário pertence a um tenant; super-admins vivem fora dos tenants.
- **Billing:** gateway externo (Stripe/Iugu/Asaas) via webhook; o app só reflete
  o status da assinatura.

> Decisões finais dependem de: volume de dados, nuvem vs. on-prem, exigência de
> isolamento por cliente e restrições de TI (seção 8).

---

## 7. Roadmap por fases

### Fase 0 — Fundação (multi-tenant + dados)
Multi-tenancy desde o dia 1 (`tenant_id` + RLS), auth com organização, papéis.
Modelo canônico + ingestão CSV/Excel com mapeador. Warehouse bronze→silver→gold.
Cadastro mínimo de tenant (mesmo que manual) para rodar o primeiro cliente.

### Fase 1 — MVP: Descobrir e ver a verdade
- **Entrevista de Descoberta** (captura de expectativas) + Direção Estratégica.
- Diagnóstico (SWOT + Radar de Maturidade 360).
- Metas (OKRs) com desdobramento + dashboards de KPIs por nível + faróis +
  painel estratégico 1 página.
- **Motor de Comparação Temporal com ajuste de calendário** (3.12): YoY, MoM,
  semana do ano, dia do mês, mesmo dia da semana + normalização por composição
  de dias — presente desde o MVP (é o que dá confiança ao número).
- Cadastro de **feriados e sazonalidade** (3.13) — base de calendário.

### Fase 2 — Executar e controlar
- Plano de Ação 5W2H + gestão de iniciativas/ações.
- Ciclo Fato→Causa→Ação + rotinas (diária/semanal/mensal/trimestral) + alertas.
- Plano vs. Realizado.

### Fase 3 — Prever e recomendar
- **Forecast sempre à frente** por loja/categoria + re-forecast contínuo.
- **Fatores externos** (3.13): concorrência (lojas afetadas), inflação
  (venda real vs. deflacionada), clima/tempo — como features do forecast e
  contexto do Advisor.
- **Inteligência de mercado geo** (3.14): geocodificação da loja + enriquecimento
  IBGE, trade area (zonas primária/secundária/terciária), mapa de concorrentes e
  importação de POIs.
- Recomendações de ajuste de rota priorizadas por impacto.

> Geocodificação básica da loja (lat/long + município) pode entrar já na Fase 1
> junto ao cadastro; o enriquecimento IBGE/trade area/POI é o aprofundamento da 3.

### Fase 4 — IA no centro (BoardOS Advisor)
- Insights narrativos + explicação de desvios.
- "Converse com seus dados" + resumos executivos automáticos.

### Fase 5 — Comercialização (admin + billing + site)
- **Painel Super-Admin** (3.11): cadastro self-service de clientes, onboarding.
- **Billing** integrado a gateway (planos, trial, assinatura, faturas).
- **Site de produto** publicado com captura de leads / início de trial
  (ver [SITE-PRODUTO.md](SITE-PRODUTO.md)).

### Fase 6 — Integração, inovação e escala
- Conectores diretos ao ERP (SAP/TOTVS/Linx).
- Módulo de Inovação (canvas + MVPs). Multi-rede, benchmarking entre lojas.

> Nota: o **painel admin básico** (cadastrar tenant manualmente) já existe desde
> a Fase 0 para operar os primeiros clientes; a Fase 5 o torna self-service e
> comercial. Billing pode ser adiantado se a venda começar antes.

---

## 8. Riscos e decisões em aberto

| # | Questão | Impacto |
|---|---------|---------|
| 1 | Nuvem vs. on-premises? | Stack, segurança, custo |
| 2 | Volume de dados (nº lojas, SKUs, histórico) | Escolha do warehouse |
| 3 | Qual(is) ERP(s) integrar primeiro | Esforço dos conectores |
| 4 | ✅ Grão = cupom/item (decidido). Falta confirmar se cada ERP exporta nesse nível | Profundidade de KPI e forecast |
| 5 | LGPD / dados de clientes | Governança e anonimização |
| 6 | BI atual a substituir/conviver? | Escopo e integração |
| 7 | Isolamento por tenant (pooled vs. schema vs. banco) | Segurança, custo, complexidade |
| 8 | Preço: base mínima + por registro de venda (v0). Definir valores. | Billing, margem, go-to-market |
| 9 | Gateway de pagamento (Stripe/Iugu/Asaas) e emissão de NF | Billing e fiscal |
| 10 | Trial self-service vs. venda assistida (onboarding) | Site, funil e esforço de suporte |
| 11 | Fonte de clima/tempo (API meteorológica) e de inflação (IPCA/setorial) | Custo, cobertura regional, forecast |
| 12 | Metodologia de impacto de concorrente (janela antes/depois, raio) | Confiabilidade do alerta |
| 13 | Calendário de varejo: ISO week (default) vs. 4-4-5 por tenant | Precisão da comparação de demanda |
| 14 | Fonte de geocodificação e POI (Google Places vs. OSM vs. Receita/CNPJ) | Custo, cobertura, qualidade dos concorrentes |

---

## 9. Próximo passo sugerido

Com o método definido, o próximo passo é **detalhar o escopo da Fase 1 (MVP)**:
o roteiro da Entrevista de Descoberta, as telas de Direção + Diagnóstico +
Metas + Painel Estratégico, a biblioteca inicial de KPIs de varejo e o formato
esperado do arquivo de vendas (para o mapeador da seção 4).

Se você me disser qual ERP/formato de dados a primeira rede usa, aterrisso o
modelo canônico e o MVP nesse caso concreto.
