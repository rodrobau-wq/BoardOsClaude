"""API do BoardOS.

Autenticação real: o cliente faz login e recebe um token JWT; o servidor deriva
o TENANT do token (o cliente nunca escolhe o tenant). Toda leitura de dados roda
dentro de `tenant_session`, com RLS no banco garantindo o isolamento.

Rodar:  uvicorn api.main:app --reload
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional  # noqa: E402

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from boardos import comparison  # noqa: E402
from boardos.auth import decode_token, make_token, verify_password  # noqa: E402
from boardos.db import platform_session, tenant_session  # noqa: E402

app = FastAPI(title="BoardOS API", version="0.3.0-auth")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # restringir aos domínios do painel em produção
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_bearer = HTTPBearer(auto_error=False)


def current(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Usuário autenticado a partir do token. 401 se ausente/inválido."""
    if creds is None:
        raise HTTPException(401, "Autenticação necessária.")
    try:
        return decode_token(creds.credentials)
    except Exception:
        raise HTTPException(401, "Sessão inválida ou expirada. Faça login novamente.")


def tenant_of(user: dict = Depends(current),
              x_tenant: Optional[str] = Header(None, alias="X-Tenant-Id")) -> str:
    """Tenant efetivo da requisição.

    Usuário comum: SEMPRE o tenant do token (header é ignorado).
    super_admin: escolhe a empresa via X-Tenant-Id (acesso a todas as bases).
    """
    if user.get("papel") == "super_admin":
        if not x_tenant:
            raise HTTPException(400, "Admin da plataforma: selecione a empresa (X-Tenant-Id).")
        return x_tenant
    return user["tenant_id"]


# ----------------------------------------------------------------- saúde
@app.get("/health")
def health():
    return {"ok": True, "service": "boardos", "stage": "auth"}


# ----------------------------------------------------------------- login
class LoginIn(BaseModel):
    email: str
    senha: str


@app.post("/auth/login")
def login(body: LoginIn):
    with platform_session() as cur:
        cur.execute(
            "SELECT email, senha_hash, nome, tenant_id, papel "
            "FROM platform.usuario_login WHERE lower(email)=lower(%s)",
            (body.email,),
        )
        row = cur.fetchone()
    if not row or not verify_password(body.senha, row[1]):
        raise HTTPException(401, "E-mail ou senha inválidos.")
    tenant_id = str(row[3]) if row[3] else ""   # super_admin não tem tenant fixo
    tenant = None
    if tenant_id:
        with platform_session() as cur:
            cur.execute("SELECT nome FROM platform.tenant WHERE id=%s", (tenant_id,))
            tenant = {"id": tenant_id, "nome": (cur.fetchone() or ["—"])[0]}
    token = make_token(sub=row[0], nome=row[2], tenant_id=tenant_id, papel=row[4])
    return {"token": token,
            "user": {"email": row[0], "nome": row[2], "papel": row[4]},
            "tenant": tenant}


@app.get("/me")
def me(user: dict = Depends(current)):
    tenant = None
    if user.get("tenant_id"):
        with platform_session() as cur:
            cur.execute("SELECT nome FROM platform.tenant WHERE id=%s", (user["tenant_id"],))
            tenant = {"id": user["tenant_id"], "nome": (cur.fetchone() or ["—"])[0]}
    return {"user": {"email": user["sub"], "nome": user.get("nome"), "papel": user.get("papel")},
            "tenant": tenant}


@app.get("/tenants")
def tenants(user: dict = Depends(current)):
    """Lista todas as empresas — SOMENTE para o super-admin da plataforma."""
    if user.get("papel") != "super_admin":
        raise HTTPException(403, "Acesso restrito ao administrador da plataforma.")
    with platform_session() as cur:
        cur.execute("SELECT id, nome, status FROM platform.tenant ORDER BY nome")
        rows = [{"id": str(r[0]), "nome": r[1], "status": r[2]} for r in cur.fetchall()]
    return {"tenants": rows}


# ------------------------------------------------------------------ OKRs
def _kr_progresso(meta, atual, base, direcao):
    meta = float(meta); atual = float(atual)
    base = float(base) if base is not None else None
    if base is not None and meta != base:
        p = (atual - base) / (meta - base)
    elif direcao == "up":
        p = atual / meta if meta else 0.0
    else:
        p = meta / atual if atual else 0.0
    p = max(0.0, min(p, 1.5))
    farol = "g" if p >= 0.7 else "a" if p >= 0.4 else "r"
    return round(p, 3), farol


