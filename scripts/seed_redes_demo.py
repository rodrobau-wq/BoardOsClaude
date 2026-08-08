#!/usr/bin/env python3
"""Popula o banco com 4 redes de supermercado de perfis distintos.

Serve para demonstração e para desenvolver as telas com dado que se parece com
o real: cada rede tem ~3 anos de venda diária por loja e por categoria, mais
direção, OKRs, FCAs, PIs, rituais, SWOT, riscos e maturidade coerentes com o
seu desempenho.

Perfis:
  aurora     — todos os indicadores NA MÉDIA do setor
  horizonte  — indicadores BONS (cresce, margem alta, OKRs no trilho)
  meridiano  — resultado RUIM (cai, margem baixa, FCAs vencidas)
  pantanal   — MISTO: vende mais, mas a margem escorre (caso de atenção)

Uso:
    export BOARDOS_ADMIN_DSN='postgresql://...'      # banco de destino
    python3 scripts/seed_redes_demo.py               # cria/atualiza as 4 redes
    python3 scripts/seed_redes_demo.py --apagar-existentes   # e remove as demais
    python3 scripts/seed_redes_demo.py --senha 'Trocar@123'  # cria logins admin

ATENÇÃO: --apagar-existentes APAGA todas as outras empresas do banco, com todos
os seus dados, em cascata. Não há desfazer.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

from boardos.auth import hash_password  # noqa: E402
from boardos.calendar_gen import upsert_into  # noqa: E402

ADMIN_DSN = (os.environ.get("BOARDOS_ADMIN_DSN") or os.environ.get("DATABASE_URL")
             or "postgresql://boardos_admin:change-me-admin@localhost:5432/boardos")

HOJE = date.today()
DE = date(HOJE.year - 2, 1, 1)
ATE = HOJE

CATEGORIAS = [
    ("MERC", "Mercearia", "mercearia", 0.32),
    ("HORT", "Hortifrúti", "hortifruti", 0.14),
    ("ACOU", "Açougue", "acougue", 0.19),
    ("FRIO", "Frios e laticínios", "frios", 0.13),
    ("BEBI", "Bebidas", "bebidas", 0.15),
    ("LIMP", "Limpeza e higiene", "limpeza", 0.07),
]

# ---------------------------------------------------------------- perfis
# fat_loja_dia: faturamento médio por loja/dia no 1º ano
# cresc: crescimento anual composto · margem: % de margem bruta
# ticket: R$ por cupom · itens: itens por cupom
REDES = [
    {
        "slug": "rede-aurora", "nome": "Supermercados Aurora", "perfil": "média",
        "fat_loja_dia": 82_000, "cresc": 0.04, "margem": 0.222, "margem_drift": 0.0,
        "ticket": 58.0, "itens": 8.5, "sazon": 0.10,
        "lojas": [("A01", "Aurora Centro", "Americana", "SP"),
                  ("A02", "Aurora Jardim", "Americana", "SP"),
                  ("A03", "Aurora Vila Nova", "Santa Bárbara d'Oeste", "SP"),
                  ("A04", "Aurora Norte", "Nova Odessa", "SP"),
                  ("A05", "Aurora Sul", "Sumaré", "SP"),
                  ("A06", "Aurora Leste", "Hortolândia", "SP")],
    },
    {
        "slug": "rede-horizonte", "nome": "Rede Horizonte", "perfil": "bons",
        "fat_loja_dia": 104_000, "cresc": 0.12, "margem": 0.275, "margem_drift": 0.004,
        "ticket": 72.0, "itens": 10.2, "sazon": 0.12,
        "lojas": [("H01", "Horizonte Matriz", "Piracicaba", "SP"),
                  ("H02", "Horizonte Paulista", "Piracicaba", "SP"),
                  ("H03", "Horizonte Vale", "Limeira", "SP"),
                  ("H04", "Horizonte Parque", "Rio Claro", "SP"),
                  ("H05", "Horizonte Alto", "Araras", "SP"),
                  ("H06", "Horizonte Shopping", "Limeira", "SP"),
                  ("H07", "Horizonte Express", "Piracicaba", "SP"),
                  ("H08", "Horizonte Bairro", "Rio Claro", "SP"),
                  ("H09", "Horizonte Rodovia", "Araras", "SP")],
    },
    {
        "slug": "rede-meridiano", "nome": "Supermercados Meridiano", "perfil": "ruim",
        "fat_loja_dia": 61_000, "cresc": -0.06, "margem": 0.163, "margem_drift": -0.006,
        "ticket": 44.0, "itens": 6.8, "sazon": 0.08,
        "lojas": [("M01", "Meridiano Centro", "Bauru", "SP"),
                  ("M02", "Meridiano Industrial", "Bauru", "SP"),
                  ("M03", "Meridiano Popular", "Jaú", "SP"),
                  ("M04", "Meridiano Vila", "Lençóis Paulista", "SP"),
                  ("M05", "Meridiano Estrada", "Pederneiras", "SP")],
    },
    {
        "slug": "rede-pantanal", "nome": "Rede Pantanal", "perfil": "misto",
        "fat_loja_dia": 88_000, "cresc": 0.08, "margem": 0.205, "margem_drift": -0.009,
        "ticket": 63.0, "itens": 9.1, "sazon": 0.11,
        "lojas": [("P01", "Pantanal Centro", "Marília", "SP"),
                  ("P02", "Pantanal Sul", "Marília", "SP"),
                  ("P03", "Pantanal Garça", "Garça", "SP"),
                  ("P04", "Pantanal Tupã", "Tupã", "SP"),
                  ("P05", "Pantanal Vera Cruz", "Vera Cruz", "SP"),
                  ("P06", "Pantanal Avenida", "Marília", "SP"),
                  ("P07", "Pantanal Bairro", "Garça", "SP")],
    },
]


def fator_dia(d: date, sazon: float) -> float:
    """Sazonalidade anual + peso do dia da semana (sexta/sábado puxam)."""
    ano = 1 + sazon * math.sin((d.timetuple().tm_yday / 365.0) * 2 * math.pi - 1.2)
    semana = {0: .82, 1: .85, 2: .90, 3: .97, 4: 1.22, 5: 1.38, 6: .86}[d.weekday()]
    if d.month == 12 and d.day >= 15:
        ano *= 1.35                      # ceia
    return ano * semana


def gerar_gold(rede, loja_ids, cat_ids, rnd):
    """Uma linha por loja/dia (total, período inteiro) + o detalhe por categoria
    nos últimos 12 meses — que é o que o drill-down usa. Gerar categoria em
    todo o histórico triplicaria o volume sem ninguém olhar."""
    linhas = []
    dias = (ATE - DE).days + 1
    cat_desde = ATE - timedelta(days=365)
    for i in range(dias):
        d = DE + timedelta(days=i)
        anos = i / 365.0
        base = rede["fat_loja_dia"] * ((1 + rede["cresc"]) ** anos)
        margem_pct = rede["margem"] + rede["margem_drift"] * anos
        margem_pct = max(0.06, min(0.42, margem_pct))
        com_categoria = d >= cat_desde
        for lid in loja_ids:
            porte = 0.72 + (hash(lid) % 60) / 100.0        # cada loja tem seu porte
            fat = base * porte * fator_dia(d, rede["sazon"]) * rnd.uniform(0.94, 1.06)
            fat = round(fat, 2)
            cupons = max(1, int(fat / (rede["ticket"] * rnd.uniform(0.97, 1.03))))
            itens = int(cupons * rede["itens"] * rnd.uniform(0.97, 1.03))
            margem = round(fat * margem_pct, 2)
            linhas.append((d, lid, None, round(fat * 1.06, 2), fat,
                           round(fat - margem, 2), margem, itens, cupons, float(itens)))
            if not com_categoria:
                continue
            for (cod, _nome, _sec, peso) in CATEGORIAS:
                pc = peso * rnd.uniform(0.9, 1.1)
                fc = round(fat * pc, 2)
                mc = round(fc * margem_pct * rnd.uniform(0.75, 1.25), 2)
                linhas.append((d, lid, cat_ids[cod], round(fc * 1.06, 2), fc,
                               round(fc - mc, 2), mc, int(itens * pc),
                               int(cupons * pc), float(int(itens * pc))))
    return linhas


# ------------------------------------------------------- conteúdo por perfil
DIRECAO = {
    "média": ("Abastecer o dia a dia das famílias da região com preço justo e atendimento de vizinho.",
              "Ser a rede preferida das cidades onde atuamos, com 10 lojas e padrão de operação uniforme.",
              "Palavra cumprida\nGente que atende gente\nCusto sob controle\nLoja limpa e abastecida",
              "Chegar a 15 lojas mantendo a margem acima de 22%."),
    "bons": ("Provar que supermercado de bairro pode ter a eficiência de rede grande sem perder o calor do atendimento.",
             "Ser a rede mais rentável do interior paulista, referência em perecíveis e em gente.",
             "Excelência em perecíveis\nDado antes do achismo\nDono presente na loja\nGente que cresce junto",
             "R$ 1 bilhão de faturamento com margem de 28% e NPS acima de 70."),
    "ruim": ("Garantir que a família da periferia encontre o básico perto de casa e cabendo no bolso.",
             "Recuperar a rentabilidade e voltar a crescer, com as 5 lojas no azul.",
             "Preço honesto\nNinguém fica sem o básico\nTrabalho duro",
             "Voltar ao lucro operacional e retomar a expansão."),
    "misto": ("Ser o supermercado que resolve a semana da família, do básico ao churrasco de domingo.",
              "Dobrar de tamanho na região sem abrir mão da margem.",
              "Crescer com pé no chão\nCliente fiel vale mais que cliente novo\nControle de perdas é cultura",
              "12 lojas rentáveis e marca própria em 15% da venda."),
}

OKRS = {
    "média": [("Crescer venda comparável com margem preservada", [
                  ("Venda comparável", "%", 5.0, 4.1, 0.0, "up"),
                  ("Margem bruta", "%", 22.5, 22.2, 21.8, "up")]),
              ("Melhorar a experiência na loja", [
                  ("Itens por cupom", "un", 9.0, 8.5, 8.3, "up"),
                  ("Ticket médio", "R$", 62.0, 58.0, 56.4, "up")])],
    "bons": [("Consolidar a liderança em rentabilidade", [
                  ("Venda comparável", "%", 10.0, 12.4, 0.0, "up"),
                  ("Margem bruta", "%", 27.0, 27.5, 25.9, "up")]),
             ("Fazer de perecíveis o nosso diferencial", [
                  ("Participação de perecíveis", "%", 33.0, 34.2, 30.5, "up"),
                  ("Itens por cupom", "un", 10.0, 10.2, 9.4, "up")]),
             ("Abrir a 10ª loja no prazo", [
                  ("Obra concluída", "%", 100.0, 82.0, 0.0, "up")])],
    "ruim": [("Estancar a queda de venda", [
                  ("Venda comparável", "%", 0.0, -6.2, -8.1, "up"),
                  ("Clientes atendidos/mês", "mil", 210.0, 168.0, 175.0, "up")]),
             ("Recuperar margem", [
                  ("Margem bruta", "%", 20.0, 16.3, 17.9, "up"),
                  ("Quebra sobre venda", "%", 1.8, 3.4, 3.1, "down")]),
             ("Colocar a casa em ordem", [
                  ("Ruptura de itens A", "%", 4.0, 11.2, 12.0, "down")])],
    "misto": [("Crescer sem perder margem", [
                  ("Venda comparável", "%", 7.0, 8.3, 0.0, "up"),
                  ("Margem bruta", "%", 22.0, 20.5, 21.4, "up")]),
              ("Controlar perdas", [
                  ("Quebra sobre venda", "%", 1.5, 2.4, 2.0, "down"),
                  ("Ruptura de itens A", "%", 5.0, 7.1, 6.4, "down")])],
}

FCAS = {
    "média": [("Margem de bebidas 1,4 pp abaixo do plano", "aberto", 12,
               "Bebidas fechou o mês com 18,6% contra 20,0% do plano.",
               "Promoção de cerveja sem negociação de verba com a indústria.",
               "Renegociar verba de trade e revisar a grade de promoções.", "Compras", "margem", "C"),
              ("Fila de caixa acima de 8 min na sexta", "em_andamento", 5,
               "Tempo médio de fila passou de 8 min nos picos de sexta.",
               "Escala não acompanha o pico das 18h.",
               "Remanejar escala e abrir caixa rápido das 17h às 20h.", "Operações", "ticket", "E")],
    "bons": [("Ruptura de hortifrúti subiu para 6%", "em_andamento", 9,
              "Ruptura de hortifrúti saiu de 3,8% para 6,0% em duas semanas.",
              "Atraso do fornecedor de folhosas após a chuva.",
              "Homologar segundo fornecedor de folhosas.", "Compras", "ruptura", "A")],
    "ruim": [("Venda cai 6,2% com fluxo em queda", "aberto", -22,
              "Venda comparável em -6,2% e clientes atendidos em -4%.",
              "Atacarejo novo a 900 m da loja Centro puxou o cliente de abastecimento.",
              "Rever posicionamento de preço da cesta e criar programa de fidelidade.", "Diretoria", "venda", "C"),
             ("Quebra de perecíveis em 3,4% da venda", "aberto", -15,
              "Quebra de perecíveis quase dobrou o padrão do setor.",
              "Falta de controle de validade e excesso de pedido no açougue.",
              "Implantar conferência diária de validade e revisar o pedido.", "Operações", "quebra", "R"),
             ("Ruptura de itens A em 11,2%", "aberto", -8,
              "Mais de 1 em cada 10 itens A sem estoque na gôndola.",
              "Ruptura de gôndola por falta de reposição, com estoque no depósito.",
              "Rotina de reposição 3x ao dia nos 200 itens A.", "Operações", "ruptura", "A"),
             ("Margem 3,7 pp abaixo do necessário", "em_andamento", 3,
              "Margem bruta em 16,3% contra 20,0% necessários para o ponto de equilíbrio.",
              "Preço defensivo generalizado, sem seletividade.",
              "Definir cesta de 80 itens sensíveis e recompor o resto.", "Comercial", "margem", "C"),
             ("Contas a pagar concentradas na 1ª semana", "aberto", -3,
              "72% dos vencimentos caem entre os dias 1 e 7.",
              "Negociação de prazo feita fornecedor a fornecedor, sem calendário.",
              "Escalonar vencimentos com os 20 maiores fornecedores.", "Financeiro", "venda", "D")],
    "misto": [("Margem cai 0,9 pp enquanto a venda sobe 8%", "aberto", 7,
               "Venda +8,3% mas margem passou de 21,4% para 20,5%.",
               "Crescimento veio de itens de baixa margem e promoção agressiva.",
               "Rever mix promocional e subir a participação de marca própria.", "Comercial", "margem", "C"),
              ("Quebra acima da meta em 3 lojas", "em_andamento", 11,
               "Quebra em 2,4% contra meta de 1,5% nas lojas Centro, Sul e Avenida.",
               "Pedido de perecíveis dimensionado no feeling.",
               "Parametrizar pedido sugerido e treinar os 3 encarregados.", "Operações", "quebra", "R")],
}

RISCOS = {
    "média": [("Concorrente regional anunciou 2 lojas na área", "medio", "alto"),
              ("Dependência de um único distribuidor de bebidas", "medio", "medio")],
    "bons": [("Custo de obra da 10ª loja acima do orçado", "medio", "medio"),
             ("Disputa por mão de obra qualificada em perecíveis", "alto", "medio")],
    "ruim": [("Fluxo de caixa aperta no 2º semestre", "alto", "alto"),
             ("Atacarejo novo consolidando participação", "alto", "alto"),
             ("Perda de fornecedores por atraso de pagamento", "medio", "alto")],
    "misto": [("Margem seguir caindo com a expansão", "alto", "alto"),
              ("Quebra fora de controle em perecíveis", "medio", "alto")],
}

MATURIDADE = {   # 6 dimensões, nota atual → alvo
    "média": [3.0, 3.2, 2.8, 3.1, 2.9, 3.0],
    "bons": [4.2, 4.4, 4.0, 4.3, 3.9, 4.1],
    "ruim": [1.8, 2.0, 1.6, 2.2, 1.7, 1.9],
    "misto": [3.3, 2.6, 3.0, 2.8, 2.5, 3.1],
}
DIMENSOES = ["Planejamento", "Indicadores", "Rituais de gestão",
             "Pessoas e metas", "Processos", "Uso de dados"]

SWOT = {
    "média": {"forca": ["Ponto consolidado no centro", "Equipe antiga e fiel"],
              "fraqueza": ["Margem apertada em bebidas", "Pouco controle de perdas"],
              "oportunidade": ["Bairro novo em expansão", "Marca própria"],
              "ameaca": ["Atacarejo regional", "Custo de energia"]},
    "bons": {"forca": ["Melhor açougue da região", "Gestão por indicadores", "Caixa saudável"],
             "fraqueza": ["Dependência do fundador nas decisões"],
             "oportunidade": ["Expansão para 3 cidades vizinhas", "Retail media com a indústria"],
             "ameaca": ["Rede nacional de olho na praça"]},
    "ruim": {"forca": ["Preço competitivo na cesta básica", "Clientela de bairro fiel"],
             "fraqueza": ["Quebra alta", "Ruptura crônica", "Caixa apertado", "Loja precisando de reforma"],
             "oportunidade": ["Renegociar prazo com fornecedores", "Enxugar mix improdutivo"],
             "ameaca": ["Atacarejo a 900 m", "Juros e inadimplência"]},
    "misto": {"forca": ["Crescimento de venda consistente", "Boa aceitação da marca própria"],
              "fraqueza": ["Margem escorrendo", "Pedido de perecíveis no feeling"],
              "oportunidade": ["Fidelidade e cashback", "Negociação conjunta de compras"],
              "ameaca": ["Guerra de preço na praça"]},
}

RITUAIS = [("DIA", "Daily da loja · 15 min", "gerentes + operação", "desbloquear o dia", "seg–sáb 8h"),
           ("SEM", "Semanal de resultados · 1h", "diretoria", "revisar ações e FCAs", "toda terça 9h"),
           ("MES", "Mensal de OKRs · 2h", "CEO + diretoria", "FCA dos desvios, ajustar plano", "1ª quinta 14h"),
           ("TRI", "Trimestral do conselho · 3h", "conselho + diretoria", "resultados e rota", "a agendar")]

PIS = [("venda", "Venda total", "C", "financeira", "up", 0),
       ("margem", "Margem bruta", "C", "financeira", "up", 1),
       ("ticket", "Ticket médio", "E", "cliente", "up", 2),
       ("itens_cupom", "Itens por cupom", "M", "produto", "up", 3),
       ("ruptura", "Ruptura", "A", "produto", "down", 4),
       ("quebra", "Quebra / perdas", "R", "produto", "down", 5)]


def semear_tenant(cur, tid, rede):
    """Conteúdo de gestão coerente com o perfil da rede."""
    p = rede["perfil"]
    prop, visao, valores, sonho = DIRECAO[p]
    cur.execute("INSERT INTO direcao_estrategica (tenant_id, proposito, visao, valores, objetivo_lp) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id) DO UPDATE SET "
                "proposito=EXCLUDED.proposito, visao=EXCLUDED.visao, valores=EXCLUDED.valores, "
                "objetivo_lp=EXCLUDED.objetivo_lp", (tid, prop, visao, valores, sonho))

    for i, (obj, krs) in enumerate(OKRS[p]):
        cur.execute("INSERT INTO okr_objetivo (tenant_id, titulo, periodo, nivel, ordem) "
                    "VALUES (%s,%s,%s,'corporativo',%s) RETURNING id",
                    (tid, obj, str(HOJE.year), i))
        oid = cur.fetchone()[0]
        for j, (t, un, meta, atual, base, dirn) in enumerate(krs):
            cur.execute("INSERT INTO okr_kr (tenant_id, objetivo_id, titulo, unidade, meta, atual, base, direcao, ordem) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (tid, oid, t, un, meta, atual, base, dirn, j))

    for (tit, st, dias, fato, causa, acao, dono, kpi, pilar) in FCAS[p]:
        cur.execute("INSERT INTO fca_ciclo (tenant_id, titulo, fato, causa, acao, responsavel, "
                    "prazo, status, kpi, pilar) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (tid, tit, fato, causa, acao, dono, HOJE + timedelta(days=dias), st, kpi, pilar))

    for i, (tit, prob, imp) in enumerate(RISCOS[p]):
        cur.execute("INSERT INTO risco (tenant_id, titulo, probabilidade, impacto, status, revisao, ordem) "
                    "VALUES (%s,%s,%s,%s,'ativo','revisão mensal',%s)", (tid, tit, prob, imp, i))

    for dim, nota in zip(DIMENSOES, MATURIDADE[p]):
        alvo = min(5.0, round(nota + (1.5 if nota < 3 else 0.8), 1))
        cur.execute("INSERT INTO maturidade_gestao (tenant_id, dimensao, nota, alvo) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, dimensao) DO UPDATE SET "
                    "nota=EXCLUDED.nota, alvo=EXCLUDED.alvo", (tid, dim, nota, alvo))

    for quad, itens in SWOT[p].items():
        for i, txt in enumerate(itens):
            cur.execute("INSERT INTO swot_item (tenant_id, quadrante, texto, ordem) "
                        "VALUES (%s,%s,%s,%s)", (tid, quad, txt, i))

    for i, (fq, nm, qm, ob, px) in enumerate(RITUAIS):
        cur.execute("INSERT INTO ritual (tenant_id, freq, nome, quem, objetivo, proxima, ordem) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)", (tid, fq, nm, qm, ob, px, i))

    metas = {"venda": None, "margem": {"média": 22.5, "bons": 27.0, "ruim": 20.0, "misto": 22.0}[p],
             "ticket": rede["ticket"] * 1.06, "itens_cupom": rede["itens"] * 1.05,
             "ruptura": 4.0, "quebra": 1.5}
    for chave, nome, pilar, jornada, dirn, ordem in PIS:
        cur.execute("INSERT INTO pi (tenant_id, chave, nome, pilar, jornada, direcao, meta, ordem, fonte) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'importação de vendas') "
                    "ON CONFLICT (tenant_id, chave) DO NOTHING",
                    (tid, chave, nome, pilar, jornada, dirn, metas.get(chave), ordem))


def semear(apagar_existentes=False, senha=None, log=print):
    """Cria/atualiza as 4 redes. Devolve o resumo do que foi feito.

    Chamável da API (POST /admin/seed-demo) e da linha de comando.
    """
    resumo = {"redes": [], "apagadas": [], "calendario": 0}
    rnd = random.Random(20260808)
    os.environ.setdefault("BOARDOS_DSN", ADMIN_DSN)
    from boardos.db import tenant_session  # noqa: E402  (depois do BOARDOS_DSN)

    slugs = [r["slug"] for r in REDES]
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        if apagar_existentes:
            outros = conn.execute(
                "SELECT nome FROM platform.tenant WHERE slug <> ALL(%s)", (slugs,)).fetchall()
            resumo["apagadas"] = [o[0] for o in outros]
            if outros:
                log("APAGANDO as empresas: " + ", ".join(resumo["apagadas"]))
            conn.execute("DELETE FROM platform.tenant WHERE slug <> ALL(%s)", (slugs,))
        with conn.cursor() as cur:
            resumo["calendario"] = upsert_into(cur, DE, date(ATE.year + 1, 12, 31))
        log(f"calendário: {resumo['calendario']} dias\n")

        for rede in REDES:
            tid = conn.execute(
                "INSERT INTO platform.tenant (nome, slug, status, segmento, origem) "
                "VALUES (%s,%s,'ativo','supermercado','manual') "
                "ON CONFLICT (slug) DO UPDATE SET nome=EXCLUDED.nome RETURNING id",
                (rede["nome"], rede["slug"])).fetchone()[0]
            conn.execute("INSERT INTO platform.assinatura (tenant_id, plano, base_mensal_cent, preco_por_1k_cent) "
                         "VALUES (%s,'v0',49900,900) ON CONFLICT (tenant_id) DO NOTHING", (tid,))
            if senha:
                email = rede["slug"].replace("rede-", "") + "@boardos.demo"
                conn.execute(
                    "INSERT INTO platform.usuario_login (email, senha_hash, nome, tenant_id, papel) "
                    "VALUES (%s,%s,%s,%s,'admin_tenant') ON CONFLICT (email) DO UPDATE SET "
                    "senha_hash=EXCLUDED.senha_hash, tenant_id=EXCLUDED.tenant_id",
                    (email, hash_password(senha), "Dono " + rede["nome"], tid))

            with tenant_session(str(tid)) as cur:
                # limpa o conteúdo antes de resemear (reexecução idempotente)
                for tbl in ("gold_venda_diaria", "okr_kr", "okr_objetivo", "fca_ciclo",
                            "risco", "swot_item", "ritual", "maturidade_gestao"):
                    cur.execute(f"DELETE FROM {tbl}")
                cat_ids = {}
                for cod, nome, secao, _peso in CATEGORIAS:
                    cur.execute("INSERT INTO categoria (tenant_id, codigo, nome, secao) "
                                "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, codigo) "
                                "DO UPDATE SET nome=EXCLUDED.nome RETURNING id",
                                (str(tid), cod, nome, secao))
                    cat_ids[cod] = cur.fetchone()[0]
                loja_ids = []
                for cod, nome, mun, uf in rede["lojas"]:
                    cur.execute("INSERT INTO loja (tenant_id, codigo, nome, municipio, uf, formato) "
                                "VALUES (%s,%s,%s,%s,%s,'vizinhanca') "
                                "ON CONFLICT (tenant_id, codigo) DO UPDATE SET nome=EXCLUDED.nome, "
                                "municipio=EXCLUDED.municipio RETURNING id",
                                (str(tid), cod, nome, mun, uf))
                    loja_ids.append(cur.fetchone()[0])

                linhas = gerar_gold(rede, loja_ids, cat_ids, rnd)
                cur.executemany(
                    "INSERT INTO gold_venda_diaria (tenant_id, data, loja_id, categoria_id, "
                    "faturamento_bruto, faturamento_liq, custo, margem, itens, cupons, qtd) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id, data, loja_id, categoria_id) DO UPDATE SET "
                    "faturamento_bruto=EXCLUDED.faturamento_bruto, faturamento_liq=EXCLUDED.faturamento_liq, "
                    "custo=EXCLUDED.custo, margem=EXCLUDED.margem, itens=EXCLUDED.itens, "
                    "cupons=EXCLUDED.cupons, qtd=EXCLUDED.qtd",
                    [(str(tid),) + l for l in linhas])
                semear_tenant(cur, str(tid), rede)

            resumo["redes"].append({"nome": rede["nome"], "perfil": rede["perfil"],
                                    "id": str(tid), "lojas": len(rede["lojas"]),
                                    "linhas": len(linhas)})
            log(f"{rede['nome']:<26} perfil={rede['perfil']:<7} "
                f"{len(rede['lojas'])} lojas · {len(linhas):>7} linhas de venda · id={tid}")
    return resumo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apagar-existentes", action="store_true",
                    help="APAGA todas as outras empresas do banco (irreversível)")
    ap.add_argument("--senha", help="se informada, cria um login admin por rede")
    a = ap.parse_args()
    semear(apagar_existentes=a.apagar_existentes, senha=a.senha)
    print("\nPronto. Entre como super-admin e escolha a empresa no seletor do topo.")
    if a.senha:
        print("Logins criados: " + ", ".join(r["slug"].replace("rede-", "") + "@boardos.demo"
                                             for r in REDES))


if __name__ == "__main__":
    main()
