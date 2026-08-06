"""Onboarding de novos clientes — entrevista guiada + Primeiro Modelo de Ação.

Roteiro enxuto do método Masi de Planejamento Estratégico (Direção → SWOT →
OKRs → Tático 5W2H → Execução): 13 perguntas digitadas, sem integração de
dados. As sub-perguntas do método viram dicas na tela. A IA devolve um modelo
em JSON estrito (validado aqui); sem IA, o fallback determinístico monta um
esqueleto honesto com as próprias respostas — sem inventar números.
"""
from __future__ import annotations

import json
import re
from datetime import date as _date
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, StringConstraints

# --------------------------------------------------------------- roteiro
# k = chave estável da resposta; bloco = rótulo do grupo; q = pergunta;
# dica = sub-perguntas do método (sempre visíveis); ph = exemplo no textarea.
PERGUNTAS: List[Dict] = [
    # A · Seu negócio
    {"k": "N1", "bloco": "Seu negócio", "obrig": True,
     "q": "Conte o básico do seu negócio: o que você vende, quantas lojas ou pontos tem e onde ficam?",
     "dica": ["Formato e porte (loja de rua, shopping, e-commerce…)",
              "Há quanto tempo a empresa existe",
              "Faturamento aproximado — pode ser faixa; confirmamos com seus dados depois"],
     "ph": "Ex.: 3 lojas de material de construção em Campinas e região, 12 anos de mercado, ~R$ 1,5 mi/mês."},
    {"k": "N2", "bloco": "Seu negócio", "obrig": True,
     "q": "Quem é seu cliente típico e por que ele compra de você — e não do concorrente?",
     "dica": ["Perfil e hábito de compra do cliente",
              "O que você resolve melhor que o concorrente mais próximo",
              "Um exemplo concreto ajuda: preço? sortimento? atendimento? prazo?"],
     "ph": "Ex.: pedreiros e pequenas construtoras; compram pela entrega no mesmo dia e crediário próprio."},
    # B · Direção (método, etapa 1)
    {"k": "N3", "bloco": "Direção", "obrig": False,
     "q": "Por que a sua empresa existe, além de dar lucro?",
     "dica": ["Por que você começou este negócio?",
              "Qual problema você está resolvendo?",
              "Como sua cidade ou mercado seria diferente sem a empresa?"],
     "ph": "Ex.: garantir que obra de gente simples não pare por falta de material ou de crédito."},
    {"k": "N4", "bloco": "Direção", "obrig": False,
     "q": "O que a sua empresa tem de especial: quais valores são inegociáveis e no que vocês são excepcionalmente bons?",
     "dica": ["Liste 3–5 valores inegociáveis (um por linha)",
              "No que sua empresa é melhor que qualquer concorrente?",
              "Como você quer ser lembrado pelos clientes?"],
     "ph": "Ex.:\nPalavra cumprida\nAgilidade na entrega\nSomos os melhores em logística de última milha."},
    {"k": "N5", "bloco": "Direção", "obrig": False,
     "q": "Se tudo der certo, onde a empresa estará em 3 a 5 anos?",
     "dica": ["Quantas lojas? Qual faturamento? Quantas pessoas?",
              "Como o mercado vai perceber a empresa?",
              "Seja específico — \"crescer\" não é visão"],
     "ph": "Ex.: 6 lojas na região, R$ 4 mi/mês, referência em atendimento ao profissional de obra."},
    {"k": "N6", "bloco": "Direção", "obrig": False,
     "q": "Qual é a meta mais ousada que você imagina para 10 anos ou mais — o sonho grande?",
     "dica": ["Se você tivesse recursos ilimitados, o que faria?",
              "Qual seria o impacto de alcançar isso?",
              "É o sonho grande, não a meta do ano"],
     "ph": "Ex.: ser a maior rede do interior do estado, com marca própria e 30 lojas."},
    # C · Diagnóstico (método, etapa 2 — SWOT)
    {"k": "N7", "bloco": "Diagnóstico", "obrig": True,
     "q": "O que a sua operação faz melhor que a concorrência hoje? (forças)",
     "dica": ["Por que os clientes escolhem você?",
              "Que recursos únicos você tem (pessoas, ponto, tecnologia, relacionamentos)?",
              "Quais vantagens são difíceis de copiar?",
              "Liste 2–4 itens, um por linha"],
     "ph": "Ex.:\nEquipe antiga e de confiança\nPonto na avenida principal\nCrediário próprio"},
    {"k": "N8", "bloco": "Diagnóstico", "obrig": True,
     "q": "O que trava a empresa por dentro — onde a concorrência é melhor ou falta recurso? (fraquezas)",
     "dica": ["Quais processos precisam melhorar?",
              "O que falta: capital, gente, sistema?",
              "O que impede de crescer mais rápido?",
              "Honestidade aqui vale ouro — isso fica só no seu painel"],
     "ph": "Ex.:\nEstoque desorganizado\nDependência do dono para tudo\nSem controle de margem por categoria"},
    {"k": "N9", "bloco": "Diagnóstico", "obrig": False,
     "q": "Que oportunidades você vê no mercado para crescer? (oportunidades)",
     "dica": ["Tendências que podem beneficiar o negócio",
              "Necessidades não atendidas na sua região ou segmento",
              "Novos canais, praças ou parcerias",
              "O que um concorrente esperto faria no seu lugar?"],
     "ph": "Ex.:\nBairro novo em expansão sem concorrente\nVenda por WhatsApp para profissionais"},
    {"k": "N10", "bloco": "Diagnóstico", "obrig": False,
     "q": "O que, vindo de fora, pode atrapalhar seus resultados? (ameaças)",
     "dica": ["Concorrentes novos ou mais agressivos",
              "Mudança de hábito dos clientes",
              "Custo, economia, regulação",
              "Para qual cenário adverso vale se preparar?"],
     "ph": "Ex.:\nAtacadista grande chegando na cidade\nJuros altos segurando as obras"},
    # D · Metas e execução (método, etapas 3–5)
    {"k": "N11", "bloco": "Metas", "obrig": True,
     "q": "Quais metas você PRECISA bater nos próximos 12 meses? Dê número e prazo.",
     "dica": ["Ex.: \"faturamento +12% até dezembro\", \"margem de 24%\", \"abrir a 5ª loja\"",
              "Meta boa é específica, com número e prazo (SMART)",
              "Liste até 3 — o resto vira plano depois"],
     "ph": "Ex.:\nFaturamento +15% até dezembro\nMargem bruta de 28%\nAbrir a loja do bairro Alto em setembro"},
    {"k": "N12", "bloco": "Metas", "obrig": True,
     "q": "Qual é o maior gargalo que trava esses resultados hoje?",
     "dica": ["É margem? estoque ou ruptura? pessoas? caixa? concorrência?",
              "Qual dói mais se nada mudar?",
              "Um exemplo real do último mês ajuda"],
     "ph": "Ex.: ruptura dos itens mais vendidos — o cliente vem e não encontra; perdemos venda toda semana."},
    {"k": "N13", "bloco": "Metas", "obrig": False,
     "q": "Como você acompanha o negócio hoje: que números olha e que reuniões de resultado faz?",
     "dica": ["Quais indicadores você acompanha (e confia)?",
              "Existe reunião de resultado? Com quem e com que frequência?",
              "Onde estão os dados de venda (sistema, planilha)?"],
     "ph": "Ex.: olho o caixa todo dia e o faturamento no fim do mês; reunião mesmo, só quando aperta."},
]

