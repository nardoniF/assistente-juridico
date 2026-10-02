"""Conta de prazo em dias úteis. Lembrete para conferir no PJe, não certidão.

Base usada na conta, e só nela:
- art. 775 da CLT: dias úteis, exclui o dia do começo e inclui o do vencimento
- art. 220 do CPC: recesso de 20 de dezembro a 20 de janeiro, inclusive
- feriados nacionais fixos e a sexta-feira da Paixão (Lei 9.093/1995)
- Lei 11.419/2006, art. 5º, § 3º: se não houver consulta, a ciência ficta
  cai no 10º dia corrido depois do envio
- Portaria GP nº 50/2025 do TRT-2, só para 2026: dias em que o expediente
  e os prazos ficam suspensos em toda a 2ª Região, mais os do município
  escolhido (Cotia ou São Paulo sede). Outro ano não inventa calendário.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

TIPOS = {
    "recurso": (8, "Recurso ordinário", "art. 895 da CLT"),
    "embargos": (5, "Embargos de declaração", "art. 897-A da CLT"),
    "contrarrazoes": (8, "Contrarrazões", "art. 900 da CLT"),
    "agravo": (8, "Agravo de petição", "art. 897, a, da CLT"),
    "agravo_instrumento": (8, "Agravo de instrumento", "art. 897, b, da CLT"),
    "revista": (8, "Recurso de revista", "art. 896 da CLT"),
    "embargos_execucao": (5, "Embargos à execução", "art. 884 da CLT"),
    "outro": (None, "Prazo informado", "contagem do art. 775 da CLT"),
}

COMARCAS = {
    "regional": "toda a 2ª Região",
    "cotia": "1ª Vara do Trabalho de Cotia",
    "saopaulo": "São Paulo (sede)",
}


def comarca_do_processo(meta: dict, texto: str) -> str:
    """Feriado municipal segue a vara escrita no PDF. Sem vara, vale a 2ª Região inteira."""
    blob = " ".join(
        [
            str((meta or {}).get("numero") or ""),
            str((meta or {}).get("titulo") or ""),
            (texto or "")[:8000],
        ]
    ).upper()
    if "COTIA" in blob:
        return "cotia"
    if (
        "VARA DO TRABALHO DE SÃO PAULO" in blob
        or "VARA DO TRABALHO DE SAO PAULO" in blob
        or "FORO DE SÃO PAULO" in blob
        or "FORO DE SAO PAULO" in blob
    ):
        return "saopaulo"
    return "regional"

# Portaria GP nº 50, de 2/10/2025, DEJT TRT-2 n. 4322, p. 2-3.
# Só os dias de 2026 que suspendem expediente na Segunda Região inteira,
# além de fim de semana, feriado nacional e recesso já contados à parte.
_TRT2_2026 = {
    date(2026, 2, 16): "carnaval (Portaria GP 50/2025, TRT-2)",
    date(2026, 2, 17): "terça de carnaval (Portaria GP 50/2025, TRT-2)",
    date(2026, 2, 18): "quarta de cinzas (Portaria GP 50/2025, TRT-2)",
    date(2026, 4, 1): "semana santa (Portaria GP 50/2025, TRT-2)",
    date(2026, 4, 2): "semana santa (Portaria GP 50/2025, TRT-2)",
    date(2026, 4, 20): "suspensão do expediente (Portaria GP 50/2025, TRT-2)",
    date(2026, 6, 5): "suspensão do expediente (Portaria GP 50/2025, TRT-2)",
    date(2026, 7, 9): "Data Magna do Estado de São Paulo (Portaria GP 50/2025, TRT-2)",
    date(2026, 7, 10): "suspensão do expediente (Portaria GP 50/2025, TRT-2)",
    date(2026, 8, 10): "antecipação do Dia da Instalação dos Cursos Jurídicos (Portaria GP 50/2025, TRT-2)",
    date(2026, 10, 30): "transferência do Dia do Servidor Público (Portaria GP 50/2025, TRT-2)",
    date(2026, 12, 7): "antecipação do Dia da Justiça (Portaria GP 50/2025, TRT-2)",
}
_COTIA_2026 = {
    date(2026, 6, 4): "Corpus Christi em Cotia (Portaria GP 50/2025)",
    date(2026, 9, 8): "feriado local de Cotia (Portaria GP 50/2025)",
}
_SAOPAULO_2026 = {
    date(2026, 6, 4): "Corpus Christi em São Paulo (Portaria GP 50/2025)",
}


def suspensoes_trt2(ano: int, comarca: str) -> dict[date, str]:
    if ano != 2026 or comarca not in COMARCAS:
        return {}
    dias = dict(_TRT2_2026)
    if comarca == "cotia":
        dias.update(_COTIA_2026)
    elif comarca == "saopaulo":
        dias.update(_SAOPAULO_2026)
    return dias


def aviso_contagem(comarca: str, anos: set[int]) -> str:
    unidade = COMARCAS.get(comarca, COMARCAS["cotia"])
    if 2026 in anos:
        return (
            f"Conta de 2026 com a Portaria GP nº 50/2025 do TRT-2 ({unidade}). "
            "Feriado de outro município e suspensão publicada depois não entram. "
            "Confira no PJe. Não certifica tempestividade."
        )
    return (
        "A portaria lida aqui é a GP nº 50/2025, só para 2026. "
        "Neste ano entram feriado nacional e o recesso de 20/12 a 20/01. "
        "Confira no PJe. Não certifica tempestividade."
    )


def conferir_tribunal(inicio: date, fim: date, comarca: str = "cotia") -> list[str]:
    """Carnaval ou Corpus Christi no intervalo que esta conta não pulou."""
    avisos = []
    ano = inicio.year
    while ano <= fim.year:
        pascoa = _pascoa(ano)
        suspensos = set(suspensoes_trt2(ano, comarca))
        candidatos = (
            (pascoa - timedelta(days=48), "segunda de carnaval"),
            (pascoa - timedelta(days=47), "terça de carnaval"),
            (pascoa + timedelta(days=60), "Corpus Christi"),
        )
        for dia, nome in candidatos:
            if not (inicio < dia <= fim) or dia in suspensos:
                continue
            if ano == 2026:
                avisos.append(
                    f"{_br(dia)} ({nome}) não está no calendário desta unidade "
                    "na Portaria GP 50/2025 — confira no PJe"
                )
            else:
                avisos.append(
                    f"{_br(dia)} ({nome}) não foi descontado — a portaria lida aqui é só a de 2026"
                )
        ano += 1
    return avisos


def _pascoa(ano: int) -> date:
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    pascoa = _pascoa(ano)
    return {
        date(ano, 1, 1),
        date(ano, 4, 21),
        date(ano, 5, 1),
        date(ano, 9, 7),
        date(ano, 10, 12),
        date(ano, 11, 2),
        date(ano, 11, 15),
        date(ano, 11, 20),
        date(ano, 12, 25),
        pascoa - timedelta(days=2),
    }


def em_recesso(dia: date) -> bool:
    return (dia.month == 12 and dia.day >= 20) or (dia.month == 1 and dia.day <= 20)


def dia_util(dia: date, comarca: str = "cotia") -> bool:
    if dia.weekday() >= 5 or em_recesso(dia):
        return False
    if dia in feriados_nacionais(dia.year):
        return False
    return dia not in suspensoes_trt2(dia.year, comarca)


def _motivo_pulo(dia: date, comarca: str) -> str:
    nome = suspensoes_trt2(dia.year, comarca).get(dia)
    if nome:
        return nome
    if em_recesso(dia):
        return "recesso 20/12–20/01"
    if dia.weekday() >= 5:
        return "fim de semana"
    if dia in feriados_nacionais(dia.year):
        return "feriado nacional"
    return "dia não útil"


def _br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def calcular(
    data_iso: str,
    modo: str,
    tipo: str,
    dias: int | None = None,
    comarca: str = "cotia",
) -> dict:
    if comarca not in COMARCAS:
        raise ValueError("Escolha o calendário: 2ª Região, Cotia ou São Paulo sede.")
    try:
        inicio = datetime.strptime((data_iso or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Informe a data no formato do calendário.")
    if tipo not in TIPOS:
        raise ValueError("Tipo de prazo desconhecido.")
    padrao, nome, fundamento = TIPOS[tipo]
    n = padrao if padrao is not None else int(dias or 0)
    if n < 1 or n > 60:
        raise ValueError("O prazo precisa ter de 1 a 60 dias úteis.")
    if modo not in ("ciencia", "envio"):
        raise ValueError("Diga se a data é a ciência ou o envio no PJe.")

    if modo == "envio":
        ciencia = inicio + timedelta(days=10)
        origem = f"Envio em {_br(inicio)}. Ciência ficta no 10º dia corrido: {_br(ciencia)}."
    else:
        ciencia = inicio
        origem = f"Ciência em {_br(ciencia)}."

    cursor = ciencia
    contados: list[date] = []
    pulados: list[str] = []
    for _ in range(500):
        cursor += timedelta(days=1)
        if dia_util(cursor, comarca):
            contados.append(cursor)
            if len(contados) == n:
                break
        else:
            if len(pulados) < 16:
                pulados.append(f"{_br(cursor)} ({_motivo_pulo(cursor, comarca)})")
    else:
        raise ValueError("Não consegui fechar a contagem nesse intervalo.")

    vencimento = contados[-1]
    anos = set(range(ciencia.year, vencimento.year + 1))
    aviso = aviso_contagem(comarca, anos)
    tribunal = conferir_tribunal(ciencia, vencimento, comarca)
    extra = (" " + " ".join(tribunal) + ".") if tribunal else ""
    resumo = (
        f"{nome}: {n} dias úteis ({fundamento}). {origem} "
        f"Vencimento calculado: {_br(vencimento)}.{extra} {aviso}"
    )
    return {
        "ok": True,
        "tipo": tipo,
        "nome": nome,
        "dias": n,
        "fundamento": fundamento,
        "comarca": comarca,
        "ciencia": ciencia.isoformat(),
        "vencimento": vencimento.isoformat(),
        "vencimento_br": _br(vencimento),
        "pulados": pulados,
        "conferir_tribunal": tribunal,
        "aviso": aviso,
        "resumo": resumo,
    }
