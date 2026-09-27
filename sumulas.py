"""Biblioteca local de súmulas do TST, extraída do Livro oficial.

Fonte: Livro de Súmulas, OJs e PNs do TST (Res. 225/2025).
https://www.tst.jus.br/livro-de-sumulas-ojs-e-pns
O enunciado que não está aqui não é inventado: a peça deve dizer que não consta.
"""
from __future__ import annotations

import re

FONTE = "https://www.tst.jus.br/livro-de-sumulas-ojs-e-pns"

# vigente=False: o próprio Livro marca cancelamento. Não usar como fundamento atual.
SUMULAS: dict[int, dict] = {
    18: {
        "titulo": "Compensação",
        "vigente": True,
        "temas": ("compensa", "dedu", "pago", "pagamento", "trct"),
        "enunciado": "A compensação, na Justiça do Trabalho, está restrita a dívidas de natureza trabalhista.",
    },
    81: {
        "titulo": "Férias",
        "vigente": True,
        "temas": ("feria", "férias"),
        "enunciado": "Os dias de férias gozados após o período legal de concessão deverão ser remunerados em dobro.",
    },
    85: {
        "titulo": "Compensação de jornada",
        "vigente": True,
        "temas": ("compensa", "banco de horas", "jornada", "hora extra"),
        "enunciado": (
            "I. A compensação de jornada de trabalho deve ser ajustada por acordo individual escrito, "
            "acordo coletivo ou convenção coletiva. II. O acordo individual para compensação de horas "
            "é válido, salvo se houver norma coletiva em sentido contrário. III. O mero não atendimento "
            "das exigências legais para a compensação de jornada, inclusive quando encetada mediante "
            "acordo tácito, não implica a repetição do pagamento das horas excedentes à jornada normal "
            "diária, se não dilatada a jornada máxima semanal, sendo devido apenas o respectivo adicional. "
            "IV. A prestação de horas extras habituais descaracteriza o acordo de compensação de jornada. "
            "V. As disposições contidas nesta súmula não se aplicam ao regime compensatório na modalidade "
            "“banco de horas”, que somente pode ser instituído por negociação coletiva. VI. Não é válido "
            "acordo de compensação de jornada em atividade insalubre, ainda que estipulado em norma coletiva, "
            "sem a necessária inspeção prévia e permissão da autoridade competente, na forma do art. 60 da CLT."
        ),
    },
    90: {
        "titulo": "Horas in itinere",
        "vigente": False,
        "nota": "cancelada por perda de eficácia a partir de 11.11.2017, pela Lei 13.467/2017 (Res. 225/2025)",
        "temas": ("itinere", "transporte"),
        "enunciado": (
            "I. O tempo despendido pelo empregado, em condução fornecida pelo empregador, até o local de "
            "trabalho de difícil acesso, ou não servido por transporte público regular, e para o seu retorno, "
            "é computável na jornada de trabalho."
        ),
    },
    126: {
        "titulo": "Recurso. Cabimento",
        "vigente": True,
        "temas": ("recurso", "revista", "prova"),
        "enunciado": "Incabível o recurso de revista ou de embargos (arts. 896 e 894, “b”, da CLT) para reexame de fatos e provas.",
    },
    212: {
        "titulo": "Despedimento. Ônus da prova",
        "vigente": True,
        "temas": ("desped", "dispens", "justa causa", "rescis"),
        "enunciado": (
            "O ônus de provar o término do contrato de trabalho, quando negados a prestação de serviço "
            "e o despedimento, é do empregador, pois o princípio da continuidade da relação de emprego "
            "constitui presunção favorável ao empregado."
        ),
    },
    219: {
        "titulo": "Honorários advocatícios. Cabimento",
        "vigente": False,
        "nota": "cancelada por perda de eficácia a partir de 11.11.2017, pela Lei 13.467/2017 (Res. 225/2025)",
        "temas": ("honorario", "sucumb"),
        "enunciado": (
            "Na redação cancelada, a condenação em honorários na Justiça do Trabalho não decorria pura "
            "e simplesmente da sucumbência."
        ),
    },
    277: {
        "titulo": "Convenção ou acordo coletivo. Ultratividade",
        "vigente": False,
        "nota": "cancelada por perda de eficácia a partir de 11.11.2017, pela Lei 13.467/2017 (Res. 225/2025)",
        "temas": ("convenção coletiva", "acordo coletivo", "ultrativ"),
        "enunciado": (
            "As cláusulas normativas dos acordos coletivos ou convenções coletivas integram os contratos "
            "individuais de trabalho e somente poderão ser modificadas ou suprimidas mediante negociação coletiva de trabalho."
        ),
    },
    331: {
        "titulo": "Contrato de prestação de serviços. Terceirização",
        "vigente": True,
        "nota": "item I cancelado a partir de 11.11.2017 (Lei 13.467/2017, Res. 225/2025). Itens II a VI seguem no Livro.",
        "temas": ("terceir", "tomador", "prestação de serviço", "prestacao de servico"),
        "enunciado": (
            "Item I cancelado. II. A contratação irregular de trabalhador, mediante empresa interposta, "
            "não gera vínculo de emprego com os órgãos da Administração Pública direta, indireta ou fundacional "
            "(art. 37, II, da CF/1988). IV. O inadimplemento das obrigações trabalhistas, por parte do empregador, "
            "implica a responsabilidade subsidiária do tomador dos serviços quanto àquelas obrigações, desde que "
            "haja participado da relação processual e conste também do título executivo judicial."
        ),
    },
    338: {
        "titulo": "Jornada de trabalho. Registro. Ônus da prova",
        "vigente": True,
        "temas": ("ponto", "jornada", "cartão", "cartao", "hora extra", "frequência", "frequencia"),
        "enunciado": (
            "I. É ônus do empregador que conta com mais de 10 (dez) empregados o registro da jornada de trabalho "
            "na forma do art. 74, § 2º, da CLT. A não-apresentação injustificada dos controles de frequência gera "
            "presunção relativa de veracidade da jornada de trabalho, a qual pode ser elidida por prova em contrário. "
            "II. A presunção de veracidade da jornada de trabalho, ainda que prevista em instrumento normativo, "
            "pode ser elidida por prova em contrário. III. Os cartões de ponto que demonstram horários de entrada "
            "e saída uniformes são inválidos como meio de prova, invertendo-se o ônus da prova, relativo às horas "
            "extras, que passa a ser do empregador, prevalecendo a jornada da inicial se dele não se desincumbir."
        ),
    },
    362: {
        "titulo": "FGTS. Prescrição",
        "vigente": True,
        "temas": ("fgts", "prescri"),
        "enunciado": (
            "I. Para os casos em que a ciência da lesão ocorreu a partir de 13.11.2014, é quinquenal a prescrição "
            "do direito de reclamar contra o não-recolhimento de contribuição para o FGTS, observado o prazo de "
            "dois anos após o término do contrato. II. Para os casos em que o prazo prescricional já estava em "
            "curso em 13.11.2014, aplica-se o prazo prescricional que se consumar primeiro: trinta anos, contados "
            "do termo inicial, ou cinco anos, a partir de 13.11.2014 (STF-ARE-709212/DF)."
        ),
    },
    378: {
        "titulo": "Estabilidade provisória. Acidente do trabalho",
        "vigente": True,
        "temas": ("acidente", "estabilidade", "auxílio-doença", "auxilio-doenca"),
        "enunciado": (
            "I. É constitucional o artigo 118 da Lei nº 8.213/1991, que assegura o direito à estabilidade "
            "provisória por período de 12 meses após a cessação do auxílio-doença ao empregado acidentado. "
            "II. São pressupostos para a concessão da estabilidade o afastamento superior a 15 dias e a "
            "consequente percepção do auxílio-doença acidentário, salvo se constatada, após a despedida, "
            "doença profissional que guarde relação de causalidade com a execução do contrato de emprego. "
            "III. O empregado submetido a contrato de trabalho por tempo determinado goza da garantia "
            "provisória de emprego decorrente de acidente de trabalho prevista no art. 118 da Lei nº 8.213/91."
        ),
    },
    437: {
        "titulo": "Intervalo intrajornada",
        "vigente": False,
        "nota": "cancelada por perda de eficácia a partir de 11.11.2017, pela Lei 13.467/2017 (Res. 225/2025)",
        "temas": ("intervalo", "intrajornada"),
        "enunciado": (
            "I. Após a edição da Lei nº 8.923/94, a não concessão ou a concessão parcial do intervalo "
            "intrajornada mínimo, para repouso e alimentação, implica o pagamento total do período correspondente, "
            "com acréscimo de, no mínimo, 50% sobre o valor da remuneração da hora normal de trabalho (art. 71 da CLT)."
        ),
    },
    443: {
        "titulo": "Dispensa discriminatória. Doença grave",
        "vigente": True,
        "temas": ("discrim", "doença", "doenca", "hiv", "reintegra"),
        "enunciado": (
            "Presume-se discriminatória a despedida de empregado portador do vírus HIV ou de outra doença "
            "grave que suscite estigma ou preconceito. Inválido o ato, o empregado tem direito à reintegração no emprego."
        ),
    },
    444: {
        "titulo": "Jornada 12 por 36",
        "vigente": False,
        "nota": "cancelada por perda de eficácia a partir de 11.11.2017, pela Lei 13.467/2017 (Res. 225/2025)",
        "temas": ("12x36", "12 por 36", "doze horas"),
        "enunciado": (
            "É válida, em caráter excepcional, a jornada de doze horas de trabalho por trinta e seis de descanso, "
            "prevista em lei ou ajustada exclusivamente mediante acordo coletivo de trabalho ou convenção coletiva de trabalho."
        ),
    },
    460: {
        "titulo": "Vale-transporte. Ônus da prova",
        "vigente": True,
        "temas": ("vale-transporte", "vale transporte"),
        "enunciado": (
            "É do empregador o ônus de comprovar que o empregado não satisfaz os requisitos indispensáveis "
            "para a concessão do vale-transporte ou não pretenda fazer uso do benefício."
        ),
    },
    461: {
        "titulo": "FGTS. Diferenças. Ônus da prova",
        "vigente": True,
        "temas": ("fgts",),
        "enunciado": (
            "É do empregador o ônus da prova em relação à regularidade dos depósitos do FGTS, "
            "pois o pagamento é fato extintivo do direito do autor (art. 373, II, do CPC de 2015)."
        ),
    },
}