OBRIGATORIAS = ("N1", "N2", "N7", "N8", "N11", "N12")


# ------------------------------------------------------- modelo (schema)
Txt = Annotated[str, StringConstraints(max_length=2000)]
TxtCurto = Annotated[str, StringConstraints(max_length=300)]


class KrModelo(BaseModel):
    titulo: TxtCurto
    unidade: Optional[TxtCurto] = None     # %, R$, un, lojas…
    meta: float
    base: Optional[float] = None
    direcao: Literal["up", "down"] = "up"


class OkrModelo(BaseModel):
    objetivo: Txt
    periodo: Optional[TxtCurto] = None
    krs: List[KrModelo] = []


class AcaoModelo(BaseModel):
    oque: Txt
    porque: Optional[Txt] = None
    onde: Optional[TxtCurto] = None
    quando: Optional[TxtCurto] = None      # ISO aaaa-mm-dd; inválida é descartada
    quem: Optional[TxtCurto] = None
    como: Optional[Txt] = None
    quanto: Optional[float] = None


class IniciativaModelo(BaseModel):
    nome: Txt
    objetivo_idx: Optional[int] = None     # índice em okrs[]
    acoes: List[AcaoModelo] = []


class DirecaoModelo(BaseModel):
    proposito: Optional[Txt] = None
    visao: Optional[Txt] = None
    valores: List[TxtCurto] = []
    objetivo_lp: Optional[Txt] = None      # sonho grande
    competencia: Optional[Txt] = None


