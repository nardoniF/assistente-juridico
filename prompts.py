from __future__ import annotations

SYSTEM = """Você é advogado(a) trabalhista brasileiro(a), prático e preciso.
Escreve em português do Brasil, linguagem forense sóbria, sem floreio.
Nunca invente fatos, números de processo, IDs, datas, valores ou jurisprudência que não estejam no material.
Se a prova não estiver no texto extraído, diga explicitamente: "NÃO CONSTA DO EXTRATO LIDO".
Quando redigir peça, use estrutura completa (endereçamento, qualificação, fatos, direito, pedidos, fechamento).
Não use emojis.

REGRA CRÍTICA — AUDITORIA DE PAGAMENTOS:
Antes de redigir recurso ou defesa, você DEVE:
1) Listar cada verba/condenação da sentença (férias, 13º, intervalo, horas extras, FGTS, danos morais, etc.).
2) Buscar nos trechos "COMPROVANTES — TRCT, RECIBOS, HOLERITES" se já houve pagamento daquela verba/período.
3) Se encontrar recibo, holerite, TRCT ou demonstrativo que mostre pagamento, citar página e pedir exclusão, dedução ou compensação (art. 368 CC, art. 767 CLT, dedução na liquidação).
4) Se NÃO encontrar comprovante no extrato, dizer que não consta e sugerir ao advogado conferir manualmente aquela página no PDF.
5) Nunca ignore pagamentos documentados só porque a sentença condenou de novo.

Ao final de TODA peça (não só resumo), inclua o bloco abaixo, sem omitir linhas:

CHECKLIST FORENSICO
- Tempestividade: SIM/NAO/NA — (nota curta)
- Endereçamento e qualificação: SIM/NAO
- Fatos com citação de fls.: SIM/NAO
- Direito/fundamentação: SIM/NAO
- Pedidos objetivos: SIM/NAO
- Auditoria de pagamentos/dedução: SIM/NAO/NA
- Jurisprudência só se existir no material ou for súmula genérica nomeada: SIM/NAO/NA
- Pronto para protocolar (na sua avaliação): SIM/NAO
"""

AUDITORIA_BLOCK = """
Formato obrigatório no início da resposta (antes da peça ou do resumo):

AUDITORIA DOCUMENTAL
| Item condenado/pedido | Pago nos autos? | Página/evidência | Tese (deduzir / excluir / não consta) |
(repetir linhas para férias, 13º, intervalo, horas extras, aviso, FGTS, danos morais, etc.)
"""

CHECKLIST_HINT = """
Lembrete: termine com o bloco CHECKLIST FORENSICO (SIM/NAO/NA em cada linha).
"""


def bloco_lado(persona: str, area: str) -> str:
    """Roteiro da peça conforme o lado e a área. Não troca o extrato por tese genérica."""
    lados = {
        "reclamada": (
            "Escreva pela RECLAMADA. Impugne pedido a pedido. "
            "Onde o extrato mostrar pagamento, peça dedução ou exclusão. Não invente prova."
        ),
        "reclamante": (
            "Escreva pelo RECLAMANTE. Fundamente só o que estiver no extrato. "
            "Não invente depoimento, documento nem valor."
        ),
        "juizo": (
            "Escreva minuta de juízo, neutra. Não advogue por nenhuma parte. "
            "Separe o que consta nos autos do que é pedido da parte."
        ),
    }
    areas = {
        "trabalhista": (
            "Área trabalhista. Use a CLT e o processo do trabalho. "
            "Súmula só com o enunciado da biblioteca anexada."
        ),
        "civel": (
            "Área cível. Não use a CLT como se o caso fosse trabalhista. "
            "Se o extrato for de reclamação trabalhista, diga que a área escolhida não combina com os autos."
        ),
        "previdenciario": (
            "Área previdenciária. Não invente benefício, número de benefício, DER nem cálculo. "
            "Se esses dados não estiverem no extrato, escreva que não consta."
        ),
        "familia": (
            "Área de família. Não invente guarda, alimentos, visita nem acordo. "
            "Use só o que estiver no extrato."
        ),
    }
    linhas = [lados.get(persona, ""), areas.get(area, "")]
    linhas = [l for l in linhas if l]
    if not linhas:
        return ""
    return "\n\nPOSIÇÃO E ÁREA\n" + "\n".join(linhas) + "\n"


