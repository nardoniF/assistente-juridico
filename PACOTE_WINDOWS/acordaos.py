"""Acórdão citado na peça: lê a ementa na pesquisa pública do TST e devolve o link.

Não há biblioteca local de decisões. Se o número não voltar, a peça não ganha ementa.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request

TST_API = "https://jurisprudencia-backend.tst.jus.br/rest/pesquisa-textual/1/2"
TST_BUSCA = "https://jurisprudencia.tst.jus.br/"
CNJ_RE = re.compile(
    r"(?<!\d)(\d{1,7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})(?!\d)"
)
CLASSE_RE = re.compile(
    r"ac[oó]rd[aã]o|ementa|\b(?:AIRR|RRAg|ARR|Ag-RR|ED-RR|RR|RO)\b",
    re.I,
)
_PERTO = 80
_CACHE: dict[str, dict] = {}


def _cnj(partes: tuple[str, ...]) -> str:
    numero, digito, ano, orgao, tribunal, vara = partes
    return f"{int(numero):07d}-{digito}.{ano}.{orgao}.{tribunal}.{vara}"


def regiao_trt(tribunal: str) -> str:
    n = int(tribunal)
    if n < 1 or n > 24:
        return "TRT"
    return f"TRT da {n}ª Região"


def fonte_tst(partes: tuple[str, ...]) -> str:
    numero, digito, ano, _orgao, tribunal, vara = partes
    return (
        f"{TST_BUSCA}?tipoJuris=ACORDAO&orgao=TST"
        f"&numProc={int(numero)}&digProc={digito}&anoProc={ano}"
        f"&numTribunal={int(tribunal)}&numVara={int(vara)}"
    )


def _distancia(a_ini: int, a_fim: int, b_ini: int, b_fim: int) -> int:
    if a_fim <= b_ini:
        return b_ini - a_fim
    if b_fim <= a_ini:
        return a_ini - b_fim
    return 0


def extrair(texto: str) -> list[tuple[str, ...]]:
    bruto = texto or ""
    cnjs = [m for m in CNJ_RE.finditer(bruto) if m.group(4) == "5"]
    marcas = list(CLASSE_RE.finditer(bruto))
    escolhidos: dict[int, tuple[str, ...]] = {}
    for marca in marcas:
        melhor = None
        melhor_dist = _PERTO + 1
        for cnj in cnjs:
            dist = _distancia(marca.start(), marca.end(), cnj.start(), cnj.end())
            if dist < melhor_dist:
                melhor = cnj
                melhor_dist = dist
        if melhor is None:
            continue
        escolhidos[melhor.start()] = melhor.groups()
    vistos: list[tuple[str, ...]] = []
    chaves = set()
    for partes in escolhidos.values():
        chave = _cnj(partes)
        if chave in chaves:
            continue
        chaves.add(chave)
        vistos.append(partes)
        if len(vistos) == 3:
            break
    return vistos


def _limpo(bruto: str, limite: int = 480) -> str:
    texto = re.sub(r"(?is)<script.*?>.*?</script>", " ", bruto or "")
    texto = re.sub(r"(?is)<style.*?>.*?</style>", " ", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0]
    return corte + "…"


def _data(iso: str) -> str:
    if not iso or len(iso) < 10 or iso[4] != "-":
        return iso or ""
    ano, mes, dia = iso[:10].split("-")
    return f"{dia}/{mes}/{ano}"


def _consultar(partes: tuple[str, ...]) -> dict:
    numero, digito, ano, orgao, tribunal, vara = partes
    corpo = {
        "ou": "",
        "e": "",
        "termoExato": "",
        "naoContem": "",
        "ementa": "",
        "dispositivo": "",
        "numeracaoUnica": {
            "numero": str(int(numero)),
            "digito": str(int(digito)),
            "ano": ano,
            "orgao": orgao,
            "tribunal": str(int(tribunal)),
            "vara": str(int(vara)),
        },
        "tipos": ["ACORDAO"],
        "orgao": "TST",
        "ordenacao": "data",
    }
    pedido = urllib.request.Request(
        TST_API,
        data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(pedido, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _card(partes: tuple[str, ...], registro: dict, total: int) -> dict:
    orgao = registro.get("orgaoJudicante") or {}
    ementa = _limpo(registro.get("ementa") or "")
    return {
        "numero": _cnj(partes),
        "rotulo": registro.get("numFormatado") or _cnj(partes),
        "relator": registro.get("nomRelatorSemTratamento") or "",
        "turma": orgao.get("descricao") or "TST",
        "julgamento": _data(registro.get("dtaJulgamento") or ""),
        "publicacao": _data(registro.get("dtaPublicacao") or ""),
        "ementa": ementa,
        "fonte": fonte_tst(partes),
        "total": total,
    }


def conferir(texto: str) -> dict:
    partes_lista = extrair(texto)
    encontrados: list[dict] = []
    ausentes: list[dict] = []
    avisos: list[str] = []
    if not partes_lista and CLASSE_RE.search(texto or ""):
        avisos.append(
            "A peça cita RR ou AIRR sem o número CNJ completo. Sem esse número a fonte do TST não abre."
        )
    for partes in partes_lista:
        chave = _cnj(partes)
        fonte = fonte_tst(partes)
        if chave in _CACHE:
            pacote = _CACHE[chave]
        else:
            try:
                pacote = _consultar(partes)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                ausentes.append(
                    {
                        "numero": chave,
                        "fonte": fonte,
                        "motivo": "A pesquisa do TST não respondeu. Abra o link e confira o número.",
                    }
                )
                continue
            _CACHE[chave] = pacote
        registros = pacote.get("registros") or []
        total = int(pacote.get("totalRegistros") or 0)
        if not registros or total <= 0:
            ausentes.append(
                {
                    "numero": chave,
                    "fonte": fonte,
                    "motivo": (
                        "Este número não voltou na pesquisa de acórdãos do TST. "
                        f"Se for decisão do {regiao_trt(partes[4])}, a ementa tem de ser lida no site desse tribunal."
                    ),
                }
            )
            continue
        for item in registros[:2]:
            registro = item.get("registro") or item
            ementa = _limpo(registro.get("ementa") or "")
            if not ementa:
                continue
            encontrados.append(_card(partes, registro, total))
        if not any(c["numero"] == chave for c in encontrados):
            ausentes.append(
                {
                    "numero": chave,
                    "fonte": fonte,
                    "motivo": "O TST devolveu o processo, mas sem ementa legível. Abra a fonte.",
                }
            )
    return {"encontrados": encontrados, "ausentes": ausentes, "avisos": avisos}
