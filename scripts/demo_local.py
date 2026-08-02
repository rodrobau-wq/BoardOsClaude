#!/usr/bin/env python3
"""Demo do calendário duplo — versão enxuta que delega a matemática ao motor
oficial (boardos/comparison). Roda SEM banco.

Gera vendas diárias determinísticas de agosto/2025 e agosto/2026 (com a
composição REAL de dias da semana) e compara nas lentes Civil e Varejo.

Uso:  python3 scripts/demo_local.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardos import comparison  # noqa: E402

BASE_DOW = {1: 150, 2: 148, 3: 150, 4: 156, 5: 190, 6: 236, 7: 210}  # R$ mil
CRESC_REAL = 0.024  # crescimento real de demanda 2026 vs 2025


def _noise(d: date) -> float:
    s = (d.year * 10000 + d.month * 100 + d.day) * 2654435761 & 0xFFFFFFFF
    return 0.94 + ((s >> 8) % 1000) / 1000.0 * 0.12


def serie(ano: int, cresc: float = 0.0):
    recs = []
    for dia in range(1, 32):
        d = date(ano, 8, dia)
        base = BASE_DOW[d.isoweekday()]
        payday = 1.08 if (d.day <= 3 or d.day >= 28) else 1.0
        fat = base * payday * _noise(d) * (1 + cresc) * 1000
        recs.append({"data": d, "faturamento_liq": fat, "cupons": round(fat / 58.0), "itens": 0})
    return recs


def brl(v: float) -> str:
    return f"R$ {v/1000:,.0f} mil".replace(",", ".")


def pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v)*100:.1f}%"


def main() -> None:
    res = comparison.compare(serie(2026, CRESC_REAL), serie(2025, 0.0))

    print("=" * 66)
    print("  BoardOS — Comparação com calendário duplo (agosto 2026 vs 2025)")
    print("=" * 66)
    print("\n  Composição de dias da semana (real do calendário) — atual/base:")
    print("   " + "  ".join(f"{k}:{v['atual']}/{v['base']}"
                            for k, v in res["composicao"].items()))
    print("\n  ── LENTE CIVIL (dinheiro) ──")
    print(f"   Ago/2025: {brl(res['total_base'])}   Ago/2026: {brl(res['total_atual'])}")
    print(f"   Variação civil (bruta):     {pct(res['var_civil'])}")
    print("\n  ── LENTE VAREJO (demanda, like-for-like) ──")
    print(f"   Baseline 2025 ajustado à composição de 2026: {brl(res['baseline_ajustado'])}")
    print(f"   Variação ajustada:          {pct(res['var_ajustada'])}")

    exp = comparison.explain(res)
    print("\n  ── ✦ Advisor ──")
    for k in ("fato", "causa", "acao"):
        print(f"   {k.capitalize()}: {exp[k]}")
    print()


if __name__ == "__main__":
    main()