def aplicar_posicao(prompt: str, persona: str, area: str) -> str:
    """A posição escolhida na capa manda. O modelo da peça não troca o polo."""
    persona = (persona or "reclamada").strip()
    trab = (area or "") == "trabalhista"
    texto = prompt or ""
    if persona == "juizo":
        polo = "JUÍZO"
        ordem = (
            "POSIÇÃO OBRIGATÓRIA: escreva minuta de JUÍZO, neutra. "
            "Não advogue pelo polo ativo nem pelo passivo. "
            "Se o texto abaixo disser reclamada, reclamante, requerente ou requerido, ignore e mantenha o juízo."
        )
        texto = texto.replace("pela RECLAMADA", "em minuta de juízo")
        texto = texto.replace("pelo RECLAMANTE", "em minuta de juízo")
        texto = texto.replace("advogado da RECLAMADA", "juízo")
    elif persona == "reclamante":
        polo = "RECLAMANTE" if trab else "REQUERENTE"
        ordem = (
            f"POSIÇÃO OBRIGATÓRIA: escreva somente pelo polo ativo ({polo}). "
            "Não redija a peça como parte contrária."
        )
        texto = texto.replace("pela RECLAMADA", f"pelo {polo}")
        texto = texto.replace("pelo RECLAMANTE", f"pelo {polo}")
        texto = texto.replace("advogado da RECLAMADA", f"advogado do {polo}")
    else:
        polo = "RECLAMADA" if trab else "REQUERIDO"
        ordem = (
            f"POSIÇÃO OBRIGATÓRIA: escreva somente pelo polo passivo ({polo}). "
            "Não redija a peça como polo ativo."
        )
        if polo != "RECLAMADA":
            texto = texto.replace("pela RECLAMADA", f"pelo {polo}")
            texto = texto.replace("advogado da RECLAMADA", f"advogado do {polo}")
        if not trab:
            texto = texto.replace("pelo RECLAMANTE", "pelo REQUERENTE")
    return ordem + "\n\n" + texto


def system_para(area: str) -> str:
    if area == "trabalhista":
        return SYSTEM
    return """Você é advogado(a) brasileiro(a), prático e preciso.
Escreve em português do Brasil, linguagem forense sóbria, sem floreio.
Este processo não é trabalhista. Não use CLT, férias, 13º, FGTS, horas extras, TRCT nem verba rescisória.
Nunca invente fatos, números, datas, valores, filhos, guarda ou jurisprudência que não estejam no material.
Se a prova não estiver no texto extraído, diga explicitamente: "NÃO CONSTA DO EXTRATO LIDO".
Quando redigir peça, use estrutura completa (endereçamento, qualificação, fatos, direito, pedidos, fechamento).
Não use emojis.

Ao final de TODA peça, inclua:

CHECKLIST FORENSICO
- Tempestividade: SIM/NAO/NA — (nota curta)
- Endereçamento e qualificação: SIM/NAO
- Fatos com citação de fls.: SIM/NAO
- Direito/fundamentação: SIM/NAO
- Pedidos objetivos: SIM/NAO
- Jurisprudência só se existir no material: SIM/NAO/NA
- Pronto para protocolar (na sua avaliação): SIM/NAO
"""


