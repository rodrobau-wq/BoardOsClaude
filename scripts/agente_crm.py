#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agente de sincronização CRM → BoardOS.

Roda NA MÁQUINA que enxerga o banco do CRM (ex.: o Windows do escritório,
que acessa o Postgres `retailcrm_crema` pela VPN). Lê as vendas agregadas
por dia × loja e EMPURRA para a API do BoardOS por HTTPS — só tráfego de
saída, nada é exposto na internet.

O destino é o endpoint idempotente /dados/importar-diario: re-rodar o
agente nunca duplica (upsert por dia × loja), então a janela rolante pode
se sobrepor à vontade e capturar correções de vendas de dias anteriores.

Uso:
  python agente_crm.py                    # sincroniza a janela rolante (padrão: 7 dias)
  python agente_crm.py --desde 2022-01-01 # backfill do histórico completo
  python agente_crm.py --teste            # só consulta o CRM e mostra o resumo, sem enviar

Configuração: agente_crm.ini ao lado do script (modelo em agente_crm.example.ini).
Dependências:  pip install psycopg2-binary requests
Agendamento (Windows, todo dia às 6h):
  schtasks /Create /SC DAILY /ST 06:00 /TN "BoardOS Sync CRM" ^
    /TR "C:\\Python312\\python.exe C:\\boardos\\agente_crm.py"
"""
import argparse
import configparser
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import psycopg2
    import requests
except ImportError:
    sys.exit("Instale as dependências:  pip install psycopg2-binary requests")

LOTE = 5000          # linhas por chamada (limite do endpoint: 20.000)


def carregar_config() -> configparser.ConfigParser:
    caminho = Path(__file__).with_name("agente_crm.ini")
    if not caminho.exists():
        sys.exit(f"Config não encontrada: {caminho}\n"
                 "Copie agente_crm.example.ini para agente_crm.ini e preencha.")
    cfg = configparser.ConfigParser()
    cfg.read(caminho, encoding="utf-8")
    return cfg


def consultar_crm(cfg, desde: date, ate: date):
    """Consulta o CRM e devolve linhas {data, loja_codigo, faturamento, cupons, itens}."""
    query = cfg.get("crm", "query")
    with psycopg2.connect(cfg.get("crm", "dsn")) as conn:
        with conn.cursor() as cur:
            cur.execute(query, {"desde": desde, "ate": ate})
            cols = [d[0] for d in cur.description]
            obrigatorias = {"data", "loja_codigo", "faturamento"}
            faltam = obrigatorias - set(cols)
            if faltam:
                sys.exit(f"A query do CRM precisa devolver as colunas {sorted(obrigatorias)} "
                         f"(faltou: {sorted(faltam)}). Colunas opcionais: cupons, itens.")
            linhas = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                linhas.append({
                    "data": str(d["data"])[:10],
                    "loja_codigo": str(d["loja_codigo"]).strip(),
                    "faturamento": float(d["faturamento"] or 0),
                    "cupons": int(d.get("cupons") or 0),
                    "itens": int(d.get("itens") or 0),
                })
    return linhas


def login_boardos(cfg) -> str:
    api = cfg.get("boardos", "api").rstrip("/")
    r = requests.post(api + "/auth/login", timeout=60,
                      json={"email": cfg.get("boardos", "email"),
                            "senha": cfg.get("boardos", "senha")})
    if not r.ok:
        sys.exit(f"Login no BoardOS falhou ({r.status_code}): {r.text[:200]}")
    return r.json()["token"]


def enviar(cfg, token: str, linhas) -> int:
    api = cfg.get("boardos", "api").rstrip("/")
    headers = {"Authorization": "Bearer " + token}
    total = 0
    for i in range(0, len(linhas), LOTE):
        lote = linhas[i:i + LOTE]
        r = requests.post(api + "/dados/importar-diario", timeout=300,
                          headers=headers, json={"linhas": lote})
        if not r.ok:
            sys.exit(f"Envio falhou no lote {i//LOTE + 1} ({r.status_code}): {r.text[:300]}")
        total += r.json().get("linhas", len(lote))
        print(f"  lote {i//LOTE + 1}: {len(lote)} linhas enviadas")
    return total


def main():
    ap = argparse.ArgumentParser(description="Sincroniza vendas do CRM para o BoardOS.")
    ap.add_argument("--desde", help="início do período (YYYY-MM-DD); padrão: janela rolante")
    ap.add_argument("--ate", help="fim do período (YYYY-MM-DD); padrão: hoje")
    ap.add_argument("--teste", action="store_true", help="consulta o CRM sem enviar nada")
    args = ap.parse_args()

    cfg = carregar_config()
    janela = cfg.getint("crm", "dias_janela", fallback=7)
    ate = date.fromisoformat(args.ate) if args.ate else date.today()
    desde = date.fromisoformat(args.desde) if args.desde else ate - timedelta(days=janela)

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] CRM → BoardOS · período {desde} a {ate}")
    linhas = consultar_crm(cfg, desde, ate)
    if not linhas:
        print("Nada a sincronizar no período."); return
    fat = sum(x["faturamento"] for x in linhas)
    lojas = sorted({x["loja_codigo"] for x in linhas})
    print(f"CRM: {len(linhas)} linhas dia×loja · R$ {fat:,.2f} · lojas: {', '.join(lojas)}")

    if args.teste:
        print("(--teste: nada foi enviado)"); return

    token = login_boardos(cfg)
    total = enviar(cfg, token, linhas)
    print(f"OK: {total} linhas sincronizadas. O painel já reflete os novos dias.")


if __name__ == "__main__":
    main()
