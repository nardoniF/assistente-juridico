from __future__ import annotations

import os
import re
import time
from pathlib import Path

import fitz

HEADING_HINTS = (
    "PETIÇÃO INICIAL",
    "RECLAMAÇÃO TRABALHISTA",
    "CONTESTAÇÃO",
    "RÉPLICA",
    "REPLICA À CONTESTAÇÃO",
    "ATA DE AUDIÊNCIA",
    "LAUDO",
    "LAUDO TÉCNICO PERICIAL",
    "SENTENÇA",
    "ACÓRDÃO",
    "RECURSO ORDINÁRIO",
    "CONTRARRAZÕES",
    "DESPACHO",
    "TRCT",
    "TERMO DE RESCISÃO",
    "RECIBO DE PAGAMENTO",
    "HOLERITE",
    "CONTRACHEQUE",
    "DEMONSTRATIVO DE PAGAMENTO",
)

# Páginas com estes termos entram com prioridade (comprovantes, folha, rescisão).
PAYMENT_KEYWORDS = (
    "TRCT",
    "TERMO DE RESCISÃO",
    "TERMO DE RESCISAO",
    "RECIBO DE PAGAMENTO",
    "RECIBO DE FÉRIAS",
    "RECIBO DE FERIAS",
    "HOLERITE",
    "CONTRACHEQUE",
    "DEMONSTRATIVO DE PAGAMENTO",
    "COMPROVANTE",
    "FÉRIAS GOZADAS",
    "FERIAS GOZADAS",
    "FÉRIAS PAGAS",
    "FERIAS PAGAS",
    "13º SALÁRIO",
    "13 SALARIO",
    "DÉCIMO TERCEIRO",
    "DECIMO TERCEIRO",
    "FGTS",
    "EXTRATO FGTS",
    "GUIA FGTS",
    "GRRF",
    "AVISO PRÉVIO",
    "AVISO PREVIO",
    "VALOR LÍQUIDO",
    "VALOR LIQUIDO",
    "TOTAL PAGO",
    "PAGAMENTO EFETUADO",
    "QUITADO",
    "RECIBO DE HORAS",
    "CARTÃO PONTO",
    "CARTAO PONTO",
    "CONTROLE DE JORNADA",
    "ROMANEIO",
    "DIÁRIA",
    "DIARIA",
    "INTERVALO INTRAJORNADA",
    "HORAS EXTRAS PAGAS",
    "COMPENSAÇÃO",
    "COMPENSACAO",
    "DEDUÇÃO",
    "DEDUCAO",
)

STRONG_DOC_MARKERS = (
    "TRCT",
    "TERMO DE RESCISÃO",
    "RECIBO DE PAGAMENTO",
    "HOLERITE",
    "CONTRACHEQUE",
    "DEMONSTRATIVO DE PAGAMENTO",
    "EXTRATO FGTS",
    "DISPOSITIVO",
    "JULGO PROCEDENTE",
    "JULGO IMPROCEDENTE",
    "CONDENO",
    "DEFIRO",
    "INDEFIRO",
)

VERBAS = (
    ("ferias", "Férias + 1/3", ("FÉRIAS", "FERIAS", "TERÇO CONSTITUCIONAL")),
    ("decimo", "13º salário", ("13º", "DECIMO TERCEIRO", "DÉCIMO TERCEIRO", "13 SAL")),
    ("intervalo", "Intervalo", ("INTERVALO", "INTRAJORNADA")),
    ("he", "Horas extras", ("HORAS EXTRAS", "HORA EXTRA")),
    ("fgts", "FGTS", ("FGTS", "GRRF")),
    ("aviso", "Aviso prévio", ("AVISO PRÉVIO", "AVISO PREVIO")),
    ("moral", "Danos morais", ("DANOS MORAIS", "DANO MORAL")),
)


def _hits(pages: list[str], indices: list[int], kws: tuple[str, ...]) -> list[int]:
    found = []
    for i in indices:
        if 0 <= i < len(pages) and any(k in _norm(pages[i]) for k in kws):
            found.append(i + 1)
    return found


