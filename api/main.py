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

from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from boardos.db import tenant_session  # noqa: E402

app = FastAPI(title="BoardOS API", version="0.0.0-m0")


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
