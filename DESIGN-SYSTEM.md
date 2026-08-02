# BoardOS — Design System (v0)

Tokens e componentes **colhidos do protótipo** ([prototipo-painel.html](prototipo-painel.html)), não
inventados no vácuo. É o ponto de partida visual do produto: enxuto, focado em
UI de dados (dashboard operado, não documento lido).

> Data: 2026-08-01 · relacionado a [ESCOPO-TELAS-MVP.md](ESCOPO-TELAS-MVP.md)

---

## 1. Princípios

- **Ferramenta de informação, não peça editorial.** Resumo antes do detalhe;
  estado codificado em forma (pílula, farol, chip), não só em número.
- **Cor semântica ≠ cor de marca.** O accent (azul) é identidade e ação; os
  faróis (verde/âmbar/vermelho) são **estado** e nunca viram "série 4".
- **Faróis sempre com rótulo/ícone** — nunca cor sozinha (daltonismo).
- **Neutros escolhidos** com leve viés frio (azul), não cinza puro.
- **Dois temas com o mesmo cuidado**; tokens em `:root`, sobrescritos por
  `@media (prefers-color-scheme)` e por `:root[data-theme=…]`.
- **Tabular-nums** em toda coluna de número.

---

## 2. Cor (tokens)

### Light
| Token | Hex | Uso |
|-------|-----|-----|
| `--ground` | `#F5F7FC` | fundo da app |
| `--surface` | `#FFFFFF` | cards |
| `--surface-2` | `#FAFBFE` | fundos sutis, hover |
| `--ink` | `#0F1B2D` | texto principal |
| `--ink-2` | `#33425C` | texto secundário |
| `--muted` | `#5B6B85` | rótulos, legendas |
| `--faint` | `#8A97AE` | captions, eixos |
| `--border` | `#E4E9F3` | hairlines |
| `--border-strong` | `#D3DAE8` | hover de borda |
| `--accent` | `#2D5BE3` | marca, ação, série principal |
| `--accent-strong` | `#1E3F9E` | títulos de marca, texto sobre soft |
| `--accent-soft` | `#EAF0FD` | fundo de estado ativo/seleção |
| `--good` | `#12855A` | farol verde (estado) |
| `--warn` | `#B5790A` | farol âmbar |
| `--crit` | `#CB3A50` | farol vermelho |
| `--good/warn/crit-soft` | `#E4F4EC` / `#FBF1DC` / `#FBE7EB` | fundos de chip/alerta |
| `--grid` | `#EEF1F8` | linhas de grade do gráfico |
| `--prioryr` | `#9AA6BD` | linha "ano anterior" (neutro) |

### Dark (steps próprios, não inversão)
`--ground #0A0E16` · `--surface #141B27` · `--surface-2 #111824` · `--ink #E9EEF8`
· `--ink-2 #C4CEDF` · `--muted #8B9AB5` · `--faint #66748E` · `--border #232D3E`
· `--border-strong #2E3A4E` · `--accent #5A86F5` · `--accent-strong #7EA0F8`
· `--accent-soft #182338` · `--good #3CB983` · `--warn #E0A93A` · `--crit #F0697F`
· `--grid #1D2634` · `--prioryr #61708B`.

> Regra: componentes leem **tokens**, nunca hex direto nem cor dentro da media
> query. Trocar de tema = trocar tokens.

---

## 3. Tipografia

- **Sem webfont** (CSP bloqueia CDN; embutir face em base64 é pesado e arriscado
  de fallback silencioso). Stack de sistema, escolha deliberada para tool de dados:
  - UI: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`
  - Números/mono (opcional): `ui-monospace, "SF Mono", Menlo, monospace`
- **Escala:** 11 (caption) · 12 (label) · 13.5 (corpo/UI) · 14.5 (título de card)
  · 16 (título de tela) · 27 (valor de KPI). `font-variant-numeric: tabular-nums`
  em todo número; labels em maiúscula com `letter-spacing:.3–.4px`.
- Títulos com `text-wrap: balance`; corpo perto de 65ch.

---

## 4. Forma e espaço

- **Raios:** 7 (chip/segment) · 9 (botão/controle) · 14 (card).
- **Sombra:** `--shadow` (dupla, sutil) nos cards/controles elevados.
- **Espaçamento:** grid/flex com `gap` (14 entre KPIs, 18 entre blocos, 16–17
  padding de card). Nada de margin per-elemento que colapsa.
- **Overflow:** conteúdo largo (tabela, gráfico) rola no próprio container
  (`overflow-x:auto`); body nunca rola lateralmente.

---

## 5. Inventário de componentes (do protótipo)

| Componente | Papel | Notas |
|-----------|-------|-------|
| **App shell** | sidebar + topbar + main | sidebar sticky; topbar sticky com blur |
| **Nav item** | navegação | estados hover/active (`--accent-soft`), foco visível |
| **Seletor (escopo/período)** | filtro global | rótulo maiúsculo + valor; no topo |
| **Segmented Civil↔Varejo** | toggle da lente de calendário | `aria-pressed`, estado `on` elevado |
| **KPI Card** | valor + meta + variação + farol | valor 27px; chip up/down; farol com rótulo |
| **Farol / Pílula** | estado (verde/âmbar/vermelho) | `led` + texto; direção correta (maior/menor é melhor) |
| **Chip de variação** | delta vs. período | up/down/flat com cor semântica + seta |
| **Card** | contêiner padrão | header (título + sub) + body |
| **Gráfico de linha/área** | série no tempo | área do atual, ano ant. tracejado, projeção tracejada, marcador "hoje", crosshair+tooltip |
| **Barra de OKR** | progresso de meta | barra + % + meta + pílula de status |
| **Bloco Advisor** | insight IA | avatar ✦ + texto + estrutura Fato/Causa/Ação |
| **Alerta** | desvio no vermelho/âmbar | ícone + título + descrição, fundo soft |
| **Tabela de indicadores** | KPIs por loja/categoria | 1ª coluna sticky, números à direita, pílula de status |
| **Tooltip de gráfico** | leitura de ponto | swatch + valor tabular |
| **Estados** | vazio / carregando / indisponível | empty guia próxima ação; skeleton; "indisponível" com pré-requisito |

---

## 6. Regras de gráfico (herdadas do dataviz)

- Série principal = `--accent`; **ano anterior** = `--prioryr` (neutro,
  tracejado); **projeção** = accent tracejado leve. Distinção por **estilo +
  matiz neutro**, não por cores concorrentes.
- Grade recessiva (`--grid`), eixos discretos, endpoint enfatizado.
- Sempre **hover** (crosshair + tooltip) em linha/área.
- Legenda presente quando ≥2 séries; rótulos diretos seletivos (nunca número em
  todo ponto).
- Texto do gráfico usa tokens de tinta, nunca a cor da série.

---

## 7. Acessibilidade e robustez

- Foco de teclado sempre visível (`:focus-visible` com outline accent).
- `prefers-reduced-motion`: desliga transições.
- Faróis/pílulas com texto (não cor sozinha); tabela alternativa aos gráficos.
- Contraste legível nos dois temas; accent funciona sobre os dois fundos.

---

## 8. Como evoluir

Este v0 cobre o MVP. Quando entrar **marca própria** (logo, cor definitiva),
trocam-se os tokens `--accent*` e reavalia-se a paleta com o validador do
dataviz (rodar `scripts/validate_palette.js` nos faróis + accent). Estrutura,
componentes e regras permanecem.
