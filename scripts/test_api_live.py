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

    # Bloco 3: forecast + categorias
    st, f = req("GET", "/forecast/mes?ano=2026&mes=8", token=tok)
    check("forecast/mes 200 + soma bate", st == 200 and
          abs(f.get("total_projetado", 0) - (f.get("total_realizado", 0) + f.get("total_previsto", 0))) < 0.05,
          f"projetado={f.get('total_projetado')}")
    st, cg = req("GET", "/categorias/resumo?ano=2026&mes=8", token=tok)
    part_total = sum(c.get("participacao", 0) for c in cg.get("categorias", []))
    check("categorias/resumo 200 + participações ~100%", st == 200 and
          len(cg.get("categorias", [])) >= 4 and 0.95 <= part_total <= 1.05,
          f"{len(cg.get('categorias', []))} categorias")

    st, a = req("POST", "/acoes", token=tok,
                body={"oque": "TESTE smoke — remover", "quem": "QA", "status": "planejada"})
    check("acoes POST", st == 200 and a.get("id"))
    st, _ = req("DELETE", "/acoes/" + a.get("id", "x"), token=tok)
    check("acoes DELETE", st == 200)

    # 2.2/2.3 IA (fallback quando sem chave) + 3.4 feriados
    st, pg = req("POST", "/advisor/pergunta", token=tok, body={"pergunta": "Qual loja mais caiu?"})
    check("advisor/pergunta 200 (ia|indisponivel)", st == 200 and pg.get("fonte") in ("ia", "indisponivel"),
          "fonte=" + str(pg.get("fonte")))
    # 3.14 cadastro de lojas + IBGE
    st, lj2 = req("POST", "/lojas", token=tok,
                  body={"codigo": "QA1", "nome": "Loja QA", "municipio": "Campinas", "uf": "SP"})
    check("loja POST + IBGE automático", st == 200 and (lj2.get("populacao") or 0) > 1_000_000,
          f"pop={lj2.get('populacao')} pib/hab={lj2.get('pib_per_capita')}")
    if lj2.get("id"):
        st, _ = req("POST", "/lojas/" + lj2["id"] + "/ibge", token=tok)
        check("loja IBGE refresh", st == 200)
        st, _ = req("DELETE", "/lojas/" + lj2["id"], token=tok)
        check("loja DELETE (sem vendas)", st == 200)

    st, cons = req("GET", "/conselho/pautas", token=tok)
    check("conselho/pautas 200 + 5 conselheiros", st == 200 and len(cons.get("conselheiros", [])) == 5,
          " | ".join(c["nome"].split(" ")[-1] for c in cons.get("conselheiros", [])))
    st, pp = req("POST", "/advisor/pergunta", token=tok,
                 body={"pergunta": "Qual categoria priorizar?", "persona": "categorias"})
    check("pergunta com persona 200", st == 200 and pp.get("fonte") in ("ia", "indisponivel"))
    st, _ = req("POST", "/advisor/pergunta", token=tok,
                body={"pergunta": "x", "persona": "invalida"})
    check("persona inválida => 400", st == 400)

    st, rx = req("GET", "/advisor/resumo-executivo", token=tok)
    check("resumo-executivo 200 com texto", st == 200 and bool(rx.get("texto")),
          "fonte=" + str(rx.get("fonte")))
    st, fer = req("POST", "/feriados", token=tok,
                  body={"data": "2026-12-25", "nome": "Natal TESTE", "tipo": "feriado"})
    check("feriado POST", st == 200 and fer.get("id"))
    st, fl = req("GET", "/feriados", token=tok)
    check("feriado GET", st == 200 and any(f["nome"] == "Natal TESTE" for f in fl.get("feriados", [])))
    if fer.get("id"):
        st, _ = req("DELETE", "/feriados/" + fer["id"], token=tok)
        check("feriado DELETE", st == 200)

    # 4.2 painel super-admin
    st, mm = req("GET", "/admin/metricas", token=atok)
    check("admin/metricas 200", st == 200 and mm.get("totais", {}).get("tenants", 0) >= 3,
          f"MRR={mm.get('totais', {}).get('mrr_estimado_cent', 0)/100:.0f}")
    st, _ = req("GET", "/admin/metricas", token=tok)
    check("CEO em /admin/metricas => 403", st == 403)
    st, nt = req("POST", "/tenants", token=atok, body={"nome": "TESTE Smoke Ltda"})
    check("tenant POST", st == 200 and nt.get("id"))
    if nt.get("id"):
        st, _ = req("PUT", "/tenants/" + nt["id"], token=atok,
                    body={"nome": "TESTE Smoke Ltda", "status": "cancelado"})
        check("tenant PUT (suspender)", st == 200)
        st, _ = req("DELETE", "/tenants/" + nt["id"], token=atok)
        check("tenant DELETE (limpeza)", st == 200)

    print(f"\n{_ok} ok, {_fail} falha(s).")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
