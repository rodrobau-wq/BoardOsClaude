"""Gerador da dimensão de calendário DUPLO (civil + varejo/ISO week).

Fonte única da lógica de calendário. Usado tanto para popular `dim_calendario`
no Postgres quanto pelo demo local (scripts/demo_local.py).

Civil = mês/ano-calendário (dinheiro). Varejo = semana ISO alinhada (demanda).
Ver PLANO.md 3.12.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Dict, Iterator

DOW_LABEL = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]  # index = iso_weekday-1


def _same_dow_count_in_month(d: date) -> int:
    """Quantos dias com o MESMO dia-da-semana existem no mês civil de d.

    Base do ajuste de composição de calendário (trading-day): é isto que
    diferencia um mês com 5 sábados de um com 4.
    """
    weekday = d.weekday()  # 0=segunda ... 6=domingo
    days_in_month = calendar.monthrange(d.year, d.month)[1]
    return sum(
        1
        for day in range(1, days_in_month + 1)
        if date(d.year, d.month, day).weekday() == weekday
    )


def _is_split_week(d: date) -> bool:
    """A semana ISO de d cruza dois meses civis? (semana partida)"""
    iso_weekday = d.isoweekday()  # 1..7
    monday = d - timedelta(days=iso_weekday - 1)
    sunday = monday + timedelta(days=6)
    return monday.month != sunday.month


def calendar_row(d: date) -> Dict:
    """Retorna a linha da dimensão para uma data (civil + varejo)."""
    iso_year, iso_week, iso_weekday = d.isocalendar()
    return {
        "data": d,
        # civil
        "ano_civil": d.year,
        "mes_civil": d.month,
        "dia_mes": d.day,
        # dia da semana
        "dow_iso": iso_weekday,                       # 1=seg ... 7=dom
        "dow_label": DOW_LABEL[iso_weekday - 1],
        "is_fim_semana": iso_weekday >= 6,
        "is_util": iso_weekday <= 5,
        "is_periodo_pagamento": d.day <= 3 or d.day >= 28,
        "feriado": False,                             # populado depois por cadastro
        # varejo (ISO week = default; retail_* permite 4-4-5 no futuro)
        "iso_year": iso_year,
        "iso_week": iso_week,
        "retail_year": iso_year,
        "retail_week": iso_week,
        "retail_period": None,
        "semana_partida": _is_split_week(d),
        # ajuste trading-day
        "qtd_mesmo_dow_no_mes": _same_dow_count_in_month(d),
    }


def date_range(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def generate(start: date, end: date) -> Iterator[Dict]:
    """Gera as linhas da dimensão para [start, end]."""
    for d in date_range(start, end):
        yield calendar_row(d)


# --- persistência opcional (psycopg) -------------------------------------
_COLS = [
    "data", "ano_civil", "mes_civil", "dia_mes", "dow_iso", "dow_label",
    "is_fim_semana", "is_util", "is_periodo_pagamento", "feriado",
    "iso_year", "iso_week", "retail_year", "retail_week", "retail_period",
    "semana_partida", "qtd_mesmo_dow_no_mes",
]


def upsert_into(cur, start: date, end: date) -> int:
    """Insere/atualiza dim_calendario via um cursor psycopg. Retorna nº de linhas."""
    rows = list(generate(start, end))
    placeholders = ",".join(["%s"] * len(_COLS))
    updates = ",".join(f"{c}=EXCLUDED.{c}" for c in _COLS if c != "data")
    sql = (
        f"INSERT INTO dim_calendario ({','.join(_COLS)}) VALUES ({placeholders}) "
        f"ON CONFLICT (data) DO UPDATE SET {updates}"
    )
    cur.executemany(sql, [[r[c] for c in _COLS] for r in rows])
    return len(rows)


if __name__ == "__main__":
    # Demonstração rápida: composição de dois agostos (efeito calendário).
    for ano in (2025, 2026):
        comp: Dict[str, int] = {}
        for r in generate(date(ano, 8, 1), date(ano, 8, 31)):
            comp[r["dow_label"]] = comp.get(r["dow_label"], 0) + 1
        print(f"Agosto/{ano}:", comp)
