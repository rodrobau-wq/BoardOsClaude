#!/usr/bin/env python3
"""Testes do motor de forecast (stdlib).  Uso: python3 scripts/test_forecast.py"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardos import forecast  # noqa: E402

FAT = {1: 100, 2: 100, 3: 100, 4: 100, 5: 180, 6: 300, 7: 250}  # padrão semanal


def _serie(de, ate):
    out = []
    d = de
    from datetime import timedelta
    while d <= ate:
        out.append({"data": d, "faturamento_liq": FAT[d.isoweekday()]})
        d += timedelta(days=1)
    return out


def test_projecao_respeita_dow():
    """Com histórico perfeitamente semanal, a previsão reproduz o padrão."""
    hist = _serie(date(2026, 7, 1), date(2026, 8, 10))
    r = forecast.forecast_mes(hist, 2026, 8, cutoff=date(2026, 8, 10))
    assert len(r["previsto"]) == 21, len(r["previsto"])  # 11..31
    for p in r["previsto"]:
        assert abs(p["valor"] - FAT[p["data"].isoweekday()]) < 1e-6, p


def test_total_projetado_soma():
    hist = _serie(date(2026, 7, 1), date(2026, 8, 10))
    r = forecast.forecast_mes(hist, 2026, 8, cutoff=date(2026, 8, 10))
    assert abs(r["total_projetado"] - (r["total_realizado"] + r["total_previsto"])) < 0.01


def test_mes_fechado_sem_previsto():
    hist = _serie(date(2026, 7, 1), date(2026, 8, 31))
    r = forecast.forecast_mes(hist, 2026, 8, cutoff=date(2026, 9, 15))
    assert r["previsto"] == []
    assert len(r["realizado"]) == 31


def test_sem_historico_sem_invencao():
    r = forecast.forecast_mes([], 2026, 8, cutoff=date(2026, 8, 10))
    assert r["previsto"] == [] and r["total_projetado"] == 0


def main():
    testes = [v for k, v in globals().items() if k.startswith("test_")]
    for t in testes:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(testes)} testes passaram.")


if __name__ == "__main__":
    main()
