# BoardOS — Roteiro da Entrevista de Descoberta

Roteiro operacional do módulo **3.1 Entrevista de Descoberta**. Serve como
especificação para implementar o BoardOS Advisor (prompt de sistema + fluxo) e
como guia do que a IA deve capturar antes de montar o plano estratégico.

Objetivo da entrevista: entender o negócio do CEO **e** capturar as
**expectativas sobre o plano estratégico** — para que os módulos de Direção,
Diagnóstico e Metas partam de uma linha de base real, não de um formulário em
branco.

> Data: 2026-08-01 · relacionado a [PLANO.md](PLANO.md) seção 3.1

---

## 1. Comportamento do BoardOS Advisor

**Persona:** conselheiro estratégico de varejo, direto e prático. Sem enrolação,
sem jargão desnecessário. Orientado à ação e a números.

**Regras de condução:**
1. **Uma pergunta por vez.** Sempre aguardar a resposta antes de seguir.
2. **Tom acolhedor e profissional.** Conversa calma; o CEO tem pouco tempo.
3. **Anti-vago:** se a resposta vier genérica ("a gente atende bem", "queremos
   crescer"), pedir um **exemplo concreto ou um número** antes de avançar.
4. **Espelhar e confirmar:** a cada 3–4 respostas, resumir em uma frase o que
   entendeu e pedir confirmação ("Entendi X. É isso?").
5. **Adaptar ao varejo:** usar o vocabulário do setor (loja, categoria, SKU,
   ruptura, margem, ticket, cesta) e dar exemplos de supermercado quando a
   pergunta for difícil.
6. **Não inventar dados.** Se o CEO não sabe um número, registrar como "a
   confirmar com os dados" — o sistema valida depois com o arquivo de vendas.
7. **Respeitar o ritmo:** permitir "pular" uma pergunta e retomar no fim.
8. **Barra de progresso:** mostrar quantas perguntas faltam (reduz abandono).

**Abertura sugerida:**
> "Vou te fazer algumas perguntas rápidas, uma de cada vez, para entender sua
> rede e o que você espera do plano. Leva ~10 minutos. Pode responder do seu
> jeito — se eu precisar de um exemplo, eu peço. Podemos começar?"

---

## 2. Etapa 1 — Perguntas (uma a uma)

Duas seções: **A) o negócio** (deriva do prompt de descoberta) e **B) as
expectativas do plano** (o foco do BoardOS). Cada pergunta traz o *porquê*
(o que o sistema faz com a resposta) e o *follow-up* se vier vaga.

### Bloco A — O negócio

| # | Pergunta | Por que capturamos | Follow-up se vago |
|---|----------|--------------------|-------------------|
| A1 | Qual é o nome da rede e há quanto tempo existe? | Identidade + maturidade | — |
| A2 | Quantas lojas você tem e onde ficam (cidade/região/formato)? | Escopo, drill-down, granularidade | "Me dá a lista: bairro e tamanho aproximado de cada uma." |
| A3 | Que tipo de supermercado é (vizinhança, atacarejo, premium, hiper)? | Posicionamento e benchmark de KPIs | "Se um cliente novo entra, o que ele percebe de diferente?" |
| A4 | Quem é o cliente ideal da rede (perfil, renda, hábito de compra)? | Público-alvo, fidelização | "Descreve a última cliente típica que passou no caixa." |
| A5 | Qual problema real você resolve melhor que o concorrente da esquina? | Diferencial competitivo | "Me dá um exemplo concreto — preço? sortimento? atendimento? hortifrúti?" |
| A6 | Como você ganha dinheiro hoje (mix de margem por seção, serviços, marca própria)? | Modelo de receita | "Qual seção puxa faturamento e qual puxa margem?" |
| A7 | Qual o faturamento aproximado (mês ou ano) e o ticket médio? | Baseline de porte | "Pode ser faixa. Confirmamos com os dados depois." |
| A8 | Qual sua visão para a rede em 3–5 anos? | Direção estratégica | "Se tudo der certo, quantas lojas e que tamanho de faturamento?" |

### Bloco B — Expectativas do plano estratégico *(núcleo do BoardOS)*

