"""Conta de prazo em dias úteis. Lembrete para conferir no PJe, não certidão.

Base usada na conta, e só nela:
- art. 775 da CLT: dias úteis, exclui o dia do começo e inclui o do vencimento
- art. 220 do CPC: recesso de 20 de dezembro a 20 de janeiro, inclusive
- feriados nacionais fixos e a sexta-feira da Paixão (Lei 9.093/1995)
- Lei 11.419/2006, art. 5º, § 3º: se não houver consulta, a ciência ficta
  cai no 10º dia corrido depois do envio

Carnaval e Corpus Christi aparecem na resposta quando caem dentro do prazo,
mas não são descontados: muitos tribunais suspendem esses dias no calendário
próprio, e esta conta não tem esse calendário. Feriado municipal e estadual
também ficam de fora. Por isso o resultado manda conferir no PJe.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

TIPOS = {
    "recurso": (8, "Recurso ordinário", "art. 895 da CLT"),
    "embargos": (5, "Embargos de declaração", "art. 897-A da CLT"),
    "contrarrazoes": (8, "Contrarrazões", "art. 900 da CLT"),
    "agravo": (8, "Agravo de petição", "art. 897 da CLT"),
    "revista": (8, "Recurso de revista", "art. 896 da CLT"),
    "outro": (None, "Prazo informado", "contagem do art. 775 da CLT"),
}

AVISO = (
    "Confira no PJe. Carnaval e Corpus Christi, se caírem no intervalo, são listados "
    "e não são descontados. Feriado local e o calendário do tribunal não entram. "
    "Não certifica tempestividade."
)


def conferir_tribunal(inicio: date, fim: date) -> list[str]:
    """Datas que muitos TRTs suspendem e esta conta não pula."""
    avisos = []
    ano = inicio.year
    while ano <= fim.year:
        pascoa = _pascoa(ano)
        candidatos = (
            (pascoa - timedelta(days=48), "segunda de carnaval"),
            (pascoa - timedelta(days=47), "terça de carnaval"),
            (pascoa + timedelta(days=60), "Corpus Christi"),
        )
        for dia, nome in candidatos:
            if inicio < dia <= fim:
                avisos.append(f"{_br(dia)} ({nome}) não foi descontado — confira o calendário do TRT")
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


def dia_util(dia: date) -> bool:
    if dia.weekday() >= 5 or em_recesso(dia):
        return False
    return dia not in feriados_nacionais(dia.year)


def _br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def calcular(data_iso: str, modo: str, tipo: str, dias: int | None = None) -> dict:
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
        if dia_util(cursor):
            contados.append(cursor)
            if len(contados) == n:
                break
        else:
            motivo = "recesso 20/12–20/01" if em_recesso(cursor) else (
                "fim de semana" if cursor.weekday() >= 5 else "feriado nacional"
            )
            if len(pulados) < 12:
                pulados.append(f"{_br(cursor)} ({motivo})")
    else:
        raise ValueError("Não consegui fechar a contagem nesse intervalo.")

    vencimento = contados[-1]
    tribunal = conferir_tribunal(ciencia, vencimento)
    extra = (" " + " ".join(tribunal) + ".") if tribunal else ""
    resumo = (
        f"{nome}: {n} dias úteis ({fundamento}). {origem} "
        f"Vencimento calculado: {_br(vencimento)}.{extra} {AVISO}"
    )
    return {
        "ok": True,
        "tipo": tipo,
        "nome": nome,
        "dias": n,
        "fundamento": fundamento,
        "ciencia": ciencia.isoformat(),
        "vencimento": vencimento.isoformat(),
        "vencimento_br": _br(vencimento),
        "pulados": pulados,
        "conferir_tribunal": tribunal,
        "aviso": AVISO,
        "resumo": resumo,
    }
