from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from organizer import HOME_APP, ensure_dirs

PROMPTS_CASE = "prompts_caso.json"
ULTIMA = "ultima_geracao.json"
APRENDIZADO_TXT = "Aprendizado.txt"
GLOBAL_TXT = "Aprendizado_global.txt"
GLOBAL_FILE = HOME_APP / "aprendizado_global.json"
EXCLUSOES = HOME_APP / "exclusoes.jsonl"


def _uid_seguro(user_id: str) -> str:
    limpo = "".join(ch for ch in (user_id or "") if ch.isalnum() or ch in "-_")
    return limpo or "local"


def _pasta_global(user_id: str = "") -> Path:
    pasta = HOME_APP / "aprendizado" / _uid_seguro(user_id)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


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


def _ler_json(path: Path, vazio: dict) -> dict:
    if not path.exists():
        return dict(vazio)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(vazio)
    if not isinstance(data, dict):
        return dict(vazio)
    return data


def load_global(user_id: str = "") -> dict:
    ensure_dirs()
    path = _pasta_global(user_id) / "aprendizado_global.json"
    data = _ler_json(path, {"por_tipo": {}, "todos": []})
    if not data.get("por_tipo") and not data.get("todos") and GLOBAL_FILE.exists():
        data = _ler_json(GLOBAL_FILE, {"por_tipo": {}, "todos": []})
    data.setdefault("por_tipo", {})
    data.setdefault("todos", [])
    return data


def save_global(data: dict, user_id: str = "") -> None:
    ensure_dirs()
    path = _pasta_global(user_id) / "aprendizado_global.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _texto_caso(case: Path) -> str:
    geral = load_case_prompts(case).get("geral") or []
    linhas = ["APRENDIZADO DESTE PROCESSO", ""]
    if not geral:
        linhas.append("(nada gravado ainda)")
    else:
        linhas.extend(f"- {item}" for item in geral)
    return "\n".join(linhas) + "\n"


def _texto_global(user_id: str = "") -> str:
    g = load_global(user_id)
    linhas = [
        "APRENDIZADO GLOBAL",
        "Vale para os outros processos deste perfil.",
        "",
    ]
    todos = list(g.get("todos") or [])
    if not todos:
        for itens in (g.get("por_tipo") or {}).values():
            for item in itens or []:
                if item not in todos:
                    todos.append(item)
    if not todos:
        linhas.append("(nada gravado ainda)")
    else:
        linhas.extend(f"- {item}" for item in todos)
    return "\n".join(linhas) + "\n"


def escrever_aprendizado(case: Path, user_id: str = "") -> None:
    """Um arquivo legível na pasta do processo e outro na pasta global do perfil."""
    (case / APRENDIZADO_TXT).write_text(_texto_caso(case), encoding="utf-8")
    (_pasta_global(user_id) / GLOBAL_TXT).write_text(_texto_global(user_id), encoding="utf-8")


def caminho_global_txt(user_id: str = "") -> Path:
    path = _pasta_global(user_id) / GLOBAL_TXT
    if not path.exists():
        path.write_text(_texto_global(user_id), encoding="utf-8")
    return path


def append_learning(
    case: Path,
    tipo: str,
    texto: str,
    *,
    also_global: bool = True,
    user_id: str = "",
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
        g = load_global(user_id)
        lista = g["por_tipo"].setdefault(tipo, [])
        if texto not in lista:
            lista.append(texto)
        g["por_tipo"][tipo] = lista[-30:]
        todos = g.setdefault("todos", [])
        if texto not in todos:
            todos.append(texto)
        g["todos"] = todos[-40:]
        save_global(g, user_id)

    escrever_aprendizado(case, user_id)
    return case_data


def _limpar_itens(itens) -> list[str]:
    saida: list[str] = []
    for item in itens or []:
        texto = str(item or "").strip()
        if not texto or texto in saida or texto == "(nada gravado ainda)":
            continue
        saida.append(texto[:2000])
    return saida[-40:]


def _tirar(lista, texto: str) -> list:
    return [item for item in (lista or []) if item != texto]


def remover_aprendizado(case: Path, texto: str, *, onde: str, user_id: str = "") -> dict:
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Informe o que deve sair.")
    if onde in ("caso", "ambos"):
        data = load_case_prompts(case)
        data["geral"] = _tirar(data.get("geral") or [], texto)
        for tipo, itens in list((data.get("por_tipo") or {}).items()):
            data["por_tipo"][tipo] = _tirar(itens, texto)
        save_case_prompts(case, data)
    if onde in ("global", "ambos"):
        g = load_global(user_id)
        g["todos"] = _tirar(g.get("todos") or [], texto)
        for tipo, itens in list((g.get("por_tipo") or {}).items()):
            g["por_tipo"][tipo] = _tirar(itens, texto)
        save_global(g, user_id)
    escrever_aprendizado(case, user_id)
    return {"caso": load_case_prompts(case), "global": load_global(user_id)}


def restaurar_aprendizado(
    case: Path,
    caso_itens,
    global_itens,
    *,
    user_id: str = "",
    caso: bool = False,
    global_: bool = False,
) -> dict:
    """Recoloca listas que o navegador ou a pasta do Mac ainda têm."""
    if caso:
        data = load_case_prompts(case)
        limpos = _limpar_itens(caso_itens)
        data["geral"] = limpos
        data.setdefault("por_tipo", {})["geral"] = list(limpos)
        save_case_prompts(case, data)
    if global_:
        g = load_global(user_id)
        g["todos"] = _limpar_itens(global_itens)
        save_global(g, user_id)
    escrever_aprendizado(case, user_id)
    return {"caso": load_case_prompts(case), "global": load_global(user_id)}


def combined_instructions(case: Path, tipo: str, extra: str = "", user_id: str = "") -> str:
    """Monta instruções: aprendizado global do tipo + prompts do processo + campo livre."""
    parts: list[str] = []
    g = load_global(user_id)
    for item in g.get("todos") or []:
        parts.append(item)
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
    if not uniq:
        return ""
    return (
        "Estilo pedido pela advogada. Use só o jeito de escrever. "
        "Não copie fato, valor, folha, parte nem número de outro processo.\n"
        + "\n".join(f"- {u}" for u in uniq)
    )


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


CONVERSA = "conversa.json"


def load_conversa(case: Path) -> list:
    path = case / CONVERSA
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("texto")]


def gravar_conversa(case: Path, mensagens: list) -> list:
    corte = mensagens[-40:]
    (case / CONVERSA).write_text(json.dumps(corte, indent=2, ensure_ascii=False), encoding="utf-8")
    return corte


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


def registrar_exclusao(usuario: str, case_id: str, numero: str = "") -> None:
    """Fica fora da pasta do processo, porque a pasta é apagada em seguida."""
    ensure_dirs()
    line = json.dumps(
        {
            "quando": _now(),
            "usuario": usuario or "local",
            "processo": case_id,
            "numero": (numero or "")[:40],
        },
        ensure_ascii=False,
    )
    with EXCLUSOES.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def listar_exclusoes(limite: int = 20) -> list[dict]:
    if not EXCLUSOES.exists():
        return []
    linhas = []
    for line in EXCLUSOES.read_text(encoding="utf-8").splitlines()[-limite:]:
        try:
            linhas.append(json.loads(line))
        except Exception:
            continue
    return linhas


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