class SwotModelo(BaseModel):
    forcas: List[Txt] = []
    fraquezas: List[Txt] = []
    oportunidades: List[Txt] = []
    ameacas: List[Txt] = []


class ModeloAcao(BaseModel):
    leitura: Txt
    direcao: DirecaoModelo
    swot: SwotModelo
    okrs: List[OkrModelo]
    iniciativas: List[IniciativaModelo]


def _limpa_lista(itens: List[str], max_itens: int = 6) -> List[str]:
    out = []
    for t in itens:
        t = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", (t or "").strip())
        if t and t not in out:
            out.append(t)
    return out[:max_itens]


def validar_modelo(dado: dict) -> ModeloAcao:
    """Valida e normaliza o modelo (IA ou editado pelo usuário)."""
    m = ModeloAcao.model_validate(dado)
    m.direcao.valores = _limpa_lista(m.direcao.valores, 6)
    m.swot.forcas = _limpa_lista(m.swot.forcas)
    m.swot.fraquezas = _limpa_lista(m.swot.fraquezas)
    m.swot.oportunidades = _limpa_lista(m.swot.oportunidades)
    m.swot.ameacas = _limpa_lista(m.swot.ameacas)
    m.okrs = [o for o in m.okrs if o.objetivo.strip()][:5]
    for o in m.okrs:
        o.krs = o.krs[:4]
    m.iniciativas = [i for i in m.iniciativas if i.nome.strip()][:5]
    for i in m.iniciativas:
        i.acoes = i.acoes[:4]
        if i.objetivo_idx is not None and not (0 <= i.objetivo_idx < len(m.okrs)):
            i.objetivo_idx = None
        for a in i.acoes:
            if a.quando:
                try:
                    _date.fromisoformat(a.quando)
                except ValueError:
                    a.quando = None
            else:
                a.quando = None
    if not m.okrs:
        raise ValueError("modelo sem nenhum OKR")
    return m


