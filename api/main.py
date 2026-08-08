"""API do BoardOS.

Autenticação real: o cliente faz login e recebe um token JWT; o servidor deriva
o TENANT do token (o cliente nunca escolhe o tenant). Toda leitura de dados roda
dentro de `tenant_session`, com RLS no banco garantindo o isolamento.

Rodar:  uvicorn api.main:app --reload
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Optional  # noqa: E402

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from pydantic import BaseModel, field_validator  # noqa: E402

from boardos import advisor, agentes, comparison, descoberta as desc, forecast as fc, onboarding as onb  # noqa: E402
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
# versão implantada: commit do deploy (Render injeta RENDER_GIT_COMMIT) e
# hora do boot do processo (≈ hora do deploy; também muda em restart).
from datetime import datetime as _dt, timezone as _tz  # noqa: E402
DEPLOY_EM = _dt.now(_tz.utc)
VERSAO = (os.environ.get("RENDER_GIT_COMMIT") or "dev")[:7]


@app.get("/health")
def health():
    return {"ok": True, "service": "boardos", "stage": "auth",
            "versao": VERSAO, "deploy_em": DEPLOY_EM.isoformat()}


@app.get("/versao")
def versao():
    """Versão e hora do deploy da API (público — sem dado sensível)."""
    return {"api": VERSAO, "deploy_em": DEPLOY_EM.isoformat()}


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
            cur.execute("SELECT nome, status, trial_expira_em FROM platform.tenant WHERE id=%s",
                        (tenant_id,))
            trow = cur.fetchone()
        if trow and trow[1] == "cancelado":
            raise HTTPException(403, "O acesso desta empresa está suspenso. Fale com o suporte BoardOS.")
        if trow and trow[1] == "trial" and trow[2] is not None and trow[2] < _dt.now(_tz.utc):
            raise HTTPException(403, "Seu teste de 14 dias terminou. Fale com a gente para ativar seu plano.")
        tenant = {"id": tenant_id, "nome": trow[0] if trow else "—",
                  "status": trow[1] if trow else None,
                  "trial_expira_em": trow[2].isoformat() if trow and trow[2] else None,
                  "onboarding": _onboarding_estado(tenant_id)}
    exp_limite = trow[2] if (tenant_id and trow and trow[1] == "trial" and trow[2] is not None) else None
    token = make_token(sub=row[0], nome=row[2], tenant_id=tenant_id, papel=row[4], exp_limite=exp_limite)
    return {"token": token,
            "user": {"email": row[0], "nome": row[2], "papel": row[4]},
            "tenant": tenant}


def _onboarding_estado(tenant_id: str) -> Optional[str]:
    """pendente | confirmado | None (tenant sem linha de onboarding — antigo)."""
    with tenant_session(tenant_id) as cur:
        cur.execute("SELECT confirmado_em IS NOT NULL FROM jornada WHERE jornada='onboarding'")
        r = cur.fetchone()
    if r is None:
        return None
    return "confirmado" if r[0] else "pendente"


@app.get("/me")
def me(user: dict = Depends(current)):
    tenant = None
    if user.get("tenant_id"):
        with platform_session() as cur:
            cur.execute("SELECT nome, status, trial_expira_em FROM platform.tenant WHERE id=%s",
                        (user["tenant_id"],))
            trow = cur.fetchone()
        tenant = {"id": user["tenant_id"], "nome": trow[0] if trow else "—",
                  "status": trow[1] if trow else None,
                  "trial_expira_em": trow[2].isoformat() if trow and trow[2] else None,
                  "onboarding": _onboarding_estado(user["tenant_id"])}
    return {"user": {"email": user["sub"], "nome": user.get("nome"), "papel": user.get("papel")},
            "tenant": tenant}


def _super(user: dict) -> None:
    if user.get("papel") != "super_admin":
        raise HTTPException(403, "Acesso restrito ao administrador da plataforma.")


@app.get("/tenants")
def tenants(user: dict = Depends(current)):
    """Lista todas as empresas — SOMENTE para o super-admin da plataforma."""
    _super(user)
    with platform_session() as cur:
        cur.execute("SELECT id, nome, status FROM platform.tenant ORDER BY nome")
        rows = [{"id": str(r[0]), "nome": r[1], "status": r[2]} for r in cur.fetchall()]
    return {"tenants": rows}


class TenantIn(BaseModel):
    nome: str
    status: str = "ativo"
    admin_email: Optional[str] = None
    admin_senha: Optional[str] = None
    admin_nome: Optional[str] = None


TENANT_STATUS = ("trial", "ativo", "inadimplente", "cancelado")


def _provisionar_tenant(cur, nome: str, status: str = "trial", *,
                        segmento: Optional[str] = None, origem: str = "manual",
                        trial_dias: Optional[int] = None,
                        admin_email: Optional[str] = None,
                        admin_senha: Optional[str] = None,
                        admin_nome: Optional[str] = None):
    """Cria tenant + assinatura v0 (+ admin opcional) num cursor platform aberto.

    Devolve (tenant_id, slug, trial_expira_em|None). 409 se o e-mail já existir.
    """
    from boardos.crm import slugify
    base_slug = slugify(nome)
    slug = base_slug
    for i in range(2, 30):
        cur.execute("SELECT 1 FROM platform.tenant WHERE slug=%s", (slug,))
        if not cur.fetchone():
            break
        slug = f"{base_slug}-{i}"
    else:
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"   # muitos homônimos: sufixo único
    expira = None
    if trial_dias:
        cur.execute("SELECT now() + make_interval(days => %s)", (trial_dias,))
        expira = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO platform.tenant (nome, slug, status, segmento, origem, trial_expira_em) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (nome, slug, status, segmento, origem, expira))
    tid = str(cur.fetchone()[0])
    cur.execute(
        "INSERT INTO platform.assinatura (tenant_id, plano, base_mensal_cent, preco_por_1k_cent) "
        "VALUES (%s,'v0',49900,900)", (tid,))
    if admin_email:
        email = admin_email.strip().lower()
        cur.execute("SELECT 1 FROM platform.usuario_login WHERE lower(email)=%s", (email,))
        if cur.fetchone():
            raise HTTPException(409, "Já existe um usuário com esse e-mail.")
        cur.execute(
            "INSERT INTO platform.usuario_login (email, senha_hash, nome, tenant_id, papel) "
            "VALUES (%s,%s,%s,%s,'admin_tenant')",
            (email, hash_password(admin_senha), admin_nome, tid))
    return tid, slug, expira


@app.post("/tenants")
def tenant_create(body: TenantIn, user: dict = Depends(current)):
    """Cadastra uma nova empresa (tenant) — opcionalmente já com o admin inicial."""
    _super(user)
    nome = body.nome.strip()
    if not nome:
        raise HTTPException(400, "Informe o nome da empresa.")
    if body.status not in TENANT_STATUS:
        raise HTTPException(400, "Status inválido.")
    if body.admin_email and (not body.admin_senha or len(body.admin_senha) < 8):
        raise HTTPException(400, "Senha inicial do admin: mínimo 8 caracteres.")
    with platform_session() as cur:
        tid, slug, _ = _provisionar_tenant(
            cur, nome, status=body.status, origem="manual",
            admin_email=body.admin_email, admin_senha=body.admin_senha,
            admin_nome=body.admin_nome)
    return {"id": tid, "slug": slug}


# ------------------------------------------------------- cadastro (trial)
SEGMENTOS = ("supermercado", "farmacia", "moda", "material_construcao", "pet",
             "eletromoveis", "autopecas", "alimentacao", "outro")
TRIAL_DIAS = 14


class CadastroIn(BaseModel):
    empresa: str
    segmento: str
    nome: str
    email: str
    senha: str
    site: Optional[str] = None   # honeypot — humano deixa vazio


# Rate-limit do cadastro público (in-memory): 3/h por IP e 2/h por e-mail.
# OrderedDict com teto e descarte LRU — evita crescer sem limite se alguém
# varrer o endpoint trocando de chave a cada chamada.
from collections import OrderedDict as _OrderedDict  # noqa: E402
_CAD_HITS: "_OrderedDict[str, list]" = _OrderedDict()
_CAD_MAX_IP, _CAD_MAX_EMAIL, _CAD_JANELA, _CAD_MAX_CHAVES = 3, 2, 3600.0, 10000


def _cad_estourou(chave: str, limite: int) -> bool:
    import time as _t
    agora = _t.time()
    if len(_CAD_HITS) > _CAD_MAX_CHAVES:
        for k in [k for k, v in _CAD_HITS.items() if not v or agora - v[-1] >= _CAD_JANELA]:
            _CAD_HITS.pop(k, None)
        while len(_CAD_HITS) > _CAD_MAX_CHAVES:
            _CAD_HITS.popitem(last=False)
    hits = [t for t in _CAD_HITS.get(chave, []) if agora - t < _CAD_JANELA]
    estourou = len(hits) >= limite
    if not estourou:
        hits.append(agora)
    _CAD_HITS[chave] = hits
    _CAD_HITS.move_to_end(chave)
    return estourou


@app.post("/cadastro")
def cadastro(body: CadastroIn, request: Request):
    """Autoatendimento: cria a empresa em teste grátis de 14 dias + o usuário
    dono (admin) e já devolve o token logado. Público — protegido por honeypot
    e rate-limit simples por IP e por e-mail."""
    if body.site:            # bot preencheu o campo invisível: finge sucesso
        return {"ok": True}
    email = body.email.strip().lower()
    empresa = body.empresa.strip()
    nome = body.nome.strip()
    if not empresa:
        raise HTTPException(400, "Informe o nome da empresa.")
    if len(empresa) > 120:
        raise HTTPException(400, "Nome da empresa muito longo (máx. 120 caracteres).")
    if body.segmento not in SEGMENTOS:
        raise HTTPException(400, "Escolha o segmento do seu varejo.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Informe um e-mail válido.")
    if len(body.senha) < 8:
        raise HTTPException(400, "Senha: mínimo 8 caracteres.")
    # último hop do X-Forwarded-For: é o que o proxy confiável (Render) anexa;
    # o primeiro é escrito pelo próprio cliente e é falsificável.
    _xff = [p.strip() for p in (request.headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    ip = _xff[-1] if _xff else ((request.client.host if request.client else "") or "?")
    if _cad_estourou("ip:" + ip, _CAD_MAX_IP) or _cad_estourou("em:" + email, _CAD_MAX_EMAIL):
        raise HTTPException(429, "Muitos cadastros seguidos. Tente de novo em uma hora.")
    for tentativa in (1, 2):
        try:
            with platform_session() as cur:
                tid, _slug, expira = _provisionar_tenant(
                    cur, empresa, status="trial", segmento=body.segmento,
                    origem="self_service", trial_dias=TRIAL_DIAS,
                    admin_email=email, admin_senha=body.senha, admin_nome=nome or None)
                # onboarding nasce pendente — mesma transação: se isto falhar,
                # tenant/assinatura/admin fazem rollback junto (tudo ou nada).
                cur.execute("SELECT set_config('app.current_tenant', %s, true)", (tid,))
                cur.execute(
                    "INSERT INTO jornada (tenant_id, jornada, respostas) VALUES (%s,'onboarding','{}') "
                    "ON CONFLICT (tenant_id, jornada) DO NOTHING", (tid,))
            break
        except HTTPException as e:
            if e.status_code == 409:
                raise HTTPException(409, 'Já existe uma conta com esse e-mail — use "Já sou cliente" para entrar.')
            raise
        except Exception as e:   # corrida de e-mail ou de slug
            msg = str(e)
            if "usuario_login" in msg:
                raise HTTPException(409, 'Já existe uma conta com esse e-mail — use "Já sou cliente" para entrar.')
            if "tenant_slug" in msg and tentativa == 1:
                continue   # slug ocupado pela requisição concorrente: tenta de novo
            raise
    token = make_token(sub=email, nome=nome, tenant_id=tid, papel="admin_tenant", exp_limite=expira)
    return {"token": token,
            "user": {"email": email, "nome": nome, "papel": "admin_tenant"},
            "tenant": {"id": tid, "nome": empresa, "status": "trial",
                       "trial_expira_em": expira.isoformat() if expira else None,
                       "onboarding": "pendente"}}


@app.put("/tenants/{tid2}")
def tenant_update(tid2: str, body: TenantIn, user: dict = Depends(current)):
    """Edita nome/status da empresa (suspensão = status 'cancelado')."""
    _super(user)
    if body.status not in TENANT_STATUS:
        raise HTTPException(400, "Status inválido.")
    with platform_session() as cur:
        cur.execute("UPDATE platform.tenant SET nome=%s, status=%s WHERE id=%s",
                    (body.nome.strip(), body.status, tid2))
        if cur.rowcount == 0:
            raise HTTPException(404, "Empresa não encontrada.")
    return {"ok": True}


@app.delete("/tenants/{tid2}")
def tenant_delete(tid2: str, user: dict = Depends(current)):
    """Exclui uma empresa e TODOS os seus dados (cascade). Irreversível —
    uso operacional do super-admin (ex.: cadastro de teste)."""
    _super(user)
    with platform_session() as cur:
        cur.execute("DELETE FROM platform.tenant WHERE id=%s", (tid2,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Empresa não encontrada.")
    return {"ok": True}


class SeedDemoIn(BaseModel):
    apagar_existentes: bool = False
    senha: Optional[str] = None


@app.post("/admin/seed-demo")
def admin_seed_demo(body: SeedDemoIn, user: dict = Depends(current)):
    """Popula o banco com as 4 redes de demonstração (perfis médio/bom/ruim/misto).

    Só o super-admin. Com apagar_existentes=true, remove TODAS as demais
    empresas e seus dados em cascata — irreversível.
    """
    _super(user)
    if body.senha is not None and len(body.senha) < 8:
        raise HTTPException(400, "Senha dos logins demo: mínimo 8 caracteres.")
    import importlib.util
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "scripts", "seed_redes_demo.py")
    spec = importlib.util.spec_from_file_location("seed_redes_demo", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    linhas_log = []
    resumo = mod.semear(apagar_existentes=body.apagar_existentes,
                        senha=body.senha, log=linhas_log.append)
    return {"ok": True, "resumo": resumo, "log": linhas_log}


@app.get("/admin/metricas")
def admin_metricas(user: dict = Depends(current)):
    """Métricas da plataforma: por empresa (usuários, uso do mês, receita
    estimada = base + uso variável) e totais (tenants ativos, MRR estimado)."""
    _super(user)
    with platform_session() as cur:
        cur.execute(
            """
            SELECT t.id, t.nome, t.status,
                   COALESCE(a.base_mensal_cent, 0), COALESCE(a.preco_por_1k_cent, 0),
                   (SELECT count(*) FROM platform.usuario_login u WHERE u.tenant_id = t.id),
                   COALESCE((SELECT m.registros FROM platform.medidor_uso m
                              WHERE m.tenant_id = t.id
                                AND m.competencia = date_trunc('month', now())::date), 0),
                   t.segmento, t.origem, t.trial_expira_em
              FROM platform.tenant t
              LEFT JOIN platform.assinatura a ON a.tenant_id = t.id
             ORDER BY t.nome
            """)
        empresas = []
        mrr = 0
        for (tid_, nome, status, base_c, preco1k_c, nusers, registros,
             segmento, origem, trial_exp) in cur.fetchall():
            receita = int(base_c) + int(int(registros) / 1000 * int(preco1k_c))
            if status in ("ativo", "trial"):
                mrr += receita
            empresas.append({"id": str(tid_), "nome": nome, "status": status,
                             "usuarios": int(nusers), "registros_mes": int(registros),
                             "base_cent": int(base_c), "receita_estimada_cent": receita,
                             "segmento": segmento, "origem": origem,
                             "trial_expira_em": trial_exp.isoformat() if trial_exp else None})
    ativos = sum(1 for e in empresas if e["status"] in ("ativo", "trial"))
    return {"empresas": empresas,
            "totais": {"tenants": len(empresas), "ativos": ativos,
                       "mrr_estimado_cent": mrr}}


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


@app.get("/kpi/ultimo-dia")
def kpi_ultimo_dia(tid: str = Depends(tenant_of)):
    """Último dia com dados no gold — o painel usa para achar o mês certo."""
    with tenant_session(tid) as cur:
        cur.execute("SELECT max(data) FROM gold_venda_diaria")
        r = cur.fetchone()
    return {"ultimo_dia": str(r[0]) if r and r[0] else None}


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
        SELECT data, sum(faturamento_liq), sum(cupons), sum(itens), sum(margem)
          FROM gold_venda_diaria
         WHERE categoria_id IS NULL AND date_trunc('month', data) = make_date(%s, %s, 1)
         GROUP BY data ORDER BY data
        """,
        (ano, mes),
    )
    return [{"data": r[0], "faturamento_liq": float(r[1]), "cupons": int(r[2]), "itens": int(r[3]),
             "margem": float(r[4] or 0)}
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
        SELECT l.id, l.nome, g.data, g.faturamento_liq, g.cupons, g.itens, g.margem
          FROM gold_venda_diaria g JOIN loja l ON l.id = g.loja_id
         WHERE g.categoria_id IS NULL
           AND date_trunc('month', g.data) IN (make_date(%s,%s,1), make_date(%s,%s,1))
         ORDER BY l.nome, g.data
        """,
        (ano, mes, ano - 1, mes),
    )
    por_loja: dict = {}
    for lid, nome, d, fat, cup, itn, mrg in cur.fetchall():
        key = str(lid)
        por_loja.setdefault(key, {"nome": nome, "atual": [], "base": []})
        rec = {"data": d, "faturamento_liq": float(fat),
               "cupons": int(cup), "itens": int(itn), "margem": float(mrg or 0)}
        (por_loja[key]["atual"] if d.year == ano else por_loja[key]["base"]).append(rec)

    lojas = []
    for lid, v in por_loja.items():
        fat = sum(r["faturamento_liq"] for r in v["atual"])
        cup = sum(r["cupons"] for r in v["atual"])
        mrg = sum(r["margem"] for r in v["atual"])
        item = {"id": lid, "nome": v["nome"], "faturamento": round(fat, 2),
                "ticket": round(fat / cup, 2) if cup else None,
                "margem_pct": round(mrg / fat, 4) if fat and 0 < mrg < fat else None,
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
    competencia: Optional[str] = None


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
    iniciativa_id: Optional[str] = None


# Framework MERCADO — 7 pilares (protótipo v3); o radar de maturidade usa 1–5.
RADAR_AREAS = ["Mercadológico", "Experiência do Cliente", "Redução de Perdas",
               "Comercial & Pricing", "Abastecimento & Estoque",
               "Digital & Multicanal", "Operações de Loja"]
PILARES = {"M": "Mercadológico", "E": "Experiência do Cliente", "R": "Redução de Perdas",
           "C": "Comercial & Pricing", "A": "Abastecimento & Estoque",
           "D": "Digital & Multicanal", "O": "Operações de Loja"}
JORNADAS = ("produto", "cliente", "financeira")


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
        cur.execute("SELECT proposito, visao, valores, objetivo_lp, competencia "
                    "FROM direcao_estrategica WHERE tenant_id=%s", (tid,))
        row = cur.fetchone()
    campos = ["proposito", "visao", "valores", "objetivo_lp", "competencia"]
    return dict(zip(campos, row)) if row else {c: None for c in campos}


@app.put("/direcao")
def direcao_put(body: DirecaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO direcao_estrategica (tenant_id, proposito, visao, valores, objetivo_lp, competencia, atualizado_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (tenant_id) DO UPDATE SET "
            "proposito=EXCLUDED.proposito, visao=EXCLUDED.visao, valores=EXCLUDED.valores, "
            "objetivo_lp=EXCLUDED.objetivo_lp, competencia=EXCLUDED.competencia, atualizado_em=now()",
            (tid, body.proposito, body.visao, body.valores, body.objetivo_lp, body.competencia))
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
    # notas gravadas com os nomes antigos (radar de 5 áreas) são aproveitadas
    LEGADO = {"Comercial/Vendas": "Comercial & Pricing",
              "Marketing/Fidelização": "Experiência do Cliente",
              "Operação/Pessoas": "Operações de Loja",
              "Inovação": "Digital & Multicanal"}
    with tenant_session(tid) as cur:
        cur.execute("SELECT area, nota FROM radar_nota WHERE tenant_id=%s", (tid,))
        cru = {r[0]: int(r[1]) for r in cur.fetchall()}
    notas = {}
    for area, nota in cru.items():
        alvo = area if area in RADAR_AREAS else LEGADO.get(area)
        if alvo and alvo not in notas:
            notas[alvo] = nota
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
            "a.status, a.objetivo_id, o.titulo, a.iniciativa_id "
            "FROM acao_5w2h a LEFT JOIN okr_objetivo o ON o.id=a.objetivo_id "
            "ORDER BY (a.status IN ('concluida','cancelada')), a.quando NULLS LAST, a.criado_em")
        cols = ["id", "oque", "porque", "onde", "quando", "quem", "como", "quanto",
                "status", "objetivo_id", "objetivo", "iniciativa_id"]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["id"] = str(d["id"])
            d["quando"] = str(d["quando"]) if d["quando"] else None
            d["quanto"] = float(d["quanto"]) if d["quanto"] is not None else None
            d["objetivo_id"] = str(d["objetivo_id"]) if d["objetivo_id"] else None
            d["iniciativa_id"] = str(d["iniciativa_id"]) if d["iniciativa_id"] else None
            rows.append(d)
    return {"acoes": rows}


@app.post("/acoes")
def acoes_post(body: AcaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.oque.strip():
        raise HTTPException(400, "Descreva a ação (O quê).")
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO acao_5w2h (tenant_id, objetivo_id, oque, porque, onde, quando, quem, como, quanto, status, iniciativa_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (tid, body.objetivo_id, body.oque.strip(), body.porque, body.onde,
             body.quando or None, body.quem, body.como, body.quanto, body.status,
             body.iniciativa_id))
        aid = cur.fetchone()[0]
    return {"id": str(aid)}


@app.put("/acoes/{aid}")
def acoes_put(aid: str, body: AcaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "UPDATE acao_5w2h SET oque=%s, porque=%s, onde=%s, quando=%s, quem=%s, "
            "como=%s, quanto=%s, status=%s, objetivo_id=%s, iniciativa_id=%s WHERE id=%s",
            (body.oque.strip(), body.porque, body.onde, body.quando or None,
             body.quem, body.como, body.quanto, body.status, body.objetivo_id,
             body.iniciativa_id, aid))
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


# ------------------------------------- cadastro de lojas + IBGE (3.14)
class LojaIn(BaseModel):
    codigo: str
    nome: str
    formato: Optional[str] = None
    cep: Optional[str] = None
    numero: Optional[str] = None
    endereco: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    area_vendas_m2: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


LOJA_COLS = ("id, codigo, nome, formato, endereco, municipio, uf, area_vendas_m2, "
             "ibge_id, populacao, populacao_ano, pib_per_capita, pib_ano, lat, lng, cep, numero")


def _loja_row(r):
    return {"id": str(r[0]), "codigo": r[1], "nome": r[2], "formato": r[3],
            "endereco": r[4], "municipio": r[5], "uf": r[6],
            "area_vendas_m2": float(r[7]) if r[7] is not None else None,
            "ibge_id": r[8], "populacao": r[9], "populacao_ano": r[10],
            "pib_per_capita": float(r[11]) if r[11] is not None else None,
            "pib_ano": r[12],
            "lat": float(r[13]) if r[13] is not None else None,
            "lng": float(r[14]) if r[14] is not None else None,
            "cep": r[15], "numero": r[16]}


def _ibge_atualiza(cur, loja_id: str, municipio: str, uf: str) -> None:
    """Best-effort: busca IBGE e grava na loja. Nunca falha o request principal."""
    from boardos import ibge as _ibge
    try:
        d = _ibge.enriquecer(municipio or "", uf or "")
    except Exception:
        d = None
    if d:
        cur.execute(
            "UPDATE loja SET ibge_id=%s, populacao=%s, populacao_ano=%s, "
            "pib_per_capita=%s, pib_ano=%s, ibge_atualizado_em=now() WHERE id=%s",
            (d.get("ibge_id"), d.get("populacao"), d.get("populacao_ano"),
             d.get("pib_per_capita"), d.get("pib_ano"), loja_id))


@app.get("/lojas")
def lojas_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute(f"SELECT {LOJA_COLS} FROM loja ORDER BY codigo")
        rows = [_loja_row(r) for r in cur.fetchall()]
    return {"lojas": rows}


@app.post("/lojas")
def lojas_post(body: LojaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.codigo.strip() or not body.nome.strip():
        raise HTTPException(400, "Informe código e nome da loja.")
    with tenant_session(tid) as cur:
        cur.execute("SELECT 1 FROM loja WHERE codigo=%s", (body.codigo.strip(),))
        if cur.fetchone():
            raise HTTPException(409, "Já existe uma loja com esse código.")
        cur.execute(
            "INSERT INTO loja (tenant_id, codigo, nome, formato, endereco, municipio, uf, area_vendas_m2, lat, lng, cep, numero) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (tid, body.codigo.strip(), body.nome.strip(), body.formato,
             body.endereco, body.municipio, (body.uf or "").upper()[:2] or None,
             body.area_vendas_m2, body.lat, body.lng, body.cep, body.numero))
        lid = str(cur.fetchone()[0])
        if body.municipio and body.uf:
            _ibge_atualiza(cur, lid, body.municipio, body.uf)
        cur.execute(f"SELECT {LOJA_COLS} FROM loja WHERE id=%s", (lid,))
        loja = _loja_row(cur.fetchone())
    return loja


@app.put("/lojas/{lid}")
def lojas_put(lid: str, body: LojaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute(
            "UPDATE loja SET codigo=%s, nome=%s, formato=%s, endereco=%s, "
            "municipio=%s, uf=%s, area_vendas_m2=%s, lat=%s, lng=%s, cep=%s, numero=%s WHERE id=%s",
            (body.codigo.strip(), body.nome.strip(), body.formato, body.endereco,
             body.municipio, (body.uf or "").upper()[:2] or None,
             body.area_vendas_m2, body.lat, body.lng, body.cep, body.numero, lid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Loja não encontrada.")
        if body.municipio and body.uf:
            _ibge_atualiza(cur, lid, body.municipio, body.uf)
        cur.execute(f"SELECT {LOJA_COLS} FROM loja WHERE id=%s", (lid,))
        loja = _loja_row(cur.fetchone())
    return loja


@app.post("/lojas/{lid}/ibge")
def lojas_ibge(lid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    """Reconsulta os dados do IBGE para a loja (município/UF do cadastro)."""
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT municipio, uf FROM loja WHERE id=%s", (lid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Loja não encontrada.")
        if not (row[0] and row[1]):
            raise HTTPException(400, "Preencha município e UF da loja primeiro.")
        _ibge_atualiza(cur, lid, row[0], row[1])
        cur.execute(f"SELECT {LOJA_COLS} FROM loja WHERE id=%s", (lid,))
        loja = _loja_row(cur.fetchone())
    if not loja.get("ibge_id"):
        raise HTTPException(404, f"Município \"{row[0]}/{row[1]}\" não encontrado no IBGE — confira a grafia.")
    return loja


@app.delete("/lojas/{lid}")
def lojas_delete(lid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        try:
            cur.execute("DELETE FROM loja WHERE id=%s", (lid,))
        except Exception:
            raise HTTPException(409, "Esta loja tem vendas registradas — não pode ser excluída.")
        if cur.rowcount == 0:
            raise HTTPException(404, "Loja não encontrada.")
    return {"ok": True}


# ------------------------------------- 4.4 upload de dados (self-service)
@app.post("/dados/importar")
async def dados_importar(
    arquivo: UploadFile = File(...),
    loja_codigo: str = Form(...),
    loja_nome: str = Form(""),
    mapa: str = Form(...),
    user: dict = Depends(current),
    tid: str = Depends(tenant_of),
):
    """Importa um CSV de vendas (grão cupom/item) pelo painel.

    `mapa` = JSON {campo_canonico: coluna_do_arquivo}. Pipeline idempotente:
    reenviar o mesmo arquivo substitui, não duplica. Atualiza o gold e o
    medidor de uso (billing).
    """
    import json as _json
    import os as _os
    import tempfile

    from boardos.ingestion import ingest_csv
    from boardos.mapping import ColumnMap

    _can_edit(user)
    if not loja_codigo.strip():
        raise HTTPException(400, "Informe o código da loja.")
    try:
        cmap = ColumnMap({k: v for k, v in _json.loads(mapa).items() if v})
    except Exception:
        raise HTTPException(400, "Mapa de colunas inválido.")
    faltam = cmap.missing_required()
    if faltam:
        raise HTTPException(400, f"Mapeie as colunas obrigatórias: {', '.join(faltam)}.")
    conteudo = await arquivo.read()
    if len(conteudo) > 25_000_000:
        raise HTTPException(413, "Arquivo acima de 25 MB — divida em partes.")
    if not conteudo.strip():
        raise HTTPException(400, "Arquivo vazio.")
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    try:
        tmp.write(conteudo)
        tmp.close()
        try:
            res = ingest_csv(
                tenant_id=tid,
                loja_codigo=loja_codigo.strip(),
                loja_nome=loja_nome.strip() or ("Loja " + loja_codigo.strip()),
                csv_path=tmp.name,
                cmap=cmap,
                origem=arquivo.filename or "importacao.csv",
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception:
            raise HTTPException(400, "Não foi possível processar o arquivo — confira o formato e o mapa de colunas.")
    finally:
        _os.unlink(tmp.name)
    return {"ok": True, "linhas": res["linhas"], "dias": res["dias"]}


class LinhaDiariaIn(BaseModel):
    data: str
    loja_codigo: str
    faturamento: float
    cupons: int = 0
    itens: int = 0


class ImportDiarioIn(BaseModel):
    linhas: list


@app.post("/dados/importar-diario")
def dados_importar_diario(body: ImportDiarioIn, user: dict = Depends(current),
                          tid: str = Depends(tenant_of)):
    """Importa vendas já agregadas por dia×loja direto no gold (para fontes que
    só têm cabeçalho de cupom/diário — ex.: CRM). Upsert idempotente; sem custo
    sintético (margem fica zerada até existir custo real)."""
    from datetime import date as _date

    _can_edit(user)
    if not body.linhas:
        raise HTTPException(400, "Envie ao menos uma linha.")
    if len(body.linhas) > 20000:
        raise HTTPException(413, "Máximo de 20.000 linhas por chamada — divida em partes.")
    records = []
    for i, l in enumerate(body.linhas):
        try:
            li = LinhaDiariaIn(**l)
            records.append({"data": _date.fromisoformat(li.data[:10]),
                            "loja": li.loja_codigo.strip(),
                            "faturamento": float(li.faturamento),
                            "cupons": int(li.cupons), "itens": int(li.itens)})
        except Exception:
            raise HTTPException(400, f"Linha {i+1} inválida (esperado data ISO, loja_codigo, faturamento).")
    # garante a dim_calendario (calendário duplo) para o período importado —
    # sem isso o JOIN do KPI descarta datas fora do range semeado
    from boardos.calendar_gen import upsert_into as _cal
    dmin = min(r["data"] for r in records)
    dmax = max(r["data"] for r in records)
    with tenant_session(tid) as cur:
        _cal(cur, dmin.replace(month=1, day=1), dmax.replace(month=12, day=31))
    from boardos.crm import import_vendas_diarias_rows
    res = import_vendas_diarias_rows(tid, records, margem_sintetica=False)
    # registra o lote para a lista de importações do painel
    with tenant_session(tid) as cur:
        cur.execute(
            "INSERT INTO ingest_batch (tenant_id, origem, data_de, data_ate, linhas, status) "
            "VALUES (%s,%s,%s,%s,%s,'ok')",
            (tid, "importação diária (API)", dmin, dmax, len(records)))
    return {"ok": True, "linhas": res["linhas"]}


@app.get("/dados/importacoes")
def dados_importacoes(tid: str = Depends(tenant_of)):
    """Histórico de importações do tenant (mais recentes primeiro)."""
    with tenant_session(tid) as cur:
        cur.execute(
            "SELECT b.origem, b.data_de, b.data_ate, b.linhas, b.status, b.criado_em, l.nome "
            "FROM ingest_batch b LEFT JOIN loja l ON l.id = b.loja_id "
            "ORDER BY b.criado_em DESC LIMIT 60")
        rows = cur.fetchall()
    return {"importacoes": [
        {"arquivo": o or "—", "data_de": str(de) if de else None,
         "data_ate": str(ate) if ate else None, "registros": int(n or 0),
         "status": st, "enviado_em": env.isoformat(), "loja": lj}
        for o, de, ate, n, st, env, lj in rows]}


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
def _contexto_tenant(tid: str):
    """Contexto numérico do tenant para a IA: YoY, lojas, metas, FCA e feriados."""
    with tenant_session(tid) as cur:
        cur.execute("SELECT max(data) FROM gold_venda_diaria")
        row = cur.fetchone()
        ult = row[0] if row else None
        if not ult:
            return None, None
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
        cur.execute("SELECT titulo, status, causa, acao, responsavel FROM fca_ciclo "
                    "WHERE status IN ('aberto','em_andamento') ORDER BY criado_em DESC LIMIT 10")
        fcas = [{"titulo": r[0], "status": r[1], "causa": r[2], "acao": r[3],
                 "responsavel": r[4]} for r in cur.fetchall()]
        cur.execute("SELECT data, nome, tipo FROM feriado "
                    "WHERE data BETWEEN now()::date AND now()::date + 45 ORDER BY data LIMIT 10")
        feriados = [{"data": str(r[0]), "nome": r[1], "tipo": r[2]} for r in cur.fetchall()]

    if not yoy:
        return None, ult
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
        "planos_de_acao_abertos": fcas,
        "proximos_feriados_e_datas": feriados,
    }
    return contexto, ult


@app.get("/advisor/insight")
def advisor_insight(tid: str = Depends(tenant_of)):
    """Leitura executiva do último mês gerada por IA (Claude), com fallback."""
    contexto, ult = _contexto_tenant(tid)
    if not contexto:
        return {"fonte": "motor"}
    texto = advisor.gerar_insight(contexto, cache_key=f"{tid}:{ult.isoformat()}")
    if texto:
        return {"fonte": "ia", "texto": texto}
    return {"fonte": "motor"}


class PerguntaIn(BaseModel):
    pergunta: str
    persona: Optional[str] = None


@app.post("/advisor/pergunta")
def advisor_pergunta(body: PerguntaIn, tid: str = Depends(tenant_of)):
    """2.2 — Converse com seus dados (opcionalmente na voz de um conselheiro)."""
    if not body.pergunta.strip():
        raise HTTPException(400, "Escreva a pergunta.")
    if body.persona and body.persona not in advisor.PERSONAS:
        raise HTTPException(400, "Conselheiro inválido.")
    contexto, _ = _contexto_tenant(tid)
    if not contexto:
        return {"fonte": "indisponivel",
                "resposta": "Ainda não há dados suficientes para responder."}
    texto = advisor.responder_pergunta(contexto, body.pergunta.strip(), body.persona)
    if texto:
        return {"fonte": "ia", "resposta": texto}
    return {"fonte": "indisponivel",
            "resposta": "A IA do Conselho ainda não está ativa (configure a ANTHROPIC_API_KEY no servidor)."}


@app.get("/conselho/pautas")
def conselho_pautas(tid: str = Depends(tenant_of)):
    """O Conselho BoardOS: pauta de cada conselheiro calculada dos dados reais."""
    contexto, ult = _contexto_tenant(tid)
    cats = []
    cesta = None
    clientes_identificados = 0
    if ult:
        with tenant_session(tid) as cur:
            # categorias do último mês vs ano anterior
            cur.execute(
                """
                SELECT c.nome, g.data, sum(g.faturamento_liq)
                  FROM gold_venda_diaria g JOIN categoria c ON c.id = g.categoria_id
                 WHERE date_trunc('month', g.data) IN (make_date(%s,%s,1), make_date(%s,%s,1))
                 GROUP BY c.nome, g.data
                """, (ult.year, ult.month, ult.year - 1, ult.month))
            porc: dict = {}
            for nome, d, fat in cur.fetchall():
                porc.setdefault(nome, {"atual": [], "base": []})
                rec = {"data": d, "faturamento_liq": float(fat), "cupons": 0, "itens": 0}
                (porc[nome]["atual"] if d.year == ult.year else porc[nome]["base"]).append(rec)
            for nome, v in porc.items():
                fat = sum(r["faturamento_liq"] for r in v["atual"])
                var = None
                if v["atual"] and v["base"]:
                    var = comparison.compare(v["atual"], v["base"])["var_ajustada"]
                cats.append({"nome": nome, "faturamento": fat, "var": var})
            cats.sort(key=lambda x: -x["faturamento"])
            # cesta do mês (itens/cupom) atual vs ano anterior
            cur.execute(
                "SELECT date_trunc('year', data)::date, sum(itens)::float / NULLIF(sum(cupons),0) "
                "FROM gold_venda_diaria WHERE categoria_id IS NULL "
                "AND date_trunc('month', data) IN (make_date(%s,%s,1), make_date(%s,%s,1)) "
                "GROUP BY 1 ORDER BY 1", (ult.year, ult.month, ult.year - 1, ult.month))
            rr = cur.fetchall()
            if rr:
                cesta = {str(r[0])[:4]: (round(float(r[1]), 2) if r[1] else None) for r in rr}
            cur.execute("SELECT count(DISTINCT cliente_id) FROM item_venda WHERE cliente_id IS NOT NULL")
            clientes_identificados = int(cur.fetchone()[0])

    def _pct(v):
        return f"{v*100:+.1f}%" if v is not None else "s/ base"

    pautas: dict = {}
    P = advisor.PERSONAS
    if contexto:
        c = contexto["comparacao_yoy"]
        metas_r = [m for m in contexto["metas"] if m["farol"] == "r"]
        lojas_q = [l for l in contexto["lojas"] if (l.get("var_varejo_pct") or 0) <= -3]
        pautas["estrategia"] = [
            f"Mês {contexto['mes_referencia']}: civil {c['var_civil_pct']:+.1f}% × varejo {c['var_varejo_ajustada_pct']:+.1f}% (efeito calendário {c['efeito_calendario_pp']:+.1f}pp).",
            (f"{len(metas_r)} meta(s) fora da rota — priorize: " + "; ".join(m["kr"] for m in metas_r[:2]))
            if metas_r else "Metas do ano na rota — mantenha o ritmo.",
            (f"Queda real em {len(lojas_q)} loja(s): " + ", ".join(l["nome"] for l in lojas_q[:3]))
            if lojas_q else "Nenhuma loja com queda real relevante no mês.",
        ]
    if cats:
        melhor = max((x for x in cats if x["var"] is not None), key=lambda x: x["var"], default=None)
        pior = min((x for x in cats if x["var"] is not None), key=lambda x: x["var"], default=None)
        lider = cats[0]
        tot = sum(x["faturamento"] for x in cats) or 1
        pautas["categorias"] = [
            f"{lider['nome']} lidera o mix com {lider['faturamento']/tot*100:.0f}% do faturamento.",
            (f"Destaque: {melhor['nome']} {_pct(melhor['var'])} vs. ano anterior — avalie mais espaço/frente.") if melhor else "",
            (f"Atenção: {pior['nome']} {_pct(pior['var'])} — revise preço, sortimento e planograma.") if pior else "",
        ]
        pautas["trade"] = [
            (f"Leve {pior['nome']} para o JBP: negocie verba, encarte e ação de recuperação com os fornecedores da categoria.") if pior else "Monte a agenda de JBP com os 3 maiores fornecedores.",
            (f"{melhor['nome']} em alta — proponha ação casada (ponta de gôndola / combo) para acelerar com verba da indústria.") if melhor else "",
            f"Calendário promocional: {len(contexto['proximos_feriados_e_datas']) if contexto else 0} data(s) sazonal(is) cadastrada(s) nos próximos 45 dias — planeje encarte por data.",
        ]
    if contexto:
        c = contexto["comparacao_yoy"]
        tk_a, tk_b = c.get("ticket_atual"), c.get("ticket_ano_anterior")
        var_tk = ((tk_a / tk_b - 1) * 100) if (tk_a and tk_b) else None
        cesta_txt = ""
        if cesta and len(cesta) == 2:
            anos = sorted(cesta)
            cesta_txt = f"Cesta: {cesta[anos[1]]} itens/cupom vs {cesta[anos[0]]} no ano anterior."
        pautas["clientes"] = [
            (f"Ticket médio R$ {tk_a:.2f} ({var_tk:+.1f}% vs. ano anterior)." if var_tk is not None
             else "Ticket médio ainda sem base de comparação."),
            cesta_txt or "Cesta média em consolidação.",
            ("Nenhum cliente identificado no cupom — ative CPF na nota/fidelidade para abrir frequência, churn e LTV."
             if clientes_identificados == 0 else
             f"{clientes_identificados} clientes identificados — hora de segmentar e ativar campanhas."),
        ]
        fat_mes = c["faturamento_total"]
        pautas["receitas"] = [
            f"Retail media: potencial estimado de R$ {fat_mes*0.005:,.0f}–{fat_mes*0.015:,.0f}/mês (benchmark de mercado: 0,5–1,5% do faturamento; estimativa).",
            "Monetize o sell-out: relatórios por categoria para a indústria dentro do JBP.",
            "Espaços vendáveis: encarte digital, mídia em tela no PDV e pontas de gôndola patrocinadas.",
        ]
    conselheiros = [{"id": k, "nome": v["nome"], "foco": v["foco"],
                     "pauta": [x for x in pautas.get(k, ["Aguardando dados para montar a pauta."]) if x]}
                    for k, v in P.items()]
    return {"conselheiros": conselheiros}


@app.get("/advisor/resumo-executivo")
def advisor_resumo_exec(tid: str = Depends(tenant_of)):
    """2.3 — Briefing do board gerado pela IA, com fallback numérico."""
    contexto, _ = _contexto_tenant(tid)
    if not contexto:
        return {"fonte": "motor", "texto": "Sem dados suficientes para o resumo."}
    texto = advisor.resumo_executivo(contexto)
    if texto:
        return {"fonte": "ia", "texto": texto}
    c = contexto["comparacao_yoy"]
    metas_r = [m for m in contexto["metas"] if m["farol"] == "r"]
    fallback = (
        f"RESUMO {contexto['mes_referencia']}\n"
        f"Faturamento {c['faturamento_total']:,.0f} — civil {c['var_civil_pct']:+.1f}% / "
        f"varejo (ajustado) {c['var_varejo_ajustada_pct']:+.1f}% vs. ano anterior "
        f"(efeito calendário {c['efeito_calendario_pp']:+.1f}pp).\n"
        f"Metas fora da rota: {len(metas_r)}"
        + (" — " + "; ".join(m["kr"] for m in metas_r[:3]) if metas_r else "")
        + f".\nPlanos de ação abertos: {len(contexto['planos_de_acao_abertos'])}."
    )
    return {"fonte": "motor", "texto": fallback}


# ------------------------------------------------- feriados (3.4)
class FeriadoIn(BaseModel):
    data: str
    nome: str
    tipo: str = "feriado"


@app.get("/feriados")
def feriados_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, data, nome, tipo FROM feriado ORDER BY data")
        rows = [{"id": str(r[0]), "data": str(r[1]), "nome": r[2], "tipo": r[3]}
                for r in cur.fetchall()]
    return {"feriados": rows}


@app.post("/feriados")
def feriados_post(body: FeriadoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if body.tipo not in ("feriado", "sazonal"):
        raise HTTPException(400, "Tipo inválido.")
    if not body.nome.strip():
        raise HTTPException(400, "Dê um nome à data.")
    with tenant_session(tid) as cur:
        try:
            cur.execute("INSERT INTO feriado (tenant_id, data, nome, tipo) "
                        "VALUES (%s,%s,%s,%s) RETURNING id",
                        (tid, body.data, body.nome.strip(), body.tipo))
            fid = cur.fetchone()[0]
        except Exception:
            raise HTTPException(409, "Essa data/nome já está cadastrada.")
    return {"id": str(fid)}


@app.delete("/feriados/{fid}")
def feriados_delete(fid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM feriado WHERE id=%s", (fid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Data não encontrada.")
    return {"ok": True}


def _add_meses(ano: int, mes: int, delta: int):
    t = ano * 12 + (mes - 1) + delta
    return t // 12, t % 12 + 1


@app.get("/kpi/mensal")
def kpi_mensal(fut: int = 3, tid: str = Depends(tenant_of)):
    """Visão mensal + tendência: 12 meses fechados, o mês corrente
    (realizado + projeção do restante, recalculada a cada dia) e os próximos
    `fut` meses projetados (3 a 6). "Programado" = faturamento do mesmo mês do
    ano anterior × meta anual do KR de faturamento (quando existirem).
    Cada mês realizado carrega também itens/cupons/margem para as séries de
    Volume, Ticket, Margem e Preço×Custo da tela Evolução.
    """
    import calendar as _cal2
    from datetime import date as _date, timedelta as _td

    fut = max(1, min(6, fut))
    with tenant_session(tid) as cur:
        cur.execute("SELECT max(data) FROM gold_venda_diaria")
        row = cur.fetchone()
        ult = row[0] if row else None
        if not ult:
            return {"meses": [], "ancora": None}
        ancora = min(_date.today(), ult)
        a0, m0 = ancora.year, ancora.month
        # histórico diário: 25 meses p/ trás (cobre ano-anterior dos 13+fut meses)
        ia, im = _add_meses(a0, m0, -25)
        cur.execute(
            "SELECT data, sum(faturamento_liq), sum(itens), sum(cupons), sum(margem) "
            "FROM gold_venda_diaria "
            "WHERE categoria_id IS NULL AND data BETWEEN %s AND %s "
            "GROUP BY data ORDER BY data",
            (_date(ia, im, 1), ancora))
        rows = cur.fetchall()
        hist = [{"data": r[0], "faturamento_liq": float(r[1])} for r in rows]
        cur.execute("SELECT meta FROM okr_kr WHERE fonte='fat_yoy_pct' LIMIT 1")
        r = cur.fetchone()
        meta_pct = float(r[0]) if r else None

    por_mes: dict = {}
    for d0, fat, itn, cup, mrg in rows:
        k = (d0.year, d0.month)
        acc = por_mes.setdefault(k, {"fat": 0.0, "itens": 0, "cupons": 0, "margem": 0.0})
        acc["fat"] += float(fat)
        acc["itens"] += int(itn or 0)
        acc["cupons"] += int(cup or 0)
        acc["margem"] += float(mrg or 0)

    def _fat(ano: int, mes: int) -> float:
        return por_mes.get((ano, mes), {}).get("fat", 0.0)

    def _meta(ano: int, mes: int):
        if meta_pct is None:
            return None
        base = _fat(ano - 1, mes)
        return round(base * (1 + meta_pct / 100), 2) if base else None

    def _extras(ano: int, mes: int) -> dict:
        m = por_mes.get((ano, mes))
        if not m:
            return {}
        return {"itens": m["itens"], "cupons": m["cupons"],
                "margem": round(m["margem"], 2)}

    meses = []
    # 12 meses fechados antes do corrente
    for d in range(-12, 0):
        ay, am = _add_meses(a0, m0, d)
        item = {"mes": f"{ay}-{am:02d}", "tipo": "fechado",
                "realizado": round(_fat(ay, am), 2), "meta": _meta(ay, am)}
        item.update(_extras(ay, am))
        meses.append(item)
    # mês corrente: realizado até a âncora + projeção do restante
    fcm = fc.forecast_mes(hist, a0, m0, cutoff=ancora)
    corrente = {"mes": f"{a0}-{m0:02d}", "tipo": "corrente",
                "realizado": fcm["total_realizado"],
                "previsto_restante": fcm["total_previsto"],
                "projetado": fcm["total_projetado"],
                "meta": _meta(a0, m0)}
    corrente.update(_extras(a0, m0))
    meses.append(corrente)
    # próximos meses: média por dia-da-semana das últimas 8 semanas
    base56 = [h for h in hist if h["data"] >= ancora - _td(days=56)]
    for d in range(1, fut + 1):
        ay, am = _add_meses(a0, m0, d)
        dias = fc.prever_dias(base56, _date(ay, am, 1),
                              _date(ay, am, _cal2.monthrange(ay, am)[1]))
        meses.append({"mes": f"{ay}-{am:02d}", "tipo": "previsto",
                      "previsto": round(sum(x["valor"] for x in dias), 2),
                      "meta": _meta(ay, am)})
    return {"meses": meses, "ancora": str(ancora)}


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
def categorias_resumo(ano: int, mes: int, loja_id: Optional[str] = None,
                      tid: str = Depends(tenant_of)):
    """Drill-down por categoria no mês: faturamento, participação e YoY.
    Com loja_id, restringe às vendas daquela loja (drill loja → categorias)."""
    if loja_id:
        try:
            uuid.UUID(loja_id)
        except ValueError:
            raise HTTPException(400, "loja_id inválido.")
    filtro_loja = " AND g.loja_id = %s" if loja_id else ""
    params = (ano, mes, ano - 1, mes) + ((loja_id,) if loja_id else ())
    with tenant_session(tid) as cur:
        cur.execute(
            """
            SELECT c.id, c.nome, g.data, sum(g.faturamento_liq), sum(g.cupons), sum(g.itens),
                   sum(g.margem)
              FROM gold_venda_diaria g JOIN categoria c ON c.id = g.categoria_id
             WHERE date_trunc('month', g.data) IN (make_date(%s,%s,1), make_date(%s,%s,1))
             """ + filtro_loja + """
             GROUP BY c.id, c.nome, g.data ORDER BY c.nome, g.data
            """,
            params)
        por_cat: dict = {}
        for cid, nome, d, fat, cup, itn, mrg in cur.fetchall():
            key = str(cid)
            por_cat.setdefault(key, {"nome": nome, "atual": [], "base": []})
            rec = {"data": d, "faturamento_liq": float(fat),
                   "cupons": int(cup), "itens": int(itn), "margem": float(mrg or 0)}
            (por_cat[key]["atual"] if d.year == ano else por_cat[key]["base"]).append(rec)

    cats = []
    for v in por_cat.values():
        fat = sum(r["faturamento_liq"] for r in v["atual"])
        mrg = sum(r["margem"] for r in v["atual"])
        item = {"nome": v["nome"], "faturamento": round(fat, 2),
                "margem_pct": round(mrg / fat, 4) if fat and 0 < mrg < fat else None,
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
                                  "loja_id": lj["id"], "loja": lj["nome"],
                                  "titulo": f"Queda real de venda — {lj['nome']}",
                                  "detalhe": f"{lj['nome']}: venda comparável {lj['var_ajustada']*100:+.1f}% vs. ano anterior."})
        # KRs no vermelho
        cur.execute("SELECT k.id, k.titulo, k.meta, k.atual, k.base, k.direcao, k.fonte, o.titulo "
                    "FROM okr_kr k JOIN okr_objetivo o ON o.id=k.objetivo_id")
        for kid, kt, meta, atual, base, direcao, fonte, ot in cur.fetchall():
            a = float(atual)
            auto = _kr_auto(fonte, yoy) if fonte else None
            if auto is not None:
                a = auto
            prog, farol = _kr_progresso(meta, a, base, direcao)
            if farol == "r":
                itens.append({"sev": "r", "kpi": "okr", "kr_id": str(kid),
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
    kr_id: Optional[str] = None          # indicador que esta ação quer mover
    pilar: Optional[str] = None          # M|E|R|C|A|D|O


def _baseline_do_kr(cur, kr_id: str):
    """Valor vivo do KR no momento em que a ação nasce (mede eficácia depois).
    Usa a MESMA régua do Verificador (agentes.kr_valor_atual) — se a valoração
    divergisse, o delta mediria a troca de método, não o efeito da ação."""
    cur.execute("SELECT titulo, meta, atual, base, direcao, fonte FROM okr_kr WHERE id=%s", (kr_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(400, "KR não encontrado.")
    kr = {"titulo": row[0], "meta": float(row[1]), "atual": float(row[2]),
          "base": float(row[3]) if row[3] is not None else None,
          "direcao": row[4], "fonte": row[5]}
    ctx = agentes._coletar(cur) or {}
    return agentes.kr_valor_atual(kr, ctx)


@app.get("/fca")
def fca_list(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute(
            "SELECT f.id, f.titulo, f.fato, f.causa, f.acao, f.responsavel, f.prazo, f.status, "
            "f.kpi, f.origem, f.resultado, f.kr_id, k.titulo, f.baseline, f.baseline_em, "
            "v.veredito, v.delta, v.verificado_em, f.pilar "
            "FROM fca_ciclo f LEFT JOIN okr_kr k ON k.id=f.kr_id "
            "LEFT JOIN LATERAL (SELECT veredito, delta, verificado_em FROM acao_verificacao "
            "  WHERE fca_id=f.id ORDER BY verificado_em DESC LIMIT 1) v ON true "
            "ORDER BY (f.status IN ('resolvido','descartado')), f.criado_em DESC")
        cols = ["id", "titulo", "fato", "causa", "acao", "responsavel", "prazo",
                "status", "kpi", "origem", "resultado", "kr_id", "kr", "baseline",
                "baseline_em", "veredito", "veredito_delta", "verificado_em", "pilar"]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["id"] = str(r["id"])
            r["kr_id"] = str(r["kr_id"]) if r["kr_id"] else None
            r["prazo"] = str(r["prazo"]) if r["prazo"] else None
            r["baseline"] = float(r["baseline"]) if r["baseline"] is not None else None
            r["baseline_em"] = str(r["baseline_em"]) if r["baseline_em"] else None
            r["veredito_delta"] = float(r["veredito_delta"]) if r["veredito_delta"] is not None else None
            r["verificado_em"] = r["verificado_em"].isoformat() if r["verificado_em"] else None
    return {"ciclos": rows}


@app.post("/fca")
def fca_create(body: FcaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        baseline = _baseline_do_kr(cur, body.kr_id) if body.kr_id else None
        cur.execute(
            "INSERT INTO fca_ciclo (tenant_id, titulo, fato, causa, acao, responsavel, prazo, "
            "status, kpi, origem, resultado, kr_id, baseline, baseline_em, pilar) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s::uuid IS NULL THEN NULL ELSE CURRENT_DATE END, %s) "
            "RETURNING id",
            (tid, body.titulo, body.fato, body.causa, body.acao, body.responsavel,
             body.prazo or None, body.status, body.kpi, body.origem, body.resultado,
             body.kr_id or None, baseline, body.kr_id or None, body.pilar))
        fid = cur.fetchone()[0]
    return {"id": str(fid)}


@app.put("/fca/{fid}")
def fca_update(fid: str, body: FcaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        # ligar um KR depois de criado também grava o baseline daquele momento
        cur.execute("SELECT kr_id FROM fca_ciclo WHERE id=%s", (fid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Ciclo não encontrado.")
        kr_antigo = str(row[0]) if row[0] else None
        baseline_sql = ""
        params = [body.titulo, body.fato, body.causa, body.acao, body.responsavel,
                  body.prazo or None, body.status, body.kpi, body.resultado,
                  body.kr_id or None]
        if body.kr_id and body.kr_id != kr_antigo:
            baseline = _baseline_do_kr(cur, body.kr_id)
            baseline_sql = ", baseline=%s, baseline_em=CURRENT_DATE"
            params.append(baseline)
        elif not body.kr_id and kr_antigo:
            baseline_sql = ", baseline=NULL, baseline_em=NULL"
        params.append(fid)
        params.insert(-1, body.pilar)   # pilar antes do id
        cur.execute(
            "UPDATE fca_ciclo SET titulo=%s, fato=%s, causa=%s, acao=%s, responsavel=%s, "
            "prazo=%s, status=%s, kpi=%s, resultado=%s, kr_id=%s" + baseline_sql +
            ", pilar=%s, atualizado_em=now() WHERE id=%s", params)
    return {"ok": True}


@app.delete("/fca/{fid}")
def fca_delete(fid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM fca_ciclo WHERE id=%s", (fid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ciclo não encontrado.")
    return {"ok": True}


# ═══════════════════════════ governança (handoff v2) ═══════════════════════════
# Rituais de gestão, sala do conselho, iniciativas do plano tático e as
# jornadas guiadas do Advisor (Método Masi: cultura e posicionamento).

class RitualIn(BaseModel):
    freq: str = "SEM"                    # DIA | SEM | MES | TRI
    nome: str
    quem: Optional[str] = None
    objetivo: Optional[str] = None
    proxima: Optional[str] = None


RITUAIS_PADRAO = [
    ("DIA", "Daily da loja · 15 min", "gerentes + operação", "desbloquear o dia", "seg–sáb 8h"),
    ("SEM", "Semanal de resultados · 1h", "diretoria", "revisar ações e FCAs", "toda terça 9h"),
    ("MES", "Mensal de OKRs · 2h", "CEO + diretoria", "FCA dos desvios, ajustar plano", "1ª quinta 14h"),
    ("TRI", "Trimestral do conselho · 3h", "conselho + diretoria", "resultados, deliberações, rota", "a agendar"),
]


@app.get("/rituais")
def rituais_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, freq, nome, quem, objetivo, proxima FROM ritual "
                    "ORDER BY array_position(ARRAY['DIA','SEM','MES','TRI'], freq), ordem")
        rituais = [{"id": str(r[0]), "freq": r[1], "nome": r[2], "quem": r[3],
                    "objetivo": r[4], "proxima": r[5]} for r in cur.fetchall()]
    return {"rituais": rituais}


@app.post("/rituais/padrao")
def rituais_padrao(user: dict = Depends(current), tid: str = Depends(tenant_of)):
    """Cria os 4 rituais padrão do método (só se ainda não houver nenhum)."""
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT count(*) FROM ritual")
        if cur.fetchone()[0]:
            raise HTTPException(409, "Já existem rituais cadastrados.")
        for i, (fq, nm, qm, ob, px) in enumerate(RITUAIS_PADRAO):
            cur.execute("INSERT INTO ritual (tenant_id, freq, nome, quem, objetivo, proxima, ordem) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)", (tid, fq, nm, qm, ob, px, i))
    return {"ok": True}


@app.post("/rituais")
def rituais_post(body: RitualIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.nome.strip():
        raise HTTPException(400, "Dê um nome ao ritual.")
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO ritual (tenant_id, freq, nome, quem, objetivo, proxima) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, body.freq, body.nome.strip(), body.quem, body.objetivo, body.proxima))
        rid = cur.fetchone()[0]
    return {"id": str(rid)}


@app.put("/rituais/{rid}")
def rituais_put(rid: str, body: RitualIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE ritual SET freq=%s, nome=%s, quem=%s, objetivo=%s, proxima=%s WHERE id=%s",
                    (body.freq, body.nome.strip(), body.quem, body.objetivo, body.proxima, rid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ritual não encontrado.")
    return {"ok": True}


@app.delete("/rituais/{rid}")
def rituais_delete(rid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM ritual WHERE id=%s", (rid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Ritual não encontrado.")
    return {"ok": True}


# ------------------------------------------------ membros (diretoria/conselho)
class MembroIn(BaseModel):
    nome: str
    papel: Optional[str] = None
    tag: str = "diretoria"               # diretoria | conselho


@app.get("/governanca/membros")
def membros_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, nome, papel, tag FROM governanca_membro "
                    "ORDER BY (tag <> 'diretoria'), ordem, nome")
        membros = [{"id": str(r[0]), "nome": r[1], "papel": r[2], "tag": r[3]}
                   for r in cur.fetchall()]
    return {"membros": membros}


@app.post("/governanca/membros")
def membros_post(body: MembroIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.nome.strip():
        raise HTTPException(400, "Informe o nome.")
    if body.tag not in ("diretoria", "conselho"):
        raise HTTPException(400, "Tag deve ser diretoria ou conselho.")
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO governanca_membro (tenant_id, nome, papel, tag) "
                    "VALUES (%s,%s,%s,%s) RETURNING id",
                    (tid, body.nome.strip(), body.papel, body.tag))
        mid = cur.fetchone()[0]
    return {"id": str(mid)}


@app.put("/governanca/membros/{mid}")
def membros_put(mid: str, body: MembroIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE governanca_membro SET nome=%s, papel=%s, tag=%s WHERE id=%s",
                    (body.nome.strip(), body.papel, body.tag, mid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Membro não encontrado.")
    return {"ok": True}


@app.delete("/governanca/membros/{mid}")
def membros_delete(mid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM governanca_membro WHERE id=%s", (mid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Membro não encontrado.")
    return {"ok": True}


# ------------------------------------------------ reuniões do conselho + pauta
class PautaItemIn(BaseModel):
    item: str
    tempo: Optional[str] = None
    material: Optional[str] = None


class ReuniaoIn(BaseModel):
    titulo: str = "Reunião trimestral do conselho"
    data: Optional[str] = None
    hora: Optional[str] = None
    local: Optional[str] = None
    status: str = "agendada"             # agendada | realizada
    assinada: bool = False
    pauta: Optional[list] = None         # [{item, tempo, material}]
    tipo: str = "conselho"               # conselho|diretoria|fechamento|one_on_one|calibracao|war_room
    participantes: Optional[list] = None


def _reuniao_row(cur, rid):
    cur.execute("SELECT id, titulo, data, hora, local, status, assinada, tipo, participantes "
                "FROM conselho_reuniao WHERE id=%s", (rid,))
    r = cur.fetchone()
    if not r:
        return None
    cur.execute("SELECT id, item, tempo, material FROM conselho_pauta "
                "WHERE reuniao_id=%s ORDER BY ordem", (rid,))
    pauta = [{"id": str(p[0]), "item": p[1], "tempo": p[2], "material": p[3]}
             for p in cur.fetchall()]
    return {"id": str(r[0]), "titulo": r[1], "data": str(r[2]) if r[2] else None,
            "hora": r[3], "local": r[4], "status": r[5], "assinada": r[6],
            "tipo": r[7] or "conselho", "participantes": r[8] or [],
            "pauta": pauta}


@app.get("/conselho/reunioes")
def reunioes_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT id FROM conselho_reuniao ORDER BY data DESC NULLS LAST, criado_em DESC")
        ids = [r[0] for r in cur.fetchall()]
        reunioes = [_reuniao_row(cur, i) for i in ids]
    return {"reunioes": reunioes}


@app.post("/conselho/reunioes")
def reunioes_post(body: ReuniaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO conselho_reuniao (tenant_id, titulo, data, hora, local, status, assinada, tipo, participantes) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, body.titulo.strip(), body.data or None, body.hora, body.local,
                     body.status, body.assinada, body.tipo, body.participantes or None))
        rid = cur.fetchone()[0]
        for i, p in enumerate(body.pauta or []):
            cur.execute("INSERT INTO conselho_pauta (tenant_id, reuniao_id, item, tempo, material, ordem) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (tid, rid, p.get("item", ""), p.get("tempo"), p.get("material"), i))
        reuniao = _reuniao_row(cur, rid)
    return reuniao


@app.put("/conselho/reunioes/{rid}")
def reunioes_put(rid: str, body: ReuniaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE conselho_reuniao SET titulo=%s, data=%s, hora=%s, local=%s, "
                    "status=%s, assinada=%s, tipo=%s, participantes=%s WHERE id=%s",
                    (body.titulo.strip(), body.data or None, body.hora, body.local,
                     body.status, body.assinada, body.tipo, body.participantes or None, rid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Reunião não encontrada.")
        if body.pauta is not None:       # pauta enviada substitui a atual
            cur.execute("DELETE FROM conselho_pauta WHERE reuniao_id=%s", (rid,))
            for i, p in enumerate(body.pauta):
                cur.execute("INSERT INTO conselho_pauta (tenant_id, reuniao_id, item, tempo, material, ordem) "
                            "VALUES (%s,%s,%s,%s,%s,%s)",
                            (tid, rid, p.get("item", ""), p.get("tempo"), p.get("material"), i))
        reuniao = _reuniao_row(cur, rid)
    return reuniao


@app.delete("/conselho/reunioes/{rid}")
def reunioes_delete(rid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM conselho_reuniao WHERE id=%s", (rid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Reunião não encontrada.")
    return {"ok": True}


@app.post("/conselho/reunioes/{rid}/caderno")
def reuniao_caderno(rid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    """Caderno da reunião: compila plano, resultados, FCAs e deliberações num
    texto pronto para circular antes do encontro (IA quando disponível)."""
    _can_edit(user)
    with tenant_session(tid) as cur:
        reuniao = _reuniao_row(cur, rid)
        if not reuniao:
            raise HTTPException(404, "Reunião não encontrada.")
        cur.execute("SELECT titulo, status FROM okr_objetivo ORDER BY criado_em")
        objetivos = cur.fetchall()
        cur.execute("SELECT titulo, status, responsavel, prazo FROM fca_ciclo "
                    "WHERE status IN ('aberto','em_andamento') ORDER BY criado_em DESC LIMIT 6")
        fcas = cur.fetchall()
        cur.execute("SELECT texto, status, follow FROM deliberacao ORDER BY data DESC NULLS LAST LIMIT 8")
        delibs = cur.fetchall()
        yoy = _yoy_do_ultimo_mes(cur)

    linhas = [f"CADERNO — {reuniao['titulo']}",
              f"Data: {reuniao['data'] or 'a agendar'} · {reuniao['hora'] or ''} · {reuniao['local'] or ''}", ""]
    if yoy:
        linhas.append(f"Resultado do último mês: civil {yoy['var_civil']*100:+.1f}% · "
                      f"varejo (ajustado) {yoy['var_ajustada']*100:+.1f}% vs. ano anterior.")
    if reuniao["pauta"]:
        linhas.append("")
        linhas.append("PAUTA")
        for p in reuniao["pauta"]:
            linhas.append(f"  • {p['item']} ({p['tempo'] or 's/ tempo'}) — material: {p['material'] or '—'}")
    if objetivos:
        linhas.append("")
        linhas.append("OKRS DO CICLO")
        for t, _ in objetivos:
            linhas.append(f"  • {t}")
    if fcas:
        linhas.append("")
        linhas.append("FCAS EM CURSO")
        for t, st, resp, prazo in fcas:
            linhas.append(f"  • {t} — {st} (dono: {resp or '—'}, prazo: {prazo or '—'})")
    if delibs:
        linhas.append("")
        linhas.append("DELIBERAÇÕES")
        for t, st, fu in delibs:
            linhas.append(f"  • {t} — {st}" + (f" · follow-up: {fu}" if fu else ""))
    base = "\n".join(linhas)
    texto = advisor._chamada(
        "Você é o Advisor do BoardOS. Transforme o rascunho abaixo num caderno de reunião "
        "de conselho claro e executivo, em português, com seções e leitura fluida. "
        "Não invente números que não estão no rascunho.", base, 1500) if advisor.disponivel() else None
    return {"caderno": texto or base, "fonte": "ia" if texto else "modelo"}


# ------------------------------------------------------------- deliberações
class DeliberacaoIn(BaseModel):
    texto: str
    data: Optional[str] = None
    status: str = "em_pauta"             # em_pauta | aprovada | concluida
    follow: Optional[str] = None
    iniciativa_id: Optional[str] = None  # follow-up automático da iniciativa
    dono: Optional[str] = None
    prazo: Optional[str] = None


@app.get("/deliberacoes")
def deliberacoes_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT d.id, d.texto, d.data, d.status, d.follow, d.iniciativa_id, i.nome, "
                    "d.dono, d.prazo "
                    "FROM deliberacao d LEFT JOIN iniciativa i ON i.id=d.iniciativa_id "
                    "ORDER BY (d.status='concluida'), d.data DESC NULLS LAST")
        rows = [{"id": str(r[0]), "texto": r[1], "data": str(r[2]) if r[2] else None,
                 "status": r[3], "follow": r[4],
                 "iniciativa_id": str(r[5]) if r[5] else None, "iniciativa": r[6],
                 "dono": r[7], "prazo": str(r[8]) if r[8] else None}
                for r in cur.fetchall()]
    return {"deliberacoes": rows}


@app.post("/deliberacoes")
def deliberacoes_post(body: DeliberacaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.texto.strip():
        raise HTTPException(400, "Descreva a deliberação.")
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO deliberacao (tenant_id, texto, data, status, follow, iniciativa_id, dono, prazo) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, body.texto.strip(), body.data or None, body.status, body.follow,
                     body.iniciativa_id or None, body.dono, body.prazo or None))
        did = cur.fetchone()[0]
    return {"id": str(did)}


@app.put("/deliberacoes/{did}")
def deliberacoes_put(did: str, body: DeliberacaoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE deliberacao SET texto=%s, data=%s, status=%s, follow=%s, iniciativa_id=%s, "
                    "dono=%s, prazo=%s WHERE id=%s",
                    (body.texto.strip(), body.data or None, body.status, body.follow,
                     body.iniciativa_id or None, body.dono, body.prazo or None, did))
        if cur.rowcount == 0:
            raise HTTPException(404, "Deliberação não encontrada.")
    return {"ok": True}


@app.delete("/deliberacoes/{did}")
def deliberacoes_delete(did: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM deliberacao WHERE id=%s", (did,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Deliberação não encontrada.")
    return {"ok": True}


# ----------------------------------------------- iniciativas (plano tático)
class IniciativaIn(BaseModel):
    nome: str
    objetivo_id: Optional[str] = None
    dono: Optional[str] = None
    orcamento: Optional[float] = None
    pilar: Optional[str] = None
    marco: Optional[str] = None
    marco_prazo: Optional[str] = None


@app.get("/iniciativas")
def iniciativas_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT i.id, i.nome, i.objetivo_id, o.titulo, i.dono, i.orcamento, "
                    "i.pilar, i.marco, i.marco_prazo "
                    "FROM iniciativa i LEFT JOIN okr_objetivo o ON o.id=i.objetivo_id "
                    "ORDER BY i.nome")
        inis = [{"id": str(r[0]), "nome": r[1],
                 "objetivo_id": str(r[2]) if r[2] else None, "objetivo": r[3],
                 "dono": r[4], "orcamento": float(r[5]) if r[5] is not None else None,
                 "pilar": r[6], "marco": r[7],
                 "marco_prazo": str(r[8]) if r[8] else None,
                 "acoes": []} for r in cur.fetchall()]
        por_id = {i["id"]: i for i in inis}
        cur.execute("SELECT iniciativa_id, id, oque, como, quem, quando, quanto, status "
                    "FROM acao_5w2h WHERE iniciativa_id IS NOT NULL ORDER BY quando NULLS LAST")
        for iid, aid, oq, cm, qm, qd, qt, st in cur.fetchall():
            i = por_id.get(str(iid))
            if i is not None:
                i["acoes"].append({"id": str(aid), "oque": oq, "como": cm, "quem": qm,
                                   "quando": str(qd) if qd else None,
                                   "quanto": float(qt) if qt is not None else None,
                                   "status": st})
    return {"iniciativas": inis}


@app.post("/iniciativas")
def iniciativas_post(body: IniciativaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.nome.strip():
        raise HTTPException(400, "Dê um nome à iniciativa.")
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO iniciativa (tenant_id, nome, objetivo_id, dono, orcamento, pilar, marco, marco_prazo) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, body.nome.strip(), body.objetivo_id or None, body.dono, body.orcamento,
                     body.pilar, body.marco, body.marco_prazo or None))
        iid = cur.fetchone()[0]
    return {"id": str(iid)}


@app.put("/iniciativas/{iid}")
def iniciativas_put(iid: str, body: IniciativaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE iniciativa SET nome=%s, objetivo_id=%s, dono=%s, orcamento=%s, "
                    "pilar=%s, marco=%s, marco_prazo=%s WHERE id=%s",
                    (body.nome.strip(), body.objetivo_id or None, body.dono, body.orcamento,
                     body.pilar, body.marco, body.marco_prazo or None, iid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Iniciativa não encontrada.")
    return {"ok": True}


@app.delete("/iniciativas/{iid}")
def iniciativas_delete(iid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM iniciativa WHERE id=%s", (iid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Iniciativa não encontrada.")
    return {"ok": True}


# --------------------------------- jornadas guiadas do Advisor (Método Masi)
JORNADAS = {
    "cultura": {
        "nome": "Cultura Organizacional",
        "desc": "13 perguntas sobre a cultura atual e desejada → guia interno + manifesto.",
        "perguntas": [
            {"k": "c1", "q": "Você já sente que existe uma cultura na sua empresa? Se sim, como você descreveria essa cultura hoje?"},
            {"k": "c2", "q": "As pessoas do seu time vivem essa cultura no dia a dia? Por quê?"},
            {"k": "c3", "q": "Que comportamentos você percebe que são mais comuns no time atualmente?"},
            {"k": "c4", "q": "Que tipo de atitude é valorizada dentro da sua empresa, mesmo que informalmente?"},
            {"k": "c5", "q": "O que vocês costumam considerar como um “bom profissional” por aí?"},
            {"k": "c6", "q": "Agora vamos olhar para o futuro: como você gostaria que fosse a cultura da sua empresa?"},
            {"k": "c7", "q": "Quais comportamentos e atitudes você gostaria de reforçar?"},
            {"k": "c8", "q": "E quais você gostaria de eliminar ou mudar?"},
            {"k": "c9", "q": "Que valores você acredita que não podem faltar na cultura da sua empresa?"},
            {"k": "c10", "q": "O que você espera que todas as pessoas do time pratiquem no dia a dia?"},
        ],
        "system": ("Você é o Conselheiro do BoardOS guiando a construção da Cultura Organizacional "
                   "de uma rede de supermercados (Método MASI). A partir das respostas do empresário, "
                   "gere um GUIA INTERNO com: descrição geral da cultura desejada; valores principais; "
                   "comportamentos e atitudes esperadas; o que será tolerado ou não; o que define um "
                   "\"bom profissional\"; gaps entre a cultura atual e a desejada. Depois, escreva um "
                   "MANIFESTO em primeira pessoa, com tom emocional, linguagem de liderança e clareza "
                   "inspiradora, para o dono compartilhar com a equipe. Português, direto, sem inventar fatos."),
    },
    "posicionamento": {
        "nome": "Posicionamento",
        "desc": "“O que minha empresa faz?” — clareza para clientes, time e conselho.",
        "perguntas": [
            {"k": "p1", "q": "O que exatamente vocês vendem (produto, serviço ou solução)?"},
            {"k": "p2", "q": "Qual problema real do cliente vocês resolvem?"},
            {"k": "p3", "q": "Quem é o cliente ideal (perfil, segmento, porte)?"},
            {"k": "p4", "q": "Como vocês entregam valor na prática?"},
            {"k": "p5", "q": "O que diferencia sua empresa da concorrência?"},
            {"k": "p6", "q": "Qual é o principal resultado que o cliente obtém?"},
            {"k": "p7", "q": "Qual é o modelo de receita (como ganham dinheiro)?"},
            {"k": "p8", "q": "Onde atuam (região, online, nacional, nicho)?"},
            {"k": "p9", "q": "Qual é a visão futura ou objetivo principal do negócio?"},
            {"k": "p10", "q": "Há algo que hoje fica vago quando você explica a empresa para alguém de fora?"},
        ],
        "system": ("Você é um especialista em estratégia e comunicação empresarial (Método MASI). "
                   "A partir das respostas, produza um documento claro com: 1. Resumo executivo (3–5 linhas); "
                   "2. O que a empresa faz; 3. Problema que resolve; 4. Público-alvo; 5. Diferenciais "
                   "competitivos; 6. Como ganha dinheiro; 7. Posicionamento resumido numa frase simples. "
                   "Linguagem simples, sem jargão, sem inventar fatos."),
    },
}


class JornadaIn(BaseModel):
    respostas: Dict[str, str]


@app.get("/jornadas")
def jornadas_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT jornada, respostas, resumo FROM jornada")
        salvas = {r[0]: {"respostas": r[1] or {}, "resumo": r[2]} for r in cur.fetchall()}
        # a jornada de Direção é a Descoberta já existente
        cur.execute("SELECT respostas FROM descoberta WHERE tenant_id=%s", (tid,))
        row = cur.fetchone()
        desc_resp = (row[0] if row else {}) or {}
    out = []
    for k, j in JORNADAS.items():
        s = salvas.get(k, {"respostas": {}, "resumo": None})
        resp = s["respostas"]
        n = sum(1 for p in j["perguntas"] if (resp.get(p["k"]) or "").strip())
        out.append({"jornada": k, "nome": j["nome"], "desc": j["desc"],
                    "perguntas": j["perguntas"], "respostas": resp,
                    "respondidas": n, "total": len(j["perguntas"]),
                    "resumo": s["resumo"]})
    n_desc = sum(1 for v in desc_resp.values() if (v or "").strip())
    return {"jornadas": out, "descoberta_respondidas": n_desc}


@app.put("/jornadas/{jkey}")
def jornadas_put(jkey: str, body: JornadaIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    import json as _json
    _can_edit(user)
    if jkey not in JORNADAS:
        raise HTTPException(404, "Jornada desconhecida.")
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO jornada (tenant_id, jornada, respostas, atualizado_em) "
                    "VALUES (%s,%s,%s,now()) ON CONFLICT (tenant_id, jornada) DO UPDATE SET "
                    "respostas=EXCLUDED.respostas, atualizado_em=now()",
                    (tid, jkey, _json.dumps(body.respostas)))
    return {"ok": True}


@app.post("/jornadas/{jkey}/resumo")
def jornadas_resumo(jkey: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    j = JORNADAS.get(jkey)
    if not j:
        raise HTTPException(404, "Jornada desconhecida.")
    with tenant_session(tid) as cur:
        cur.execute("SELECT respostas FROM jornada WHERE tenant_id=%s AND jornada=%s", (tid, jkey))
        row = cur.fetchone()
        respostas = (row[0] if row else {}) or {}
        respondidas = [(p["q"], respostas.get(p["k"], "").strip())
                       for p in j["perguntas"] if (respostas.get(p["k"]) or "").strip()]
        if len(respondidas) < len(j["perguntas"]) // 2:
            raise HTTPException(400, "Responda ao menos metade das perguntas antes de gerar o material.")
        qa = "\n\n".join(f"P: {q}\nR: {r}" for q, r in respondidas)
        texto = advisor._chamada(j["system"], qa, 1800) if advisor.disponivel() else None
        if not texto:
            # fallback sem IA: organiza as respostas em material legível
            texto = (f"{j['nome'].upper()} — material de trabalho (gere com IA para a versão final)\n\n"
                     + "\n\n".join(f"• {q}\n  {r}" for q, r in respondidas))
            fonte = "modelo"
        else:
            fonte = "ia"
        cur.execute("UPDATE jornada SET resumo=%s, atualizado_em=now() "
                    "WHERE tenant_id=%s AND jornada=%s", (texto, tid, jkey))
    return {"resumo": texto, "fonte": fonte}


# ══════════════════ onboarding (primeiro modelo de ação) ══════════════════
class OnboardingIn(BaseModel):
    respostas: Dict[str, str]

    @field_validator("respostas")
    @classmethod
    def _tamanho_ok(cls, v):
        if len(v) > 30:
            raise ValueError("muitas respostas de uma vez")
        for k, val in v.items():
            if len(k) > 40 or len(val or "") > 4000:
                raise ValueError("resposta muito longa")
        return v


@app.get("/onboarding")
def onboarding_get(tid: str = Depends(tenant_of)):
    """Roteiro da entrevista + respostas salvas + modelo proposto (se houver)."""
    with tenant_session(tid) as cur:
        cur.execute("SELECT respostas, modelo, confirmado_em FROM jornada "
                    "WHERE tenant_id=%s AND jornada='onboarding'", (tid,))
        row = cur.fetchone()
    return {"perguntas": onb.PERGUNTAS, "obrigatorias": list(onb.OBRIGATORIAS),
            "respostas": (row[0] if row else {}) or {},
            "modelo": row[1] if row else None,
            "confirmado": bool(row and row[2])}


@app.put("/onboarding")
def onboarding_put(body: OnboardingIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    import json as _json
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO jornada (tenant_id, jornada, respostas, atualizado_em) "
                    "VALUES (%s,'onboarding',%s,now()) ON CONFLICT (tenant_id, jornada) DO UPDATE SET "
                    "respostas=EXCLUDED.respostas, atualizado_em=now()",
                    (tid, _json.dumps(body.respostas)))
    return {"ok": True}


@app.post("/onboarding/modelo")
def onboarding_modelo(user: dict = Depends(current), tid: str = Depends(tenant_of)):
    """Gera o Primeiro Modelo de Ação: IA em JSON estrito com validação e um
    retry; sem IA, fallback determinístico (nunca bloqueia o fluxo)."""
    import json as _json
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT respostas FROM jornada WHERE tenant_id=%s AND jornada='onboarding'", (tid,))
        row = cur.fetchone()
    respostas = (row[0] if row else {}) or {}
    if [k for k in onb.OBRIGATORIAS if not (respostas.get(k) or "").strip()]:
        raise HTTPException(400, "Responda as perguntas obrigatórias antes de gerar o modelo.")
    with platform_session() as cur:
        cur.execute("SELECT nome, segmento FROM platform.tenant WHERE id=%s", (tid,))
        trow = cur.fetchone()
    empresa = trow[0] if trow else "sua empresa"
    segmento = (trow[1] if trow else None) or "outro"
    ano = _dt.now(_tz.utc).year
    qa = "\n\n".join(f"P: {p['q']}\nR: {respostas[p['k']].strip()}"
                     for p in onb.PERGUNTAS if (respostas.get(p["k"]) or "").strip())
    modelo, fonte = None, "modelo"
    if advisor.disponivel():
        system = onb.system_modelo(segmento, empresa, ano)
        texto = advisor._chamada(system, qa, 3500)
        for tentativa in range(2):
            if not texto:
                break
            try:
                modelo = onb.validar_modelo(onb.parse_modelo(texto)).model_dump()
                fonte = "ia"
                break
            except Exception as e:
                texto = advisor._chamada(
                    system, qa + f"\n\nSua resposta anterior era inválida ({e}). "
                    "Responda novamente SOMENTE com o JSON corrigido.", 3500) if tentativa == 0 else None
    if modelo is None:
        modelo = onb.validar_modelo(
            onb.modelo_fallback(respostas, empresa, segmento, ano)).model_dump()
    with tenant_session(tid) as cur:
        cur.execute("UPDATE jornada SET modelo=%s, atualizado_em=now() "
                    "WHERE tenant_id=%s AND jornada='onboarding'", (_json.dumps(modelo), tid))
        if cur.rowcount == 0:   # tenant antigo, sem a linha semeada no cadastro
            cur.execute("INSERT INTO jornada (tenant_id, jornada, respostas, modelo) "
                        "VALUES (%s,'onboarding',%s,%s)",
                        (tid, _json.dumps(respostas), _json.dumps(modelo)))
    return {"modelo": modelo, "fonte": fonte}


@app.post("/onboarding/confirmar")
def onboarding_confirmar(body: onb.ModeloAcao, user: dict = Depends(current),
                         tid: str = Depends(tenant_of)):
    """Grava o modelo REVISADO pelo dono nas telas reais — nada nasce sem esta
    confirmação — e semeia rituais e PIs padrão se ainda não existirem.
    Transação única (commit no fechamento da tenant_session)."""
    import json as _json
    _can_edit(user)
    try:
        m = onb.validar_modelo(body.model_dump())
    except Exception as e:
        raise HTTPException(400, f"Modelo inválido: {e}")
    ano = _dt.now(_tz.utc).year
    criados = {"swot": 0, "okrs": 0, "krs": 0, "iniciativas": 0, "acoes": 0,
               "rituais": False, "pis": False}
    with tenant_session(tid) as cur:
        # serializa aprovações concorrentes do mesmo tenant (ex.: duplo clique
        # + reload); o 2º request só segue depois do commit do 1º.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('onboarding_confirmar:'||%s::text, 0))",
                    (tid,))
        cur.execute("SELECT confirmado_em FROM jornada "
                    "WHERE tenant_id=%s AND jornada='onboarding'", (tid,))
        row = cur.fetchone()
        if row and row[0]:
            raise HTTPException(409, "Onboarding já aprovado.")
        cur.execute("SELECT (SELECT count(*) FROM okr_objetivo) "
                    "+ (SELECT count(*) FROM direcao_estrategica) "
                    "+ (SELECT count(*) FROM swot_item)")
        if cur.fetchone()[0]:
            # o dono já montou parte do plano na mão (ex.: "Concluir depois" e
            # cadastrou OKR/Direção/SWOT antes de voltar ao onboarding) — não
            # sobrescrevemos nada, mas fechamos o onboarding para não prender
            # o usuário num wizard que nunca mais vai conseguir aprovar.
            cur.execute(
                "INSERT INTO jornada (tenant_id, jornada, respostas, confirmado_em, atualizado_em) "
                "VALUES (%s,'onboarding','{}',now(),now()) "
                "ON CONFLICT (tenant_id, jornada) DO UPDATE SET confirmado_em=now(), atualizado_em=now()",
                (tid,))
            return {"ok": True, "ja_tinha_plano": True, "criados": criados}
        d = m.direcao
        cur.execute(
            "INSERT INTO direcao_estrategica (tenant_id, proposito, visao, valores, objetivo_lp, competencia, atualizado_em) "
            "VALUES (%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (tenant_id) DO UPDATE SET "
            "proposito=EXCLUDED.proposito, visao=EXCLUDED.visao, valores=EXCLUDED.valores, "
            "objetivo_lp=EXCLUDED.objetivo_lp, competencia=EXCLUDED.competencia, atualizado_em=now()",
            (tid, d.proposito, d.visao, "\n".join(d.valores) or None, d.objetivo_lp, d.competencia))
        for campo, qd in (("forcas", "forca"), ("fraquezas", "fraqueza"),
                          ("oportunidades", "oportunidade"), ("ameacas", "ameaca")):
            for i, txt in enumerate(getattr(m.swot, campo)):
                cur.execute("INSERT INTO swot_item (tenant_id, quadrante, texto, ordem) "
                            "VALUES (%s,%s,%s,%s)", (tid, qd, txt, i))
                criados["swot"] += 1
        obj_ids = []
        for i, o in enumerate(m.okrs):
            cur.execute("INSERT INTO okr_objetivo (tenant_id, titulo, periodo, nivel, ordem) "
                        "VALUES (%s,%s,%s,'corporativo',%s) RETURNING id",
                        (tid, o.objetivo, o.periodo or str(ano), i))
            oid = str(cur.fetchone()[0])
            obj_ids.append(oid)
            criados["okrs"] += 1
            for j, kr in enumerate(o.krs):
                cur.execute("INSERT INTO okr_kr (tenant_id, objetivo_id, titulo, unidade, meta, atual, base, direcao, ordem) "
                            "VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s)",
                            (tid, oid, kr.titulo, kr.unidade, kr.meta, kr.base, kr.direcao, j))
                criados["krs"] += 1
        for ini in m.iniciativas:
            obj_id = obj_ids[ini.objetivo_idx] if ini.objetivo_idx is not None else None
            cur.execute("INSERT INTO iniciativa (tenant_id, nome, objetivo_id) "
                        "VALUES (%s,%s,%s) RETURNING id", (tid, ini.nome, obj_id))
            iid = str(cur.fetchone()[0])
            criados["iniciativas"] += 1
            for a in ini.acoes:
                cur.execute("INSERT INTO acao_5w2h (tenant_id, objetivo_id, iniciativa_id, oque, porque, onde, quando, quem, como, quanto) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (tid, obj_id, iid, a.oque, a.porque, a.onde, a.quando, a.quem, a.como, a.quanto))
                criados["acoes"] += 1
        cur.execute("SELECT count(*) FROM ritual")
        if not cur.fetchone()[0]:
            for i, (fq, nm, qm, ob, px) in enumerate(RITUAIS_PADRAO):
                cur.execute("INSERT INTO ritual (tenant_id, freq, nome, quem, objetivo, proxima, ordem) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s)", (tid, fq, nm, qm, ob, px, i))
            criados["rituais"] = True
        cur.execute("SELECT count(*) FROM pi")
        if not cur.fetchone()[0]:
            for chave, nome, pilar, jornada, direcao, ordem in PIS_PADRAO:
                cur.execute("INSERT INTO pi (tenant_id, chave, nome, pilar, jornada, direcao, ordem, fonte) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                            (tid, chave, nome, pilar, jornada, direcao, ordem, "importação de vendas"))
            criados["pis"] = True
        cur.execute("INSERT INTO jornada (tenant_id, jornada, respostas, modelo, confirmado_em, atualizado_em) "
                    "VALUES (%s,'onboarding','{}',%s,now(),now()) "
                    "ON CONFLICT (tenant_id, jornada) DO UPDATE SET "
                    "modelo=EXCLUDED.modelo, confirmado_em=now(), atualizado_em=now()",
                    (tid, _json.dumps(m.model_dump())))
    return {"ok": True, "criados": criados}


# ═══════════════════════════ perfil do usuário ═══════════════════════════
class PerfilIn(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None


@app.get("/perfil")
def perfil_get(user: dict = Depends(current)):
    """Dados do próprio usuário logado (qualquer papel, inclusive super_admin)."""
    with platform_session() as cur:
        cur.execute("SELECT email, nome, telefone, papel FROM platform.usuario_login "
                    "WHERE lower(email)=lower(%s)", (user["sub"],))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Usuário não encontrado.")
    return {"email": row[0], "nome": row[1], "telefone": row[2], "papel": row[3]}


@app.put("/perfil")
def perfil_put(body: PerfilIn, user: dict = Depends(current)):
    """Atualiza nome e telefone do próprio usuário. O e-mail é a chave de
    login e não muda por aqui (evita se trancar para fora da conta)."""
    with platform_session() as cur:
        cur.execute("UPDATE platform.usuario_login SET nome=%s, telefone=%s "
                    "WHERE lower(email)=lower(%s)",
                    ((body.nome or "").strip() or None,
                     (body.telefone or "").strip() or None, user["sub"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "Usuário não encontrado.")
    # espelha o nome no cadastro do tenant, quando existir
    if user.get("tenant_id"):
        try:
            with tenant_session(user["tenant_id"]) as cur:
                cur.execute("UPDATE app_user SET nome=%s WHERE lower(email)=lower(%s)",
                            ((body.nome or "").strip() or None, user["sub"]))
        except Exception:
            pass
    return {"ok": True}


# ═══════════════════ demografia das áreas de influência ═══════════════════
class DemografiaIn(BaseModel):
    aneis: list                          # [{anel, raio_km, populacao, domicilios, setores, potencial_ano}]
    fonte: Optional[str] = None


@app.put("/lojas/{lid}/demografia")
def demografia_put(lid: str, body: DemografiaIn, user: dict = Depends(current),
                   tid: str = Depends(tenant_of)):
    """Grava o agregado do Censo por anel (calculado pelo scripts/demografia_ibge.py)."""
    _can_edit(user)
    validos = {"primaria", "secundaria", "terciaria"}
    with tenant_session(tid) as cur:
        cur.execute("SELECT 1 FROM loja WHERE id=%s", (lid,))
        if not cur.fetchone():
            raise HTTPException(404, "Loja não encontrada.")
        for a in body.aneis:
            if a.get("anel") not in validos:
                raise HTTPException(400, f"Anel inválido: {a.get('anel')}")
            cur.execute(
                "INSERT INTO loja_demografia (tenant_id, loja_id, anel, raio_km, populacao, "
                "domicilios, setores, potencial_ano, fonte, calculado_em) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
                "ON CONFLICT (tenant_id, loja_id, anel) DO UPDATE SET "
                "raio_km=EXCLUDED.raio_km, populacao=EXCLUDED.populacao, "
                "domicilios=EXCLUDED.domicilios, setores=EXCLUDED.setores, "
                "potencial_ano=EXCLUDED.potencial_ano, fonte=EXCLUDED.fonte, calculado_em=now()",
                (tid, lid, a["anel"], a.get("raio_km"), int(a.get("populacao") or 0),
                 int(a.get("domicilios") or 0), int(a.get("setores") or 0),
                 a.get("potencial_ano"), body.fonte))
    return {"ok": True}


@app.get("/lojas/{lid}/demografia")
def demografia_get(lid: str, tid: str = Depends(tenant_of)):
    ordem = {"primaria": 0, "secundaria": 1, "terciaria": 2}
    with tenant_session(tid) as cur:
        cur.execute("SELECT anel, raio_km, populacao, domicilios, setores, potencial_ano, "
                    "fonte, calculado_em FROM loja_demografia WHERE loja_id=%s", (lid,))
        rows = [{"anel": r[0], "raio_km": float(r[1]) if r[1] is not None else None,
                 "populacao": int(r[2]), "domicilios": int(r[3]), "setores": int(r[4]),
                 "potencial_ano": float(r[5]) if r[5] is not None else None,
                 "fonte": r[6], "calculado_em": r[7].isoformat()} for r in cur.fetchall()]
    rows.sort(key=lambda x: ordem.get(x["anel"], 9))
    return {"aneis": rows}


# ═══════════ trajetória de metas + squad de agentes (ciclo fechado) ═══════════
@app.get("/okrs/trajetoria")
def okrs_trajetoria(tid: str = Depends(tenant_of)):
    """Meta mês a mês de cada KR do ciclo: faturamento usa o mês do ano
    anterior × meta anual; KRs de nível (%/R$) interpolam base (jan) → meta (dez)."""
    from datetime import date as _date
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, titulo, unidade, meta, base, direcao, fonte FROM okr_kr")
        krs = cur.fetchall()
        cur.execute("SELECT max(data) FROM gold_venda_diaria")
        row = cur.fetchone()
        ult = row[0] if row else None
        ano = ult.year if ult else _date.today().year
        por_mes_fat = {}
        if ult:
            cur.execute(
                "SELECT date_trunc('month', data)::date, sum(faturamento_liq) "
                "FROM gold_venda_diaria WHERE categoria_id IS NULL "
                "AND extract(year FROM data) = %s GROUP BY 1", (ano - 1,))
            por_mes_fat = {r[0].month: float(r[1]) for r in cur.fetchall()}
    out = []
    for kid, titulo, unidade, meta, base, direcao, fonte in krs:
        meta = float(meta)
        base = float(base) if base is not None else None
        metas = []
        for m in range(1, 13):
            if fonte == "fat_yoy_pct":
                b = por_mes_fat.get(m)
                metas.append(round(b * (1 + meta / 100), 2) if b else None)
            elif base is not None:
                metas.append(round(base + (meta - base) * m / 12.0, 2))
            else:
                metas.append(meta)
        out.append({"kr_id": str(kid), "titulo": titulo, "unidade": unidade,
                    "meta": meta, "fonte": fonte, "ano": ano, "metas_mensais": metas})
    return {"krs": out}


@app.post("/agentes/rodar")
def agentes_rodar(force: bool = False, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    """Roda o squad (Analista → Verificador → Projetista → Relator).
    Idempotente por dia — o cron e o botão do painel podem chamar à vontade."""
    _can_edit(user)
    return agentes.rodar(tid, force=force)


@app.get("/agentes/ultima")
def agentes_ultima(tid: str = Depends(tenant_of)):
    return agentes.ultima(tid)


# ═══════════════════════════ Portal v3 (protótipo novo) ═══════════════════════════
# Fatos Relevantes, catálogo de PIs, riscos, maturidade de gestão, chat do
# Conselheiro e o assistente de redação de OKRs.

class FatoIn(BaseModel):
    texto: str
    loja_id: Optional[str] = None
    pilar: Optional[str] = None          # M|E|R|C|A|D|O
    tags: Optional[list] = None
    propagacao: Optional[dict] = None    # {fca:bool, swot:bool, war_room:bool}


def _classificar_fato(texto: str, tags: list) -> dict:
    """Proposta de classificação/propagação (Secretário ✦) — heurística com IA opcional."""
    t = (texto or "").lower() + " " + " ".join(tags or []).lower()
    prop = {"fca": False, "swot": False, "war_room": False}
    pilar = None
    if any(k in t for k in ("concorren", "atacarejo", "abriu", "inaugur")):
        pilar, prop["swot"], prop["war_room"] = "C", True, True
    elif any(k in t for k in ("clima", "geada", "chuva", "custo", "fornecedor", "leite")):
        pilar, prop["fca"], prop["swot"] = "A", True, True
    elif any(k in t for k in ("ruptura", "estoque", "falta")):
        pilar, prop["fca"] = "A", True
    elif any(k in t for k in ("preço", "preco", "margem", "promo")):
        pilar, prop["fca"] = "C", True
    elif any(k in t for k in ("fila", "atendimento", "reclama")):
        pilar, prop["fca"] = "E", True
    classificacao = None
    if advisor.disponivel():
        classificacao = advisor._chamada(
            "Você é o Secretário do BoardOS. Classifique o fato relevante abaixo em 1 frase "
            "curta (o que é e o que ameaça/beneficia) e sugira o pilar MERCADO "
            "(M mercadológico, E experiência, R perdas, C comercial/pricing, A abastecimento, "
            "D digital, O operações). Responda só a frase.", texto, 200)
    return {"pilar": pilar, "classificacao": classificacao, "propagacao": prop}


@app.get("/fatos")
def fatos_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT f.id, f.texto, f.autor, f.loja_id, l.nome, f.pilar, f.tags, "
                    "f.classificacao, f.propagacao, f.confirmado, f.fca_id, f.criado_em "
                    "FROM fato_relevante f LEFT JOIN loja l ON l.id=f.loja_id "
                    "ORDER BY f.criado_em DESC LIMIT 100")
        fatos = [{"id": str(r[0]), "texto": r[1], "autor": r[2],
                  "loja_id": str(r[3]) if r[3] else None, "loja": r[4],
                  "pilar": r[5], "tags": r[6] or [], "classificacao": r[7],
                  "propagacao": r[8] or {}, "confirmado": r[9],
                  "fca_id": str(r[10]) if r[10] else None,
                  "criado_em": r[11].isoformat()} for r in cur.fetchall()]
    return {"fatos": fatos}


@app.post("/fatos")
def fatos_post(body: FatoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    import json as _json
    if not body.texto.strip():
        raise HTTPException(400, "Descreva o fato.")
    sug = _classificar_fato(body.texto, body.tags or [])
    pilar = body.pilar or sug["pilar"]
    prop = body.propagacao if body.propagacao is not None else sug["propagacao"]
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO fato_relevante (tenant_id, texto, autor, loja_id, pilar, tags, "
                    "classificacao, propagacao) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, body.texto.strip(), user.get("nome") or user.get("sub"),
                     body.loja_id or None, pilar, body.tags or None,
                     sug["classificacao"], _json.dumps(prop)))
        fid = cur.fetchone()[0]
    return {"id": str(fid), "pilar": pilar, "classificacao": sug["classificacao"],
            "propagacao": prop}


class FatoConfirmarIn(BaseModel):
    fca: Optional[bool] = None           # sobrescreve a propagação proposta
    swot: Optional[bool] = None


@app.post("/fatos/{fid}/confirmar")
def fatos_confirmar(fid: str, body: Optional[FatoConfirmarIn] = None,
                    user: dict = Depends(current), tid: str = Depends(tenant_of)):
    """Confirma o fato e aplica a propagação: cria FCA e/ou item de SWOT.
    Nada acontece sem esta confirmação humana (contrato do design system)."""
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT texto, pilar, propagacao, confirmado, loja_id FROM fato_relevante WHERE id=%s", (fid,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Fato não encontrado.")
        texto, pilar, prop, confirmado, loja_id = row[0], row[1], row[2] or {}, row[3], row[4]
        if body is not None:             # o usuário editou a propagação no modal
            if body.fca is not None:
                prop["fca"] = body.fca
            if body.swot is not None:
                prop["swot"] = body.swot
        if confirmado:
            return {"ok": True, "ja_confirmado": True}
        fca_id = None
        if prop.get("fca"):
            cur.execute("INSERT INTO fca_ciclo (tenant_id, titulo, fato, status, origem, pilar) "
                        "VALUES (%s,%s,%s,'aberto','fato_relevante',%s) RETURNING id",
                        (tid, texto[:120], texto, pilar))
            fca_id = cur.fetchone()[0]
        if prop.get("swot"):
            cur.execute("INSERT INTO swot_item (tenant_id, quadrante, texto, ordem) "
                        "SELECT %s,'ameaca',%s, COALESCE(max(ordem)+1,0) FROM swot_item WHERE quadrante='ameaca'",
                        (tid, texto[:200] + " (fato)"))
        import json as _json
        cur.execute("UPDATE fato_relevante SET confirmado=true, fca_id=%s, propagacao=%s WHERE id=%s",
                    (fca_id, _json.dumps(prop), fid))
    return {"ok": True, "fca_id": str(fca_id) if fca_id else None}


# ----------------------------------------------------- catálogo de PIs
PIS_PADRAO = [
    ("venda", "Venda total", "C", "financeira", "up", 0),
    ("margem", "Margem bruta", "C", "financeira", "up", 1),
    ("ticket", "Ticket médio", "E", "cliente", "up", 2),
    ("itens_cupom", "Itens por cupom", "M", "produto", "up", 3),
    ("ruptura", "Ruptura", "A", "produto", "down", 4),
    ("quebra", "Quebra / perdas", "R", "produto", "down", 5),
]


@app.get("/pis")
def pis_get(ano: int, mes: int, tid: str = Depends(tenant_of)):
    """Catálogo de PIs com o realizado do mês (derivado do gold) e meta."""
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, chave, nome, pilar, jornada, direcao, meta, fonte, oficial "
                    "FROM pi ORDER BY ordem")
        cat = [{"id": str(r[0]), "chave": r[1], "nome": r[2], "pilar": r[3],
                "jornada": r[4], "direcao": r[5],
                "meta": float(r[6]) if r[6] is not None else None,
                "fonte": r[7], "oficial": r[8]} for r in cur.fetchall()]
        atual = _gold_mes(cur, ano, mes)
        base = _gold_mes(cur, ano - 1, mes)
    yoy = comparison.compare(atual, base) if atual and base else None
    fat = sum(d["faturamento_liq"] for d in atual)
    cup = sum(d.get("cupons", 0) for d in atual)
    itn = sum(d.get("itens", 0) for d in atual)
    mrg = sum(d.get("margem", 0) for d in atual)
    valores = {
        "venda": {"valor": fat, "fmt": "brl",
                  "delta": yoy["var_ajustada"] if yoy else None},
        "margem": {"valor": mrg / fat * 100 if fat and 0 < mrg < fat else None, "fmt": "pct1"},
        "ticket": {"valor": fat / cup if cup else None, "fmt": "rs2",
                   "delta": (yoy["ticket_atual"] / yoy["ticket_base"] - 1)
                   if yoy and yoy.get("ticket_atual") and yoy.get("ticket_base") else None},
        "itens_cupom": {"valor": itn / cup if cup else None, "fmt": "num1"},
        "ruptura": {"valor": None, "fmt": "pct1", "nota": "requer integração de estoque"},
        "quebra": {"valor": None, "fmt": "pct1", "nota": "requer integração de perdas"},
    }
    for c in cat:
        c.update(valores.get(c["chave"], {}))
    return {"pis": cat, "periodo": f"{ano}-{mes:02d}"}


@app.post("/pis/padrao")
def pis_padrao(user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("SELECT count(*) FROM pi")
        if cur.fetchone()[0]:
            raise HTTPException(409, "Catálogo já criado.")
        for chave, nome, pilar, jornada, direcao, ordem in PIS_PADRAO:
            cur.execute("INSERT INTO pi (tenant_id, chave, nome, pilar, jornada, direcao, ordem, fonte) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (tid, chave, nome, pilar, jornada, direcao, ordem, "importação de vendas"))
    return {"ok": True}


class PiIn(BaseModel):
    nome: str
    pilar: Optional[str] = None
    jornada: Optional[str] = None
    meta: Optional[float] = None
    direcao: str = "up"
    fonte: Optional[str] = None


@app.put("/pis/{pid}")
def pis_put(pid: str, body: PiIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE pi SET nome=%s, pilar=%s, jornada=%s, meta=%s, direcao=%s, fonte=%s "
                    "WHERE id=%s",
                    (body.nome.strip(), body.pilar, body.jornada, body.meta, body.direcao,
                     body.fonte, pid))
        if cur.rowcount == 0:
            raise HTTPException(404, "PI não encontrado.")
    return {"ok": True}


# ----------------------------------------------------------- riscos
class RiscoIn(BaseModel):
    titulo: str
    probabilidade: str = "medio"
    impacto: str = "medio"
    status: str = "ativo"
    revisao: Optional[str] = None


@app.get("/riscos")
def riscos_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, titulo, probabilidade, impacto, status, revisao FROM risco "
                    "ORDER BY (status<>'ativo'), ordem, titulo")
        riscos = [{"id": str(r[0]), "titulo": r[1], "probabilidade": r[2], "impacto": r[3],
                   "status": r[4], "revisao": r[5]} for r in cur.fetchall()]
    return {"riscos": riscos}


@app.post("/riscos")
def riscos_post(body: RiscoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    if not body.titulo.strip():
        raise HTTPException(400, "Descreva o risco.")
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO risco (tenant_id, titulo, probabilidade, impacto, status, revisao) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (tid, body.titulo.strip(), body.probabilidade, body.impacto, body.status, body.revisao))
        rid = cur.fetchone()[0]
    return {"id": str(rid)}


@app.put("/riscos/{rid}")
def riscos_put(rid: str, body: RiscoIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("UPDATE risco SET titulo=%s, probabilidade=%s, impacto=%s, status=%s, revisao=%s "
                    "WHERE id=%s", (body.titulo.strip(), body.probabilidade, body.impacto,
                                    body.status, body.revisao, rid))
        if cur.rowcount == 0:
            raise HTTPException(404, "Risco não encontrado.")
    return {"ok": True}


@app.delete("/riscos/{rid}")
def riscos_delete(rid: str, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        cur.execute("DELETE FROM risco WHERE id=%s", (rid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Risco não encontrado.")
    return {"ok": True}


# ------------------------------------------------ maturidade de gestão (6D)
MATURIDADE_DIMENSOES = ["Estratégia & desdobramento", "Rituais", "Indicadores & metas",
                        "Pessoas & consequência", "Dados & integração", "Uso de IA na rotina"]


class MaturidadeIn(BaseModel):
    notas: Dict[str, float]
    alvos: Optional[Dict[str, float]] = None


@app.get("/maturidade")
def maturidade_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT dimensao, nota, alvo FROM maturidade_gestao")
        salvo = {r[0]: {"nota": float(r[1]) if r[1] is not None else None,
                        "alvo": float(r[2]) if r[2] is not None else None} for r in cur.fetchall()}
    return {"dimensoes": [{"dimensao": d,
                          "nota": salvo.get(d, {}).get("nota"),
                          "alvo": salvo.get(d, {}).get("alvo")} for d in MATURIDADE_DIMENSOES]}


@app.put("/maturidade")
def maturidade_put(body: MaturidadeIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    _can_edit(user)
    with tenant_session(tid) as cur:
        for d, n in body.notas.items():
            if d not in MATURIDADE_DIMENSOES:
                continue
            alvo = (body.alvos or {}).get(d)
            cur.execute("INSERT INTO maturidade_gestao (tenant_id, dimensao, nota, alvo) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, dimensao) DO UPDATE SET "
                        "nota=EXCLUDED.nota, alvo=COALESCE(EXCLUDED.alvo, maturidade_gestao.alvo)",
                        (tid, d, n, alvo))
    return {"ok": True}


# --------------------------------------------- chat persistido do Conselheiro
class ChatIn(BaseModel):
    texto: str


@app.get("/conversa")
def conversa_get(tid: str = Depends(tenant_of)):
    with tenant_session(tid) as cur:
        cur.execute("SELECT autor, papel, texto, fontes, criado_em FROM conversa_msg "
                    "ORDER BY criado_em DESC LIMIT 40")
        msgs = [{"autor": r[0], "papel": r[1], "texto": r[2], "fontes": r[3] or [],
                 "criado_em": r[4].isoformat()} for r in cur.fetchall()]
    msgs.reverse()
    return {"mensagens": msgs}


@app.post("/conversa")
def conversa_post(body: ChatIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    if not body.texto.strip():
        raise HTTPException(400, "Escreva a pergunta.")
    contexto, _ = _contexto_tenant(tid)
    resposta = advisor.responder_pergunta(contexto, body.texto.strip()) if contexto else None
    persistir_resposta = bool(resposta)      # aviso de IA inativa não vira histórico
    if not resposta:
        resposta = ("A IA do Conselheiro ainda não está ativa (configure a ANTHROPIC_API_KEY "
                    "no servidor) — mas seus números continuam no Painel e nos PIs.")
    fontes = []
    low = resposta.lower()
    for chave, rot in (("fatur", "Venda total"), ("venda", "Venda total"),
                       ("margem", "Margem bruta"), ("ticket", "Ticket médio")):
        if chave in low and rot not in fontes:
            fontes.append(rot)
    with tenant_session(tid) as cur:
        cur.execute("INSERT INTO conversa_msg (tenant_id, autor, papel, texto, criado_em) "
                    "VALUES (%s,%s,'user',%s, clock_timestamp())",
                    (tid, user.get("nome") or user.get("sub"), body.texto.strip()))
        if persistir_resposta:
            cur.execute("INSERT INTO conversa_msg (tenant_id, autor, papel, texto, fontes, criado_em) "
                        "VALUES (%s,'conselheiro','ia',%s,%s, clock_timestamp())",
                        (tid, resposta, fontes or None))
    return {"resposta": resposta, "fontes": fontes}


# ------------------------------------------- assistente de redação de OKRs (Guia ✦)
class OkrAssistIn(BaseModel):
    titulo: str


@app.post("/okrs/assistente")
def okrs_assistente(body: OkrAssistIn, user: dict = Depends(current), tid: str = Depends(tenant_of)):
    t = body.titulo.strip()
    if not t:
        raise HTTPException(400, "Escreva o objetivo.")
    vago = not any(ch.isdigit() for ch in t)
    critica = None
    if advisor.disponivel():
        critica = advisor._chamada(
            "Você é o Guia do BoardOS. Critique em 1 frase o objetivo/KR abaixo se ele for "
            "vago (sem número, sem prazo, sem dono) e proponha uma reescrita mensurável no "
            "formato 'Elevar X de A para B até DATA'. Responda em JSON: "
            '{"vago": true|false, "critica": "...", "sugestao": "..."}. Só o JSON.', t, 300)
    if critica:
        import json as _json
        try:
            return _json.loads(critica[critica.index("{"):critica.rindex("}") + 1])
        except Exception:
            pass
    return {"vago": vago,
            "critica": "Objetivo sem número nem prazo — difícil de verificar no fechamento."
            if vago else "Objetivo já traz medida — confira se tem dono único e prazo.",
            "sugestao": f"{t} — defina: métrica, valor atual → alvo e prazo (ex.: até o fim do ciclo)."
            if vago else t}


# --------------------------------------- taxa de execução de decisões
@app.get("/decisoes/taxa")
def decisoes_taxa(tid: str = Depends(tenant_of)):
    """% das deliberações com prazo que foram concluídas dentro dele."""
    from datetime import date as _date
    with tenant_session(tid) as cur:
        cur.execute("SELECT status, prazo FROM deliberacao WHERE prazo IS NOT NULL")
        rows = cur.fetchall()
    if not rows:
        return {"taxa": None, "total": 0,
                "nota": "cadastre prazo nas deliberações para medir a execução"}
    hoje = _date.today()
    concluidas = sum(1 for st, _ in rows if st == "concluida")
    vencidas = sum(1 for st, pz in rows if st != "concluida" and pz < hoje)
    elegiveis = concluidas + vencidas        # pendentes dentro do prazo ficam fora
    return {"taxa": round(concluidas / elegiveis, 3) if elegiveis else None,
            "total": len(rows), "vencidas": vencidas,
            "nota": "taxa = concluídas ÷ (concluídas + vencidas); pendentes no prazo não contam"}
