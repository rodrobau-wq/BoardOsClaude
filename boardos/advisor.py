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