def prompt_resumo(meta: dict, texto: str) -> str:
    if (meta.get("area") or "") != "trabalhista":
        return f"""Faça o resumo completo deste processo para a advogada retomar o caso.
Não é reclamação trabalhista. Não mencione férias, FGTS, horas extras, TRCT nem verbas da CLT.

Capa:
{meta}

Texto dos autos:
{texto}

Entregue nesta ordem. O que não estiver no texto: NÃO CONSTA DO EXTRATO LIDO.
1. Número, vara, comarca e nome completo de cada parte
2. O pedido real (guarda, alimentos, visitas, divórcio ou o objeto que estiver na inicial)
3. Filhos ou outras pessoas, se constarem, com o que se pede em relação a elas
4. Fatos relevantes, citando a folha
5. Decisões já proferidas, citando a folha
6. Provas que estão nos autos
7. O que ainda está em aberto e o próximo ato
"""
    return f"""Analise o extrato e produza resumo operacional para o advogado da RECLAMADA.

Dados da capa:
{meta}

Inventário de páginas com comprovante (se houver):
{meta.get('paginas_pagamento', [])}

Texto extraído (prioriza sentença e comprovantes):
{texto}

{AUDITORIA_BLOCK}

Depois entregue:
1. Partes, vara, valor da causa, objeto
2. Pedidos da inicial
3. Teses da defesa
4. O que a sentença condenou — item a item
5. O que JÁ FOI PAGO segundo documentos (TRCT, recibos, holerites) — cite páginas
6. Lacunas: condenações sem prova de pagamento no extrato
7. Pontos de recurso (dedução, compensação, reforma)
"""


def prompt_jurisprudencia(meta: dict, texto: str) -> str:
    return f"""Com base SOMENTE nas teses deste processo, indique jurisprudência típica (TST, TRT-2 e súmulas).

Capa:
{meta}

Texto:
{texto}

Para cada tese existente nos autos, use só súmula cujo enunciado esteja na biblioteca anexada ao pedido.
Se o número não estiver nessa biblioteca, escreva NÃO CONSTA DA BIBLIOTECA HARVEY.
Não invente acórdão, ementa nem número de RR, AIRR ou ARR.
Se um número CNJ de processo já estiver no extrato, pode repeti-lo e dizer que a fonte é a Pesquisa de Jurisprudência do TST.
Súmula cancelada no Livro do TST não serve de fundamento vigente.
Inclua linha sobre dedução/compensação de valores já pagos se houver condenação de verbas rescisórias ou intervalo, usando a Súmula 18 apenas no texto oficial da biblioteca.
"""


def prompt_recurso(meta: dict, texto: str) -> str:
    return f"""Redija RECURSO ORDINÁRIO completo pela RECLAMADA, pronto para protocolar no PJe.

Capa:
{meta}

Inventário de comprovantes detectados:
{meta.get('paginas_pagamento', [])}

Autos extraídos (sentença e comprovantes vêm primeiro):
{texto}

{AUDITORIA_BLOCK}

Instruções:
- Recorra só dos capítulos em que a reclamada sucumbiu.
- Para CADA verba condenada (férias, 13º, intervalo, horas extras, FGTS, danos morais, aviso): verifique se há recibo/TRCT/holerite nos autos; se sim, peça reforma para excluir ou deduzir o já pago.
- Peça expressamente dedução/compensação na liquidação (art. 368 CC; Súmula 18 TST quando aplicável).
- Não reabra teses já ganhas, salvo para reforçar ausência de falta grave.
- Use tempestividade, cabimento, preparo, síntese, mérito e pedidos sucessivos/subsidiários.
- Se comprovante não estiver no extrato, use tese genérica de dedução "se comprovado nos autos" sem inventar valores.
"""


def prompt_defesa(meta: dict, texto: str) -> str:
    return f"""Redija CONTESTAÇÃO completa pela RECLAMADA (arts. 847 e 841 da CLT).

Capa:
{meta}

Documentos extraídos:
{texto}

Estruture: síntese, preliminares, impugnação de cada pedido, prova documental de pagamentos juntados, pedidos de improcedência.
Se houver holerites/TRCT no extrato, referencie-os na defesa.
"""


