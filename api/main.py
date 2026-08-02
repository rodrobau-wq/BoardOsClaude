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
from boardos.db import tenant_session  # noqa: E402
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
        cur.execute(
            """
            SELECT data, ano_civil, mes_civil, dow_label, is_fim_semana,
                   retail_year, retail_week, qtd_mesmo_dow_no_mes,
                   faturamento_liq, cupons, itens,
                   ticket_medio, itens_por_cupom, margem_pct
              FROM v_kpi_diario
             WHERE categoria_id IS NULL
               AND data BETWEEN %s AND %s
             ORDER BY data
            """,
            (data_de, data_ate),
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
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
