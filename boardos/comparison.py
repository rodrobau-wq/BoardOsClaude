"""Motor de Comparação Temporal com ajuste de calendário (calendário duplo).

Opera sobre séries diárias (nível gold: uma linha por dia com faturamento etc.).
É independente de banco — funções puras — para ser testável e reutilizável tanto
pela API quanto pelos demos. Ver PLANO.md 3.12.

Conceito central: comparar dois períodos em duas lentes.
- CIVIL: soma bruta do período vs. soma bruta do período-base (mês-calendário).
- VAREJO (like-for-like): remove o efeito de COMPOSIÇÃO de dias da semana,
  projetando a performance/dia-da-semana do período-base sobre a composição do
  período atual. Assim, um mês que trocou uma sexta (dia forte) por uma segunda
  (dia fraco) não é lido como queda.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, List, Sequence

DOW_LABEL = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]  # index = isoweekday-1

# Uma linha diária mínima. `data` é date; `faturamento_liq` é o valor comparado.
DailyRecord = Dict


def _dow(d: date) -> int:
    return d.isoweekday()  # 1=seg ... 7=dom


def totals(records: Sequence[DailyRecord]) -> Dict[str, float]:
    fat = sum(r["faturamento_liq"] for r in records)
    cup = sum(r.get("cupons", 0) for r in records)
    itn = sum(r.get("itens", 0) for r in records)
    return {"faturamento": fat, "cupons": cup, "itens": itn}


def _weekday_means(records: Sequence[DailyRecord], field: str = "faturamento_liq") -> Dict[int, float]:
    soma: Dict[int, float] = defaultdict(float)
    cnt: Dict[int, int] = defaultdict(int)
    for r in records:
        w = _dow(r["data"])
        soma[w] += r.get(field, 0)
        cnt[w] += 1
    return {w: soma[w] / cnt[w] for w in soma if cnt[w]}


def _counts_by_dow(records: Sequence[DailyRecord]) -> Dict[int, int]:
    cnt: Dict[int, int] = defaultdict(int)
    for r in records:
        cnt[_dow(r["data"])] += 1
    return cnt


def compare(current: Sequence[DailyRecord], baseline: Sequence[DailyRecord]) -> Dict:
    """Compara `current` contra `baseline` nas duas lentes.

    Retorna dict com totais, variação civil (bruta) e variação ajustada por
    calendário (varejo), além da composição de dias da semana e dos dias que
    mudaram (para a explicação do Advisor).
    """
    tc = totals(current)
    tb = totals(baseline)

    means_b = _weekday_means(baseline)
    count_c = _counts_by_dow(current)
    count_b = _counts_by_dow(baseline)

    # baseline projetado na composição do período atual (remove efeito calendário)
    adjusted_baseline = sum(means_b.get(w, 0.0) * count_c.get(w, 0) for w in count_c)

    civil_var = (tc["faturamento"] - tb["faturamento"]) / tb["faturamento"] if tb["faturamento"] else 0.0
    adjusted_var = (tc["faturamento"] - adjusted_baseline) / adjusted_baseline if adjusted_baseline else 0.0

    composicao = {
        DOW_LABEL[w - 1]: {"atual": count_c.get(w, 0), "base": count_b.get(w, 0),
                           "delta": count_c.get(w, 0) - count_b.get(w, 0)}
        for w in range(1, 8)
    }
    ganhou = [lbl for lbl, c in composicao.items() if c["delta"] > 0]
    perdeu = [lbl for lbl, c in composicao.items() if c["delta"] < 0]

    return {
        "total_atual": round(tc["faturamento"], 2),
        "total_base": round(tb["faturamento"], 2),
        "baseline_ajustado": round(adjusted_baseline, 2),
        "var_civil": civil_var,
        "var_ajustada": adjusted_var,
        "efeito_calendario": adjusted_var - civil_var,
        "composicao": composicao,
        "dias_ganhos": ganhou,
        "dias_perdidos": perdeu,
        # ticket é razão: use somas para não enviesar
        "ticket_atual": round(tc["faturamento"] / tc["cupons"], 2) if tc["cupons"] else None,
        "ticket_base": round(tb["faturamento"] / tb["cupons"], 2) if tb["cupons"] else None,
    }


def select_month(series: Sequence[DailyRecord], year: int, month: int) -> List[DailyRecord]:
    return [r for r in series if r["data"].year == year and r["data"].month == month]


def compare_yoy(series: Sequence[DailyRecord], year: int, month: int) -> Dict:
    """Compara um mês contra o mesmo mês do ano anterior (YoY)."""
    atual = select_month(series, year, month)
    base = select_month(series, year - 1, month)
    if not atual or not base:
        raise ValueError("Série insuficiente para YoY (falta o mês atual ou o do ano anterior).")
    res = compare(atual, base)
    res["periodo"] = {"tipo": "YoY", "atual": f"{year}-{month:02d}", "base": f"{year-1}-{month:02d}"}
    return res


def _pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v) * 100:.1f}%"


def explain(res: Dict) -> Dict[str, str]:
    """Gera a narrativa Fato → Causa → Ação do Advisor a partir do resultado."""
    if abs(res["efeito_calendario"]) < 0.003:
        return {
            "fato": f"Faturamento {_pct(res['var_civil'])} vs. período-base.",
            "causa": "Composição de calendário quase idêntica — civil e varejo batem.",
            "acao": "Ler a variação como desempenho real.",
        }
    pior = "abaixo do" if res["var_civil"] < res["var_ajustada"] else "acima do"
    return {
        "fato": f"No fechamento CIVIL o período está {_pct(res['var_civil'])} vs. o ano anterior.",
        "causa": (f"Composição de calendário: o período trocou "
                  f"{'/'.join(res['dias_perdidos']) or '—'} por "
                  f"{'/'.join(res['dias_ganhos']) or '—'}; por isso o civil fica {pior} real."),
        "acao": (f"Usar a lente VAREJO — o desempenho real (ajustado) é "
                 f"{_pct(res['var_ajustada'])}."),
    }
