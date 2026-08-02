#!/usr/bin/env python3
"""Testes do motor de comparação (stdlib, sem framework).

Uso:  python3 scripts/test_comparison.py
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardos import comparison  # noqa: E402


def _mes(ano, fat_por_dow, cupons=10):
    """Agosto do `ano` com faturamento fixo por dia da semana."""
    return [
        {"data": date(ano, 8, d), "faturamento_liq": fat_por_dow[date(ano, 8, d).isoweekday()],
         "cupons": cupons, "itens": 0}
        for d in range(1, 32)
    ]


# sexta mais forte que os demais dias úteis + fim de semana forte:
# assim trocar uma sexta por uma segunda muda o total civil (como no varejo real).
FORTE_FDS = {1: 100, 2: 100, 3: 100, 4: 100, 5: 180, 6: 300, 7: 300}


def test_mesma_performance_ajustado_zero():
    """Mesma performance/dia-da-semana => variação ajustada ~0, mesmo com
    composição diferente entre os anos."""
    r = comparison.compare(_mes(2026, FORTE_FDS), _mes(2025, FORTE_FDS))
    assert abs(r["var_ajustada"]) < 1e-9, r["var_ajustada"]


def test_composicao_afeta_civil_mas_nao_ajustado():
    """Sem crescimento real, a diferença de composição move o CIVIL mas não o
    AJUSTADO (o efeito de calendário é toda a variação civil)."""
    r = comparison.compare(_mes(2026, FORTE_FDS), _mes(2025, FORTE_FDS))
    assert abs(r["efeito_calendario"] - (r["var_ajustada"] - r["var_civil"])) < 1e-12
    # civil difere de 0 (composição de ago/2026 != ago/2025), ajustado ~0
    assert abs(r["var_civil"]) > 1e-6
    assert abs(r["var_ajustada"]) < 1e-9


def test_crescimento_uniforme_civil_igual_ajustado():
    """Crescimento uniforme de +10% em todos os dias, mantendo a mesma
    performance relativa por dia da semana."""
    base = _mes(2025, FORTE_FDS)
    atual = _mes(2026, {k: v * 1.10 for k, v in FORTE_FDS.items()})
    r = comparison.compare(atual, base)
    assert abs(r["var_ajustada"] - 0.10) < 1e-9, r["var_ajustada"]


def test_yoy_exige_serie():
    try:
        comparison.compare_yoy(_mes(2026, FORTE_FDS), 2026, 8)  # sem 2025
        raise AssertionError("deveria ter falhado por falta de série")
    except ValueError:
        pass


def main():
    testes = [v for k, v in globals().items() if k.startswith("test_")]
    for t in testes:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(testes)} testes passaram.")


if __name__ == "__main__":
    main()
