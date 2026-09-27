from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from organizer import HOME_APP, ensure_dirs

PROMPTS_CASE = "prompts_caso.json"
ULTIMA = "ultima_geracao.json"
GLOBAL_FILE = HOME_APP / "aprendizado_global.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _empty_case() -> dict:
    return {"geral": [], "por_tipo": {}, "historico": []}


def load_case_prompts(case: Path) -> dict:
    path = case / PROMPTS_CASE
    if not path.exists():
        return _empty_case()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_case()
    data.setdefault("geral", [])
    data.setdefault("por_tipo", {})
    data.setdefault("historico", [])
    return data


def save_case_prompts(case: Path, data: dict) -> None:
    (case / PROMPTS_CASE).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_global() -> dict:
    ensure_dirs()
    if not GLOBAL_FILE.exists():
        return {"por_tipo": {}}
    try:
        data = json.loads(GLOBAL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"por_tipo": {}}
    data.setdefault("por_tipo", {})
    return data


def save_global(data: dict) -> None:
    ensure_dirs()
    GLOBAL_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_learning(
    case: Path,
    tipo: str,
    texto: str,
    *,
    also_global: bool = True,
) -> dict:
    """Guarda feedback do advogado no processo e, se quiser, no aprendizado global."""
    texto = (texto or "").strip()
    if not texto:
        return load_case_prompts(case)

    case_data = load_case_prompts(case)
    entry = {"quando": _now(), "tipo": tipo, "texto": texto}
    case_data["historico"].append(entry)
    case_data["geral"].append(texto)
    por = case_data["por_tipo"].setdefault(tipo, [])
    if texto not in por:
        por.append(texto)
    # evita lista geral infinita duplicada
    case_data["geral"] = list(dict.fromkeys(case_data["geral"]))[-40:]
    save_case_prompts(case, case_data)

    if also_global:
        g = load_global()
        lista = g["por_tipo"].setdefault(tipo, [])
        if texto not in lista:
            lista.append(texto)
        g["por_tipo"][tipo] = lista[-30:]
        save_global(g)

    return case_data


def combined_instructions(case: Path, tipo: str, extra: str = "") -> str:
    """Monta instruções: aprendizado global do tipo + prompts do processo + campo livre."""
    parts: list[str] = []
    g = load_global()
    for item in g.get("por_tipo", {}).get(tipo) or []:
        parts.append(item)
    case_data = load_case_prompts(case)
    for item in case_data.get("geral") or []:
        parts.append(item)
    for item in (case_data.get("por_tipo") or {}).get(tipo) or []:
        parts.append(item)
    if extra and extra.strip():
        parts.append(extra.strip())
    # dedupe preservando ordem
    seen = set()
    uniq = []
    for p in parts:
        p = p.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return "\n".join(f"- {u}" for u in uniq)


def save_ultima(case: Path, payload: dict) -> None:
    (case / ULTIMA).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_ultima(case: Path) -> dict | None:
    path = case / ULTIMA
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


ESTADO = "pecas_estado.json"


def load_estado(case: Path) -> dict:
    path = case / ESTADO
    if not path.exists():
        return {"aberta": None, "tipos": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"aberta": None, "tipos": {}}
    data.setdefault("aberta", None)
    data.setdefault("tipos", {})
    return data


def save_estado(case: Path, data: dict) -> None:
    (case / ESTADO).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def registrar_peca_aberta(case: Path, payload: dict) -> None:
    """A peça gerada ou refinada fica aberta até a advogada fechar."""
    estado = load_estado(case)
    tipo = payload.get("tipo") or "personalizado"
    estado["tipos"][tipo] = {
        "tipo": tipo,
        "titulo": payload.get("titulo") or tipo,
        "base": payload.get("base"),
        "docx": payload.get("docx"),
        "pdf": payload.get("pdf"),
        "texto": payload.get("texto") or "",
        "fechada": False,
        "refines": payload.get("refines") or 0,
    }
    estado["aberta"] = tipo
    save_estado(case, estado)


def estado_publico(case: Path) -> dict:
    estado = load_estado(case)
    tipos = {}
    for tipo, info in (estado.get("tipos") or {}).items():
        tipos[tipo] = {
            "tipo": tipo,
            "titulo": info.get("titulo") or tipo,
            "docx": info.get("docx"),
            "pdf": info.get("pdf"),
            "pje_pdf": info.get("pje_pdf") or "",
            "fechada": bool(info.get("fechada")),
            "refines": info.get("refines") or 0,
        }
    return {"aberta": estado.get("aberta"), "tipos": tipos}


def fechar_peca(case: Path) -> dict:
    import docx_out

    estado = load_estado(case)
    tipo = estado.get("aberta")
    if not tipo or tipo not in estado["tipos"]:
        raise ValueError("Não há peça aberta para fechar.")
    info = estado["tipos"][tipo]
    numero = ""
    meta_path = case / "meta.json"
    if meta_path.exists():
        try:
            numero = (json.loads(meta_path.read_text(encoding="utf-8")).get("numero") or "").strip()
        except Exception:
            numero = ""
    try:
        docx_out.publicar_pdf_pje(case, info, numero)
    except FileNotFoundError as e:
        raise ValueError(str(e)) from e
    info["fechada"] = True
    estado["aberta"] = None
    save_estado(case, estado)
    return estado_publico(case)


def reabrir_peca(case: Path, tipo: str) -> dict:
    estado = load_estado(case)
    if estado.get("aberta"):
        aberta = estado["tipos"].get(estado["aberta"]) or {}
        raise ValueError(
            f"Feche “{aberta.get('titulo') or estado['aberta']}” antes de reabrir outra peça."
        )
    info = (estado.get("tipos") or {}).get(tipo)
    if not info:
        raise ValueError("Essa ação ainda não tem peça neste processo.")
    info["fechada"] = False
    estado["aberta"] = tipo
    save_estado(case, estado)
    save_ultima(
        case,
        {
            "tipo": tipo,
            "titulo": info.get("titulo") or tipo,
            "texto": info.get("texto") or "",
            "base": info.get("base"),
            "docx": info.get("docx"),
            "pdf": info.get("pdf"),
            "fechada": False,
            "refines": info.get("refines") or 0,
        },
    )
    return estado_publico(case)


def auditar(case: Path, usuario: str, acao: str, detalhe: str = "") -> None:
    line = json.dumps(
        {
            "quando": _now(),
            "usuario": usuario or "local",
            "acao": acao,
            "detalhe": (detalhe or "")[:300],
        },
        ensure_ascii=False,
    )
    with (case / "auditoria.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
