"""Conexão Postgres + contexto de tenant (RLS).

A app conecta como role `boardos_app` (sujeita a RLS) e, no início de cada
unidade de trabalho, faz `SET app.current_tenant`. Sem isso, RLS não deixa ver
nada — default deny. Ver db/migrations/0007_rls.sql.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

try:
    import psycopg  # psycopg 3
except ImportError:  # pragma: no cover - psycopg é dependência de runtime
    psycopg = None

DSN = os.environ.get(
    "BOARDOS_DSN",
    "postgresql://boardos_app:change-me@localhost:5432/boardos",
)


def connect():
    if psycopg is None:
        raise RuntimeError("psycopg não instalado — rode `pip install -r requirements.txt`")
    return psycopg.connect(DSN)


@contextmanager
def platform_session():
    """Conexão para tabelas de plataforma (platform.*), que NÃO têm RLS de tenant.

    Uso: listar/gerir tenants, billing, etc. Em produção, proteger por auth de
    super-admin — aqui é usado pelo seletor de empresa do painel (MVP).
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def tenant_session(tenant_id: str):
    """Abre uma conexão já escopada a um tenant (SET app.current_tenant).

    Uso:
        with tenant_session(tid) as cur:
            cur.execute("SELECT count(*) FROM loja")
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            # set_config com is_local=true => vale só nesta transação
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant_id,))
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
