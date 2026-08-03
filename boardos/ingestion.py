"""Pipeline de ingestão: CSV (cupom/item) → item_venda → gold → medidor de uso.

Propriedades:
- Idempotente pela chave natural (reenvio substitui, não duplica).
- Reprocessamento por recorte (loja + intervalo de datas) via batch.
- Recompute incremental do gold só nos dias afetados.
- Medidor de uso conta itens distintos (não linhas) → billing à prova de duplicidade.

Requer psycopg + Postgres. A lógica de agregação/comparação, testável sem banco,
está em scripts/demo_local.py.
"""
from __future__ import annotations

import csv
import os
import uuid
from datetime import date
from typing import Dict, Iterable, Tuple

from .db import tenant_session
from .mapping import ColumnMap, normalize_row


def _get_or_create(cur, table: str, codigo: str, extra: Dict) -> str:
    cur.execute(f"SELECT id FROM {table} WHERE codigo = %s", (codigo,))
    row = cur.fetchone()
    if row:
        return row[0]
    cols = ["codigo"] + list(extra.keys())
    vals = [codigo] + list(extra.values())
    ph = ",".join(["%s"] * len(cols))
    cur.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph}) RETURNING id",
        vals,
    )
    return cur.fetchone()[0]


def ingest_csv(
    tenant_id: str,
    loja_codigo: str,
    loja_nome: str,
    csv_path: str,
    cmap: ColumnMap,
    origem: str | None = None,
) -> Dict:
    """Ingere um CSV para um tenant/loja. Retorna resumo (linhas, dias, novos itens).
    `origem` é o nome exibível do arquivo (o painel lista as importações por ele)."""
    missing = cmap.missing_required()
    if missing:
        raise ValueError(f"Colunas obrigatórias não mapeadas: {missing}")

    with tenant_session(tenant_id) as cur:
        loja_id = _get_or_create(cur, "loja", loja_codigo,
                                 {"nome": loja_nome, "tenant_id": tenant_id})

        # cria o lote
        batch_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO ingest_batch (id, tenant_id, origem, loja_id, status) "
            "VALUES (%s,%s,%s,%s,'processando')",
            (batch_id, tenant_id, origem or os.path.basename(csv_path), loja_id),
        )

        dias_afetados: set = set()
        cat_cache: Dict[str, str] = {}
        sku_cache: Dict[str, str] = {}
        seq_por_cupom: Dict[Tuple[date, str], int] = {}
        linhas = 0

        with open(csv_path, newline="", encoding="utf-8-sig") as fh:
            sample = fh.read(2048)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
                delim = dialect.delimiter
            except csv.Error:
                delim = ";" if sample.count(";") > sample.count(",") else ","
            reader = csv.DictReader(fh, delimiter=delim)
            for raw in reader:
                # seq fallback pela ordem no cupom
                r = normalize_row(raw, cmap, seq_fallback=0)
                k = (r["data"], r["cupom_id"])
                if r["seq_item"] == 0:
                    seq_por_cupom[k] = seq_por_cupom.get(k, 0) + 1
                    r["seq_item"] = seq_por_cupom[k]

                # item sem categoria vai para um balde "GERAL" — assim as linhas
                # por categoria no gold nunca têm categoria NULL (que é reservado
                # para a linha de TOTAL da loja).
                if not r["categoria_codigo"]:
                    r["categoria_codigo"] = "GERAL"
                cat_id = None
                if r["categoria_codigo"]:
                    cat_id = cat_cache.get(r["categoria_codigo"])
                    if not cat_id:
                        cat_id = _get_or_create(
                            cur, "categoria", r["categoria_codigo"],
                            {"nome": r["categoria_codigo"], "tenant_id": tenant_id})
                        cat_cache[r["categoria_codigo"]] = cat_id

                sku_id = sku_cache.get(r["sku_codigo"])
                if not sku_id:
                    sku_id = _get_or_create(
                        cur, "sku", r["sku_codigo"],
                        {"descricao": r["sku_codigo"], "categoria_id": cat_id,
                         "tenant_id": tenant_id})
                    sku_cache[r["sku_codigo"]] = sku_id

                # UPSERT idempotente pela chave natural
                cur.execute(
                    """
                    INSERT INTO item_venda
                      (tenant_id, loja_id, data, cupom_id, seq_item, cliente_id,
                       sku_id, categoria_id, qtd, valor_bruto, desconto,
                       valor_liquido, custo, batch_id, origem)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (tenant_id, loja_id, data, cupom_id, seq_item)
                    DO UPDATE SET
                       cliente_id=EXCLUDED.cliente_id, sku_id=EXCLUDED.sku_id,
                       categoria_id=EXCLUDED.categoria_id, qtd=EXCLUDED.qtd,
                       valor_bruto=EXCLUDED.valor_bruto, desconto=EXCLUDED.desconto,
                       valor_liquido=EXCLUDED.valor_liquido, custo=EXCLUDED.custo,
                       batch_id=EXCLUDED.batch_id, ingerido_em=now()
                    """,
                    (tenant_id, loja_id, r["data"], r["cupom_id"], r["seq_item"],
                     r["cliente_id"], sku_id, cat_id, r["qtd"], r["valor_bruto"],
                     r["desconto"], r["valor_liquido"], r["custo"], batch_id, csv_path),
                )
                dias_afetados.add(r["data"])
                linhas += 1

        # garante a dim_calendario para o período do arquivo (JOINs de KPI)
        if dias_afetados:
            from .calendar_gen import upsert_into as _cal
            _cal(cur, min(dias_afetados).replace(month=1, day=1),
                 max(dias_afetados).replace(month=12, day=31))

        # recompute incremental do gold só nos dias afetados
        for d in sorted(dias_afetados):
            cur.execute("SELECT recompute_gold(%s,%s,%s)", (tenant_id, loja_id, d))

        # fecha o lote
        cur.execute(
            "UPDATE ingest_batch SET linhas=%s, data_de=%s, data_ate=%s, status='ok' "
            "WHERE id=%s",
            (linhas, min(dias_afetados) if dias_afetados else None,
             max(dias_afetados) if dias_afetados else None, batch_id),
        )

        # medidor de uso: itens DISTINTOS por competência (não linhas ingeridas)
        _atualiza_medidor(cur, tenant_id, sorted(dias_afetados))

    return {"linhas": linhas, "dias": len(dias_afetados), "batch_id": batch_id}


def _atualiza_medidor(cur, tenant_id: str, dias: Iterable[date]) -> None:
    competencias = {date(d.year, d.month, 1) for d in dias}
    for comp in competencias:
        cur.execute(
            """
            INSERT INTO platform.medidor_uso (tenant_id, competencia, registros, atualizado_em)
            SELECT %s, %s, count(*), now()
              FROM item_venda
             WHERE tenant_id=%s AND date_trunc('month', data)=%s
            ON CONFLICT (tenant_id, competencia)
            DO UPDATE SET registros=EXCLUDED.registros, atualizado_em=now()
            """,
            (tenant_id, comp, tenant_id, comp),
        )
