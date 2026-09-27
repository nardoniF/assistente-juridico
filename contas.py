"""Contas simples: cada advogada vê os próprios processos."""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from organizer import HOME_APP, ensure_dirs

USERS = HOME_APP / "usuarios.json"
SESSIONS = HOME_APP / "sessoes.json"


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
        user = {"id": secrets.token_hex(8), "nome": nome, "salt": salt, "hash": _hash(senha, salt)}
        users.append(user)
        _save(USERS, users)
    else:
        raise ValueError("Conta não encontrada. Peça para criar o acesso.")
    token = secrets.token_urlsafe(24)
    sessions = _load(SESSIONS, {})
    sessions[token] = {"id": user["id"], "nome": user["nome"]}
    _save(SESSIONS, sessions)
    return {"token": token, "id": user["id"], "nome": user["nome"]}


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
    return sessions.get(token)
