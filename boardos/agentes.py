# -*- coding: utf-8 -*-
"""Squad de agentes do BoardOS: analisa → verifica → projeta → relata.

Uma RODADA percorre quatro agentes, sempre sobre dado real do tenant:

  1. Analista    — realizado × esperado: desvios que merecem ação (FCA);
  2. Verificador — para cada ação ligada a um KR, o indicador se moveu desde
                   o baseline? (funcionou / sem_efeito / piorou / cedo_demais);
  3. Projetista  — trajetória de cada KR até o fim do ciclo: vamos alcançar?
  4. Relator     — consolida tudo na "Reflexão do mês" (IA quando disponível,
                   texto determinístico quando não).

Sem ANTHROPIC_API_KEY tudo continua funcionando — os números são calculados
aqui; a IA só melhora a prosa do Relator.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Dict, List, Optional

from . import advisor, comparison
from .db import tenant_session

CEDO_DEMAIS_DIAS = 14      # ações mais novas que isso ainda não são julgadas
FCA_ATIVO = ("aberto", "em_andamento")


# ------------------------------------------------------------- coleta
def _gold_mes(cur, ano: int, mes: int) -> List[dict]:
    cur.execute(
        "SELECT data, sum(faturamento_liq), sum(cupons), sum(itens), sum(margem) "
        "FROM gold_venda_diaria WHERE categoria_id IS NULL "
        "AND date_trunc('month', data) = make_date(%s,%s,1) GROUP BY data ORDER BY data",
        (ano, mes))
    return [{"data": r[0], "faturamento_liq": float(r[1]), "cupons": int(r[2] or 0),
             "itens": int(r[3] or 0), "margem": float(r[4] or 0)} for r in cur.fetchall()]


def _coletar(cur) -> Optional[dict]:
    cur.execute("SELECT max(data) FROM gold_venda_diaria")
    row = cur.fetchone()
    ult = row[0] if row else None
    if not ult:
        return None
    atual = _gold_mes(cur, ult.year, ult.month)
    base = _gold_mes(cur, ult.year - 1, ult.month)
    yoy = None
    if atual and base:
        yoy = comparison.compare(atual, base)

    # 12 semanas de venda diária → séries semanais (tendência/projeção)
    cur.execute(
        "SELECT data, sum(faturamento_liq), sum(cupons), sum(itens), sum(margem) "
        "FROM gold_venda_diaria WHERE categoria_id IS NULL AND data > %s "
        "GROUP BY data ORDER BY data", (ult - timedelta(days=84),))
    dias = cur.fetchall()
    semanas = []
    for i in range(0, len(dias) - 6, 7):
        w = dias[i:i + 7]
        fat = sum(float(d[1]) for d in w)
        cup = sum(int(d[2] or 0) for d in w)
        mrg = sum(float(d[4] or 0) for d in w)
        semanas.append({"fat": fat, "ticket": fat / cup if cup else None,
                        "margem_pct": mrg / fat * 100 if fat and 0 < mrg < fat else None})

    cur.execute("SELECT k.id, k.titulo, k.unidade, k.meta, k.atual, k.base, k.direcao, "
                "k.fonte, o.id, o.titulo FROM okr_kr k JOIN okr_objetivo o ON o.id=k.objetivo_id")
    krs = [{"id": str(r[0]), "titulo": r[1], "unidade": r[2], "meta": float(r[3]),
            "atual": float(r[4]), "base": float(r[5]) if r[5] is not None else None,
            "direcao": r[6], "fonte": r[7], "objetivo_id": str(r[8]), "objetivo": r[9]}
           for r in cur.fetchall()]

    cur.execute("SELECT id, titulo, status, kr_id, baseline, baseline_em, responsavel, prazo "
                "FROM fca_ciclo WHERE status IN %s", (FCA_ATIVO,))
    fcas = [{"id": str(r[0]), "titulo": r[1], "status": r[2],
             "kr_id": str(r[3]) if r[3] else None,
             "baseline": float(r[4]) if r[4] is not None else None,
             "baseline_em": r[5], "responsavel": r[6], "prazo": r[7]}
            for r in cur.fetchall()]

    return {"ultimo_dia": ult, "yoy": yoy, "semanas": semanas, "krs": krs, "fcas": fcas}


def kr_valor_atual(kr: dict, ctx: dict) -> float:
    """Valor vivo do KR: calculado do dado real quando a fonte permite."""
    yoy, sem = ctx.get("yoy"), ctx.get("semanas") or []
    f = kr.get("fonte")
    if f == "fat_yoy_pct" and yoy:
        return round(yoy["var_ajustada"] * 100, 1)
    if f == "ticket_yoy_pct" and yoy and yoy.get("ticket_atual") and yoy.get("ticket_base"):
        return round((yoy["ticket_atual"] / yoy["ticket_base"] - 1) * 100, 1)
    if f == "margem_pct" and sem:
        vals = [s["margem_pct"] for s in sem if s["margem_pct"] is not None]
        if vals:
            return round(vals[-1], 1)
    return kr["atual"]


def _tendencia(vals: List[float]) -> Optional[float]:
    """Inclinação (unidade/semana) por regressão linear simples."""
    vs = [v for v in vals if v is not None]
    n = len(vs)
    if n < 4:
        return None
    sx = sum(range(n)); sy = sum(vs)
    sxy = sum(i * v for i, v in enumerate(vs)); sxx = sum(i * i for i in range(n))
    den = n * sxx - sx * sx
    return (n * sxy - sx * sy) / den if den else None


# ------------------------------------------------------------- agentes
def agente_analista(ctx: dict) -> List[dict]:
    """Desvios entre realizado e esperado que merecem virar ação."""
    desvios = []
    yoy = ctx.get("yoy")
    if yoy and yoy["var_ajustada"] < 0:
        desvios.append({"sev": "r", "kr_id": None,
                        "titulo": "Venda comparável em queda",
                        "detalhe": f"Ajustada por calendário: {yoy['var_ajustada']*100:+.1f}% vs. ano anterior."})
    for kr in ctx["krs"]:
        atual = kr_valor_atual(kr, ctx)
        from_api = _kr_progresso(kr["meta"], atual, kr["base"], kr["direcao"])
        if from_api[1] == "r":
            desvios.append({"sev": "r", "kr_id": kr["id"],
                            "titulo": f"Meta fora da rota — {kr['titulo']}",
                            "detalhe": f"Atual {atual:g} vs. meta {kr['meta']:g} "
                                       f"({kr['objetivo']}) — progresso {from_api[0]*100:.0f}%."})
    sem = ctx["semanas"]
    t = _tendencia([s["margem_pct"] for s in sem])
    if t is not None and t < -0.08:
        desvios.append({"sev": "a", "kr_id": None,
                        "titulo": "Margem em tendência de queda",
                        "detalhe": f"{t:+.2f}pp por semana nas últimas {len(sem)} semanas."})
    return desvios


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
    return round(p, 3), ("g" if p >= 0.7 else "a" if p >= 0.4 else "r")


def agente_verificador(ctx: dict, hoje: date) -> List[dict]:
    """A ação moveu o indicador que queria mover?"""
    por_id = {k["id"]: k for k in ctx["krs"]}
    out = []
    for f in ctx["fcas"]:
        if not f["kr_id"] or f["baseline"] is None or f["kr_id"] not in por_id:
            continue
        kr = por_id[f["kr_id"]]
        atual = kr_valor_atual(kr, ctx)
        delta = round(atual - f["baseline"], 4)
        melhorou = delta > 0 if kr["direcao"] == "up" else delta < 0
        dias = (hoje - f["baseline_em"]).days if f["baseline_em"] else 0
        span = abs(kr["meta"] - (kr["base"] if kr["base"] is not None else 0)) or 1.0
        relevante = abs(delta) >= 0.05 * span      # moveu ≥5% do caminho da meta
        if dias < CEDO_DEMAIS_DIAS:
            veredito = "cedo_demais"
        elif melhorou and relevante:
            veredito = "funcionou"
        elif (not melhorou) and relevante:
            veredito = "piorou"
        else:
            veredito = "sem_efeito"
        out.append({"fca_id": f["id"], "fca": f["titulo"], "kr_id": kr["id"],
                    "kr": kr["titulo"], "baseline": f["baseline"], "valor_atual": atual,
                    "delta": delta, "dias": dias, "veredito": veredito})
    return out


def agente_projetista(ctx: dict, hoje: date) -> List[dict]:
    """Se nada mudar, onde cada KR termina o ciclo?"""
    sem = ctx["semanas"]
    semanas_restantes = max(0, (date(hoje.year, 12, 31) - hoje).days // 7)
    out = []
    for kr in ctx["krs"]:
        atual = kr_valor_atual(kr, ctx)
        proj, metodo = None, None
        f = kr.get("fonte")
        if f in ("fat_yoy_pct", "ticket_yoy_pct"):
            proj, metodo = atual, "ritmo YoY atual mantido até dez"
        elif f == "margem_pct" or "margem" in (kr["titulo"] or "").lower():
            t = _tendencia([s["margem_pct"] for s in sem])
            if t is not None:
                proj = round(atual + t * semanas_restantes, 1)
                metodo = f"regressão de {len(sem)} semanas extrapolada"
        elif "ticket" in (kr["titulo"] or "").lower() and kr["unidade"] not in ("%",):
            t = _tendencia([s["ticket"] for s in sem])
            if t is not None:
                proj = round(atual + t * semanas_restantes, 2)
                metodo = f"regressão de {len(sem)} semanas extrapolada"
        if proj is None:
            proj, metodo = atual, "sem série automática — usa o valor atual"
        alcanca = proj >= kr["meta"] if kr["direcao"] == "up" else proj <= kr["meta"]
        folga = round(proj - kr["meta"], 2)
        p, farol = _kr_progresso(kr["meta"], proj, kr["base"], kr["direcao"])
        out.append({"kr_id": kr["id"], "kr": kr["titulo"], "objetivo": kr["objetivo"],
                    "atual": atual, "meta": kr["meta"], "projetado": proj,
                    "folga": folga, "alcanca": alcanca, "farol": farol, "metodo": metodo})
    return out


def agente_relator(ctx: dict, analise, verifs, projs, hoje: date) -> str:
    linhas = [f"Reflexão do ciclo — dados até {ctx['ultimo_dia']}"]
    ok = [p for p in projs if p["alcanca"]]
    ruim = [p for p in projs if not p["alcanca"]]
    if projs:
        linhas.append(f"Projeção: {len(ok)} de {len(projs)} KRs alcançam a meta se nada mudar.")
        for p in ruim:
            linhas.append(f"  ▼ {p['kr']}: projeta {p['projetado']:g} vs. meta {p['meta']:g} ({p['metodo']}).")
    if verifs:
        for v in verifs:
            rot = {"funcionou": "▲ funcionando", "piorou": "▼ piorou",
                   "sem_efeito": "◆ ainda sem efeito", "cedo_demais": "○ cedo demais"}[v["veredito"]]
            linhas.append(f"  {rot}: \"{v['fca']}\" → {v['kr']} {v['delta']:+g} desde o baseline ({v['dias']} dias).")
    else:
        linhas.append("Nenhuma ação ligada a indicador ainda — ligue os FCAs aos KRs para medir eficácia.")
    if analise:
        linhas.append("Desvios do momento: " + "; ".join(a["titulo"] for a in analise[:4]) + ".")
    base = "\n".join(linhas)
    if advisor.disponivel():
        texto = advisor._chamada(
            "Você é o Relator do BoardOS, preparando a reflexão do mês para a reunião de "
            "resultados de uma rede de supermercados. Reescreva o rascunho abaixo em 3 blocos "
            "curtos (Acima do esperado / Abaixo do esperado — com as ações e sua eficácia / "
            "Rota para as metas), tom executivo, português, sem inventar números.", base, 900)
        if texto:
            return texto
    return base


# ------------------------------------------------------------- rodada
def rodar(tid: str, force: bool = False) -> dict:
    """Executa a rodada do squad para o tenant e grava o resultado.
    Idempotente por dia (a 2ª chamada devolve a rodada existente, salvo force)."""
    hoje = date.today()
    with tenant_session(tid) as cur:
        if not force:
            cur.execute("SELECT id FROM agente_rodada WHERE executado_em::date = %s "
                        "ORDER BY executado_em DESC LIMIT 1", (hoje,))
            row = cur.fetchone()
            if row:
                return ultima(tid)
        ctx = _coletar(cur)
        if not ctx:
            return {"ok": False, "motivo": "sem dados de venda ainda"}
        analise = agente_analista(ctx)
        verifs = agente_verificador(ctx, hoje)
        projs = agente_projetista(ctx, hoje)
        texto = agente_relator(ctx, analise, verifs, projs, hoje)
        saida = {"analise": analise, "verificacoes": verifs, "projecoes": projs}
        cur.execute("INSERT INTO agente_rodada (tenant_id, saida, texto) VALUES (%s,%s,%s) "
                    "RETURNING id, executado_em",
                    (tid, json.dumps(saida, default=str), texto))
        rid, quando = cur.fetchone()
        for v in verifs:
            cur.execute("INSERT INTO acao_verificacao (tenant_id, fca_id, kr_id, baseline, "
                        "valor_atual, delta, veredito) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (tid, v["fca_id"], v["kr_id"], v["baseline"], v["valor_atual"],
                         v["delta"], v["veredito"]))
    return {"ok": True, "rodada_id": str(rid), "executado_em": quando.isoformat(),
            "texto": texto, **saida}


def ultima(tid: str) -> dict:
    with tenant_session(tid) as cur:
        cur.execute("SELECT id, executado_em, saida, texto FROM agente_rodada "
                    "ORDER BY executado_em DESC LIMIT 1")
        row = cur.fetchone()
    if not row:
        return {"ok": False, "motivo": "nenhuma rodada ainda"}
    saida = row[2] or {}
    return {"ok": True, "rodada_id": str(row[0]), "executado_em": row[1].isoformat(),
            "texto": row[3], "analise": saida.get("analise", []),
            "verificacoes": saida.get("verificacoes", []),
            "projecoes": saida.get("projecoes", [])}