def _yoy_do_ultimo_mes(cur):
    """Comparação YoY do mês mais recente com dados no gold (None se faltar série)."""
    cur.execute("SELECT max(data) FROM gold_venda_diaria")
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    ult = row[0]
    atual = _gold_mes(cur, ult.year, ult.month)
    base = _gold_mes(cur, ult.year - 1, ult.month)
    if not atual or not base:
        return None
    return comparison.compare(atual, base)


def _kr_auto(fonte: str, yoy: dict):
    """Valor 'atual' calculado do dado real, conforme a fonte do KR."""
    if not yoy:
        return None
    if fonte == "fat_yoy_pct":
        return round(yoy["var_ajustada"] * 100, 1)
    if fonte == "ticket_yoy_pct":
        ta, tb = yoy.get("ticket_atual"), yoy.get("ticket_base")
        if ta and tb:
            return round((ta / tb - 1) * 100, 1)
    return None


@app.get("/okrs")
def okrs(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        yoy = _yoy_do_ultimo_mes(cur)
        cur.execute("SELECT id, titulo, periodo, nivel, owner FROM okr_objetivo ORDER BY ordem, criado_em")
        objs = [{"id": str(r[0]), "titulo": r[1], "periodo": r[2],
                 "nivel": r[3], "owner": r[4], "krs": []} for r in cur.fetchall()]
        by_id = {o["id"]: o for o in objs}
        cur.execute("SELECT objetivo_id, titulo, unidade, meta, atual, base, direcao, fonte, id "
                    "FROM okr_kr ORDER BY ordem")
        for r in cur.fetchall():
            oid = str(r[0])
            if oid not in by_id:
                continue
            atual = float(r[4])
            auto = _kr_auto(r[7], yoy) if r[7] else None
            if auto is not None:
                atual = auto
            prog, farol = _kr_progresso(r[3], atual, r[5], r[6])
            by_id[oid]["krs"].append({"id": str(r[8]), "titulo": r[1], "unidade": r[2],
                                      "meta": float(r[3]), "atual": atual,
                                      "base": float(r[5]) if r[5] is not None else None,
                                      "direcao": r[6], "fonte": r[7],
                                      "progresso": prog, "farol": farol,
                                      "auto": auto is not None})
    return {"objetivos": objs}


# ------------------------------------------------------ OKRs: edição (CRUD)
class ObjetivoIn(BaseModel):
    titulo: str
    periodo: Optional[str] = None
    nivel: str = "corporativo"
    owner: Optional[str] = None


class KrIn(BaseModel):
    titulo: str
    unidade: Optional[str] = None
    meta: float
    atual: float = 0
    base: Optional[float] = None
    direcao: str = "up"
    fonte: Optional[str] = None


def _can_edit(user: dict) -> None:
    if user.get("papel") not in ("super_admin", "admin_tenant", "estrategico"):
        raise HTTPException(403, "Seu papel não permite editar metas.")


@app.post("/okrs/objetivo")
def criar_objetivo(body: ObjetivoIn, user: dict = Depends(current),
                   tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO okr_objetivo (tenant_id, titulo, periodo, nivel, owner, ordem) "
            "SELECT %s,%s,%s,%s,%s, COALESCE(max(ordem)+1,0) FROM okr_objetivo "
            "RETURNING id",
            (tid, body.titulo, body.periodo, body.nivel, body.owner))
        oid = cur.fetchone()[0]
    return {"id": str(oid)}


@app.put("/okrs/objetivo/{oid}")
def editar_objetivo(oid: str, body: ObjetivoIn, user: dict = Depends(current),
                    tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "UPDATE okr_objetivo SET titulo=%s, periodo=%s, nivel=%s, owner=%s WHERE id=%s",
            (body.titulo, body.periodo, body.nivel, body.owner, oid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Objetivo não encontrado.")
    return {"ok": True}


@app.delete("/okrs/objetivo/{oid}")
def excluir_objetivo(oid: str, user: dict = Depends(current),
                     tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM okr_objetivo WHERE id=%s", (oid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Objetivo não encontrado.")
    return {"ok": True}


@app.post("/okrs/objetivo/{oid}/kr")
def criar_kr(oid: str, body: KrIn, user: dict = Depends(current),
             tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT 1 FROM okr_objetivo WHERE id=%s", (oid,))
        if not cur.fetchone():
            raise HTTPException(404, "Objetivo não encontrado.")
        cur.execute(
            "INSERT INTO okr_kr (tenant_id, objetivo_id, titulo, unidade, meta, atual, base, direcao, fonte, ordem) "
            "SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s, COALESCE(max(ordem)+1,0) FROM okr_kr WHERE objetivo_id=%s "
            "RETURNING id",
            (tid, oid, body.titulo, body.unidade, body.meta, body.atual,
             body.base, body.direcao, body.fonte, oid))
        kid = cur.fetchone()[0]
    return {"id": str(kid)}


@app.put("/okrs/kr/{kid}")
def editar_kr(kid: str, body: KrIn, user: dict = Depends(current),
              tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "UPDATE okr_kr SET titulo=%s, unidade=%s, meta=%s, atual=%s, base=%s, "
            "direcao=%s, fonte=%s WHERE id=%s",
            (body.titulo, body.unidade, body.meta, body.atual, body.base,
             body.direcao, body.fonte, kid))
        if cur.rowcount == 0:
            raise HTTPException(404, "KR não encontrado.")
    return {"ok": True}


@app.delete("/okrs/kr/{kid}")
def excluir_kr(kid: str, user: dict = Depends(current),
               tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM okr_kr WHERE id=%s", (kid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "KR não encontrado.")
    return {"ok": True}


# ------------------------------------------------------------- KPI diário
@app.get("/kpi/diario")
def kpi_diario(data_de: str, data_ate: str, tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute(
            """
            SELECT data,
                   sum(faturamento_liq) AS faturamento_liq,
                   sum(cupons) AS cupons, sum(itens) AS itens,
                   max(dow_label) AS dow_label, bool_or(is_fim_semana) AS is_fim_semana,
                   max(retail_year) AS retail_year, max(retail_week) AS retail_week
              FROM v_kpi_diario
             WHERE categoria_id IS NULL AND data BETWEEN %s AND %s
             GROUP BY data ORDER BY data
            """,
            (data_de, data_ate),
        )
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["data"] = str(r["data"])
            r["faturamento_liq"] = float(r["faturamento_liq"])
    if not rows:
        raise HTTPException(404, "Sem dados no período.")
    return {"periodo": [data_de, data_ate], "dias": rows}


# ------------------------------------------------------ comparação YoY
def _gold_mes(cur, ano: int, mes: int):
    cur.execute(
        """
        SELECT data, sum(faturamento_liq), sum(cupons), sum(itens)
          FROM gold_venda_diaria
         WHERE categoria_id IS NULL AND date_trunc('month', data) = make_date(%s, %s, 1)
         GROUP BY data ORDER BY data
        """,
        (ano, mes),
    )
    return [{"data": r[0], "faturamento_liq": float(r[1]), "cupons": int(r[2]), "itens": int(r[3])}
            for r in cur.fetchall()]


@app.get("/comparacao/yoy")
def comparacao_yoy(ano: int, mes: int, tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        atual = _gold_mes(cur, ano, mes)
        base = _gold_mes(cur, ano - 1, mes)
    if not atual or not base:
        raise HTTPException(404, "Série insuficiente (falta o mês atual ou o do ano anterior).")
    res = comparison.compare(atual, base)
    res["periodo"] = {"tipo": "YoY", "atual": f"{ano}-{mes:02d}", "base": f"{ano-1}-{mes:02d}"}
    res["advisor"] = comparison.explain(res)
    return res


# --------------------------------------------------- drill-down por loja
@app.get("/lojas/resumo")
def lojas_resumo(ano: int, mes: int, tid: str = Depends(tenant_of)):
    """Resumo por loja no mês: faturamento + variação YoY civil e ajustada."""
    with tenant_session(tid) as cur:
        cur.execute(
            """
            SELECT l.id, l.nome, g.data, g.faturamento_liq, g.cupons, g.itens
              FROM gold_venda_diaria g JOIN loja l ON l.id = g.loja_id
             WHERE g.categoria_id IS NULL
               AND date_trunc('month', g.data) IN (make_date(%s,%s,1), make_date(%s,%s,1))
             ORDER BY l.nome, g.data
            """,
            (ano, mes, ano - 1, mes),
        )
        por_loja: dict = {}
        for lid, nome, d, fat, cup, itn in cur.fetchall():
            key = str(lid)
            por_loja.setdefault(key, {"nome": nome, "atual": [], "base": []})
            rec = {"data": d, "faturamento_liq": float(fat),
                   "cupons": int(cup), "itens": int(itn)}
            (por_loja[key]["atual"] if d.year == ano else por_loja[key]["base"]).append(rec)

    lojas = []
    for v in por_loja.values():
        fat = sum(r["faturamento_liq"] for r in v["atual"])
        item = {"nome": v["nome"], "faturamento": round(fat, 2),
                "var_civil": None, "var_ajustada": None}
        if v["atual"] and v["base"]:
            r = comparison.compare(v["atual"], v["base"])
            item["var_civil"] = r["var_civil"]
            item["var_ajustada"] = r["var_ajustada"]
        lojas.append(item)
    lojas.sort(key=lambda x: -x["faturamento"])
    return {"periodo": f"{ano}-{mes:02d}", "lojas": lojas}
