#!/usr/bin/env python3
"""Demo do Motor de Comparação Temporal com AJUSTE DE CALENDÁRIO (calendário duplo).

Roda SEM banco, só stdlib. Gera vendas diárias determinísticas de agosto/2025 e
agosto/2026 (com composição de dias-da-semana REAL do calendário) e mostra:

  - Comparação CIVIL (mês-calendário): total 2026 vs total 2025.
  - Comparação VAREJO/ajustada (like-for-like por dia da semana): remove o efeito
    de composição de calendário, revelando o desempenho real.

Uso:  python3 scripts/demo_local.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

# permite importar boardos.* rodando da raiz do repo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardos.calendar_gen import calendar_row, generate  # noqa: E402

# --- modelo de venda diária (R$ mil), determinístico -----------------------
# base por dia da semana: sexta e fim de semana vendem mais.
BASE_DOW = {1: 150, 2: 148, 3: 150, 4: 156, 5: 190, 6: 236, 7: 210}  # 1=seg..7=dom
CRESC_REAL = 0.015  # crescimento real de demanda 2026 vs 2025 (+1,5%)


def _noise(d: date) -> float:
    s = (d.year * 10000 + d.month * 100 + d.day) * 2654435761 & 0xFFFFFFFF
    return 0.94 + ((s >> 8) % 1000) / 1000.0 * 0.12  # 0.94..1.06


def venda_dia(d: date, crescimento: float = 0.0) -> float:
    row = calendar_row(d)
    base = BASE_DOW[row["dow_iso"]]
    payday = 1.08 if row["is_periodo_pagamento"] else 1.0
    return round(base * payday * _noise(d) * (1 + crescimento), 1)


def serie_mes(ano: int, mes: int, crescimento: float = 0.0):
    ultimo = 31 if mes in (1, 3, 5, 7, 8, 10, 12) else 30 if mes != 2 else 28
    return [(d, venda_dia(d, crescimento))
            for d in (date(ano, mes, dia) for dia in range(1, ultimo + 1))]


def composicao(ano: int, mes: int):
    comp = {}
    for r in generate(date(ano, mes, 1), date(ano, mes, 28 if mes == 2 else 30 if mes in (4,6,9,11) else 31)):
        comp[r["dow_label"]] = comp.get(r["dow_label"], 0) + 1
    return comp


def brl(v: float) -> str:
    return f"R$ {v:,.0f} mil".replace(",", ".")


def pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v)*100:.1f}%"


def main() -> None:
    ANO_ANT, ANO_ATUAL, MES = 2025, 2026, 8

    s25 = serie_mes(ANO_ANT, MES, 0.0)
    s26 = serie_mes(ANO_ATUAL, MES, CRESC_REAL)
    t25 = sum(v for _, v in s25)
    t26 = sum(v for _, v in s26)

    # média por dia-da-semana em 2025 (base do ajuste)
    from collections import defaultdict
    soma25, cnt25 = defaultdict(float), defaultdict(int)
    for d, v in s25:
        dow = calendar_row(d)["dow_iso"]
        soma25[dow] += v
        cnt25[dow] += 1
    media25 = {dow: soma25[dow] / cnt25[dow] for dow in soma25}

    # baseline ajustado: performance/dia de 2025 projetada na COMPOSIÇÃO de 2026
    cnt26 = defaultdict(int)
    for d, _ in s26:
        cnt26[calendar_row(d)["dow_iso"]] += 1
    baseline_ajustado = sum(media25[dow] * cnt26[dow] for dow in cnt26)

    var_civil = (t26 - t25) / t25
    var_ajust = (t26 - baseline_ajustado) / baseline_ajustado

    comp25, comp26 = composicao(ANO_ANT, MES), composicao(ANO_ATUAL, MES)

    print("=" * 68)
    print(" BoardOS — Comparação com calendário duplo (agosto 2026 vs 2025)")
    print("=" * 68)
    print("\nComposição de dias da semana (real do calendário):")
    print(f"  {'':4} " + " ".join(f"{k:>4}" for k in ["seg","ter","qua","qui","sex","sab","dom"]))
    print(f"  2025 " + " ".join(f"{comp25.get(k,0):>4}" for k in ["seg","ter","qua","qui","sex","sab","dom"]))
    print(f"  2026 " + " ".join(f"{comp26.get(k,0):>4}" for k in ["seg","ter","qua","qui","sex","sab","dom"]))
    dif = [(k, comp26.get(k,0)-comp25.get(k,0)) for k in ["seg","ter","qua","qui","sex","sab","dom"]]
    mudou = [f"{'+' if x>0 else '−'}1 {k}" for k, x in dif if x != 0]
    print(f"  Δ    {'  '.join(mudou) if mudou else 'sem diferença'}")

    print("\n──────────────── LENTE CIVIL (dinheiro / fechamento) ────────────────")
    print(f"  Agosto 2025:            {brl(t25)}")
    print(f"  Agosto 2026:            {brl(t26)}")
    print(f"  Variação civil (bruta): {pct(var_civil)}")

    print("\n──────────── LENTE VAREJO (demanda / like-for-like) ─────────────")
    print(f"  Baseline 2025 ajustado à composição de 2026: {brl(baseline_ajustado)}")
    print(f"  Variação ajustada por calendário:            {pct(var_ajust)}")

    print("\n──────────────────────── ✦ Advisor ─────────────────────────")
    ganhou = [k for k, x in dif if x > 0]
    perdeu = [k for k, x in dif if x < 0]
    if abs(var_civil - var_ajust) < 0.003:
        print("  Composição de calendário quase idêntica — civil e varejo batem.")
    else:
        pior = "abaixo" if var_civil < var_ajust else "acima"
        print(f"  Fato:  no fechamento CIVIL o mês está {pct(var_civil)} vs. ano anterior.")
        print(f"  Causa: composição de calendário — 2026 trocou "
              f"{('/'.join(perdeu)) or '—'} (dia mais forte) por "
              f"{('/'.join(ganhou)) or '—'} (dia mais fraco); por isso o civil fica {pior}.")
        print(f"  Ação:  usar a lente VAREJO — o crescimento REAL de demanda é {pct(var_ajust)}.")
    print()


if __name__ == "__main__":
    main()
