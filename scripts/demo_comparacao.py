#!/usr/bin/env python3
"""Demo do motor de comparação (boardos/comparison) sobre a série de ~3 anos.

Roda SEM banco. Gera o dataset se ainda não existir, agrega por rede e mês, e
compara agosto/2026 vs agosto/2025 (YoY) nas lentes Civil e Varejo.

Uso:  python3 scripts/demo_comparacao.py
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from boardos import comparison  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "gold_diario_exemplo.csv")


def load_series():
    if not os.path.exists(CSV_PATH):
        from gen_dataset import main as gen_main  # type: ignore
        gen_main()
    # agrega as lojas -> total da rede por dia
    por_dia = defaultdict(lambda: {"faturamento_liq": 0.0, "cupons": 0, "itens": 0})
    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            d = date.fromisoformat(r["data"])
            acc = por_dia[d]
            acc["faturamento_liq"] += float(r["faturamento_liq"])
            acc["cupons"] += int(r["cupons"])
            acc["itens"] += int(r["itens"])
    return [dict(data=d, **v) for d, v in sorted(por_dia.items())]


def brl(v: float) -> str:
    return f"R$ {v/1000:,.0f} mil".replace(",", ".")


def pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v)*100:.1f}%"


def main() -> None:
    series = load_series()
    res = comparison.compare_yoy(series, 2026, 8)

    print("=" * 66)
    print("  BoardOS — Comparação YoY (rede) · agosto 2026 vs 2025")
    print("=" * 66)
    print(f"\n  Total ago/2026 (civil):          {brl(res['total_atual'])}")
    print(f"  Total ago/2025 (civil):          {brl(res['total_base'])}")
    print(f"  Baseline 2025 ajustado à composição de 2026: {brl(res['baseline_ajustado'])}")
    print(f"\n  ▸ Variação CIVIL (bruta):        {pct(res['var_civil'])}")
    print(f"  ▸ Variação VAREJO (ajustada):    {pct(res['var_ajustada'])}")
    print(f"  ▸ Efeito de calendário:          {pct(res['efeito_calendario'])}")

    print("\n  Composição de dias da semana (atual/base):")
    print("   " + "  ".join(f"{k}:{v['atual']}/{v['base']}"
                            for k, v in res["composicao"].items()))
    print(f"  Ticket: {res['ticket_base']} → {res['ticket_atual']}")

    exp = comparison.explain(res)
    print("\n  ──────────────── ✦ Advisor ────────────────")
    print(f"  Fato:  {exp['fato']}")
    print(f"  Causa: {exp['causa']}")
    print(f"  Ação:  {exp['acao']}")
    print()


if __name__ == "__main__":
    main()
