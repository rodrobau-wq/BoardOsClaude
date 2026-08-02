"""Conector CRM → BoardOS.

O CRM do cliente guarda (1) uma base de EMPRESAS e (2) VENDAS por empresa.
Este módulo faz a ponte para o modelo do BoardOS:
  - cada EMPRESA do CRM  → um TENANT (platform.tenant)
  - cada LOJA nas vendas → uma loja do tenant
  - vendas diárias       → camada gold (gold_venda_diaria)

LAYOUT ASSUMIDO (provisório — trocar o mapeamento quando vier o export real):
  empresas.csv:  id_externo;nome;cidade;uf;formato
  vendas.csv:    data;empresa_id;loja;faturamento;cupons;itens

Três modos de acesso existem no CRM (CSV, API, banco). Aqui o CSV está
implementado; API e banco ficam como stubs com o mesmo contrato.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from datetime import date, datetime
from typing import Dict

try:
    import psycopg
except ImportError:  # runtime dependency; ausente em dev sem banco
    psycopg = None

from .db import tenant_session
from .ingestion import _get_or_create

# --- mapeamentos padrão (ajustar quando vier o CRM real) -------------------
MAP_EMPRESAS = {"id_externo": "id_externo", "nome": "nome",
                "cidade": "cidade", "uf": "uf", "formato": "formato"}
MAP_VENDAS = {"data": "data", "empresa_id": "empresa_id", "loja": "loja",
              "faturamento": "faturamento", "cupons": "cupons", "itens": "itens"}


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "empresa"


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    s = str(v).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _read(path: str):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        return list(csv.DictReader(fh, delimiter=delim))


# --- CSV: onboarding de empresas ------------------------------------------
def onboard_empresas_csv(path: str, admin_dsn: str, mapping: Dict = None) -> Dict[str, str]:
    """Cria/atualiza um tenant por empresa do CRM. Retorna {id_externo: tenant_id}."""
    m = mapping or MAP_EMPRESAS
    out: Dict[str, str] = {}
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        for row in _read(path):
            ext = str(row[m["id_externo"]]).strip()
            nome = str(row[m["nome"]]).strip()
            slug = slugify(ext)  # slug ESTÁVEL pelo id do CRM: renomear atualiza, não duplica
            tid = conn.execute(
                "INSERT INTO platform.tenant (nome, slug, status) VALUES (%s,%s,'ativo') "
                "ON CONFLICT (slug) DO UPDATE SET nome=EXCLUDED.nome RETURNING id",
                (nome, slug),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO platform.assinatura (tenant_id, plano, base_mensal_cent, preco_por_1k_cent) "
                "VALUES (%s,'v0',49900,900) ON CONFLICT (tenant_id) DO NOTHING", (tid,))
            out[ext] = str(tid)
    return out


# --- CSV: importação de vendas diárias (nível gold) ------------------------
def import_vendas_diarias_csv(tenant_id: str, path: str, mapping: Dict = None) -> Dict:
    """Importa vendas diárias (uma linha por loja/dia) de UMA empresa para o gold.

    Grão diário: bom quando o CRM só tem faturamento por dia (não cupom/item).
    A comparação civil-vs-varejo funciona; cesta/ruptura por SKU exigem grão item.
    """
    m = mapping or MAP_VENDAS
    linhas = 0
    with tenant_session(tenant_id) as cur:
        loja_cache: Dict[str, str] = {}
        rows = []
        for r in _read(path):
            d = _parse_date(r[m["data"]])
            loja_cod = str(r[m["loja"]]).strip() if m["loja"] in r else "0001"
            loja_id = loja_cache.get(loja_cod)
            if not loja_id:
                loja_id = _get_or_create(cur, "loja", loja_cod,
                                         {"nome": "Loja " + loja_cod, "tenant_id": tenant_id})
                loja_cache[loja_cod] = loja_id
            fat = _num(r[m["faturamento"]])
            cup = int(_num(r.get(m["cupons"], 0)))
            itn = int(_num(r.get(m["itens"], 0)))
            rows.append((tenant_id, d, loja_id, round(fat * 1.03, 2), fat,
                         round(fat * 0.71, 2), round(fat * 0.29, 2), itn, cup, float(itn)))
        cur.executemany(
            """
            INSERT INTO gold_venda_diaria
              (tenant_id, data, loja_id, categoria_id, faturamento_bruto, faturamento_liq,
               custo, margem, itens, cupons, qtd)
            VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, data, loja_id, categoria_id) DO UPDATE SET
              faturamento_bruto=EXCLUDED.faturamento_bruto, faturamento_liq=EXCLUDED.faturamento_liq,
              custo=EXCLUDED.custo, margem=EXCLUDED.margem, itens=EXCLUDED.itens,
              cupons=EXCLUDED.cupons, qtd=EXCLUDED.qtd
            """,
            rows,
        )
        linhas = len(rows)
    return {"linhas": linhas}


def _parse_date(v) -> date:
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return datetime.fromisoformat(s).date()


def import_vendas_diarias_rows(tenant_id: str, records, margem_sintetica: bool = False) -> Dict:
    """Igual ao _csv, mas recebe registros já tipados em memória.

    records: iterável de dicts {data: date, loja: str, faturamento: float,
    cupons: int, itens: int}. margem_sintetica=True só para dados de DEMO
    (custo 71%/margem 29% fictícios); dados reais entram com custo/margem 0 —
    o painel esconde o KPI de margem quando não há custo de verdade.
    """
    with tenant_session(tenant_id) as cur:
        loja_cache: Dict[str, str] = {}
        rows = []
        for r in records:
            cod = str(r["loja"])
            loja_id = loja_cache.get(cod)
            if not loja_id:
                loja_id = _get_or_create(cur, "loja", cod,
                                         {"nome": "Loja " + cod, "tenant_id": tenant_id})
                loja_cache[cod] = loja_id
            fat = float(r["faturamento"])
            custo = round(fat * 0.71, 2) if margem_sintetica else 0.0
            margem = round(fat * 0.29, 2) if margem_sintetica else 0.0
            rows.append((tenant_id, r["data"], loja_id, round(fat * 1.03, 2) if margem_sintetica else fat,
                         fat, custo, margem,
                         int(r.get("itens", 0)), int(r.get("cupons", 0)), float(r.get("itens", 0))))
        cur.executemany(
            """
            INSERT INTO gold_venda_diaria
              (tenant_id, data, loja_id, categoria_id, faturamento_bruto, faturamento_liq,
               custo, margem, itens, cupons, qtd)
            VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, data, loja_id, categoria_id) DO UPDATE SET
              faturamento_bruto=EXCLUDED.faturamento_bruto, faturamento_liq=EXCLUDED.faturamento_liq,
              custo=EXCLUDED.custo, margem=EXCLUDED.margem, itens=EXCLUDED.itens,
              cupons=EXCLUDED.cupons, qtd=EXCLUDED.qtd
            """,
            rows,
        )
        return {"linhas": len(rows)}


# --- API / Banco: stubs (mesmo contrato) -----------------------------------
def onboard_empresas_api(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError(
        "Conector via API do CRM: implementar quando soubermos o endpoint/schema. "
        "Deve retornar {id_externo: tenant_id}, igual ao onboard_empresas_csv.")


def import_vendas_api(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError(
        "Importação via API do CRM: paginar as vendas por empresa/período e "
        "reutilizar a mesma escrita no gold do import_vendas_diarias_csv.")
