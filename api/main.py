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

from typing import Dict, Optional  # noqa: E402

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from boardos import advisor, comparison, descoberta as desc, forecast as fc  # noqa: E402
from boardos.auth import decode_token, hash_password, make_token, verify_password  # noqa: E402
from boardos.db import platform_session, tenant_session  # noqa: E402

app = FastAPI(title="BoardOS API", version="0.4.0")

# CORS restrito aos domínios do painel (override por env p/ novos domínios)
_ORIGENS = os.environ.get(
    "BOARDOS_CORS_ORIGINS",
    "https://boardos-painel.onrender.com,http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ORIGENS if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
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


# Rate-limit simples do login (in-memory): 5 falhas por e-mail em 60s => 429.
_LOGIN_FAILS: dict = {}
_LOGIN_MAX, _LOGIN_JANELA = 5, 60.0


def _login_bloqueado(email: str) -> bool:
    import time as _t
    agora = _t.time()
    falhas = [t for t in _LOGIN_FAILS.get(email, []) if agora - t < _LOGIN_JANELA]
    _LOGIN_FAILS[email] = falhas
    return len(falhas) >= _LOGIN_MAX


def _login_falhou(email: str) -> None:
    import time as _t
    _LOGIN_FAILS.setdefault(email, []).append(_t.time())


@app.post("/auth/login")
def login(body: LoginIn):
    email_norm = body.email.strip().lower()
    if _login_bloqueado(email_norm):
        raise HTTPException(429, "Muitas tentativas. Aguarde um minuto e tente de novo.")
    with platform_session() as cur:
        cur.execute(
            "SELECT email, senha_hash, nome, tenant_id, papel "
            "FROM platform.usuario_login WHERE lower(email)=lower(%s)",
            (body.email,),
        )
        row = cur.fetchone()
    if not row or not verify_password(body.senha, row[1]):
        _login_falhou(email_norm)
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
                   sum(margem) AS margem,
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
            r["margem"] = float(r["margem"]) if r["margem"] is not None else 0.0
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
def _lojas_mes(cur, ano: int, mes: int):
    """Faturamento + variação YoY (civil/ajustada) por loja no mês."""
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
    return lojas


@app.get("/lojas/resumo")
def lojas_resumo(ano: int, mes: int, tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        lojas = _lojas_mes(cur, ano, mes)
    return {"periodo": f"{ano}-{mes:02d}", "lojas": lojas}


# ---------------------------------------- módulo de Plano (1.2–1.5)
class DescobertaIn(BaseModel):
    respostas: Dict[str, str]


class DirecaoIn(BaseModel):
    proposito: Optional[str] = None
    visao: Optional[str] = None
    valores: Optional[str] = None
    objetivo_lp: Optional[str] = None


class SwotIn(BaseModel):
    quadrante: str
    texto: str


class RadarIn(BaseModel):
    notas: Dict[str, int]


class AcaoIn(BaseModel):
    oque: str
    porque: Optional[str] = None
    onde: Optional[str] = None
    quando: Optional[str] = None
    quem: Optional[str] = None
    como: Optional[str] = None
    quanto: Optional[float] = None
    status: str = "planejada"
    objetivo_id: Optional[str] = None


RADAR_AREAS = ["Comercial/Vendas", "Marketing/Fidelização", "Operação/Pessoas",
               "Financeiro", "Inovação"]


@app.get("/descoberta")
def descoberta_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT respostas, resumo FROM descoberta WHERE tenant_id=%s", (tid,))
        row = cur.fetchone()
    return {"perguntas": desc.PERGUNTAS, "obrigatorias": list(desc.OBRIGATORIAS),
            "respostas": (row[0] if row else {}) or {},
            "resumo": row[1] if row else None}


@app.put("/descoberta")
def descoberta_put(body: DescobertaIn, user: dict = Depends(current),
                   tid: str = Depends(tenant_of)):
    _can_edit(user)
    import json as _json
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO descoberta (tenant_id, respostas, atualizado_em) "
            "VALUES (%s,%s,now()) ON CONFLICT (tenant_id) DO UPDATE SET "
            "respostas=EXCLUDED.respostas, atualizado_em=now()",
            (tid, _json.dumps(body.respostas)))
    return {"ok": True}


@app.post("/descoberta/resumo")
def descoberta_resumo(user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT respostas FROM descoberta WHERE tenant_id=%s", (tid,))
        row = cur.fetchone()
        respostas = (row[0] if row else {}) or {}
        faltam = [k for k in desc.OBRIGATORIAS if not (respostas.get(k) or "").strip()]
        if faltam:
            raise HTTPException(400, f"Responda antes as perguntas obrigatórias: {', '.join(faltam)}.")
        qa = {p["k"]: {"pergunta": p["q"], "resposta": respostas.get(p["k"], "")}
              for p in desc.PERGUNTAS}
        texto = advisor.gerar_resumo_descoberta(qa)
        fonte = "ia" if texto else "modelo"
        if not texto:
            texto = desc.resumo_fallback(respostas)
        cur.execute("UPDATE descoberta SET resumo=%s, atualizado_em=now() WHERE tenant_id=%s",
                    (texto, tid))
    return {"resumo": texto, "fonte": fonte}


@app.get("/direcao")
def direcao_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT proposito, visao, valores, objetivo_lp "
                    "FROM direcao_estrategica WHERE tenant_id=%s", (tid,))
        row = cur.fetchone()
    campos = ["proposito", "visao", "valores", "objetivo_lp"]
    return dict(zip(campos, row)) if row else {c: None for c in campos}


@app.put("/direcao")
def direcao_put(body: DirecaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO direcao_estrategica (tenant_id, proposito, visao, valores, objetivo_lp, atualizado_em) "
            "VALUES (%s,%s,%s,%s,%s,now()) ON CONFLICT (tenant_id) DO UPDATE SET "
            "proposito=EXCLUDED.proposito, visao=EXCLUDED.visao, valores=EXCLUDED.valores, "
            "objetivo_lp=EXCLUDED.objetivo_lp, atualizado_em=now()",
            (tid, body.proposito, body.visao, body.valores, body.objetivo_lp))
    return {"ok": True}


@app.get("/swot")
def swot_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, quadrante, texto FROM swot_item ORDER BY quadrante, ordem, criado_em")
        itens = [{"id": str(r[0]), "quadrante": r[1], "texto": r[2]} for r in cur.fetchall()]
    return {"itens": itens}


@app.post("/swot")
def swot_post(body: SwotIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if body.quadrante not in ("forca", "fraqueza", "oportunidade", "ameaca"):
        raise HTTPException(400, "Quadrante inválido.")
    if not body.texto.strip():
        raise HTTPException(400, "Escreva o item.")
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO swot_item (tenant_id, quadrante, texto, ordem) "
            "SELECT %s,%s,%s, COALESCE(max(ordem)+1,0) FROM swot_item WHERE quadrante=%s "
            "RETURNING id",
            (tid, body.quadrante, body.texto.strip(), body.quadrante))
        sid = cur.fetchone()[0]
    return {"id": str(sid)}


@app.delete("/swot/{sid}")
def swot_delete(sid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM swot_item WHERE id=%s", (sid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Item não encontrado.")
    return {"ok": True}


@app.get("/radar")
def radar_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT area, nota FROM radar_nota")
        notas = {r[0]: r[1] for r in cur.fetchall()}
    return {"areas": RADAR_AREAS, "notas": notas}


@app.put("/radar")
def radar_put(body: RadarIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        for area, nota in body.notas.items():
            if not (0 <= int(nota) <= 10):
                raise HTTPException(400, f"Nota de {area} deve ser 0–10.")
            cur.execute(
                "INSERT INTO radar_nota (tenant_id, area, nota) VALUES (%s,%s,%s) "
                "ON CONFLICT (tenant_id, area) DO UPDATE SET nota=EXCLUDED.nota",
                (tid, area, int(nota)))
    return {"ok": True}


@app.get("/acoes")
def acoes_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute(
            "SELECT a.id, a.oque, a.porque, a.onde, a.quando, a.quem, a.como, a.quanto, "
            "a.status, a.objetivo_id, o.titulo "
            "FROM acao_5w2h a LEFT JOIN okr_objetivo o ON o.id=a.objetivo_id "
            "ORDER BY (a.status IN ('concluida','cancelada')), a.quando NULLS LAST, a.criado_em")
        cols = ["id", "oque", "porque", "onde", "quando", "quem", "como", "quanto",
                "status", "objetivo_id", "objetivo"]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["id"] = str(d["id"])
            d["quando"] = str(d["quando"]) if d["quando"] else None
            d["quanto"] = float(d["quanto"]) if d["quanto"] is not None else None
            d["objetivo_id"] = str(d["objetivo_id"]) if d["objetivo_id"] else None
            rows.append(d)
    return {"acoes": rows}


@app.post("/acoes")
def acoes_post(body: AcaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.oque.strip():
        raise HTTPException(400, "Descreva a ação (O quê).")
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO acao_5w2h (tenant_id, objetivo_id, oque, porque, onde, quando, quem, como, quanto, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (tid, body.objetivo_id, body.oque.strip(), body.porque, body.onde,
             body.quando or None, body.quem, body.como, body.quanto, body.status))
        aid = cur.fetchone()[0]
    return {"id": str(aid)}


@app.put("/acoes/{aid}")
def acoes_put(aid: str, body: AcaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "UPDATE acao_5w2h SET oque=%s, porque=%s, onde=%s, quando=%s, quem=%s, "
            "como=%s, quanto=%s, status=%s, objetivo_id=%s WHERE id=%s",
            (body.oque.strip(), body.porque, body.onde, body.quando or None,
             body.quem, body.como, body.quanto, body.status, body.objetivo_id, aid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ação não encontrada.")
    return {"ok": True}


@app.delete("/acoes/{aid}")
def acoes_delete(aid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM acao_5w2h WHERE id=%s", (aid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ação não encontrada.")
    return {"ok": True}


# ------------------------------------------------- gestão de usuários
class UsuarioIn(BaseModel):
    email: str
    nome: Optional[str] = None
    papel: str = "estrategico"
    senha: Optional[str] = None      # obrigatória ao criar; opcional ao editar (reset)


PAPEIS_TENANT = ("admin_tenant", "estrategico", "tatico", "operacional")


def _admin_do_tenant(user: dict) -> None:
    if user.get("papel") not in ("super_admin", "admin_tenant"):
        raise HTTPException(403, "Somente o administrador pode gerir usuários.")


@app.get("/usuarios")
def usuarios_list(user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _admin_do_tenant(user)
    with platform_session() as cur:
        cur.execute(
            "SELECT email, nome, papel, criado_em FROM platform.usuario_login "
            "WHERE tenant_id = %s ORDER BY criado_em", (tid,))
        rows = [{"email": r[0], "nome": r[1], "papel": r[2],
                 "criado_em": str(r[3])} for r in cur.fetchall()]
    return {"usuarios": rows}


@app.post("/usuarios")
def usuarios_create(body: UsuarioIn, user: dict = Depends(current),
                    tid: str = Depends(tenant_of)):
    _admin_do_tenant(user)
    if body.papel not in PAPEIS_TENANT:
        raise HTTPException(400, "Papel inválido.")
    if not body.senha or len(body.senha) < 8:
        raise HTTPException(400, "Defina uma senha inicial com pelo menos 8 caracteres.")
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "E-mail inválido.")
    with platform_session() as cur:
        cur.execute("SELECT 1 FROM platform.usuario_login WHERE lower(email)=%s", (email,))
        if cur.fetchone():
            raise HTTPException(409, "Já existe um usuário com esse e-mail.")
        cur.execute(
            "INSERT INTO platform.usuario_login (email, senha_hash, nome, tenant_id, papel) "
            "VALUES (%s,%s,%s,%s,%s)",
            (email, hash_password(body.senha), body.nome, tid, body.papel))
    return {"ok": True}


@app.put("/usuarios/{email}")
def usuarios_update(email: str, body: UsuarioIn, user: dict = Depends(current),
                    tid: str = Depends(tenant_of)):
    _admin_do_tenant(user)
    if body.papel not in PAPEIS_TENANT:
        raise HTTPException(400, "Papel inválido.")
    if body.senha and len(body.senha) < 8:
        raise HTTPException(400, "A nova senha precisa de pelo menos 8 caracteres.")
    with platform_session() as cur:
        if body.senha:
            cur.execute(
                "UPDATE platform.usuario_login SET nome=%s, papel=%s, senha_hash=%s "
                "WHERE lower(email)=lower(%s) AND tenant_id=%s",
                (body.nome, body.papel, hash_password(body.senha), email, tid))
        else:
            cur.execute(
                "UPDATE platform.usuario_login SET nome=%s, papel=%s "
                "WHERE lower(email)=lower(%s) AND tenant_id=%s",
                (body.nome, body.papel, email, tid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Usuário não encontrado nesta empresa.")
    return {"ok": True}


@app.delete("/usuarios/{email}")
def usuarios_delete(email: str, user: dict = Depends(current),
                    tid: str = Depends(tenant_of)):
    _admin_do_tenant(user)
    if email.strip().lower() == str(user.get("sub", "")).lower():
        raise HTTPException(400, "Você não pode excluir o próprio usuário.")
    with platform_session() as cur:
        cur.execute(
            "DELETE FROM platform.usuario_login WHERE lower(email)=lower(%s) AND tenant_id=%s",
            (email, tid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Usuário não encontrado nesta empresa.")
    return {"ok": True}


class TrocaSenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str


@app.post("/auth/trocar-senha")
def trocar_senha(body: TrocaSenhaIn, user: dict = Depends(current)):
    if len(body.senha_nova) < 8:
        raise HTTPException(400, "A nova senha precisa de pelo menos 8 caracteres.")
    with platform_session() as cur:
        cur.execute("SELECT senha_hash FROM platform.usuario_login WHERE lower(email)=lower(%s)",
                    (user["sub"],))
        row = cur.fetchone()
        if not row or not verify_password(body.senha_atual, row[0]):
            raise HTTPException(401, "Senha atual incorreta.")
        cur.execute("UPDATE platform.usuario_login SET senha_hash=%s WHERE lower(email)=lower(%s)",
                    (hash_password(body.senha_nova), user["sub"]))
    return {"ok": True}


# ---------------------------------------------------- Advisor com IA
@app.get("/advisor/insight")
def advisor_insight(tid: str = Depends(tenant_of)):
    """Leitura executiva do último mês gerada por IA (Claude), com fallback.

    fonte="ia": texto narrativo gerado sobre os números reais do tenant.
    fonte="motor": sem chave/erro — o painel usa o Fato/Causa/Ação estatístico.
    """
    with tenant_session(tid) as cur:
        cur.execute("SELECT max(data) FROM gold_venda_diaria")
        row = cur.fetchone()
        ult = row[0] if row else None
        if not ult:
            return {"fonte": "motor"}
        yoy = _yoy_do_ultimo_mes(cur)
        lojas = _lojas_mes(cur, ult.year, ult.month)
        cur.execute(
            "SELECT k.titulo, k.meta, k.atual, k.base, k.direcao, k.fonte, o.titulo "
            "FROM okr_kr k JOIN okr_objetivo o ON o.id=k.objetivo_id ORDER BY k.ordem")
        metas = []
        for kt, meta, atual, base, direcao, fonte, ot in cur.fetchall():
            a = float(atual)
            auto = _kr_auto(fonte, yoy) if fonte else None
            if auto is not None:
                a = auto
            prog, farol = _kr_progresso(meta, a, base, direcao)
            metas.append({"objetivo": ot, "kr": kt, "meta": float(meta),
                          "atual": a, "progresso": prog, "farol": farol})

    if not yoy:
        return {"fonte": "motor"}
    contexto = {
        "mes_referencia": f"{ult.year}-{ult.month:02d}",
        "comparacao_yoy": {
            "faturamento_total": yoy["total_atual"],
            "var_civil_pct": round(yoy["var_civil"] * 100, 1),
            "var_varejo_ajustada_pct": round(yoy["var_ajustada"] * 100, 1),
            "efeito_calendario_pp": round(yoy["efeito_calendario"] * 100, 1),
            "dias_ganhos": yoy["dias_ganhos"], "dias_perdidos": yoy["dias_perdidos"],
            "ticket_atual": yoy.get("ticket_atual"), "ticket_ano_anterior": yoy.get("ticket_base"),
        },
        "lojas": [{"nome": l["nome"], "faturamento": l["faturamento"],
                   "var_civil_pct": round(l["var_civil"] * 100, 1) if l["var_civil"] is not None else None,
                   "var_varejo_pct": round(l["var_ajustada"] * 100, 1) if l["var_ajustada"] is not None else None}
                  for l in lojas],
        "metas": metas,
    }
    texto = advisor.gerar_insight(contexto, cache_key=f"{tid}:{ult.isoformat()}")
    if texto:
        return {"fonte": "ia", "texto": texto}
    return {"fonte": "motor"}


# -------------------------------------------- forecast + categorias
@app.get("/forecast/mes")
def forecast_mes_api(ano: int, mes: int, tid: str = Depends(tenant_of)):
    """Projeção do restante do mês (média por dia-da-semana das últimas semanas).

    cutoff = hoje (ou o fim do mês, se já fechou). previsto=[] quando não há
    nada a projetar ou não há histórico suficiente.
    """
    import calendar as _cal
    from datetime import date as _date, timedelta as _td
    primeiro = _date(ano, mes, 1)
    ultimo = _date(ano, mes, _cal.monthrange(ano, mes)[1])
    cutoff = min(_date.today(), ultimo)
    if cutoff < primeiro:
        return {"cutoff": None, "realizado": [], "previsto": [],
                "total_realizado": 0, "total_previsto": 0, "total_projetado": 0}
    ini = primeiro - _td(days=42)
    with tenant_session(tid) as cur:
        cur.execute(
            "SELECT data, sum(faturamento_liq) FROM gold_venda_diaria "
            "WHERE categoria_id IS NULL AND data BETWEEN %s AND %s "
            "GROUP BY data ORDER BY data", (ini, cutoff))
        hist = [{"data": r[0], "faturamento_liq": float(r[1])} for r in cur.fetchall()]
    r = fc.forecast_mes(hist, ano, mes, cutoff=cutoff)
    return {
        "cutoff": str(r["cutoff"]),
        "realizado": [{"data": str(x["data"]), "valor": x["valor"]} for x in r["realizado"]],
        "previsto": [{"data": str(x["data"]), "valor": x["valor"]} for x in r["previsto"]],
        "total_realizado": r["total_realizado"],
        "total_previsto": r["total_previsto"],
        "total_projetado": r["total_projetado"],
    }


@app.get("/categorias/resumo")
def categorias_resumo(ano: int, mes: int, tid: str = Depends(tenant_of)):
    """Drill-down por categoria no mês: faturamento, participação e YoY."""
    with tenant_session(tid) as cur:
        cur.execute(
            """
            SELECT c.id, c.nome, g.data, sum(g.faturamento_liq), sum(g.cupons), sum(g.itens)
              FROM gold_venda_diaria g JOIN categoria c ON c.id = g.categoria_id
             WHERE date_trunc('month', g.data) IN (make_date(%s,%s,1), make_date(%s,%s,1))
             GROUP BY c.id, c.nome, g.data ORDER BY c.nome, g.data
            """,
            (ano, mes, ano - 1, mes))
        por_cat: dict = {}
        for cid, nome, d, fat, cup, itn in cur.fetchall():
            key = str(cid)
            por_cat.setdefault(key, {"nome": nome, "atual": [], "base": []})
            rec = {"data": d, "faturamento_liq": float(fat),
                   "cupons": int(cup), "itens": int(itn)}
            (por_cat[key]["atual"] if d.year == ano else por_cat[key]["base"]).append(rec)

    cats = []
    for v in por_cat.values():
        fat = sum(r["faturamento_liq"] for r in v["atual"])
        item = {"nome": v["nome"], "faturamento": round(fat, 2),
                "var_civil": None, "var_ajustada": None}
        if v["atual"] and v["base"]:
            r = comparison.compare(v["atual"], v["base"])
            item["var_civil"] = r["var_civil"]
            item["var_ajustada"] = r["var_ajustada"]
        cats.append(item)
    total = sum(c["faturamento"] for c in cats) or 1.0
    for c in cats:
        c["participacao"] = round(c["faturamento"] / total, 4)
    cats.sort(key=lambda x: -x["faturamento"])
    return {"periodo": f"{ano}-{mes:02d}", "categorias": cats}


# ------------------------------------------------- alertas + Ciclo FCA
@app.get("/alertas")
def alertas(tid: str = Depends(tenant_of)):
    """Desvios que precisam de atenção, calculados do dado real.
    Cada alerta pode virar um ciclo FCA no painel."""
    itens = []
    with tenant_session(tid) as cur:
        cur.execute("SELECT max(data) FROM gold_venda_diaria")
        row = cur.fetchone()
        ult = row[0] if row else None
        yoy = _yoy_do_ultimo_mes(cur)
        if yoy:
            if yoy["var_ajustada"] < 0:
                itens.append({"sev": "r", "kpi": "venda_comparavel",
                              "titulo": "Venda comparável em queda",
                              "detalhe": f"Venda ajustada por calendário {yoy['var_ajustada']*100:+.1f}% vs. ano anterior no último mês."})
            if abs(yoy["efeito_calendario"]) >= 0.02:
                itens.append({"sev": "a", "kpi": "calendario",
                              "titulo": "Efeito de calendário relevante",
                              "detalhe": f"O fechamento civil difere {yoy['efeito_calendario']*100:+.1f}pp do desempenho real — usar a lente Varejo na leitura do mês."})
        if ult:
            for lj in _lojas_mes(cur, ult.year, ult.month):
                if lj["var_ajustada"] is not None and lj["var_ajustada"] <= -0.03:
                    itens.append({"sev": "r", "kpi": "venda_loja",
                                  "titulo": f"Queda real de venda — {lj['nome']}",
                                  "detalhe": f"{lj['nome']}: venda comparável {lj['var_ajustada']*100:+.1f}% vs. ano anterior."})
        # KRs no vermelho
        cur.execute("SELECT k.titulo, k.meta, k.atual, k.base, k.direcao, k.fonte, o.titulo "
                    "FROM okr_kr k JOIN okr_objetivo o ON o.id=k.objetivo_id")
        for kt, meta, atual, base, direcao, fonte, ot in cur.fetchall():
            a = float(atual)
            auto = _kr_auto(fonte, yoy) if fonte else None
            if auto is not None:
                a = auto
            prog, farol = _kr_progresso(meta, a, base, direcao)
            if farol == "r":
                itens.append({"sev": "r", "kpi": "okr",
                              "titulo": f"Meta fora da rota — {kt}",
                              "detalhe": f"KR \"{kt}\" ({ot}): atual {a:g} vs. meta {float(meta):g} — progresso {prog*100:.0f}%."})
    return {"alertas": itens}


class FcaIn(BaseModel):
    titulo: str
    fato: Optional[str] = None
    causa: Optional[str] = None
    acao: Optional[str] = None
    responsavel: Optional[str] = None
    prazo: Optional[str] = None
    status: str = "aberto"
    kpi: Optional[str] = None
    origem: str = "manual"
    resultado: Optional[str] = None


@app.get("/fca")
def fca_list(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute(
            "SELECT id, titulo, fato, causa, acao, responsavel, prazo, status, kpi, origem, resultado "
            "FROM fca_ciclo ORDER BY (status IN ('resolvido','descartado')), criado_em DESC")
        cols = ["id", "titulo", "fato", "causa", "acao", "responsavel", "prazo",
                "status", "kpi", "origem", "resultado"]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["id"] = str(r["id"])
            r["prazo"] = str(r["prazo"]) if r["prazo"] else None
    return {"ciclos": rows}


@app.post("/fca")
def fca_create(body: FcaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO fca_ciclo (tenant_id, titulo, fato, causa, acao, responsavel, prazo, status, kpi, origem, resultado) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (tid, body.titulo, body.fato, body.causa, body.acao, body.responsavel,
             body.prazo or None, body.status, body.kpi, body.origem, body.resultado))
        fid = cur.fetchone()[0]
    return {"id": str(fid)}


@app.put("/fca/{fid}")
def fca_update(fid: str, body: FcaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "UPDATE fca_ciclo SET titulo=%s, fato=%s, causa=%s, acao=%s, responsavel=%s, "
            "prazo=%s, status=%s, kpi=%s, resultado=%s, atualizado_em=now() WHERE id=%s",
            (body.titulo, body.fato, body.causa, body.acao, body.responsavel,
             body.prazo or None, body.status, body.kpi, body.resultado, fid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ciclo não encontrado.")
    return {"ok": True}


@app.delete("/fca/{fid}")
def fca_delete(fid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM fca_ciclo WHERE id=%s", (fid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ciclo não encontrado.")
    return {"ok": True}