def build_cruzamento(pages: list[str], sent_idx: list[int], pay_idx: list[int]) -> list[dict]:
    """Cruza palavras da sentença com comprovantes. Heurística — a advogada corrige."""
    rows = []
    for key, label, kws in VERBAS:
        folhas_sentenca = _hits(pages, sent_idx, kws)
        folhas_pago = _hits(pages, pay_idx, kws)
        condenado = "sim" if folhas_sentenca else "incerto"
        pago = "sim" if folhas_pago else "nao"
        if condenado == "sim" and pago == "sim":
            tese = "Possível bis in idem — pedir dedução/compensação"
        elif condenado == "sim":
            tese = "Condenação sem estas palavras nos comprovantes lidos"
        elif pago == "sim":
            tese = "Pagamento localizado; condenação não achada com estas palavras"
        else:
            tese = "Não localizado no extrato"
        rows.append(
            {
                "id": key,
                "verba": label,
                "condenado": condenado,
                "pago": pago,
                "folhas_sentenca": folhas_sentenca[:8],
                "folhas_pago": folhas_pago[:8],
                "tese": tese,
            }
        )
    return rows


def estrategia_acordo(rows: list[dict]) -> str:
    """Estratégia só com o cruzamento. Não prevê resultado nem sugere valor."""
    deduzir = []
    sem_prova = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        nome = r.get("verba") or "verba"
        if r.get("condenado") == "sim" and r.get("pago") == "sim":
            fls = ", ".join(str(n) for n in (r.get("folhas_pago") or [])[:4])
            deduzir.append(f"{nome} (fls. {fls or '—'})")
        elif r.get("condenado") == "sim":
            sem_prova.append(nome)
    partes = []
    if deduzir:
        partes.append(
            "Ponto de dedução ou de conversa de acordo, porque o extrato achou condenação e pagamento: "
            + "; ".join(deduzir)
            + "."
        )
    if sem_prova:
        partes.append(
            "Não tratar como pago, o extrato não achou comprovante com essas palavras: "
            + "; ".join(sem_prova)
            + "."
        )
    if not partes:
        partes.append("O extrato não mostrou verba condenada com pagamento localizado.")
    partes.append("Isto não prevê resultado nem sugere valor de acordo.")
    return " ".join(partes)


def cruzamento_texto(rows: list[dict]) -> str:
    lines = ["=== CRUZAMENTO COMPROVANTE × CONDENAÇÃO (heurística, conferir) ==="]
    for r in rows:
        fs = ", ".join(str(n) for n in r["folhas_sentenca"]) or "—"
        fp = ", ".join(str(n) for n in r["folhas_pago"]) or "—"
        lines.append(
            f"- {r['verba']}: condenado={r['condenado']} (fls. {fs}) | "
            f"pago={r['pago']} (fls. {fp}) | {r['tese']}"
        )
    return "\n".join(lines)


def _norm(s: str) -> str:
    return (s or "").upper()


def _score_page(text: str) -> tuple[int, list[str]]:
    u = _norm(text)
    hits = []
    score = 0
    for kw in PAYMENT_KEYWORDS:
        if kw in u:
            hits.append(kw)
            score += 3 if kw in STRONG_DOC_MARKERS else 1
    for hint in HEADING_HINTS:
        if hint in u[:1200]:
            hits.append(hint)
            score += 5
    if "DISPOSITIVO" in u or "JULGO PROCEDENTE" in u or "CONDENO" in u:
        score += 20
    return score, sorted(set(hits))


_ATIVO = (
    r"RECLAMANTE|AUTOR(?:A)?|REQUERENTE|REQTE|EXEQUENTE|EXEQTE|APELANTE|"
    r"EMBARGANTE|AGRAVANTE|IMPETRANTE|GENITORA?|POLO\s+ATIVO"
)
_PASSIVO = (
    r"RECLAMADO|R[ÉE]U|REQUERID[OA]|REQD[OA]|EXECUTAD[OA]|EXECTD[OA]|APELAD[OA]|"
    r"EMBARGAD[OA]|AGRAVAD[OA]|IMPETRAD[OA]|POLO\s+PASSIVO"
)


def _limpa_parte(texto: str) -> str:
    linha = (texto or "").split("\n")[0]
    linha = re.split(
        r"\b(?:ADVOGADO|ADVOGADA|ADV|CPF|CNPJ|OAB|PERITO)\b",
        linha,
        maxsplit=1,
        flags=re.I,
    )[0]
    linha = re.split(
        r",?\s+\b(?:representad[oa]|representante|rep\.\s*por|assistid[oa]|menor(?:\s+imp[uú]bere)?)\b",
        linha,
        maxsplit=1,
        flags=re.I,
    )[0]
    linha = re.sub(r"\s+", " ", linha).strip(" \t.;:-")
    if len(linha) > 80:
        return ""
    if re.fullmatch(
        r"(?:RECLAMANTE|RECLAMAD[OA]|AUTOR|AUTORA|R[ÉE]U|REQUERENTE|REQUERID[OA]|"
        r"EXEQUENTE|EXECUTAD[OA]|PARTE)",
        linha,
        flags=re.I,
    ):
        return ""
    if not _parece_nome(linha):
        return ""
    return linha


