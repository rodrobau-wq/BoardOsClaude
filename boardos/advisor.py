"""BoardOS Advisor — insights com IA (Claude) e fallback estatístico.

Gera a análise executiva do tenant a partir dos números reais (comparação YoY,
lojas, metas, alertas). Sem ANTHROPIC_API_KEY (ou em qualquer erro), retorna
None e o painel continua com a narrativa do motor estatístico — a IA é um
upgrade, nunca um ponto único de falha.
"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, Optional

try:
    import anthropic
except ImportError:  # dependência de runtime; ausente em dev sem pip install
    anthropic = None

MODEL = "claude-opus-5"
_TTL_SEGUNDOS = 3600  # cache por tenant/mês — evita custo/latência a cada load
_cache: Dict[str, tuple] = {}

SYSTEM = """Você é o BoardOS Advisor, conselheiro estratégico de CEOs de supermercado.

Estilo: direto, prático, sem enrolação, em português do Brasil. Sempre cite os
números que embasam cada conclusão. Você fala com o CEO — vocabulário de varejo
(loja, categoria, ruptura, ticket, margem), sem jargão de dados.

Conceito central do BoardOS: o CALENDÁRIO DUPLO. A lente CIVIL (mês-calendário)
mede o dinheiro/fechamento; a lente VAREJO (semanas alinhadas, ajustada pela
composição de dias da semana) mede a demanda real. Quando as duas divergem,
explique o porquê (ex.: o mês trocou uma sexta por uma segunda).

Formato da resposta (texto puro, sem markdown de cabeçalho):
1) Um parágrafo curto com a leitura executiva do mês (o que importa).
2) Linhas "Fato:", "Causa:" e "Ação:" — uma frase cada, concretas.
3) Se houver metas fora da rota ou lojas em queda real, aponte a prioridade nº 1.
Máximo ~150 palavras. Nunca invente números que não estejam nos dados."""


def disponivel() -> bool:
    return anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))


def gerar_insight(contexto: Dict, cache_key: Optional[str] = None) -> Optional[str]:
    """Análise narrativa dos dados do tenant. None => usar fallback do motor."""
    if not disponivel():
        return None
    agora = time.time()
    if cache_key and cache_key in _cache:
        ts, texto = _cache[cache_key]
        if agora - ts < _TTL_SEGUNDOS:
            return texto
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            output_config={"effort": "low"},  # resumo curto; latência de UI importa
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": ("Dados reais do supermercado (JSON):\n"
                            + json.dumps(contexto, ensure_ascii=False, default=str)
                            + "\n\nGere a leitura executiva."),
            }],
        )
        if resp.stop_reason == "refusal":
            return None
        texto = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not texto:
            return None
        if cache_key:
            _cache[cache_key] = (agora, texto)
        return texto
    except Exception:
        return None  # qualquer falha => fallback estatístico silencioso


def _chamada(system: str, user_text: str, max_tokens: int = 1200) -> Optional[str]:
    """Chamada padrão ao modelo com fallback silencioso (None)."""
    if not disponivel():
        return None
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL, max_tokens=max_tokens,
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": user_text}],
        )
        if resp.stop_reason == "refusal":
            return None
        texto = "".join(b.text for b in resp.content if b.type == "text").strip()
        return texto or None
    except Exception:
        return None


SYSTEM_PERGUNTA = SYSTEM + """

