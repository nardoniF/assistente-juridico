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
5) Nunca ignore pagamentos documentados só porque a sentença condenou de novo."""

AUDITORIA_BLOCK = """
Formato obrigatório no início da resposta (antes da peça ou do resumo):

AUDITORIA DOCUMENTAL
| Item condenado/pedido | Pago nos autos? | Página/evidência | Tese (deduzir / excluir / não consta) |
(repetir linhas para férias, 13º, intervalo, horas extras, aviso, FGTS, danos morais, etc.)
"""


def prompt_resumo(meta: dict, texto: str) -> str:
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

Para cada tese existente nos autos, traga enunciado, súmula/OJ, precedente (sem inventar número) e utilidade para a RECLAMADA.
Inclua linha sobre dedução/compensação de valores já pagos se houver condenação de verbas rescisórias ou intervalo.
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
    if not extra:
        return prompt
    return (
        prompt
        + "\n\n--- INSTRUÇÕES ADICIONAIS DO ADVOGADO (prioridade sobre o modelo) ---\n"
        + extra
        + "\n"
    )
