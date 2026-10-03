from __future__ import annotations

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
    r"RECLAMANTE|AUTOR(?:A)?|REQUERENTE|EXEQUENTE|APELANTE|"
    r"EMBARGANTE|AGRAVANTE|IMPETRANTE|POLO\s+ATIVO"
)
_PASSIVO = (
    r"RECLAMADO|R[ÉE]U|REQUERID[OA]|EXECUTAD[OA]|APELAD[OA]|"
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


MAX_OCR_PAGES = 120
OCR_SECONDS = 150
_OCR_BROKEN = False


def _rank_ocr(texts: list[str], candidatos: list[int]) -> list[int]:
    """Páginas-imagem perto de TRCT, holerite ou laudo passam na frente das primeiras do PDF."""

    def pontos(i: int) -> tuple[int, int]:
        janela = " ".join(texts[j] for j in range(max(0, i - 2), min(len(texts), i + 3)))
        u = _norm(janela)
        peso = 0
        if any(k in u for k in PAYMENT_KEYWORDS):
            peso += 10
        if any(k in u for k in ("LAUDO", "SENTENÇA", "SENTENCA")):
            peso += 4
        if len((texts[i] or "").strip()) < 20:
            peso += 1
        return (-peso, i)

    return sorted(candidatos, key=pontos)


def _needs_ocr(page: fitz.Page, text: str) -> bool:
    if len((text or "").strip()) >= 80:
        return False
    try:
        return bool(page.get_images(full=False))
    except Exception:
        return False


def _ocr_page(page: fitz.Page) -> str:
    """OCR de página escaneada (TRCT, holerite). Falha silencioso se não houver Tesseract."""
    global _OCR_BROKEN
    if _OCR_BROKEN:
        return ""
    try:
        tp = page.get_textpage_ocr(language="por+eng", dpi=140, full=True)
        return page.get_text(textpage=tp) or ""
    except Exception:
        _OCR_BROKEN = True
        return ""


def extract_process(pdf_path: Path, max_chars: int = 550_000) -> dict:
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

        ocr_puladas = 0
        inicio = time.monotonic()
        for n, i in enumerate(_rank_ocr(pages, candidatos)):
            if len(ocr_pages) >= MAX_OCR_PAGES:
                ocr_puladas = len(candidatos) - n
                break
            if ocr_pages and time.monotonic() - inicio > OCR_SECONDS:
                ocr_puladas = len(candidatos) - n
                break
            ocr = _ocr_page(doc[i])
            if _OCR_BROKEN:
                ocr_puladas = len(candidatos) - n
                break
            if ocr.strip():
                pages[i] = (pages[i] + "\n" + ocr).strip()
                ocr_pages.append(i + 1)
        ocr_pages.sort()

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

        wanted: set[int] = set()

        # Inicial (primeiras páginas)
        for i in range(min(35, len(pages))):
            wanted.add(i)

        # Sentença, contestação, ata: janela ao redor do índice
        for item in compact:
            p = item["page"] - 1
            span = 18 if item["tipo"] in ("SENTENÇA", "CONTESTAÇÃO", "ATA DE AUDIÊNCIA") else 12
            for j in range(max(0, p), min(len(pages), p + span)):
                wanted.add(j)

        # Todas as páginas com comprovante / pagamento / TRCT (varredura completa)
        payment_pages: list[dict] = []
        for i, (sc, hits) in enumerate(page_scores):
            if sc >= 3:
                wanted.add(i)
                # incluir vizinhas (recibo costuma ter 2–3 páginas)
                for j in range(max(0, i - 1), min(len(pages), i + 2)):
                    wanted.add(j)
                if hits:
                    payment_pages.append({"page": i + 1, "score": sc, "marcadores": hits[:12]})

        payment_pages.sort(key=lambda x: (-x["score"], x["page"]))

        # Montar blob por seções (prioridade documental)
        sections: list[str] = []

        inv = (
            "=== INVENTÁRIO DOCUMENTAL (varredura automática) ===\n"
            f"Total páginas PDF: {len(pages)}\n"
            f"Páginas com indício de pagamento/comprovante: {len(payment_pages)}\n"
            f"Páginas-imagem lidas por OCR: {len(ocr_pages)} de {len(candidatos)}\n"
        )
        if ocr_puladas:
            inv += f"Páginas-imagem ainda sem OCR nesta leitura: {ocr_puladas}\n"
        for p in payment_pages[:40]:
            inv += f"- Pág. {p['page']} (score {p['score']}): {', '.join(p['marcadores'][:6])}\n"
        sections.append(inv)

        # Sentença por último no PDF costuma estar no fim — garantir últimas páginas com "SENTENÇA"/DISPOSITIVO
        for i in range(max(0, len(pages) - 25), len(pages)):
            u = _norm(pages[i])
            if any(k in u for k in ("SENTENÇA", "DISPOSITIVO", "JULGO PROCEDENTE", "CONDENO")):
                for j in range(max(0, i - 2), min(len(pages), i + 15)):
                    wanted.add(j)

        def block(title: str, indices: list[int], limite: int) -> tuple[str, int]:
            parts = [f"\n\n=== {title} ===\n"]
            usados = 0
            entrou = 0
            for i in indices:
                pedaco = f"===== PAGINA {i + 1} =====\n{pages[i]}\n"
                if entrou and usados + len(pedaco) > limite:
                    break
                parts.append(pedaco)
                usados += len(pedaco)
                entrou += 1
            fora = max(0, len(indices) - entrou)
            if fora:
                parts.append(f"[{fora} página(s) desta camada ficaram de fora desta leitura.]\n")
            return "\n".join(parts), fora

        pay_idx = sorted({p["page"] - 1 for p in payment_pages})
        sent_idx = sorted(
            i
            for i in wanted
            if any(
                k in _norm(pages[i])
                for k in ("SENTENÇA", "DISPOSITIVO", "JULGO PROCEDENTE", "CONDENO", "DEFIRO")
            )
        )
        defesa_idx = sorted(
            i
            for i in wanted
            if "CONTESTAÇÃO" in _norm(pages[i][:500]) or (i in wanted and "CONTESTAÇÃO" in _norm(pages[i]))
        )
        oral_idx = sorted(i for i in wanted if "ATA DE AUDIÊNCIA" in _norm(pages[i][:400]))
        rest = sorted(wanted - set(pay_idx) - set(sent_idx) - set(defesa_idx) - set(oral_idx))

        fora_total = 0
        if sent_idx:
            trecho, fora = block("SENTENÇA / DISPOSITIVO (prioridade)", sent_idx[:80], 160_000)
            sections.append(trecho)
            fora_total += fora
        if pay_idx:
            trecho, fora = block(
                "COMPROVANTES — TRCT, RECIBOS, HOLERITES, FGTS, PONTO", pay_idx[:120], 160_000
            )
            sections.append(trecho)
            fora_total += fora
        if defesa_idx:
            trecho, fora = block("CONTESTAÇÃO E DOCUMENTOS DA RÉ", defesa_idx[:60], 70_000)
            sections.append(trecho)
            fora_total += fora
        if oral_idx:
            trecho, fora = block("PROVA ORAL — ATAS", oral_idx[:40], 40_000)
            sections.append(trecho)
            fora_total += fora
        trecho, fora = block("INICIAL E DEMAIS TRECHOS", rest[:100], 80_000)
        sections.append(trecho)
        fora_total += fora

        cruzamento = build_cruzamento(pages, sent_idx, pay_idx)
        sections.insert(1, cruzamento_texto(cruzamento))
        completar_partes(meta, pages)

        blob = "\n".join(sections)
        truncated = fora_total > 0
        if len(blob) > max_chars:
            blob = blob[:max_chars] + "\n\n[texto recortado — cada camada tem teto próprio]"
            truncated = True

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
                f"A leitura da IA reserva espaço separado para sentença, comprovante, defesa, ata e inicial. "
                f"Páginas de camada que ficaram de fora por tamanho: {fora_total}."
            ),
        }
        meta["extracao"] = {
            "paginas_selecionadas": len(wanted),
            "paginas_comprovante": len(pay_idx),
            "ocr_paginas": len(ocr_pages),
            "ocr_candidatas": len(candidatos),
            "ocr_puladas": ocr_puladas,
            "ocr_disponivel": not _OCR_BROKEN,
            "truncado": truncated,
            "versao": 7,
        }
        return {"meta": meta, "texto": blob, "paginas": doc.page_count}
    finally:
        doc.close()
