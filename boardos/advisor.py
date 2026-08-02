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
