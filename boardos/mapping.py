"""Mapeamento de colunas do CSV do cliente → modelo canônico + validação.

Cada supermercado exporta com nomes de coluna diferentes. O mapeador liga as
colunas do arquivo aos campos canônicos. A chave natural garante idempotência.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, Optional

# Campos canônicos do item de venda e se são obrigatórios.
CANONICAL_FIELDS = {
    "data": True,
    "loja_codigo": True,
    "cupom_id": True,
    "seq_item": False,       # se ausente, derivamos pela ordem no cupom
    "sku_codigo": True,
    "categoria_codigo": False,
    "cliente_id": False,
    "qtd": True,
    "valor_bruto": False,
    "desconto": False,
    "valor_liquido": True,
    "custo": False,
}


@dataclass
class ColumnMap:
    """De campo canônico -> nome da coluna no arquivo do cliente."""
    mapping: Dict[str, str]

    def missing_required(self) -> list:
        return [f for f, req in CANONICAL_FIELDS.items()
                if req and f not in self.mapping]


def _num(v) -> float:
    if v is None or v == "":
        return 0.0
    s = str(v).strip().replace(".", "").replace(",", ".") if "," in str(v) else str(v).strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(v) -> date:
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[: len(fmt) + 2], fmt).date()
        except ValueError:
            continue
    # fallback ISO
    return datetime.fromisoformat(s).date()


def normalize_row(raw: Dict[str, str], cmap: ColumnMap, seq_fallback: int) -> Dict:
    """Converte uma linha crua do CSV em um dict canônico tipado."""
    g = lambda f: raw.get(cmap.mapping[f]) if f in cmap.mapping else None
    seq = g("seq_item")
    return {
        "data": _parse_date(g("data")),
        "loja_codigo": str(g("loja_codigo")).strip(),
        "cupom_id": str(g("cupom_id")).strip(),
        "seq_item": int(seq) if seq not in (None, "") else seq_fallback,
        "sku_codigo": str(g("sku_codigo")).strip(),
        "categoria_codigo": (str(g("categoria_codigo")).strip()
                             if g("categoria_codigo") else None),
        "cliente_id": (str(g("cliente_id")).strip() if g("cliente_id") else None),
        "qtd": _num(g("qtd")),
        "valor_bruto": _num(g("valor_bruto")),
        "desconto": _num(g("desconto")),
        "valor_liquido": _num(g("valor_liquido")),
        "custo": _num(g("custo")),
    }


def natural_key(row: Dict, tenant_id: str, loja_id: str) -> tuple:
    """Chave natural: idempotência. Reenviar substitui, não duplica."""
    return (tenant_id, loja_id, row["data"], row["cupom_id"], row["seq_item"])