_LIGACOES = {"da", "de", "do", "das", "dos", "e", "di"}


def _parece_nome(linha: str) -> bool:
    """Nome de parte. Frase de lei, artigo ou pedido não entra."""
    if not linha or len(linha) > 80:
        return False
    baixo = linha.lower()
    if any(
        marca in baixo
        for marca in (
            " art.",
            " art ",
            "§",
            "cpc",
            "clt",
            "código",
            "codigo",
            "com base",
            "pressupost",
            "fls.",
            "folha",
            "não consta",
            "nao consta",
            "não identific",
            "nao identific",
        )
    ):
        return False
    if linha[:1].islower():
        return False
    palavras = linha.split()
    if not palavras or len(palavras) > 8:
        return False
    for palavra in palavras:
        nucleo = palavra.strip(".,;")
        if not nucleo:
            return False
        if nucleo.lower() in _LIGACOES:
            continue
        if not (nucleo[:1].isupper() or nucleo.isupper()):
            return False
    return True


def _acha_parte(blob: str, labels: str) -> str:
    padrao = rf"\b(?:{labels})(?:\s*/\s*(?:{labels}))*\s*[:\-]\s*(.+)"
    for m in re.finditer(padrao, blob or "", flags=re.I):
        nome = _limpa_parte(m.group(1))
        if nome:
            return nome
    for m in re.finditer(rf"\b(?:{labels})\s*\n+\s*(.+)", blob or "", flags=re.I):
        nome = _limpa_parte(m.group(1))
        if nome:
            return nome
    return ""


def partes_no_texto(texto: str) -> tuple[str, str]:
    """Nome curto depois de Exequente/Requerente e Executado/Requerido."""
    return _acha_parte(texto, _ATIVO), _acha_parte(texto, _PASSIVO)


def completar_partes(meta: dict, paginas: list[str]) -> None:
    if meta.get("reclamante") and meta.get("reclamado"):
        return
    blocos = []
    for i, trecho in enumerate(paginas):
        if i < 40 or re.search(
            r"EXEQUENTE|EXECUTAD|REQUERENTE|REQUERID|RECLAMANTE|RECLAMAD",
            trecho or "",
            flags=re.I,
        ):
            blocos.append(trecho)
    ativo, passivo = partes_no_texto("\n".join(blocos))
    if ativo and not meta.get("reclamante"):
        meta["reclamante"] = ativo
    if passivo and not meta.get("reclamado"):
        meta["reclamado"] = passivo


def extract_cover_meta(doc: fitz.Document) -> dict:
    paginas = [
        doc[i].get_text() or ""
        for i in range(min(3, doc.page_count))
    ]
    first = paginas[0] if paginas else ""
    md = doc.metadata or {}
    blob = "\n".join(paginas)
    if md.get("subject"):
        blob += "\n" + str(md["subject"])
    numero = ""
    m = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", blob)
    if m:
        numero = m.group(0)
    reclamante = _acha_parte(blob, _ATIVO)
    reclamado = _acha_parte(blob, _PASSIVO)
    valor = ""
    vm = re.search(r"Valor da causa:\s*R\$\s*([\d\.\,]+)", first)
    if vm:
        valor = vm.group(1)
    autuacao = ""
    am = re.search(r"Data da Autuação:\s*(\d{2}/\d{2}/\d{4})", first)
    if am:
        autuacao = am.group(1)
    return {
        "numero": numero,
        "reclamante": reclamante,
        "reclamado": reclamado,
        "valor_causa": valor,
        "autuacao": autuacao,
        "titulo": md.get("title") or "",
        "paginas": doc.page_count,
    }


MAX_OCR_PAGES = 800
# Página de texto entra sempre. Página-imagem só até este tempo; o que passar
# continua no texto (o que o PDF já tinha) e fica listada como sem OCR.
OCR_SECONDS = 900
_OCR_BROKEN = False


