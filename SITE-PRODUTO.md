# BoardOS — Site de Produto (Marketing)

Plano do site público que apresenta o BoardOS e converte redes de supermercado
em clientes (trial ou contato comercial). Terceira superfície da plataforma, ao
lado do app do cliente e do painel super-admin.

> Data: 2026-08-01 · relacionado a [PLANO.md](PLANO.md)

---

## 1. Objetivo e público

- **Objetivo primário:** gerar leads qualificados (CEOs/donos de rede) e iniciar
  **trial** ou **agendamento de demonstração**.
- **Público:** dono/CEO de rede de supermercado (1–50 lojas), diretor comercial,
  gerente de TI que avalia a ferramenta.
- **Métrica de sucesso do site:** visitantes → leads (form/trial) → demos
  agendadas. Rastrear conversão por seção e por origem de tráfego.

---

## 2. Mensagem central (posicionamento)

> **BoardOS — do plano à execução, com os seus dados de venda.**
> O sistema de gestão estratégica para CEOs de supermercado: define as metas,
> lê suas vendas, mostra onde está o desvio e recomenda a ação — com um
> conselheiro de IA que fala a língua do varejo.

Dores que o site ataca (linguagem do CEO):
- "Tenho relatório, mas não sei o que fazer com ele."
- "Descubro o problema tarde demais."
- "O plano do ano fica na gaveta."
- "Cada loja puxa para um lado."

---

## 3. Estrutura das páginas

### 3.1 Home (landing principal)
1. **Hero:** headline + subheadline + CTA duplo ("Começar trial" / "Agendar demo")
   + visual do painel estratégico.
2. **Problema → Solução:** 3–4 dores do CEO e como o BoardOS resolve.
3. **Como funciona (o ciclo):** Descoberta → Direção → Diagnóstico → Metas →
   Plano de Ação → Execução (Fato→Causa→Ação). Visual do loop.
4. **Recursos-chave (blocos):** Entrevista de Descoberta com IA · Painel
   Estratégico 1 página · KPIs de varejo com faróis · Forecast e ajuste de rota ·
   BoardOS Advisor (insights) · Multi-loja com drill-down.
5. **Feito para varejo alimentar:** ruptura, margem por seção, giro, quebra,
   ticket/cesta — fala o vocabulário do setor.
6. **Prova social:** logos/depoimentos (quando houver) ou "case piloto".
7. **Segurança e dados:** LGPD, isolamento por cliente, seus dados são seus.
8. **Planos (resumo):** faixas por nº de lojas + CTA para preço/contato.
9. **CTA final + rodapé.**

### 3.2 Página "Como funciona" / Produto
Detalha cada módulo com screenshots e o benefício de negócio (não só feature).

### 3.3 Página "Preços"
Planos por porte (ex.: até 3 lojas / até 10 / rede+), o que cada um inclui,
trial gratuito e CTA. Preço pode ser "sob consulta" no início (venda assistida).

### 3.4 Página "Para quem é" / Segmentos
Vizinhança, atacarejo, rede regional — como o BoardOS se ajusta a cada formato.

### 3.5 Blog / Conteúdo (SEO)
Artigos que atraem o CEO por busca: "como reduzir ruptura", "margem por seção",
"planejamento estratégico de supermercado", "o que é GMROI". Alimenta tráfego
orgânico e autoridade.

### 3.6 Páginas de conversão e legais
- **Trial / Cadastro:** cria o lead e (quando self-service) dispara o
  provisionamento de um tenant de teste.
- **Agendar demo:** formulário → calendário.
- **Contato**, **Sobre**, **Política de Privacidade / LGPD**, **Termos de Uso**.

---

## 4. Fluxos de conversão

- **Trial self-service (fase madura):** form → cria tenant trial → onboarding
  guiado (Entrevista de Descoberta) dentro do app. Liga com o Painel Super-Admin
  ([PLANO.md](PLANO.md) 3.11).
- **Venda assistida (início):** form/demo → lead cai no CRM → time BoardOS faz
  onboarding manual (cadastra o tenant no painel admin).
- **Captura de lead:** todo CTA registra origem (UTM) para medir canais.

---

## 5. Arquitetura técnica do site

- **Separado do app** (domínio raiz `boardos.com`; app em `app.boardos.com`;
  admin em `admin.boardos.com`).
- **Site estático/SSR** (ex.: Next.js ou gerador estático + CMS headless para o
  blog) — rápido, bom para SEO, fácil de editar conteúdo sem deploy.
- **Formulários** → backend de leads/CRM + e-mail de notificação.
- **Analytics** de produto e marketing (privacidade-first, LGPD).
- **SEO técnico:** meta tags, sitemap, performance, mobile-first.

---

## 6. Escopo por fase

- **V1 (junto com a comercialização):** Home + Preços + Trial/Demo + Contato +
  páginas legais. Foco em converter, não em volume de conteúdo.
- **V2:** Blog/SEO, páginas de segmento, casos de sucesso, trial self-service
  integrado ao provisionamento de tenant.

---

## 7. Decisões em aberto (herda de [PLANO.md](PLANO.md) seção 8)

- Modelo de preço a exibir (por loja / usuário / faixa) — itens 8–10 dos riscos.
- Trial self-service vs. venda assistida define quanto do fluxo é automatizado.
- Nome de domínio e identidade visual (marca BoardOS).
