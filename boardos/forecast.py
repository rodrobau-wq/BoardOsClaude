"""Forecast de vendas — projeção do restante do mês (3.3).

Método baseline honesto: média de faturamento por dia-da-semana do histórico
recente (até ~8 semanas), projetada nos dias que faltam do mês. Respeita o
padrão semanal do varejo (sábado ≠ terça) — o mesmo fundamento do calendário
duplo. Funções puras, sem banco.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

DailyRecord = Dict  # {"data": date, "faturamento_liq": float}


def media_por_dow(historico: Sequence[DailyRecord]) -> Dict[int, float]:
    """Média de faturamento por dia-da-semana ISO (1=seg..7=dom)."""
    soma: Dict[int, float] = defaultdict(float)
    cnt: Dict[int, int] = defaultdict(int)
    for r in historico:
        w = r["data"].isoweekday()
        soma[w] += float(r["faturamento_liq"])
        cnt[w] += 1
    return {w: soma[w] / cnt[w] for w in soma if cnt[w]}


def prever_dias(historico: Sequence[DailyRecord], de: date, ate: date) -> List[Dict]:
    """Projeta um valor por dia em [de, ate] usando a média por dia-da-semana.

    Dias-da-semana sem histórico caem na média global; sem histórico algum,
    retorna lista vazia (não inventamos número).
    """
    medias = media_por_dow(historico)
    if not medias:
        return []
    media_global = sum(medias.values()) / len(medias)
    out: List[Dict] = []
    d = de
    while d <= ate:
        out.append({"data": d, "valor": round(medias.get(d.isoweekday(), media_global), 2)})
        d += timedelta(days=1)
    return out


def forecast_mes(historico: Sequence[DailyRecord], ano: int, mes: int,
                 cutoff: Optional[date] = None) -> Dict:
    """Projeção do mês: realizado até o cutoff + previsto até o fim do mês.

    historico: série diária (pode incluir semanas anteriores ao mês, para
    estabilizar a média por dia-da-semana). Só dias <= cutoff são usados.
    """
    ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
    primeiro = date(ano, mes, 1)
    if cutoff is None or cutoff > ultimo:
        cutoff = ultimo
    base = [r for r in historico if r["data"] <= cutoff]
    realizado = [
        {"data": r["data"], "valor": round(float(r["faturamento_liq"]), 2)}
        for r in base if primeiro <= r["data"] <= cutoff
    ]
    previsto = (prever_dias(base, cutoff + timedelta(days=1), ultimo)
                if cutoff < ultimo else [])
    total_realizado = round(sum(r["valor"] for r in realizado), 2)
    total_previsto = round(sum(p["valor"] for p in previsto), 2)
    return {
        "cutoff": cutoff,
        "realizado": realizado,
        "previsto": previsto,
        "total_realizado": total_realizado,
        "total_previsto": total_previsto,
        "total_projetado": round(total_realizado + total_previsto, 2),
    }