def parse_modelo(texto: str) -> dict:
    """Extrai o JSON da resposta da IA (tolera cercas ```json)."""
    t = (texto or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    ini, fim = t.find("{"), t.rfind("}")
    if ini < 0 or fim <= ini:
        raise ValueError("resposta sem JSON")
    return json.loads(t[ini:fim + 1])


SEGMENTO_ROTULOS = {
    "supermercado": "supermercado", "farmacia": "farmácia", "moda": "moda e vestuário",
    "material_construcao": "material de construção", "pet": "pet shop",
    "eletromoveis": "eletro e móveis", "autopecas": "autopeças",
    "alimentacao": "alimentação", "outro": "varejo",
}


def system_modelo(segmento: str, empresa: str, ano: int) -> str:
    seg = SEGMENTO_ROTULOS.get(segmento or "outro", "varejo")
    schema = ('{"leitura": str, '
              '"direcao": {"proposito": str|null, "visao": str|null, "valores": [str], '
              '"objetivo_lp": str|null, "competencia": str|null}, '
              '"swot": {"forcas": [str], "fraquezas": [str], "oportunidades": [str], "ameacas": [str]}, '
              '"okrs": [{"objetivo": str, "periodo": str, '
              '"krs": [{"titulo": str, "unidade": str|null, "meta": number, "base": number|null, '
              '"direcao": "up"|"down"}]}], '
              '"iniciativas": [{"nome": str, "objetivo_idx": int|null, '
              '"acoes": [{"oque": str, "porque": str|null, "onde": str|null, "quando": "aaaa-mm-dd"|null, '
              '"quem": str|null, "como": str|null, "quanto": number|null}]}]}')
    return (
        "Você é o Conselheiro do BoardOS, especialista no método Masi de Planejamento "
        f"Estratégico para varejo. O dono da empresa \"{empresa}\" (segmento: {seg}) acabou de "
        "responder à entrevista inicial. Monte o PRIMEIRO MODELO DE AÇÃO da empresa.\n\n"
        f"Responda SOMENTE com JSON válido, sem comentários, neste formato: {schema}\n\n"
        "Regras:\n"
        "- Use apenas o que foi respondido; NUNCA invente números. Se a meta veio sem número, "
        "crie o objetivo SEM krs e explique na leitura o que falta quantificar.\n"
        f"- 3 a 5 OKRs do ano {ano} (periodo \"{ano}\"), derivados das metas declaradas e do gargalo; "
        "cada KR com meta numérica extraída da resposta (direcao \"down\" quando menor é melhor).\n"
        "- O maior gargalo vira a iniciativa nº 1, com 2 a 3 ações 5W2H concretas (quem = cargo, "
        "não invente nomes; quando = data ISO realista dentro do ano; quanto só se o dono citou valor).\n"
        "- SWOT com 2 a 5 itens por quadrante, frases curtas tiradas das respostas.\n"
        "- direcao.valores = lista curta (um valor por item); competencia = no que a empresa é "
        "excepcional, em uma frase.\n"
        "- leitura = 2 a 4 frases diretas do Conselheiro: o que o plano ataca primeiro e por quê, "
        "citando o gargalo. Português do Brasil, vocabulário de varejo, sem jargão.\n"
    )


def _linhas(texto: str, max_itens: int = 5) -> List[str]:
    partes = re.split(r"[\n;]+", texto or "")
    return _limpa_lista(partes, max_itens)


def modelo_fallback(respostas: Dict[str, str], empresa: str, segmento: str, ano: int) -> dict:
    """Esqueleto determinístico quando a IA está inativa: organiza as próprias
    respostas do dono, sem inventar números (OKRs nascem sem KR)."""
    r = {k: (respostas.get(k) or "").strip() for k in
         ("N3", "N4", "N5", "N6", "N7", "N8", "N9", "N10", "N11", "N12")}
    okrs = [{"objetivo": m, "periodo": str(ano), "krs": []} for m in _linhas(r["N11"], 3)]
    if not okrs:
        okrs = [{"objetivo": "Definir as metas do ano com número e prazo", "periodo": str(ano), "krs": []}]
    inic = []
    if r["N12"]:
        gargalo = r["N12"].splitlines()[0][:120]
        inic = [{"nome": f"Atacar o gargalo: {gargalo}", "objetivo_idx": 0,
                 "acoes": [{"oque": f"Investigar a fundo e montar o plano de ataque: {gargalo}",
                            "porque": "É o gargalo que o dono apontou como o que mais trava os resultados.",
                            "quem": "Dono / diretor responsável"}]}]
    return {
        "leitura": ("Organizei suas respostas no primeiro modelo de ação. A IA do BoardOS ainda não "
                    "está ativa nesta conta, então os números e refinamentos ficam para a próxima etapa: "
                    "revise as metas abaixo, dê número e prazo ao que faltou, e importe seus dados de "
                    "venda para o painel começar a medir."),
        "direcao": {"proposito": r["N3"] or None, "visao": r["N5"] or None,
                    "valores": _linhas(r["N4"], 5), "objetivo_lp": r["N6"] or None,
                    "competencia": None},
        "swot": {"forcas": _linhas(r["N7"]), "fraquezas": _linhas(r["N8"]),
                 "oportunidades": _linhas(r["N9"]), "ameacas": _linhas(r["N10"])},
        "okrs": okrs,
        "iniciativas": inic,
    }