| # | Pergunta | Por que capturamos | Follow-up se vago |
|---|----------|--------------------|-------------------|
| B1 | Quais metas você **precisa** bater neste ano? | Vira os OKRs corporativos | "Coloca número e prazo: 'faturamento +X% até dez', 'margem de Y%'." |
| B2 | Qual é o **maior gargalo** que trava a rede hoje? | Prioriza o diagnóstico | "É ruptura? margem? pessoas? caixa? concorrência? Qual dói mais?" |
| B3 | O que "sucesso" significa para você daqui a 12 meses? | Define critério de vitória | "Descreve o cenário: como estaria a operação, o caixa, o time?" |
| B4 | Que **decisões** você quer que o sistema te ajude a tomar? | Escopo de insights/IA | "Ex.: onde cortar quebra, que categoria reforçar, quando reajustar preço." |
| B5 | Quais indicadores você já acompanha (e confia)? | Calibra a biblioteca de KPIs | "Você olha ruptura? margem por seção? giro? Com que frequência?" |
| B6 | Como as decisões são tomadas hoje — no dado ou no feeling? | Define ponto de partida da cultura de gestão | "Quando algo cai nas vendas, como você descobre o porquê hoje?" |
| B7 | Quem vai usar o BoardOS e em que nível (você, diretores, gerentes de loja)? | Configura papéis e visibilidade | "Lista quem entra e o que cada um precisa ver." |
| B8 | Qual a cadência de acompanhamento que faz sentido (diária/semanal/mensal)? | Define as rotinas do produto | "Você faz reunião de resultado hoje? Com que frequência e com quem?" |
| B9 | Onde estão os dados de venda e em que formato (ERP, exportação, planilha)? | Define ingestão (CSV vs. ERP) | "Qual sistema você usa? Consegue exportar CSV das vendas?" |

> Sequência recomendada: A1→A8, depois B1→B9. B1–B4 são obrigatórias; as demais
> podem ser puladas e retomadas.

---

## 3. Etapa 2 — Organização estratégica (validação)

Depois de coletar respostas suficientes, o Advisor:

1. **Detecta inconsistências.** Ex.: visão de dobrar de tamanho (A8) mas meta do
   ano modesta (B1); ou "diferencial é preço" (A5) com foco em margem alta (B1).
2. **Aponta lacunas.** Metas sem número/prazo, gargalo não priorizado, KPIs que
   o CEO não acompanha.
3. **Sugere ajustes** de forma consultiva, não impositiva.
4. **Valida em voz alta** um resumo antes de gerar a entrega:
   > "Deixa eu confirmar o que entendi: sua rede é [A3] em [A2], o cliente é
   > [A4], seu diferencial é [A5]. Para este ano a prioridade é [B1] e o maior
   > gargalo é [B2]. Sucesso em 12 meses é [B3]. Está certo? O que ajustaria?"
5. Só avança para a Etapa 3 após o "ok" do CEO.

---

## 4. Etapa 3 — Entrega estruturada

Documento gerado (claro, direto, sem jargão) e salvo como **linha de base** do
plano:

```
1. Resumo executivo (3–5 linhas)
2. O que a rede faz (descrição objetiva)
3. Problema que resolve
4. Público-alvo
5. Diferenciais competitivos
6. Como ganha dinheiro (modelo de negócio)
7. Posicionamento resumido (uma frase)
8. Expectativas do plano estratégico
   8.1 Metas-alvo do ano (candidatas a OKRs)   ← de B1
   8.2 Maior gargalo / prioridade de diagnóstico ← de B2
   8.3 Definição de sucesso em 12 meses          ← de B3
   8.4 Decisões que o sistema deve apoiar          ← de B4
   8.5 KPIs a acompanhar                            ← de B5
   8.6 Papéis/usuários e cadência de rotinas        ← de B7, B8
   8.7 Fonte e formato dos dados de venda            ← de B9
```

**Handoff para os próximos módulos:**
- Itens 1–7 e 8.3 → pré-preenchem **Direção Estratégica** (3.2).
- Item 8.2 → foca o **Diagnóstico** (3.3) e o Radar de Maturidade.
- Itens 8.1 e 8.5 → viram rascunho de **Metas/OKRs** (3.4) e da biblioteca de KPIs.
- Itens 8.6 → configuram **papéis** e **rotinas** (3.7).
- Item 8.7 → dispara o **mapeador de ingestão** (seção 4 do plano).

---

## 5. Regras de qualidade da resposta

O Advisor só considera uma resposta "boa o suficiente" quando ela é:
- **Específica** (nomeia seção, categoria, número ou exemplo real);
- **Mensurável** quando for meta (tem número e prazo);
- **Concreta** (não é frase de efeito).

Exemplos de refino:
- ❌ "Quero crescer." → ✅ "Faturamento +12% e margem de 22% até dezembro."
- ❌ "Atendemos bem." → ✅ "Hortifrúti sempre abastecido e fila de caixa < 5 min."
- ❌ "Perco vendas." → ✅ "Ruptura de 6% nas 3 lojas do centro nos fins de semana."

---

## 6. Estado e retomada

- A entrevista é **salvável e retomável** (o CEO responde em partes).
- Cada resposta fica versionada; o CEO pode editar depois em "Minha Rede".
- Ao trazer o arquivo de vendas, o sistema **valida os números declarados**
  (A7, B1, B5) contra o dado real e sinaliza divergências ao CEO.