_OCR_ALTO = (
    "TRCT",
    "TERMO DE RESCISÃO",
    "TERMO DE RESCISAO",
    "HOLERITE",
    "CONTRACHEQUE",
    "RECIBO DE PAGAMENTO",
    "RECIBO DE FÉRIAS",
    "RECIBO DE FERIAS",
    "CARTÃO PONTO",
    "CARTAO PONTO",
    "EXTRATO FGTS",
    "GRRF",
)
_OCR_MEIO = ("LAUDO", "SENTENÇA", "SENTENCA")


def _rank_ocr(texts: list[str], candidatos: list[int]) -> list[int]:
    """Página-imagem perto de TRCT, holerite ou laudo passa na frente do restante do PDF."""
    if not candidatos:
        return []
    cand = set(candidatos)
    peso_pagina: dict[int, int] = {}
    for i, texto in enumerate(texts):
        if i in cand:
            continue
        u = _norm(texto)
        if any(k in u for k in _OCR_ALTO):
            peso_pagina[i] = 20
        elif any(k in u for k in _OCR_MEIO):
            peso_pagina[i] = 8

    def pontos(i: int) -> tuple[int, int, int]:
        peso, dist = 0, 99
        for d in range(1, 41):
            j = i - d
            if j < 0:
                break
            p = peso_pagina.get(j)
            if p:
                peso, dist = p, d
                break
        return (-peso, dist, i)

    return sorted(candidatos, key=pontos)


def _needs_ocr(page: fitz.Page, text: str) -> bool:
    # O PJe grava a assinatura eletrônica e o "Fls." em cima da imagem.
    # Isso passa de 80 caracteres e escondia o TRCT escaneado.
    if len((text or "").strip()) >= 400:
        return False
    try:
        return bool(page.get_images(full=False))
    except Exception:
        return False


def _tessdata() -> str | None:
    env = os.environ.get("TESSDATA_PREFIX") or ""
    if env and Path(env).is_dir():
        return env if env.endswith(("/", "\\")) else env + "/"
    for pasta in (
        "/usr/local/share/tessdata",
        "/opt/homebrew/share/tessdata",
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tessdata",
    ):
        if Path(pasta, "por.traineddata").exists() or Path(pasta, "eng.traineddata").exists():
            return pasta + "/"
    return None


def _ocr_page(page: fitz.Page) -> str:
    """OCR de página escaneada (TRCT, holerite). Falha silencioso se não houver Tesseract."""
    global _OCR_BROKEN
    if _OCR_BROKEN:
        return ""
    try:
        kwargs = {"language": "por+eng", "dpi": 140, "full": True}
        pasta = _tessdata()
        if pasta:
            kwargs["tessdata"] = pasta
        tp = page.get_textpage_ocr(**kwargs)
        return page.get_text(textpage=tp) or ""
    except Exception:
        _OCR_BROKEN = True
        return ""


def texto_integral(pages: list[str], sem_ocr: list[int] | None = None) -> str:
    """Todas as páginas, na ordem do PDF. Sem amostra e sem teto de caracteres."""
    faltam = list(sem_ocr or [])
    partes = [
        "=== AUTOS INTEIROS ===",
        (
            f"Total de páginas: {len(pages)}. "
            "Todas entram abaixo, na ordem do PDF. Não há recorte."
        ),
    ]
    if faltam:
        amostra = ", ".join(str(n) for n in faltam[:80])
        resto = "" if len(faltam) <= 80 else f" e mais {len(faltam) - 80}"
        partes.append(
            "Páginas-imagem sem OCR nesta leitura. O que não aparecer nelas não consta; "
            f"não invente: {amostra}{resto}."
        )
    partes.append("")
    for i, texto in enumerate(pages):
        partes.append(f"===== PAGINA {i + 1} =====")
        partes.append(texto or "")
    partes.append("===== FIM DOS AUTOS =====")
    return "\n".join(partes)


