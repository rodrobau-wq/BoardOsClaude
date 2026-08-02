#!/usr/bin/env python3
"""Gera uma série diária (nível gold) de ~3 anos para exercitar o motor de
comparação sem depender do banco.

Escreve data/gold_diario_exemplo.csv com: data;loja;faturamento_liq;cupons;itens
Uso:  python3 scripts/gen_dataset.py
"""
from __future__ import annotations

import csv
import os
from datetime import date, timedelta

BASE_DOW = {1: 150, 2: 148, 3: 150, 4: 156, 5: 190, 6: 236, 7: 210}  # 1=seg..7=dom (R$ mil)
TICKET = 58.0          # R$ por cupom
CESTA = 8.2            # itens por cupom
CRESC_ANO = {2024: 0.0, 2025: 0.030, 2026: 0.055}  # crescimento real ACUMULADO por ano
# (YoY real 2026 vs 2025 ≈ 1.055/1.030 − 1 ≈ +2,4%)
LOJAS = {"C01": 1.0, "C02": 0.62}                  # peso relativo por loja


def _noise(d: date, loja: str) -> float:
    s = (d.year * 10000 + d.month * 100 + d.day + hash(loja)) * 2654435761 & 0xFFFFFFFF
    return 0.93 + ((s >> 8) % 1000) / 1000.0 * 0.14


def gen(start: date, end: date):
    d = start
    while d <= end:
        for loja, peso in LOJAS.items():
            base = BASE_DOW[d.isoweekday()]
            payday = 1.08 if (d.day <= 3 or d.day >= 28) else 1.0
            cresc = 1 + CRESC_ANO.get(d.year, 0.0)
            fat_mil = base * peso * payday * _noise(d, loja) * cresc
            fat = round(fat_mil * 1000, 2)              # R$
            cupons = max(1, round(fat / TICKET))
            itens = round(cupons * CESTA)
            yield {"data": d.isoformat(), "loja": loja,
                   "faturamento_liq": fat, "cupons": cupons, "itens": itens}
        d += timedelta(days=1)


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "data", "gold_diario_exemplo.csv")
    rows = list(gen(date(2024, 1, 1), date(2026, 12, 31)))
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["data", "loja", "faturamento_liq", "cupons", "itens"],
                           delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"OK — {len(rows)} linhas em {os.path.relpath(out, root)}")


if __name__ == "__main__":
    main()
