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
from boardos.db import tenant_session  # noqa: E402
from boardos.auth import hash_password  # noqa: E402

SENHA_DEMO = "demo1234"

# OKRs demo (varejo). KR: (titulo, unidade, meta, atual, base, direcao, fonte)
# fonte != None => "atual" vem do dado real (calculado pela API), não do seed.
OKRS_DEMO = [
    ("Crescer com rentabilidade em 2026", "2026", [
        ("Faturamento +8% no ano", "%", 8, 0, 0, "up", "fat_yoy_pct"),
        ("Margem bruta ≥ 22%", "%", 22, 21.4, 20, "up", None),
        ("Ruptura ≤ 3%", "%", 3, 4.8, 6, "down", None),
    ]),
    ("Fidelizar o cliente", "2026", [
        ("Base fidelidade +15 mil", "clientes", 15000, 10600, 0, "up", None),
        ("Ticket médio +5%", "%", 5, 0, 0, "up", "ticket_yoy_pct"),
    ]),
]


# Categorias demo com participação típica de supermercado (soma = 1.0)
CATEGORIAS = [("MERC", "Mercearia", 0.30), ("HORT", "Hortifrúti", 0.15),
              ("ACOU", "Açougue", 0.15), ("BEB", "Bebidas", 0.14),
              ("PAD", "Padaria", 0.10), ("LIMP", "Limpeza & Perfumaria", 0.16)]


def seed_categorias_gold(tenant_id: str) -> None:
    """Desdobra o gold total da loja em linhas por categoria (share + ruído
    determinístico por dia/loja/categoria — assim cada categoria tem YoY próprio)."""
    from boardos.ingestion import _get_or_create
    with tenant_session(tenant_id) as cur:
        ids = {}
        for cod, nome, _ in CATEGORIAS:
            ids[cod] = _get_or_create(cur, "categoria", cod,
                                      {"nome": nome, "tenant_id": tenant_id})
        cur.execute("DELETE FROM gold_venda_diaria WHERE categoria_id IS NOT NULL")
        for cod, _nome, share in CATEGORIAS:
            cur.execute(
                """
                INSERT INTO gold_venda_diaria
                  (tenant_id, data, loja_id, categoria_id, faturamento_bruto,
                   faturamento_liq, custo, margem, itens, cupons, qtd)
                SELECT tenant_id, data, loja_id, %s,
                       round((faturamento_bruto*%s*f)::numeric,2), round((faturamento_liq*%s*f)::numeric,2),
                       round((custo*%s*f)::numeric,2), round((margem*%s*f)::numeric,2),
                       greatest(1, round((itens*%s*f)::numeric)), greatest(1, round((cupons*%s*f)::numeric)),
                       round((qtd*%s*f)::numeric,2)
                  FROM (SELECT g.*,
                               0.86 + (abs(hashtext(g.data::text || g.loja_id::text || %s)) %% 280)/1000.0 AS f
                          FROM gold_venda_diaria g WHERE g.categoria_id IS NULL) sub
                ON CONFLICT (tenant_id, data, loja_id, categoria_id) DO UPDATE SET
                  faturamento_bruto=EXCLUDED.faturamento_bruto,
                  faturamento_liq=EXCLUDED.faturamento_liq, custo=EXCLUDED.custo,
                  margem=EXCLUDED.margem, itens=EXCLUDED.itens,
                  cupons=EXCLUDED.cupons, qtd=EXCLUDED.qtd
                """,
                (ids[cod], share, share, share, share, share, share, share, cod))


def seed_okrs(tenant_id: str) -> None:
    with tenant_session(tenant_id) as cur:
        cur.execute("DELETE FROM okr_objetivo WHERE tenant_id = %s", (tenant_id,))
        for o_ordem, (titulo, periodo, krs) in enumerate(OKRS_DEMO):
            oid = cur.execute(
                "INSERT INTO okr_objetivo (tenant_id, titulo, periodo, ordem) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (tenant_id, titulo, periodo, o_ordem)).fetchone()[0]
            for k_ordem, (kt, un, meta, atual, base, direcao, fonte) in enumerate(krs):
                cur.execute(
                    "INSERT INTO okr_kr (tenant_id, objetivo_id, titulo, unidade, meta, atual, base, direcao, ordem, fonte) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (tenant_id, oid, kt, un, meta, atual, base, direcao, k_ordem, fonte))

ADMIN_DSN = (os.environ.get("BOARDOS_ADMIN_DSN") or os.environ.get("DATABASE_URL")
             or "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DE, ATE = date(2024, 1, 1), date(2026, 12, 31)

# perfil por empresa: lojas, escala e crescimento acumulado por ano
PERFIS = {
    "EMP-1001": {"lojas": ["C01", "C02"], "escala": 1.0, "cresc": {2024: 0, 2025: .030, 2026: .055}, "email": "ceo@aurora.demo"},
    "EMP-1002": {"lojas": ["L1"],         "escala": 2.6, "cresc": {2024: 0, 2025: .040, 2026: .070}, "email": "ceo@belavista.demo"},
    "EMP-1003": {"lojas": ["H1"],         "escala": 4.1, "cresc": {2024: 0, 2025: .015, 2026: .025}, "email": "ceo@maxpreco.demo"},
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
    # Seed demo só roda quando SEED_DEMO está setado (production-safe).
    if not os.environ.get("SEED_DEMO"):
        print("SEED_DEMO não setado — pulando seed de demonstração.")
        return

    # 1) empresas -> tenants (upsert idempotente por slug estável; NÃO apaga nada)
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
        seed_okrs(tid)
        try:
            seed_categorias_gold(tid)
        except Exception as e:  # não derruba o resto do seed; loga a causa
            print(f"  AVISO: seed de categorias falhou para {ext}: {e}")
        print(f"  {ext} ({tid}): {res['linhas']} linhas de gold + OKRs + categorias demo")

    # 4) usuários de login (senha com hash) — um CEO por empresa + super-admin
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        for ext, perfil in PERFIS.items():
            tid = idmap.get(ext)
            if not tid:
                continue
            conn.execute(
                """
                INSERT INTO platform.usuario_login (email, senha_hash, nome, tenant_id, papel)
                VALUES (%s,%s,%s,%s,'estrategico')
                ON CONFLICT (email) DO UPDATE SET
                  senha_hash=EXCLUDED.senha_hash, tenant_id=EXCLUDED.tenant_id,
                  nome=EXCLUDED.nome, papel=EXCLUDED.papel
                """,
                (perfil["email"], hash_password(SENHA_DEMO), "CEO", tid),
            )
        # super-admin da plataforma: acesso a todas as bases (tenant NULL)
        conn.execute(
            """
            INSERT INTO platform.usuario_login (email, senha_hash, nome, tenant_id, papel)
            VALUES (%s,%s,%s,NULL,'super_admin')
            ON CONFLICT (email) DO UPDATE SET
              senha_hash=EXCLUDED.senha_hash, tenant_id=NULL,
              nome=EXCLUDED.nome, papel='super_admin'
            """,
            ("rodrobau@gmail.com", hash_password(SENHA_DEMO), "Rodrigo (Admin)"),
        )

    print("\nOK — logins demo (senha: %s):" % SENHA_DEMO)
    for ext, perfil in PERFIS.items():
        print("   %-22s %s" % (perfil["email"], ext))
    print("   %-22s %s" % ("rodrobau@gmail.com", "SUPER-ADMIN (todas as bases)"))


if __name__ == "__main__":
    main()
