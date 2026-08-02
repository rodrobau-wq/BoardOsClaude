#!/usr/bin/env python3
"""Roda as migrações SQL em ordem, com rastreamento (idempotente).

Cada arquivo aplicado é registrado em schema_migrations; rodar de novo pula os
já aplicados — seguro para rodar a cada deploy (Render, etc.).

Uso:  python3 scripts/migrate.py
Requer BOARDOS_ADMIN_DSN (ou DATABASE_URL) e psycopg + Postgres no ar.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

ADMIN_DSN = (
    os.environ.get("BOARDOS_ADMIN_DSN")
    or os.environ.get("DATABASE_URL")
    or "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos"
)
MIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "db", "migrations")


def main() -> None:
    files = sorted(glob.glob(os.path.join(MIG_DIR, "*.sql")))
    with psycopg.connect(ADMIN_DSN) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(filename text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        conn.commit()
        applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()}

        novos = 0
        for f in files:
            name = os.path.basename(f)
            if name in applied:
                print(f"·  {name} (já aplicado)")
                continue
            print(f"→  {name}")
            with open(f, encoding="utf-8") as fh:
                conn.execute(fh.read())
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (name,))
            conn.commit()
            novos += 1
    print(f"OK — {novos} nova(s) migração(ões), {len(files)} total.")


if __name__ == "__main__":
    main()
