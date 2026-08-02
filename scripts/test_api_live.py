#!/usr/bin/env python3
"""Smoke test da API BoardOS em produção (stdlib, sem dependências).

Cobre: saúde, autenticação (ok/erro/sem token), isolamento por papel
(/tenants 403 p/ CEO; header alheio ignorado), endpoints de dados e o
fallback do Advisor.

Uso:  python3 scripts/test_api_live.py [BASE_URL]
      (default: https://boardos-api.onrender.com)
"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://boardos-api.onrender.com").rstrip("/")
CEO = ("ceo@aurora.demo", "demo1234")
ADMIN = ("rodrobau@gmail.com", "demo1234")

_ok = _fail = 0


def check(nome, cond, extra=""):
    global _ok, _fail
    cond = bool(cond)
    status = "ok " if cond else "FAIL"
    print(f"  [{status}] {nome}" + (f" — {extra}" if extra else ""))
    _ok += cond
    _fail += (not cond)


def req(method, path, token=None, body=None, headers=None):
    """Retorna (status_code, json|texto)."""
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    for k, v in (headers or {}).items():
        r.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(r, data, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def login(email, senha):
    st, j = req("POST", "/auth/login", body={"email": email, "senha": senha})
    return st, j


def main():
    print(f"Smoke test: {BASE}\n")

    st, j = req("GET", "/health")
    check("health", st == 200 and j.get("ok") is True)

    st, _ = req("GET", "/comparacao/yoy?ano=2026&mes=8")
    check("sem token => 401", st == 401)

    st, _ = login(CEO[0], "senha-errada")
    check("login errado => 401", st == 401)

    st, ceo = login(*CEO)
    check("login CEO", st == 200 and bool(ceo.get("token")), ceo.get("tenant", {}).get("nome", ""))
    tok = ceo.get("token")

    st, _ = req("GET", "/tenants", token=tok)
    check("CEO em /tenants => 403", st == 403)

    st, cy = req("GET", "/comparacao/yoy?ano=2026&mes=8", token=tok)
    check("comparacao/yoy 200 + campos", st == 200 and "var_civil" in cy and "advisor" in cy,
          f"civil={cy.get('var_civil')}")

    fat_ceo = cy.get("total_atual")

    st, ok_ = req("GET", "/okrs", token=tok)
    check("okrs 200", st == 200 and "objetivos" in ok_,
          f"{len(ok_.get('objetivos', []))} objetivos")

    st, lj = req("GET", "/lojas/resumo?ano=2026&mes=8", token=tok)
    check("lojas/resumo 200", st == 200 and len(lj.get("lojas", [])) >= 1)

    st, al = req("GET", "/alertas", token=tok)
    check("alertas 200", st == 200 and "alertas" in al, f"{len(al.get('alertas', []))} alertas")

    st, ai = req("GET", "/advisor/insight", token=tok)
    check("advisor/insight 200 (ia|motor)", st == 200 and ai.get("fonte") in ("ia", "motor"),
          "fonte=" + str(ai.get("fonte")))

    # isolamento: CEO com X-Tenant-Id alheio deve continuar vendo a própria base
    st, adm = login(*ADMIN)
    check("login super-admin", st == 200 and adm.get("user", {}).get("papel") == "super_admin")
    atok = adm.get("token")
    st, ts = req("GET", "/tenants", token=atok)
    check("admin lista tenants", st == 200 and len(ts.get("tenants", [])) >= 1)
    outro = next((t["id"] for t in ts.get("tenants", []) if t["nome"] != "Rede Aurora Campinas"), None)
    if outro and fat_ceo is not None:
        st, cy2 = req("GET", "/comparacao/yoy?ano=2026&mes=8", token=tok,
                      headers={"X-Tenant-Id": outro})
        check("CEO com header alheio: dados próprios", st == 200 and cy2.get("total_atual") == fat_ceo)

    st, _ = req("GET", "/comparacao/yoy?ano=2026&mes=8", token=atok)
    check("admin sem empresa => 400", st == 400)

    st, u = req("GET", "/usuarios", token=tok)
    check("CEO em /usuarios => 403 (não é admin)", st == 403)

    # módulo de Plano (1.2–1.5)
    st, dsc = req("GET", "/descoberta", token=tok)
    check("descoberta GET (roteiro)", st == 200 and len(dsc.get("perguntas", [])) == 17)
    st, _ = req("PUT", "/descoberta", token=tok,
                body={"respostas": {"A1": "Rede Teste, 12 anos"}})
    check("descoberta PUT", st == 200)
    st, _ = req("POST", "/descoberta/resumo", token=tok)
    check("resumo sem obrigatórias => 400", st == 400)

    st, _ = req("PUT", "/direcao", token=tok,
                body={"proposito": "Alimentar bem o bairro", "visao": "Referência regional"})
    check("direcao PUT", st == 200)
    st, d = req("GET", "/direcao", token=tok)
    check("direcao GET persistiu", st == 200 and d.get("proposito") == "Alimentar bem o bairro")

    st, s = req("POST", "/swot", token=tok, body={"quadrante": "forca", "texto": "Hortifrúti forte"})
    check("swot POST", st == 200 and s.get("id"))
    st, _ = req("DELETE", "/swot/" + s.get("id", "x"), token=tok)
    check("swot DELETE", st == 200)

    st, _ = req("PUT", "/radar", token=tok, body={"notas": {"Financeiro": 7}})
    check("radar PUT", st == 200)

    st, a = req("POST", "/acoes", token=tok,
                body={"oque": "TESTE smoke — remover", "quem": "QA", "status": "planejada"})
    check("acoes POST", st == 200 and a.get("id"))
    st, _ = req("DELETE", "/acoes/" + a.get("id", "x"), token=tok)
    check("acoes DELETE", st == 200)

    print(f"\n{_ok} ok, {_fail} falha(s).")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