def extract_process(pdf_path: Path, max_chars: int = 550_000) -> dict:
    # max_chars ficou na assinatura antiga. A peça lê o processo inteiro.
    global _OCR_BROKEN
    _OCR_BROKEN = False
    doc = fitz.open(pdf_path)
    try:
        meta = extract_cover_meta(doc)
        pages: list[str] = []
        index: list[dict] = []
        page_scores: list[tuple[int, list[str]]] = []
        ocr_pages: list[int] = []
        candidatos: list[int] = []

        for i in range(doc.page_count):
            page = doc[i]
            t = page.get_text() or ""
            pages.append(t)
            if _needs_ocr(page, t):
                candidatos.append(i)

        sem_ocr: list[int] = []
        inicio = time.monotonic()
        ranked = _rank_ocr(pages, candidatos)
        for n, i in enumerate(ranked):
            if len(ocr_pages) >= MAX_OCR_PAGES or (
                ocr_pages and time.monotonic() - inicio > OCR_SECONDS
            ):
                sem_ocr = [p + 1 for p in ranked[n:]]
                break
            ocr = _ocr_page(doc[i])
            if _OCR_BROKEN:
                sem_ocr = [p + 1 for p in ranked[n:]]
                break
            if ocr.strip():
                pages[i] = (pages[i] + "\n" + ocr).strip()
                ocr_pages.append(i + 1)
        ocr_pages.sort()
        ocr_puladas = len(sem_ocr)

        for i, t in enumerate(pages):
            sc, hits = _score_page(t)
            page_scores.append((sc, hits))
            head = " ".join(t.split()[:40]).upper()
            for hint in HEADING_HINTS:
                if hint in head or hint in t[:800].upper():
                    index.append(
                        {
                            "page": i + 1,
                            "tipo": hint,
                            "marcadores": hits[:8],
                            "ocr": (i + 1) in ocr_pages,
                        }
                    )
                    break

        compact: list[dict] = []
        for item in index:
            if not compact or compact[-1]["tipo"] != item["tipo"]:
                compact.append(item)

        payment_pages: list[dict] = []
        for i, (sc, hits) in enumerate(page_scores):
            if sc >= 3 and hits:
                payment_pages.append({"page": i + 1, "score": sc, "marcadores": hits[:12]})
        payment_pages.sort(key=lambda x: (-x["score"], x["page"]))
        pay_idx = [p["page"] - 1 for p in payment_pages]
        sent_idx = [
            i
            for i, t in enumerate(pages)
            if any(
                k in _norm(t)
                for k in ("SENTENÇA", "DISPOSITIVO", "JULGO PROCEDENTE", "CONDENO", "DEFIRO")
            )
        ]

        inv = (
            "=== INVENTÁRIO DOCUMENTAL (varredura automática) ===\n"
            f"Total páginas PDF: {len(pages)}. A leitura seguinte contém todas, na ordem.\n"
            f"Páginas com indício de pagamento/comprovante: {len(payment_pages)}\n"
            f"Páginas-imagem lidas por OCR: {len(ocr_pages)} de {len(candidatos)}\n"
        )
        if sem_ocr:
            inv += (
                "Páginas-imagem ainda sem OCR nesta leitura: "
                + ", ".join(str(n) for n in sem_ocr[:60])
                + "\n"
            )
        for p in payment_pages[:40]:
            inv += f"- Pág. {p['page']} (score {p['score']}): {', '.join(p['marcadores'][:6])}\n"

        cruzamento = build_cruzamento(pages, sent_idx, pay_idx)
        completar_partes(meta, pages)
        blob = "\n".join(
            [inv, cruzamento_texto(cruzamento), texto_integral(pages, sem_ocr)]
        )
        truncated = bool(sem_ocr)

        meta["indice"] = compact
        meta["paginas_pagamento"] = payment_pages[:50]
        meta["ocr_paginas"] = ocr_pages
        meta["cruzamento"] = cruzamento
        meta["extrato"] = {
            "numero": meta.get("numero") or "",
            "reclamante": meta.get("reclamante") or "",
            "reclamado": meta.get("reclamado") or "",
            "valor_causa": meta.get("valor_causa") or "",
            "autuacao": meta.get("autuacao") or "",
            "verbas": cruzamento,
        }
        meta["camadas"] = {
            "capa": (pages[0] if pages else "")[:1600],
            "sentenca": "\n".join(pages[i][:500] for i in sent_idx[:6])[:2000],
            "provas": "\n".join(pages[i][:400] for i in pay_idx[:8])[:2000],
            "leitura": (
                f"PDF com {len(pages)} páginas. "
                "O texto enviado à IA contém todas, na ordem. "
                f"Páginas-imagem sem OCR: {ocr_puladas}."
            ),
        }
        meta["extracao"] = {
            "paginas_selecionadas": len(pages),
            "paginas_comprovante": len(pay_idx),
            "ocr_paginas": len(ocr_pages),
            "ocr_candidatas": len(candidatos),
            "ocr_puladas": ocr_puladas,
            "ocr_disponivel": not _OCR_BROKEN,
            "truncado": truncated,
            "versao": 10,
        }
        return {"meta": meta, "texto": blob, "paginas": doc.page_count}
    finally:
        doc.close()
