"""Acórdão citado na peça: lê a ementa na pesquisa pública do TST.

Se o TST não devolver o número, tenta a pesquisa nacional da Justiça do Trabalho
(Falcão, jurisprudencia.jt.jus.br). A ementa só entra se a resposta trouxer o texto.
"""
from __future__ import annotations

import html
import json
import re
import secrets
import string
import urllib.error
import urllib.parse
import urllib.request

TST_API = "https://jurisprudencia-backend.tst.jus.br/rest/pesquisa-textual/1/2"
TST_BUSCA = "https://jurisprudencia.tst.jus.br/"
FALCAO_API = "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/api/no-auth/pesquisa"
FALCAO_BUSCA = "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional/home"
_FALCAO_SID = "_" + "".join(
    secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7)
)
_FALCAO_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://jurisprudencia.jt.jus.br",
    "Referer": FALCAO_BUSCA,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:139.0) "
        "Gecko/20100101 Firefox/139.0"
    ),
}
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


def fonte_falcao(partes: tuple[str, ...]) -> str:
    return FALCAO_BUSCA + "?" + urllib.parse.urlencode({"texto": _cnj(partes)})


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


def _mesmo_processo(numero_doc: str, chave: str) -> bool:
    doc = re.sub(r"\D", "", numero_doc or "")
    alvo = re.sub(r"\D", "", chave or "")
    if len(doc) < 18 or len(alvo) < 18:
        return False
    return doc[-20:].zfill(20) == alvo[-20:].zfill(20)


def _texto_campo(valor) -> str:
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, dict):
        for chave in ("nome", "descricao", "nomeRelator", "sigla"):
            texto = valor.get(chave)
            if isinstance(texto, str) and texto.strip():
                return texto.strip()
    return ""


def _consultar_falcao(partes: tuple[str, ...]) -> tuple[list, int]:
    tribunal = f"TRT{int(partes[4])}"
    params = {
        "texto": _cnj(partes),
        "colecao": "acordaos",
        "sessionId": _FALCAO_SID,
        "page": 0,
        "size": 5,
        "tribunais": tribunal,
        "ordenacao": "mais_recente",
    }
    pedido = urllib.request.Request(
        FALCAO_API + "?" + urllib.parse.urlencode(params),
        headers=_FALCAO_HEADERS,
    )
    with urllib.request.urlopen(pedido, timeout=12) as resp:
        pacote = json.loads(resp.read().decode("utf-8"))
    docs = pacote.get("documentos") or []
    total = int(pacote.get("quantidadeTotal") or 0)
    return docs, total


def _card_trt(partes: tuple[str, ...], doc: dict, total: int) -> dict:
    tribunal = _texto_campo(doc.get("tribunal")) or regiao_trt(partes[4])
    turma = _texto_campo(doc.get("turma"))
    return {
        "numero": _cnj(partes),
        "rotulo": _texto_campo(doc.get("numeroProcesso")) or _cnj(partes),
        "relator": _texto_campo(doc.get("relator")),
        "turma": " · ".join(p for p in (tribunal, turma) if p),
        "julgamento": _data(_texto_campo(doc.get("dataJulgamento"))),
        "publicacao": _data(_texto_campo(doc.get("dataJuntada"))),
        "ementa": _limpo(doc.get("ementa") or ""),
        "fonte": fonte_falcao(partes),
        "total": total,
        "origem": "TRT",
    }


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
        "origem": "TST",
    }


def _ausente_trt(partes: tuple[str, ...], motivo: str) -> dict:
    return {
        "numero": _cnj(partes),
        "fonte": fonte_falcao(partes),
        "busca": "jt",
        "motivo": motivo,
    }


def _ler_trt(partes: tuple[str, ...]) -> tuple[list[dict], dict | None]:
    chave = _cnj(partes)
    cache = "falcao:" + chave
    if cache in _CACHE:
        docs, total = _CACHE[cache]
    else:
        try:
            docs, total = _consultar_falcao(partes)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            return [], _ausente_trt(
                partes,
                "O TST não devolveu este número e a pesquisa da Justiça do Trabalho não respondeu. Abra o link.",
            )
        _CACHE[cache] = (docs, total)
    cards = []
    for doc in docs:
        if not _mesmo_processo(str(doc.get("numeroProcesso") or ""), chave):
            continue
        if not _limpo(doc.get("ementa") or ""):
            continue
        cards.append(_card_trt(partes, doc, total))
        if len(cards) == 2:
            break
    if cards:
        return cards, None
    regiao = regiao_trt(partes[4])
    return [], _ausente_trt(
        partes,
        f"Este número não voltou no TST nem nos acórdãos do {regiao} "
        "na pesquisa nacional da Justiça do Trabalho. A ementa não foi inventada.",
    )


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
                cards, falta = _ler_trt(partes)
                encontrados.extend(cards)
                if falta:
                    ausentes.append(falta)
                continue
            _CACHE[chave] = pacote
        registros = pacote.get("registros") or []
        total = int(pacote.get("totalRegistros") or 0)
        if not registros or total <= 0:
            cards, falta = _ler_trt(partes)
            encontrados.extend(cards)
            if falta:
                ausentes.append(falta)
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
                    "busca": "tst",
                    "motivo": "O TST devolveu o processo, mas sem ementa legível. Abra a fonte.",
                }
            )
    return {"encontrados": encontrados, "ausentes": ausentes, "avisos": avisos}
