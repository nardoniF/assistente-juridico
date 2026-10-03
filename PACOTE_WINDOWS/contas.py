"""Contas simples: cada advogada vê os próprios processos."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from organizer import HOME_APP, ensure_dirs

USERS = HOME_APP / "usuarios.json"
SESSIONS = HOME_APP / "sessoes.json"
CONVIDADOS = HOME_APP / "convidados.json"


def _load(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _save(path: Path, data) -> None:
    ensure_dirs()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _hash(senha: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), 120_000).hex()


def tem_usuarios() -> bool:
    return bool(_load(USERS, []))


def _acesso(user: dict, users: list) -> str:
    marcado = user.get("acesso")
    if marcado in ("dono", "cortesia", "avulso"):
        return marcado
    if users and users[0].get("id") == user.get("id"):
        return "dono"
    return "avulso"


def acesso(user_id: str) -> str:
    users = _load(USERS, [])
    found = next((u for u in users if u.get("id") == user_id), None)
    if not found:
        return "avulso"
    return _acesso(found, users)


def _convidado_por_nome(nome: str) -> dict | None:
    alvo = (nome or "").strip().lower()
    for item in _load(CONVIDADOS, []):
        if (item.get("nome") or "").strip().lower() == alvo:
            return item
    return None


def listar_convidados() -> list[dict]:
    saida = []
    for item in _load(CONVIDADOS, []):
        saida.append(
            {
                "id": item.get("id"),
                "nome": item.get("nome") or "",
                "nota": item.get("nota") or "",
                "desde": item.get("desde") or "",
                "entrou": bool(item.get("user_id")),
            }
        )
    return saida


def adicionar_convidado(nome: str, nota: str = "") -> dict:
    nome = (nome or "").strip()
    if len(nome) < 2:
        raise ValueError("Diga o nome do advogado convidado.")
    itens = _load(CONVIDADOS, [])
    if any((x.get("nome") or "").strip().lower() == nome.lower() for x in itens):
        raise ValueError("Esse nome já está na lista gratuita.")
    from datetime import datetime, timezone

    item = {
        "id": secrets.token_hex(4),
        "nome": nome,
        "nota": (nota or "").strip(),
        "desde": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "user_id": "",
    }
    itens.append(item)
    _save(CONVIDADOS, itens)
    users = _load(USERS, [])
    for user in users:
        if user.get("nome", "").strip().lower() == nome.lower() and _acesso(user, users) != "dono":
            user["acesso"] = "cortesia"
            item["user_id"] = user["id"]
            _save(USERS, users)
            _save(CONVIDADOS, itens)
            break
    return {"id": item["id"], "nome": item["nome"], "nota": item["nota"], "desde": item["desde"], "entrou": bool(item["user_id"])}


def remover_convidado(convidado_id: str) -> None:
    itens = _load(CONVIDADOS, [])
    alvo = next((x for x in itens if x.get("id") == convidado_id), None)
    if not alvo:
        raise ValueError("Convidado não encontrado.")
    if alvo.get("user_id"):
        users = _load(USERS, [])
        for user in users:
            if user.get("id") == alvo["user_id"] and user.get("acesso") == "cortesia":
                user["acesso"] = "avulso"
        _save(USERS, users)
    _save(CONVIDADOS, [x for x in itens if x.get("id") != convidado_id])


def _segredo() -> bytes:
    bruto = (
        os.environ.get("SESSION_SECRET")
        or os.environ.get("SITE_PASSWORD")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("API_KEY")
        or ""
    ).strip()
    return bruto.encode()


def _token_assinado(user: dict) -> str:
    corpo = json.dumps(
        {
            "id": user["id"],
            "nome": user["nome"],
            "exp": int(time.time()) + 60 * 60 * 24 * 120,
        },
        separators=(",", ":"),
    ).encode()
    sig = hmac.new(_segredo(), corpo, hashlib.sha256).hexdigest()
    bloco = base64.urlsafe_b64encode(corpo).decode().rstrip("=")
    return bloco + "." + sig


def _ler_token_assinado(token: str) -> dict | None:
    segredo = _segredo()
    if not segredo or "." not in (token or ""):
        return None
    bloco, sig = token.rsplit(".", 1)
    try:
        corpo = base64.urlsafe_b64decode(bloco + "=" * (-len(bloco) % 4))
    except Exception:
        return None
    esperado = hmac.new(segredo, corpo, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, esperado):
        return None
    try:
        data = json.loads(corpo.decode())
    except Exception:
        return None
    if int(data.get("exp") or 0) < int(time.time()):
        return None
    if not data.get("id"):
        return None
    return {"id": data["id"], "nome": data.get("nome") or ""}


def entrar(nome: str, senha: str, *, criar: bool = False) -> dict:
    nome = (nome or "").strip()
    senha = senha or ""
    if len(nome) < 2 or len(senha) < 4:
        raise ValueError("Nome e senha (mínimo 4 caracteres).")
    users = _load(USERS, [])
    found = next((u for u in users if u.get("nome", "").lower() == nome.lower()), None)
    if found:
        if _hash(senha, found["salt"]) != found["hash"]:
            raise ValueError("Senha incorreta.")
        user = found
    elif criar or not users:
        salt = secrets.token_hex(8)
        conv = _convidado_por_nome(nome)
        if not users:
            marcado = "dono"
        elif conv:
            marcado = "cortesia"
        else:
            marcado = "avulso"
        user = {
            "id": secrets.token_hex(8),
            "nome": nome,
            "salt": salt,
            "hash": _hash(senha, salt),
            "acesso": marcado,
        }
        users.append(user)
        _save(USERS, users)
        if conv and marcado == "cortesia":
            conv["user_id"] = user["id"]
            itens = _load(CONVIDADOS, [])
            for item in itens:
                if item.get("id") == conv.get("id"):
                    item["user_id"] = user["id"]
            _save(CONVIDADOS, itens)
    else:
        raise ValueError("Conta não encontrada. Peça para criar o acesso.")
    token = _token_assinado(user) if _segredo() else secrets.token_urlsafe(24)
    sessions = _load(SESSIONS, {})
    sessions[token] = {"id": user["id"], "nome": user["nome"]}
    _save(SESSIONS, sessions)
    return {
        "token": token,
        "id": user["id"],
        "nome": user["nome"],
        "acesso": _acesso(user, users),
    }


def sair(token: str) -> None:
    sessions = _load(SESSIONS, {})
    sessions.pop(token or "", None)
    _save(SESSIONS, sessions)


def user_from_request(request) -> dict | None:
    header = request.headers.get("authorization") or ""
    token = ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if not token:
        token = request.cookies.get("harvey_token") or ""
    if not token:
        return None
    sessions = _load(SESSIONS, {})
    achou = sessions.get(token)
    if achou:
        return achou
    return _ler_token_assinado(token)
