"""Contas simples: cada advogada vê os próprios processos."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from organizer import HOME_APP, ensure_dirs

USERS = HOME_APP / "usuarios.json"
SESSIONS = HOME_APP / "sessoes.json"
CONVIDADOS = HOME_APP / "convidados.json"
ACESSO_CFG = HOME_APP / "acesso_config.json"

# dono = administrador · free = gratuito sem prazo · pagante = teste de N dias (depois bloqueia)
_ACESSOS = ("dono", "free", "pagante")


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


def _agora() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse_iso(valor: str | None) -> datetime | None:
    bruto = (valor or "").strip()
    if not bruto:
        return None
    try:
        return datetime.fromisoformat(bruto)
    except Exception:
        return None


def load_acesso_config() -> dict:
    cfg = _load(ACESSO_CFG, {})
    try:
        dias = int(cfg.get("dias_teste") or 14)
    except (TypeError, ValueError):
        dias = 14
    dias = max(1, min(dias, 365))
    try:
        preco = float(cfg.get("preco_mensal") if cfg.get("preco_mensal") is not None else 39.9)
    except (TypeError, ValueError):
        preco = 39.9
    preco = max(5.0, min(preco, 9999.0))
    gateway = (cfg.get("gateway") or "mercadopago").strip().lower()
    # PIX/cartão: só Mercado Pago (mesmo da Sensor). Asaas/Stripe ficam fora deste fluxo.
    if gateway != "mercadopago":
        gateway = "mercadopago"
    ia_rec = (cfg.get("ia_recomendada") or "openai_mini").strip()
    if ia_rec not in ("openai_mini", "google_pro"):
        ia_rec = "openai_mini"
    return {
        "dias_teste": dias,
        "preco_mensal": round(preco, 2),
        "moeda": "BRL",
        "gateway": gateway,
        "ia_recomendada": ia_rec,
    }


def save_acesso_config(
    dias_teste=None,
    preco_mensal=None,
    gateway=None,
    ia_recomendada=None,
) -> dict:
    atual = load_acesso_config()
    if dias_teste is not None:
        try:
            dias = int(dias_teste)
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe quantos dias de teste o pagante tem.") from exc
        atual["dias_teste"] = max(1, min(dias, 365))
    if preco_mensal is not None:
        try:
            bruto = str(preco_mensal).strip().replace("R$", "").replace(" ", "").replace(",", ".")
            preco = float(bruto)
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe o preço mensal, por exemplo 39,90.") from exc
        atual["preco_mensal"] = round(max(5.0, min(preco, 9999.0)), 2)
    if gateway is not None:
        g = str(gateway).strip().lower()
        if g in ("asaas", "stripe"):
            raise ValueError(
                "PIX e cartão usam só Mercado Pago (Sensor Tattoo Fix). Asaas fica de fora neste produto."
            )
        if g != "mercadopago":
            raise ValueError("Gateway inválido. Use mercadopago.")
        atual["gateway"] = "mercadopago"
    if ia_recomendada is not None:
        ia = str(ia_recomendada).strip()
        if ia not in ("openai_mini", "google_pro"):
            raise ValueError("IA recomendada: openai_mini ou google_pro.")
        atual["ia_recomendada"] = ia
    atual["moeda"] = "BRL"
    _save(ACESSO_CFG, atual)
    return atual


def _normalizar_acesso(marcado: str | None, user: dict, users: list) -> str:
    if marcado == "dono":
        return "dono"
    if marcado in ("free", "cortesia"):
        return "free"
    if marcado in ("pagante", "avulso"):
        return "pagante"
    if users and users[0].get("id") == user.get("id"):
        return "dono"
    return "pagante"


def _acesso(user: dict, users: list) -> str:
    return _normalizar_acesso(user.get("acesso"), user, users)


def acesso(user_id: str) -> str:
    users = _load(USERS, [])
    found = next((u for u in users if u.get("id") == user_id), None)
    if not found:
        return "pagante"
    return _acesso(found, users)


def _teste_ate(user: dict) -> datetime | None:
    return _parse_iso(user.get("teste_ate") or "")


def situacao(user_id: str) -> dict:
    """Como está o acesso desta conta: livre, em teste ou expirado."""
    users = _usuarios()
    found = next((u for u in users if u.get("id") == user_id), None)
    if not found:
        return {
            "acesso": "pagante",
            "situacao": "expirado",
            "dias_restantes": 0,
            "teste_ate": "",
            "pode_usar": False,
            "motivo": "Conta não encontrada.",
        }
    nivel = _acesso(found, users)
    if nivel == "dono":
        return {
            "acesso": "dono",
            "situacao": "admin",
            "dias_restantes": None,
            "teste_ate": "",
            "pode_usar": True,
            "motivo": "",
        }
    if nivel == "free":
        return {
            "acesso": "free",
            "situacao": "gratuito",
            "dias_restantes": None,
            "teste_ate": "",
            "pode_usar": True,
            "motivo": "",
        }
    if found.get("pago"):
        return {
            "acesso": "pagante",
            "situacao": "pago",
            "dias_restantes": None,
            "teste_ate": found.get("teste_ate") or "",
            "pode_usar": True,
            "motivo": "",
        }
    ate = _teste_ate(found)
    if not ate and found.get("acesso") in ("avulso", "pagante", None, ""):
        # Conta antiga sem data de teste: abre um ciclo com o padrão do admin.
        _marcar_teste(found)
        if not found.get("criado_em"):
            found["criado_em"] = _iso(_agora())
        found["acesso"] = "pagante"
        _save(USERS, users)
        ate = _teste_ate(found)
    if not ate:
        return {
            "acesso": "pagante",
            "situacao": "expirado",
            "dias_restantes": 0,
            "teste_ate": "",
            "pode_usar": False,
            "motivo": "O período de teste acabou. Peça ao administrador para renovar ou marcar como pago.",
        }
    agora = _agora()
    if ate.tzinfo is None:
        ate = ate.replace(tzinfo=agora.tzinfo)
    resto = (ate.date() - agora.date()).days
    if resto < 0:
        return {
            "acesso": "pagante",
            "situacao": "expirado",
            "dias_restantes": 0,
            "teste_ate": _iso(ate),
            "pode_usar": False,
            "motivo": "O período de teste acabou. Peça ao administrador para renovar ou marcar como pago.",
        }
    return {
        "acesso": "pagante",
        "situacao": "teste",
        "dias_restantes": resto,
        "teste_ate": _iso(ate),
        "pode_usar": True,
        "motivo": "",
    }


def pode_usar(user_id: str) -> tuple[bool, str]:
    info = situacao(user_id)
    return bool(info.get("pode_usar")), (info.get("motivo") or "")


def gravar_assinatura(
    user_id: str,
    *,
    customer_id: str = "",
    subscription_id: str = "",
    email: str = "",
) -> None:
    users, user = _achar_usuario(user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    if customer_id:
        user["mp_payer_id"] = customer_id
    if subscription_id:
        user["mp_preapproval_id"] = subscription_id
        user["asaas_subscription_id"] = ""  # não misturar com Asaas
    if email:
        user["email"] = email.strip()
    _save(USERS, users)


def aplicar_pagamento_assinatura(
    *,
    subscription_id: str = "",
    external_reference: str = "",
    pago: bool,
) -> dict | None:
    """Webhook Mercado Pago: liga ou desliga o acesso pago do pagante."""
    users = _usuarios()
    alvo = None
    if subscription_id:
        alvo = next(
            (
                u
                for u in users
                if u.get("mp_preapproval_id") == subscription_id
                or u.get("asaas_subscription_id") == subscription_id
            ),
            None,
        )
    if not alvo and external_reference:
        alvo = next((u for u in users if u.get("id") == external_reference), None)
    if not alvo:
        return None
    if _acesso(alvo, users) == "dono":
        return None
    alvo["acesso"] = "pagante"
    if pago:
        alvo["pago"] = True
    else:
        alvo["pago"] = False
        if not _teste_ate(alvo):
            alvo["teste_ate"] = ""
    _save(USERS, users)
    return {"id": alvo.get("id"), "nome": alvo.get("nome"), "pago": bool(alvo.get("pago"))}


def dados_cobranca(user_id: str) -> dict:
    _, user = _achar_usuario(user_id)
    if not user:
        return {}
    return {
        "email": user.get("email") or "",
        "asaas_customer_id": "",
        "asaas_subscription_id": "",
        "mp_preapproval_id": user.get("mp_preapproval_id") or "",
        "mp_payer_id": user.get("mp_payer_id") or "",
    }


def _marcar_teste(user: dict, dias: int | None = None) -> None:
    n = dias if dias is not None else load_acesso_config()["dias_teste"]
    user["teste_ate"] = _iso(_agora() + timedelta(days=max(1, int(n))))
    user["pago"] = False
    if not user.get("criado_em"):
        user["criado_em"] = _iso(_agora())


def definir_acesso(
    user_id: str,
    acesso_novo: str,
    *,
    renovar: bool = False,
    pago: bool | None = None,
) -> dict:
    """Admin muda free/pagante, renova teste ou marca pagante como pago."""
    acesso_novo = (acesso_novo or "").strip().lower()
    if acesso_novo == "cortesia":
        acesso_novo = "free"
    if acesso_novo == "avulso":
        acesso_novo = "pagante"
    if acesso_novo not in ("free", "pagante"):
        raise ValueError("Escolha free ou pagante. O administrador não muda por aqui.")
    users, user = _achar_usuario(user_id)
    if not user:
        raise ValueError("Usuário não encontrado.")
    if _acesso(user, users) == "dono":
        raise ValueError("O administrador não muda de tipo por aqui.")
    user["acesso"] = acesso_novo
    if not user.get("criado_em"):
        user["criado_em"] = _iso(_agora())
    if acesso_novo == "free":
        user["teste_ate"] = ""
        user["pago"] = False
    elif pago is True:
        user["pago"] = True
    else:
        user["pago"] = False
        if renovar or not _teste_ate(user):
            _marcar_teste(user)
    _save(USERS, users)
    item = next((u for u in listar_usuarios() if u["id"] == user_id), None)
    if not item:
        raise ValueError("Usuário não encontrado.")
    return item


def garantir_dono(user: dict | None) -> str:
    """Quem já entrou e ainda não existe administrador vira o administrador geral."""
    if not user or not user.get("id"):
        return ""
    users = _usuarios()
    found = next((u for u in users if u.get("id") == user.get("id")), None)
    tem_dono = any(_acesso(u, users) == "dono" for u in users)
    if found and _acesso(found, users) == "dono":
        return "dono"
    if tem_dono:
        return _acesso(found, users) if found else "pagante"
    if not found:
        found = {
            "id": user["id"],
            "nome": (user.get("nome") or "").strip() or "Administrador",
            "salt": "",
            "hash": "",
            "acesso": "dono",
            "perfil": {},
        }
        users.append(found)
    else:
        found["acesso"] = "dono"
    _save(USERS, users)
    return "dono"


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
            user["acesso"] = "free"
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
            if user.get("id") == alvo["user_id"] and _acesso(user, users) == "free":
                user["acesso"] = "pagante"
                _marcar_teste(user)
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
            marcado = "free"
        else:
            marcado = "pagante"
        user = {
            "id": secrets.token_hex(8),
            "nome": nome,
            "salt": salt,
            "hash": _hash(senha, salt),
            "acesso": marcado,
            "criado_em": _iso(_agora()),
            "pago": False,
        }
        if marcado == "pagante":
            _marcar_teste(user)
        users.append(user)
        _save(USERS, users)
        if conv and marcado == "free":
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


def _usuarios() -> list:
    dados = _load(USERS, [])
    return dados if isinstance(dados, list) else []


def _achar_usuario(user_id: str) -> tuple[list, dict | None]:
    users = _usuarios()
    for user in users:
        if user.get("id") == user_id:
            return users, user
    return users, None


def perfil_ia(user_id: str) -> dict:
    """Chave e plano deste perfil. Não usa a Groq do servidor."""
    _, user = _achar_usuario(user_id)
    perfil = (user or {}).get("perfil") or {}
    if not isinstance(perfil, dict):
        perfil = {}
    return {
        "provider": (perfil.get("provider") or "").strip(),
        "provider_label": (perfil.get("provider_label") or "").strip(),
        "model": (perfil.get("model") or "").strip(),
        "base_url": (perfil.get("base_url") or "").strip().rstrip("/"),
        "api_key": (perfil.get("api_key") or "").strip(),
        "escritorio": (perfil.get("escritorio") or "").strip(),
        "advogada": (perfil.get("advogada") or "").strip(),
        "oab": (perfil.get("oab") or "").strip(),
        "logo_b64": perfil.get("logo_b64") or "",
        "logo_tipo": (perfil.get("logo_tipo") or "").strip(),
    }


def perfil_publico(user_id: str) -> dict:
    perfil = perfil_ia(user_id)
    chave = perfil["api_key"]
    publico = dict(perfil)
    publico["api_key"] = ""
    publico["has_key"] = bool(chave)
    publico["masked_key"] = ("••••" + chave[-4:]) if len(chave) >= 4 else ""
    publico["has_logo"] = bool(perfil.get("logo_b64"))
    publico.pop("logo_b64", None)
    return publico


def salvar_perfil(user_id: str, nome: str, dados: dict) -> dict:
    users, user = _achar_usuario(user_id)
    if not user:
        user = {
            "id": user_id,
            "nome": (nome or "").strip() or "perfil",
            "salt": "",
            "hash": "",
            "acesso": "dono" if not users else "free",
            "criado_em": _iso(_agora()),
            "perfil": {},
        }
        users.append(user)
    perfil = dict(user.get("perfil") or {})
    for campo in ("provider", "provider_label", "model", "base_url", "escritorio", "advogada", "oab", "logo_tipo"):
        if campo in dados and dados.get(campo) is not None:
            perfil[campo] = str(dados.get(campo) or "").strip()
    chave = (dados.get("api_key") or "").strip()
    if chave:
        perfil["api_key"] = chave
    logo = dados.get("logo_b64") or ""
    if logo:
        perfil["logo_b64"] = logo
        perfil["logo_tipo"] = (dados.get("logo_tipo") or "image/png").strip()
    user["perfil"] = perfil
    _save(USERS, users)
    return perfil_publico(user_id)


def listar_usuarios() -> list[dict]:
    users = _usuarios()
    saida = []
    for user in users:
        perfil = user.get("perfil") or {}
        uid = user.get("id") or ""
        info = situacao(uid) if uid else {}
        saida.append(
            {
                "id": uid,
                "nome": user.get("nome") or "",
                "acesso": info.get("acesso") or _acesso(user, users),
                "situacao": info.get("situacao") or "",
                "dias_restantes": info.get("dias_restantes"),
                "teste_ate": info.get("teste_ate") or "",
                "pago": bool(user.get("pago")),
                "pode_usar": bool(info.get("pode_usar")),
                "ia": (perfil.get("provider_label") or perfil.get("provider") or ""),
                "tem_chave": bool((perfil.get("api_key") or "").strip()),
            }
        )
    return saida


def criar_usuario(nome: str, senha: str, acesso_tipo: str = "free") -> dict:
    """Cria free ou pagante. Não devolve token: o administrador continua logado."""
    nome = (nome or "").strip()
    senha = senha or ""
    acesso_tipo = (acesso_tipo or "free").strip().lower()
    if acesso_tipo == "cortesia":
        acesso_tipo = "free"
    if acesso_tipo == "avulso":
        acesso_tipo = "pagante"
    if acesso_tipo not in ("free", "pagante"):
        raise ValueError("Escolha free ou pagante.")
    if len(nome) < 2 or len(senha) < 4:
        raise ValueError("Nome e senha (mínimo 4 caracteres).")
    users = _usuarios()
    if any((u.get("nome") or "").lower() == nome.lower() for u in users):
        raise ValueError("Já existe usuário com esse nome.")
    salt = secrets.token_hex(8)
    user = {
        "id": secrets.token_hex(8),
        "nome": nome,
        "salt": salt,
        "hash": _hash(senha, salt),
        "acesso": acesso_tipo,
        "criado_em": _iso(_agora()),
        "pago": False,
        "perfil": {},
    }
    if acesso_tipo == "pagante":
        _marcar_teste(user)
    users.append(user)
    _save(USERS, users)
    return next(u for u in listar_usuarios() if u["id"] == user["id"])
