"""API mínima do BoardOS (M0).

Demonstra o padrão de tenant + RLS: cada requisição carrega o tenant (aqui via
header X-Tenant-Id; em produção vem do token de sessão) e toda query roda dentro
de `tenant_session`, que faz SET app.current_tenant.

Rodar:  uvicorn api.main:app --reload
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date  # noqa: E402

from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from boardos.db import tenant_session, platform_session  # noqa: E402
from boardos import comparison  # noqa: E402

app = FastAPI(title="BoardOS API", version="0.2.0-m2")

# CORS: permite o painel (static site) chamar a API de outro endereço.
# Aberto no MVP; restringir aos domínios do painel quando for para produção.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _gold_mes(cur, ano: int, mes: int):
    """Total da rede por dia num mês (soma das lojas), a partir do gold."""
    cur.execute(
        """
        SELECT data, sum(faturamento_liq) AS faturamento_liq,
               sum(cupons) AS cupons, sum(itens) AS itens
          FROM gold_venda_diaria
         WHERE categoria_id IS NULL
           AND date_trunc('month', data) = make_date(%s, %s, 1)
         GROUP BY data ORDER BY data
        """,
        (ano, mes),
    )
    return [
        {"data": r[0], "faturamento_liq": float(r[1]),
         "cupons": int(r[2]), "itens": int(r[3])}
        for r in cur.fetchall()
    ]


@app.get("/health")
def health():
    return {"ok": True, "service": "boardos", "stage": "M0"}


@app.get("/tenants")
def tenants():
    """Lista as empresas (tenants) para o seletor do painel.

    Em produção: proteger por auth de super-admin. Aqui alimenta o dropdown do
    painel (MVP). Cada empresa do CRM vira um tenant.
    """
    with platform_session() as cur:
        cur.execute("SELECT id, nome, slug, status FROM platform.tenant ORDER BY nome")
        rows = [{"id": str(r[0]), "nome": r[1], "slug": r[2], "status": r[3]}
                for r in cur.fetchall()]
    return {"tenants": rows}


@app.get("/kpi/diario")
def kpi_diario(
    data_de: str,
    data_ate: str,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
):
    """KPIs diários (total da loja) no período — lê a view gold v_kpi_diario.

    Já traz as chaves do calendário duplo (civil + varejo) para o motor de
    comparação. RLS garante que só o tenant do header é visível.
    """
    with tenant_session(x_tenant_id) as cur:
        # soma por DIA (total da rede) — agrega as lojas, consistente com /comparacao
        cur.execute(
            """
            SELECT data,
                   sum(faturamento_liq)          AS faturamento_liq,
                   sum(cupons)                   AS cupons,
                   sum(itens)                    AS itens,
                   max(dow_label)                AS dow_label,
                   bool_or(is_fim_semana)        AS is_fim_semana,
                   max(retail_year)              AS retail_year,
                   max(retail_week)              AS retail_week
              FROM v_kpi_diario
             WHERE categoria_id IS NULL
               AND data BETWEEN %s AND %s
             GROUP BY data
             ORDER BY data
            """,
            (data_de, data_ate),
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:  # tipos JSON-friendly
            r["data"] = str(r["data"])
            r["faturamento_liq"] = float(r["faturamento_liq"])
    if not rows:
        raise HTTPException(404, "Sem dados no período para este tenant.")
    return {"periodo": [data_de, data_ate], "dias": rows}


@app.get("/comparacao/yoy")
def comparacao_yoy(
    ano: int,
    mes: int,
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
):
    """Comparação YoY (mês vs. mesmo mês do ano anterior) nas lentes Civil e
    Varejo, com ajuste de composição de calendário. É o número do Painel
    Estratégico ("Civil x Varejo"). Ver PLANO.md 3.12 e boardos/comparison.py.
    """
    with tenant_session(x_tenant_id) as cur:
        atual = _gold_mes(cur, ano, mes)
        base = _gold_mes(cur, ano - 1, mes)
    if not atual or not base:
        raise HTTPException(404, "Série insuficiente (falta o mês atual ou o do ano anterior).")
    res = comparison.compare(atual, base)
    res["periodo"] = {"tipo": "YoY", "atual": f"{ano}-{mes:02d}", "base": f"{ano-1}-{mes:02d}"}
    res["advisor"] = comparison.explain(res)
    return res
