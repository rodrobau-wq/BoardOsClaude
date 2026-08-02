#!/usr/bin/env python3
"""Seed de demonstração com ~3 anos no gold (linha de TOTAL por loja/dia).

Popula gold_venda_diaria (categoria_id NULL = total da loja) para 2024–2026, o
que faz /kpi/diario e /comparacao/yoy responderem com dado real. É um seed
sintético de gold (não passa pelo pipeline de item) — bom para demo.

Uso:  python3 scripts/seed_demo_gold.py
Requer BOARDOS_ADMIN_DSN/BOARDOS_DSN (ou DATABASE_URL) e Postgres no ar.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402
from boardos.calendar_gen import upsert_into  # noqa: E402
from boardos.db import tenant_session  # noqa: E402
from boardos.ingestion import _get_or_create  # noqa: E402
from gen_dataset import gen  # noqa: E402  (mesmo modelo do demo de comparação)

ADMIN_DSN = (
    os.environ.get("BOARDOS_ADMIN_DSN")
    or os.environ.get("DATABASE_URL")
    or "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos"
)
DE, ATE = date(2024, 1, 1), date(2026, 12, 31)


def main() -> None:
    # 1) tenant + assinatura + calendário (ADMIN)
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        tid = conn.execute(
            "INSERT INTO platform.tenant (nome, slug, status) "
            "VALUES ('Supermercados Aurora','aurora','ativo') "
            "ON CONFLICT (slug) DO UPDATE SET nome=EXCLUDED.nome RETURNING id"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO platform.assinatura (tenant_id, plano, base_mensal_cent, preco_por_1k_cent) "
            "VALUES (%s,'v0',49900,900) ON CONFLICT (tenant_id) DO NOTHING", (tid,))
        with conn.cursor() as cur:
            n = upsert_into(cur, DE, ATE)
    print(f"tenant={tid}  calendário={n} dias")

    # 2) lojas + gold (TENANT via RLS)
    os.environ.setdefault("BOARDOS_DSN", ADMIN_DSN)
    linhas = 0
    with tenant_session(str(tid)) as cur:
        loja_ids = {
            cod: _get_or_create(cur, "loja", cod, {"nome": nome, "tenant_id": str(tid)})
            for cod, nome in [("C01", "Loja Centro"), ("C02", "Loja Jardim")]
        }
        rows = []
        for r in gen(DE, ATE):
            fat = r["faturamento_liq"]
            rows.append((str(tid), r["data"], loja_ids[r["loja"]],
                         round(fat * 1.03, 2), fat, round(fat * 0.71, 2), round(fat * 0.29, 2),
                         r["itens"], r["cupons"], float(r["itens"])))
        cur.executemany(
            """
            INSERT INTO gold_venda_diaria
              (tenant_id, data, loja_id, categoria_id, faturamento_bruto, faturamento_liq,
               custo, margem, itens, cupons, qtd)
            VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, data, loja_id, categoria_id) DO UPDATE SET
              faturamento_bruto=EXCLUDED.faturamento_bruto, faturamento_liq=EXCLUDED.faturamento_liq,
              custo=EXCLUDED.custo, margem=EXCLUDED.margem, itens=EXCLUDED.itens,
              cupons=EXCLUDED.cupons, qtd=EXCLUDED.qtd
            """,
            rows,
        )
        linhas = len(rows)
    print(f"gold: {linhas} linhas (2024–2026, total por loja/dia)")
    print(f"\nTeste:  /comparacao/yoy?ano=2026&mes=8   com header  X-Tenant-Id: {tid}")


if __name__ == "__main__":
    main()
