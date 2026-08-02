"""Entrevista de Descoberta — roteiro (fonte única) e resumo de fallback.

O roteiro segue ROTEIRO-ENTREVISTA.md: Bloco A (o negócio) + Bloco B
(expectativas do plano). A API serve as perguntas ao painel; as respostas ficam
em `descoberta.respostas` (jsonb) e o resumo da Etapa 3 é gerado pela IA
(boardos/advisor.py) com este fallback de template quando não houver chave.
"""
from __future__ import annotations

from typing import Dict, List

PERGUNTAS: List[Dict] = [
    # Bloco A — o negócio
    {"k": "A1", "bloco": "A", "q": "Qual é o nome da rede e há quanto tempo existe?"},
    {"k": "A2", "bloco": "A", "q": "Quantas lojas você tem e onde ficam (cidade/região/formato)?"},
    {"k": "A3", "bloco": "A", "q": "Que tipo de supermercado é (vizinhança, atacarejo, premium, hiper)?"},
    {"k": "A4", "bloco": "A", "q": "Quem é o cliente ideal da rede (perfil, renda, hábito de compra)?"},
    {"k": "A5", "bloco": "A", "q": "Qual problema real você resolve melhor que o concorrente da esquina?"},
    {"k": "A6", "bloco": "A", "q": "Como você ganha dinheiro hoje (mix de margem por seção, serviços, marca própria)?"},
    {"k": "A7", "bloco": "A", "q": "Qual o faturamento aproximado (mês ou ano) e o ticket médio?"},
    {"k": "A8", "bloco": "A", "q": "Qual sua visão para a rede em 3–5 anos?"},
    # Bloco B — expectativas do plano (núcleo do BoardOS)
    {"k": "B1", "bloco": "B", "q": "Quais metas você PRECISA bater neste ano? (número e prazo)"},
    {"k": "B2", "bloco": "B", "q": "Qual é o maior gargalo que trava a rede hoje?"},
    {"k": "B3", "bloco": "B", "q": "O que 'sucesso' significa para você daqui a 12 meses?"},
    {"k": "B4", "bloco": "B", "q": "Que decisões você quer que o BoardOS te ajude a tomar?"},
    {"k": "B5", "bloco": "B", "q": "Quais indicadores você já acompanha (e confia)?"},
    {"k": "B6", "bloco": "B", "q": "Como as decisões são tomadas hoje — no dado ou no feeling?"},
    {"k": "B7", "bloco": "B", "q": "Quem vai usar o BoardOS e em que nível (você, diretores, gerentes)?"},
    {"k": "B8", "bloco": "B", "q": "Qual a cadência de acompanhamento que faz sentido (diária/semanal/mensal)?"},
    {"k": "B9", "bloco": "B", "q": "Onde estão os dados de venda e em que formato (ERP, exportação, planilha)?"},
]

OBRIGATORIAS = ("B1", "B2", "B3", "B4")


def resumo_fallback(respostas: Dict[str, str]) -> str:
    """Documento da Etapa 3 sem IA: organiza as respostas num template claro."""
    def r(k: str) -> str:
        return (respostas.get(k) or "—").strip()

    return (
        "RESUMO EXECUTIVO\n"
        f"{r('A1')}. {r('A2')}. Formato: {r('A3')}.\n\n"
        "O QUE A REDE FAZ\n"
        f"{r('A3')} atendendo {r('A4')}.\n\n"
        "PROBLEMA QUE RESOLVE\n"
        f"{r('A5')}\n\n"
        "COMO GANHA DINHEIRO\n"
        f"{r('A6')}\n\n"
        "PORTE E VISÃO\n"
        f"Faturamento/ticket: {r('A7')}. Visão 3–5 anos: {r('A8')}.\n\n"
        "EXPECTATIVAS DO PLANO ESTRATÉGICO\n"
        f"- Metas do ano: {r('B1')}\n"
        f"- Maior gargalo: {r('B2')}\n"
        f"- Sucesso em 12 meses: {r('B3')}\n"
        f"- Decisões a apoiar: {r('B4')}\n"
        f"- KPIs acompanhados: {r('B5')}\n"
        f"- Cultura de decisão: {r('B6')}\n"
        f"- Usuários e níveis: {r('B7')}\n"
        f"- Cadência: {r('B8')}\n"
        f"- Fonte dos dados: {r('B9')}\n"
    )
