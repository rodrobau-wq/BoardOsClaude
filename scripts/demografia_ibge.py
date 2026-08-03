#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demografia das áreas de influência (Censo IBGE 2022, setores censitários).

Para cada loja com latitude/longitude, agrega população e domicílios dos
setores censitários cujo centro cai nos anéis primário (1,0 km), secundário
(2,0 km) e terciário (3,5 km), e grava no BoardOS via API.

Fonte: "malha com atributos" do Censo 2022 (GPKG por UF) — geometria +
v0001 (população) e v0007 (domicílios particulares ocupados) por setor.
Potencial de consumo/ano = domicílios × gasto alimentar mensal × 12
(POF/IBGE, ajustável via GASTO_ALIMENTAR_MES).

Uso:
  BOARDOS_TOKEN=... python3 scripts/demografia_ibge.py caminho/UF_setores_CD2022.gpkg
  (ou BOARDOS_EMAIL/BOARDOS_SENHA no lugar do token)

O GPKG por UF: https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/
Agregados_por_Setores_Censitarios/malha_com_atributos/setores/gpkg/UF/
"""
import math
import os
import sqlite3
import struct
import sys

import requests

API = os.environ.get("BOARDOS_API", "https://boardos-api.onrender.com").rstrip("/")
GASTO_MES = float(os.environ.get("GASTO_ALIMENTAR_MES", "780"))
ANEIS = [("primaria", 1.0), ("secundaria", 2.0), ("terciaria", 3.5)]
FONTE = "Censo IBGE 2022 (setores) · potencial: domicílios × R$ %.0f/mês (POF) × 12" % GASTO_MES


def token() -> str:
    t = os.environ.get("BOARDOS_TOKEN")
    if t:
        return t
    email, senha = os.environ.get("BOARDOS_EMAIL"), os.environ.get("BOARDOS_SENHA")
    if not (email and senha):
        sys.exit("Defina BOARDOS_TOKEN ou BOARDOS_EMAIL/BOARDOS_SENHA.")
    r = requests.post(API + "/auth/login", json={"email": email, "senha": senha}, timeout=60)
    r.raise_for_status()
    return r.json()["token"]


def centro_envelope(gpb: bytes):
    """Centro do envelope de um GeoPackageBinary (aproxima o centroide do setor)."""
    if len(gpb) < 8 or gpb[:2] != b"GP":
        return None
    flags = gpb[3]
    env = (flags >> 1) & 0x07
    if env == 0:
        return None
    fmt = "<" if (flags & 1) else ">"
    minx, maxx, miny, maxy = struct.unpack(fmt + "4d", gpb[8:40])
    return ((miny + maxy) / 2.0, (minx + maxx) / 2.0)   # (lat, lng)


def hav_km(lat1, lng1, lat2, lng2):
    rl1, rl2 = math.radians(lat1), math.radians(lat2)
    dlat, dlng = rl2 - rl1, math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(rl1)*math.cos(rl2)*math.sin(dlng/2)**2
    return 12742.0 * math.asin(math.sqrt(a))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    gpkg = sys.argv[1]
    tok = token()
    headers = {"Authorization": "Bearer " + tok}
    tid = os.environ.get("BOARDOS_TENANT")
    if tid:
        headers["X-Tenant-Id"] = tid

    lojas = requests.get(API + "/lojas", headers=headers, timeout=60).json()["lojas"]
    com_coord = [l for l in lojas if l.get("lat") is not None and l.get("lng") is not None]
    if not com_coord:
        sys.exit("Nenhuma loja com latitude/longitude cadastrada.")
    print(f"{len(com_coord)} loja(s) com coordenadas · lendo {gpkg}…")

    db = sqlite3.connect(gpkg)
    cur = db.cursor()
    tabela = cur.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchone()[0]
    setores = []
    for geom, pop, dom in cur.execute(f'SELECT geom, v0001, v0007 FROM "{tabela}"'):
        c = centro_envelope(geom)
        if not c:
            continue
        try:
            p = int(float(pop)) if pop not in (None, "", ".") else 0
            d = int(float(dom)) if dom not in (None, "", ".") else 0
        except ValueError:
            p, d = 0, 0
        setores.append((c[0], c[1], p, d))
    print(f"{len(setores)} setores com centro e atributos.")

    for l in com_coord:
        aneis = []
        for nome, raio in ANEIS:
            pop = dom = n = 0
            for slat, slng, p, d in setores:
                if abs(slat - l["lat"]) > 0.05 or abs(slng - l["lng"]) > 0.05:
                    continue
                if hav_km(l["lat"], l["lng"], slat, slng) <= raio:
                    pop += p; dom += d; n += 1
            aneis.append({"anel": nome, "raio_km": raio, "populacao": pop,
                          "domicilios": dom, "setores": n,
                          "potencial_ano": round(dom * GASTO_MES * 12, 2)})
        r = requests.put(API + f"/lojas/{l['id']}/demografia", headers=headers,
                         json={"aneis": aneis, "fonte": FONTE}, timeout=120)
        if not r.ok:
            sys.exit(f"Erro ao gravar {l['nome']}: {r.status_code} {r.text[:200]}")
        p1 = aneis[0]
        print(f"  {l['nome']}: primária {p1['populacao']:,} hab · {p1['domicilios']:,} dom "
              f"· potencial R$ {p1['potencial_ano']:,.0f}/ano ({p1['setores']} setores)")
    print("OK — demografia gravada. O card Minha Rede → Demografia já reflete.")


if __name__ == "__main__":
    main()