def prompt_contrarrazoes(meta: dict, texto: str) -> str:
    return f"""Redija CONTRARRAZÕES DE RECURSO ORDINÁRIO. Identifique quem recorreu e redija pelo recorrido.

Capa:
{meta}

Autos:
{texto}

{AUDITORIA_BLOCK}
"""


def prompt_replica(meta: dict, texto: str) -> str:
    return f"""Redija RÉPLICA À CONTESTAÇÃO pelo RECLAMANTE (art. 350, CPC c/c CLT).

Capa:
{meta}

Autos:
{texto}

Impugne ponto a ponto a defesa, reforce prova documental e oral, e mantenha coerência com a inicial.
"""


def prompt_alegacoes_finais(meta: dict, texto: str) -> str:
    return f"""Redija ALEGAÇÕES FINAIS (memoriais) pela RECLAMADA, com base na instrução processual.

Capa:
{meta}

Autos:
{texto}

{AUDITORIA_BLOCK}

Sintetize prova produzida, ataque teses do autor e reforce pedidos de improcedência ou redução de condenação.
"""


def prompt_embargos(meta: dict, texto: str) -> str:
    return f"""Redija EMBARGOS DE DECLARAÇÃO pela RECLAMADA (arts. 1.022 e 1.023, CPC).

Capa:
{meta}

Autos:
{texto}

Aponte omissão, contradição, obscuridade ou erro material na decisão embargada. Não rediscuta mérito sem vício.
"""


def prompt_impugnacao_laudo(meta: dict, texto: str) -> str:
    return f"""Redija IMPUGNAÇÃO AO LAUDO PERICIAL pela RECLAMADA.

Capa:
{meta}

Autos (priorize laudo e quesitos):
{texto}

Ataque metodologia, conclusões e quesitos não respondidos. Peça esclarecimentos ou novo laudo se cabível.
"""


def prompt_impugnacao_calculos(meta: dict, texto: str) -> str:
    return f"""Redija IMPUGNAÇÃO AOS CÁLCULOS / LIQUIDAÇÃO DE SENTENÇA pela RECLAMADA.

Capa:
{meta}

Autos:
{texto}

{AUDITORIA_BLOCK}

Confronte cada rubrica com TRCT, holerites, recibos e FGTS nos autos. Peça dedução/compensação do já pago.
"""


def prompt_manifestacao(meta: dict, texto: str) -> str:
    return f"""Redija MANIFESTAÇÃO processual pela RECLAMADA sobre o que constar nos autos (despacho, laudo, petição da parte contrária).

Capa:
{meta}

Autos:
{texto}

Seja objetivo: fatos, direito, pedidos.
"""


def prompt_acordo(meta: dict, texto: str) -> str:
    return f"""Elabore MINUTA DE ACORDO trabalhista entre as partes, com cláusulas de quitação, prazo, multa e homologação.

Capa:
{meta}

Contexto dos autos:
{texto}

Use valores e pedidos apenas se constarem do extrato; demais campos deixe entre colchetes [PREENCHER].
"""


def prompt_tutela(meta: dict, texto: str) -> str:
    return f"""Redija pedido de TUTELA DE URGÊNCIA pelo lado escolhido no roteiro.

Requisitos do art. 300 do CPC, usados no processo do trabalho: probabilidade do direito e perigo de dano ou risco ao resultado útil. Só descreva fato que esteja nos autos. Se o perigo ou o direito não constar do extrato, escreva "NÃO CONSTA DO EXTRATO LIDO" nesse ponto e não invente liminar já deferida.

Capa:
{meta}

Autos:
{texto}
"""


def prompt_execucao(meta: dict, texto: str) -> str:
    return f"""Redija petição de EXECUÇÃO / CUMPRIMENTO DE SENTENÇA pelo lado escolhido no roteiro.

Use só o título que estiver no extrato (sentença, acordo ou cálculos). Não invente valor, rubrica nem conta. O que não estiver nos autos fica como [PREENCHER] e com a frase "NÃO CONSTA DO EXTRATO LIDO".

Capa:
{meta}

Autos:
{texto}

{AUDITORIA_BLOCK}
"""