O CEO vai fazer UMA pergunta sobre os dados. Responda só com base no JSON
fornecido; se o dado necessário não estiver lá, diga isso claramente e sugira
onde olhar. Resposta direta, máx. ~120 palavras."""

# Conselho BoardOS — perfis de conselheiro (persona muda a lente da resposta)
PERSONAS: Dict[str, Dict[str, str]] = {
    "estrategia": {
        "nome": "Conselheiro de Estratégia",
        "foco": "rota, metas e calendário duplo",
        "system": "Você responde como o Conselheiro de Estratégia: rota do ano, metas, "
                  "leitura civil × varejo e priorização. Pense como um chairman pragmático.",
    },
    "categorias": {
        "nome": "Conselheira de Categorias",
        "foco": "gerenciamento de categoria: mix, margem, espaço e planograma",
        "system": "Você responde como a Conselheira de Gerenciamento de Categoria: papel de "
                  "categoria (destino/rotina/conveniência), mix, precificação, planograma e "
                  "participação. Recomende ações de sortimento e espaço.",
    },
    "trade": {
        "nome": "Conselheiro de Trade & Indústria",
        "foco": "trade marketing, verbas e JBP com fornecedores",
        "system": "Você responde como o Conselheiro de Trade Marketing e Indústria: JBP "
                  "(Joint Business Plan), verbas, encarte, ponta de gôndola, calendário "
                  "promocional e negociação com fornecedores usando o sell-out da rede.",
    },
    "clientes": {
        "nome": "Conselheira de Clientes (CRM)",
        "foco": "fidelização, ticket, cesta e frequência",
        "system": "Você responde como a Conselheira de CRM e Fidelização: ticket, cesta, "
                  "frequência, identificação do cliente no cupom, segmentação e campanhas. "
                  "Se faltar identificação de cliente, oriente como ativar.",
    },
    "receitas": {
        "nome": "Conselheiro de Novas Receitas",
        "foco": "retail media e monetização de dados e espaços",
        "system": "Você responde como o Conselheiro de Novas Receitas: retail media (mídia "
                  "dentro da loja e no digital), monetização de dados de sell-out com a "
                  "indústria e espaços patrocinados. Use benchmarks de mercado com cautela e "
                  "sempre rotule estimativas como estimativas.",
    },
}


def responder_pergunta(contexto: Dict, pergunta: str,
                       persona: Optional[str] = None) -> Optional[str]:
    """2.2 — Converse com seus dados (opcionalmente na voz de um conselheiro)."""
    system = SYSTEM_PERGUNTA
    p = PERSONAS.get(persona or "")
    if p:
        system = system + "\n\n" + p["system"]
    return _chamada(
        system,
        ("Dados reais do supermercado (JSON):\n"
         + json.dumps(contexto, ensure_ascii=False, default=str)
         + f"\n\nPergunta do CEO: {pergunta}"))


SYSTEM_RESUMO_EXEC = SYSTEM + """

Gere o RESUMO EXECUTIVO do período para o board: 1 parágrafo de leitura geral,
depois blocos curtos "Destaques:", "Riscos:" e "Prioridades da semana:" (até 3
bullets cada, iniciados por "- "). Texto puro, máx. ~200 palavras."""


def resumo_executivo(contexto: Dict) -> Optional[str]:
    """2.3 — Briefing do board. None => IA indisponível."""
    return _chamada(
        SYSTEM_RESUMO_EXEC,
        ("Dados reais do supermercado (JSON):\n"
         + json.dumps(contexto, ensure_ascii=False, default=str)
         + "\n\nGere o resumo executivo."), max_tokens=1500)


SYSTEM_DESCOBERTA = """Você é o BoardOS Advisor. Um CEO de supermercado respondeu
à Entrevista de Descoberta. Gere o documento final em português do Brasil, claro
e direto, texto puro (títulos em MAIÚSCULAS, sem markdown), nesta estrutura:

RESUMO EXECUTIVO (3–5 linhas)
O QUE A REDE FAZ
PROBLEMA QUE RESOLVE
PÚBLICO-ALVO
DIFERENCIAIS COMPETITIVOS
COMO GANHA DINHEIRO
POSICIONAMENTO (uma frase)
EXPECTATIVAS DO PLANO ESTRATÉGICO (metas do ano, maior gargalo, sucesso em 12
meses, decisões a apoiar, KPIs, usuários e cadência, fonte dos dados)

Aponte inconsistências relevantes numa linha final "ATENÇÃO:" apenas se existirem.
Use somente o que foi respondido; não invente fatos nem números. Máx. ~250 palavras."""


def gerar_resumo_descoberta(perguntas_respostas: Dict) -> Optional[str]:
    """Documento da Etapa 3 via IA. None => usar o template de fallback."""
    if not disponivel():
        return None
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            output_config={"effort": "low"},
            system=SYSTEM_DESCOBERTA,
            messages=[{
                "role": "user",
                "content": ("Perguntas e respostas da entrevista (JSON):\n"
                            + json.dumps(perguntas_respostas, ensure_ascii=False)
                            + "\n\nGere o documento."),
            }],
        )
        if resp.stop_reason == "refusal":
            return None
        texto = "".join(b.text for b in resp.content if b.type == "text").strip()
        return texto or None
    except Exception:
        return None