def _numeros(texto: str) -> list[int]:
    vistos = []
    for m in re.finditer(r"S[úu]mula\s+n?[ºo°.]?\s*(\d+)", texto or "", re.I):
        n = int(m.group(1))
        if n not in vistos:
            vistos.append(n)
    return vistos


def conferir(texto: str) -> dict:
    conferidas = []
    avisos = []
    for n in _numeros(texto):
        item = SUMULAS.get(n)
        if not item:
            avisos.append(
                f"Súmula {n} não está na biblioteca Harvey. Confira o enunciado no Livro do TST antes de protocolar."
            )
            continue
        conferidas.append(
            {
                "numero": n,
                "titulo": item["titulo"],
                "enunciado": item["enunciado"],
                "vigente": item["vigente"],
                "nota": item.get("nota") or "",
                "fonte": FONTE,
            }
        )
        if not item["vigente"]:
            avisos.append(
                f"Súmula {n} do TST está cancelada ({item.get('nota')}). Não use como fundamento vigente."
            )
    return {"conferidas": conferidas, "avisos": avisos}


def bloco_biblioteca(texto: str) -> str:
    """Trechos oficiais que batem com o extrato, mais as súmulas canceladas que o modelo costuma citar."""
    blob = (texto or "").lower()
    linhas = [
        "BIBLIOTECA DE SÚMULAS DO TST (Livro oficial). Cite o enunciado só se estiver abaixo, e de forma literal.",
        "Se precisar de número que não está aqui, escreva NÃO CONSTA DA BIBLIOTECA HARVEY. Não invente enunciado nem número de acórdão.",
    ]
    escolhidas = []
    for n, item in SUMULAS.items():
        if not item["vigente"]:
            continue
        if any(t in blob for t in item["temas"]):
            escolhidas.append(n)
    if 18 not in escolhidas and any(t in blob for t in ("pago", "pagamento", "trct", "conden")):
        escolhidas.insert(0, 18)
    for n in escolhidas[:8]:
        item = SUMULAS[n]
        linhas.append(f"Súmula {n} TST — {item['titulo']} (vigente). {item['enunciado']}")
    canceladas = [
        f"Súmula {n} ({SUMULAS[n]['titulo']}) está cancelada: {SUMULAS[n].get('nota')}"
        for n, item in SUMULAS.items()
        if not item["vigente"]
    ]
    linhas.append("NÃO FUNDAMENTE COMO VIGENTES: " + " | ".join(canceladas))
    linhas.append(f"Fonte de conferência: {FONTE}")
    return "\n".join(linhas)