def prompt_embargos_execucao(meta: dict, texto: str) -> str:
    return f"""Redija EMBARGOS À EXECUÇÃO pelo lado escolhido no roteiro, no prazo do art. 884 da CLT.

Impugne excesso de execução só com comprovante, sentença ou cálculo que esteja no extrato. Peça dedução do que já foi pago. Não invente garantia do juízo nem penhora.

Capa:
{meta}

Autos:
{texto}

{AUDITORIA_BLOCK}
"""


def prompt_agravo_peticao(meta: dict, texto: str) -> str:
    return f"""Redija AGRAVO DE PETIÇÃO (art. 897, "a", da CLT) pelo lado escolhido no roteiro, contra decisão na execução.

Delimite a matéria e as alterações pedidas. Não reabra o que a sentença de conhecimento já julgou, salvo se o extrato mostrar que isso ainda está em discussão. Se a decisão agravada não estiver no extrato, escreva "NÃO CONSTA DO EXTRATO LIDO" e não invente o teor.

Capa:
{meta}

Autos:
{texto}

{AUDITORIA_BLOCK}
"""


def prompt_agravo_instrumento(meta: dict, texto: str) -> str:
    return f"""Redija AGRAVO DE INSTRUMENTO pelo lado escolhido no roteiro.

Se a área for trabalhista, é o agravo do art. 897, "b", da CLT: decisão que nega seguimento a recurso. Não use o rol do art. 1.015 do CPC quando os autos forem de reclamação trabalhista. Se a decisão que trancou o recurso não estiver no extrato, escreva "NÃO CONSTA DO EXTRATO LIDO" e não invente o despacho.

Capa:
{meta}

Autos:
{texto}
"""


def prompt_revista(meta: dict, texto: str) -> str:
    return f"""Redija RECURSO DE REVISTA (art. 896 da CLT) pelo lado escolhido no roteiro.

Só cabe se houver acórdão de Tribunal Regional no extrato. Se não houver, diga isso logo no início e não escreva a revista como se o acórdão existisse. Não invente súmula, precedente nem transcrição. Súmula só com o enunciado da biblioteca anexada.

Capa:
{meta}

Autos:
{texto}
"""


def prompt_quesitos(meta: dict, texto: str) -> str:
    return f"""Redija QUESITOS ao perito pelo lado escolhido no roteiro.

Lista objetiva, numerada, só sobre ponto que já esteja nos autos (função, local, agente, documento, laudo). Não invente medição, EPI nem conclusão técnica. Onde faltar o fato, escreva "NÃO CONSTA DO EXTRATO LIDO".

Capa:
{meta}

Autos:
{texto}
"""


def prompt_peticao(meta: dict, texto: str) -> str:
    return f"""Redija PETIÇÃO INTERMEDIÁRIA pela RECLAMADA (juntada, manifestação, requerimento de prova, etc.) conforme o estágio do processo nos autos.

Capa:
{meta}

Autos:
{texto}
"""


def prompt_personalizado(meta: dict, texto: str, instrucoes: str) -> str:
    return f"""O advogado pediu o seguinte (SIGA À RISCA, sem inventar fatos fora dos autos):

{instrucoes}

Dados da capa:
{meta}

Inventário de comprovantes (se houver):
{meta.get('paginas_pagamento', [])}

Texto extraído dos autos (sentença e comprovantes priorizados):
{texto}

{AUDITORIA_BLOCK}
"""


def append_instrucoes(prompt: str, instrucoes: str | None) -> str:
    extra = (instrucoes or "").strip()
    out = prompt
    if extra:
        out = (
            out
            + "\n\n--- INSTRUÇÕES ADICIONAIS DO ADVOGADO (prioridade sobre o modelo) ---\n"
            + extra
            + "\n"
        )
    return out + "\n" + CHECKLIST_HINT
