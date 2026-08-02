#!/usr/bin/env python3
"""Onboarding de demonstração a partir do CRM (layout assumido).

1) cria um TENANT por empresa (data/crm_empresas_exemplo.csv)
2) popula dim_calendario (2024–2026)
3) gera ~3 anos de vendas diárias por empresa e importa no gold

Resultado: várias empresas no seletor do painel, cada uma com dado real.
Quando vier o CRM de verdade, troca-se a fonte (CSV real / API / banco) e o
mapeamento em boardos/crm.py — o resto fica igual.

Uso:  python3 scripts/onboard_crm_demo.py
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg  # noqa: E402
except ImportError:
    psycopg = None
from boardos import crm  # noqa: E402
from boardos.calendar_gen import upsert_into  # noqa: E402

ADMIN_DSN = (os.environ.get("BOARDOS_ADMIN_DSN") or os.environ.get("DATABASE_URL")
             or "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DE, ATE = date(2024, 1, 1), date(2026, 12, 31)

# perfil por empresa: lojas, escala e crescimento acumulado por ano
PERFIS = {
    "EMP-1001": {"lojas": ["C01", "C02"], "escala": 1.0, "cresc": {2024: 0, 2025: .030, 2026: .055}},
    "EMP-1002": {"lojas": ["L1"],         "escala": 2.6, "cresc": {2024: 0, 2025: .040, 2026: .070}},
    "EMP-1003": {"lojas": ["H1"],         "escala": 4.1, "cresc": {2024: 0, 2025: .015, 2026: .025}},
}
BASE_DOW = {1: 150, 2: 148, 3: 150, 4: 156, 5: 190, 6: 236, 7: 210}  # R$ mil


def _noise(d, salt):
    s = (d.year * 10000 + d.month * 100 + d.day + salt) * 2654435761 & 0xFFFFFFFF
    return 0.93 + ((s >> 8) % 1000) / 1000.0 * 0.14


def gen_vendas(perfil, salt):
    d = DE
    while d <= ATE:
        for i, loja in enumerate(perfil["lojas"]):
            fat_mil = (BASE_DOW[d.isoweekday()] * perfil["escala"]
                       * (0.6 + 0.4 * (i == 0))  # 1a loja maior
                       * (1.08 if (d.day <= 3 or d.day >= 28) else 1.0)
                       * _noise(d, salt + i) * (1 + perfil["cresc"].get(d.year, 0)))
            fat = fat_mil * 1000
            cupons = max(1, round(fat / 58.0))
            yield {"data": d, "loja": loja, "faturamento": round(fat, 2),
                   "cupons": cupons, "itens": round(cupons * 8.2)}
        d += timedelta(days=1)


def main():
    # 0) limpeza (DEMO): remove tenants fora da lista atual do CRM (dupes/órfãos).
    #    Converge para exatamente as empresas do CRM. Só para a fase demo.
    alvo = [crm.slugify(ext) for ext in PERFIS]
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        n = conn.execute("DELETE FROM platform.tenant WHERE slug <> ALL(%s)", (alvo,)).rowcount
    print(f"limpeza: {n} tenant(s) fora da lista do CRM removido(s)")

    # 1) empresas -> tenants
    idmap = crm.onboard_empresas_csv(os.path.join(ROOT, "data", "crm_empresas_exemplo.csv"), ADMIN_DSN)
    print("empresas -> tenants:", idmap)

    # 2) calendário
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            upsert_into(cur, DE, ATE)

    # 3) vendas por empresa
    os.environ.setdefault("BOARDOS_DSN", ADMIN_DSN)
    for salt, (ext, perfil) in enumerate(PERFIS.items()):
        tid = idmap.get(ext)
        if not tid:
            continue
        res = crm.import_vendas_diarias_rows(tid, gen_vendas(perfil, salt * 97))
        print(f"  {ext} ({tid}): {res['linhas']} linhas de gold")
    print("\nOK — abra o painel e escolha a empresa no seletor.")


if __name__ == "__main__":
    main()
