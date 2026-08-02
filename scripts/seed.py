#!/usr/bin/env python3
"""Semeia um tenant de demonstração e ingere o CSV de exemplo.

1) cria tenant + assinatura (ADMIN, platform.*)
2) popula dim_calendario para 2024-2027 (ADMIN, global)
3) ingere data/vendas_exemplo.csv (via tenant_session, RLS)

Uso:  python3 scripts/seed.py
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402
from boardos.calendar_gen import upsert_into  # noqa: E402
from boardos.mapping import ColumnMap  # noqa: E402
from boardos.ingestion import ingest_csv  # noqa: E402

ADMIN_DSN = os.environ.get(
    "BOARDOS_ADMIN_DSN",
    "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos",
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        # 1) tenant de demo (idempotente pelo slug)
        tid = conn.execute(
            """
            INSERT INTO platform.tenant (nome, slug, status)
            VALUES ('Supermercados Aurora', 'aurora', 'ativo')
            ON CONFLICT (slug) DO UPDATE SET nome=EXCLUDED.nome
            RETURNING id
            """
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO platform.assinatura (tenant_id, plano, base_mensal_cent, preco_por_1k_cent) "
            "VALUES (%s,'v0',49900,900) ON CONFLICT DO NOTHING",
            (tid,),
        )
        # 2) dim_calendario
        with conn.cursor() as cur:
            n = upsert_into(cur, date(2024, 1, 1), date(2027, 12, 31))
        print(f"tenant={tid}  dim_calendario={n} dias")

    # 3) ingestão do CSV de exemplo (RLS via tenant_session)
    os.environ.setdefault(
        "BOARDOS_DSN",
        "postgresql://boardos_app:change-me@localhost:5432/boardos",
    )
    cmap = ColumnMap(json.load(open(os.path.join(ROOT, "data", "mapa_colunas_exemplo.json"))))
    cmap.mapping.pop("_comment", None)
    res = ingest_csv(
        tenant_id=str(tid),
        loja_codigo="C01",
        loja_nome="Loja Centro",
        csv_path=os.path.join(ROOT, "data", "vendas_exemplo.csv"),
        cmap=cmap,
    )
    print("ingestão:", res)
    print("Reingira o mesmo arquivo e verifique: as linhas NÃO duplicam (idempotência).")


if __name__ == "__main__":
    main()
