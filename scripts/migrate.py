#!/usr/bin/env python3
"""Roda as migrações SQL em ordem (conexão ADMIN, sem RLS).

Uso:  python3 scripts/migrate.py
Requer BOARDOS_ADMIN_DSN e psycopg instalado + Postgres no ar.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

ADMIN_DSN = os.environ.get(
    "BOARDOS_ADMIN_DSN",
    "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos",
)
MIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "db", "migrations")


def main() -> None:
    files = sorted(glob.glob(os.path.join(MIG_DIR, "*.sql")))
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        for f in files:
            print(f"→ {os.path.basename(f)}")
            with open(f, encoding="utf-8") as fh:
                conn.execute(fh.read())
    print(f"OK — {len(files)} migrações aplicadas.")


if __name__ == "__main__":
    main()
