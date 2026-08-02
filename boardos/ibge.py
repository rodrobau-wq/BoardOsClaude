"""Enriquecimento IBGE do cadastro de loja (3.14) — APIs públicas, sem chave.

Fontes (validadas empiricamente):
- Localidades: /api/v1/localidades/estados/{UF}/municipios  → id do município
- População estimada: agregado 6579, variável 9324, período -1
- PIB a preços correntes: agregado 5938, variável 37, período -1 (mil R$)
PIB per capita = PIB*1000 / população. Tudo best-effort: falha de rede => None.
"""
from __future__ import annotations

import json
import unicodedata
import urllib.request
from typing import Dict, Optional

BASE_LOC = "https://servicodados.ibge.gov.br/api/v1/localidades"
BASE_AGR = "https://servicodados.ibge.gov.br/api/v3/agregados"
TIMEOUT = 8


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "BoardOS/1.0",
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":  # o IBGE responde gzip mesmo sem pedir
        import gzip
        raw = gzip.decompress(raw)
    return json.loads(raw.decode())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.strip().lower()


def buscar_municipio(nome: str, uf: str) -> Optional[Dict]:
    """Resolve município por nome+UF → {"id", "nome"} ou None."""
    try:
        ms = _get(f"{BASE_LOC}/estados/{uf.strip().upper()}/municipios")
    except Exception:
        return None
    alvo = _norm(nome)
    for m in ms:
        if _norm(m["nome"]) == alvo:
            return {"id": int(m["id"]), "nome": m["nome"]}
    for m in ms:  # fallback: começa com (ex.: "Campinas" vs "Campinas ...")
        if _norm(m["nome"]).startswith(alvo):
            return {"id": int(m["id"]), "nome": m["nome"]}
    return None


def _serie(agregado: int, variavel: int, mun_id: int) -> Optional[Dict]:
    """Último valor da série do agregado para o município: {"ano", "valor"}."""
    url = (f"{BASE_AGR}/{agregado}/periodos/-1/variaveis/{variavel}"
           f"?localidades=N6%5B{mun_id}%5D")
    try:
        data = _get(url)
        serie = data[0]["resultados"][0]["series"][0]["serie"]
        ano, valor = sorted(serie.items())[-1]
        return {"ano": int(ano), "valor": float(valor)}
    except Exception:
        return None


def enriquecer(municipio: str, uf: str) -> Optional[Dict]:
    """Dados IBGE do município: id, população, PIB e PIB per capita (best-effort)."""
    if not (municipio or "").strip() or not (uf or "").strip():
        return None
    m = buscar_municipio(municipio, uf)
    if not m:
        return None
    out: Dict = {"ibge_id": m["id"], "municipio_ibge": m["nome"]}
    pop = _serie(6579, 9324, m["id"])
    if pop:
        out["populacao"] = int(pop["valor"])
        out["populacao_ano"] = pop["ano"]
    pib = _serie(5938, 37, m["id"])  # mil R$
    if pib:
        out["pib_mil_reais"] = pib["valor"]
        out["pib_ano"] = pib["ano"]
        if out.get("populacao"):
            out["pib_per_capita"] = round(pib["valor"] * 1000 / out["populacao"], 2)
    return out
