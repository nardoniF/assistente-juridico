"""Assinatura recorrente via Mercado Pago — mesmo token do Sensor Tattoo Fix.

PIX e cartão só pelo MP (sem Asaas nesse fluxo, para não conflitar).
"""
from __future__ import annotations

import os

import httpx

from contas import load_acesso_config

MP_API = "https://api.mercadopago.com"


class CobrancaError(RuntimeError):
    pass


def _token() -> str:
    # Mesmas variáveis do Worker da Sensor Tattoo Fix
    return (
        os.environ.get("MP_ACCESS_TOKEN")
        or os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        or ""
    ).strip()


def configurado() -> bool:
    return bool(_token())


def _sandbox() -> bool:
    tok = _token()
    return tok.startswith("TEST-") or (os.environ.get("MP_SANDBOX") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _headers() -> dict:
    tok = _token()
    if not tok:
        raise CobrancaError(
            "Cobrança ainda não está ligada. Coloque MP_ACCESS_TOKEN no Render "
            "(a mesma chave Mercado Pago da Sensor Tattoo Fix)."
        )
    return {
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": os.urandom(8).hex(),
    }


def _pedir(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{MP_API}{path}"
    with httpx.Client(timeout=60.0) as client:
        r = client.request(method, url, headers=_headers(), json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:400]}
        if r.status_code >= 400:
            msg = ""
            if isinstance(data, dict):
                msg = (
                    data.get("message")
                    or data.get("error")
                    or str(data.get("cause") or "")[:300]
                )
            raise CobrancaError(f"Mercado Pago respondeu {r.status_code}: {msg or str(data)[:300]}")
        return data if isinstance(data, dict) else {"ok": True}


def _back_url() -> str:
    return (
        os.environ.get("MP_BACK_URL")
        or os.environ.get("PUBLIC_SITE_URL")
        or "https://www.xthemis.com.br/"
    ).strip()


def criar_assinatura(*, user_id: str, nome: str, email: str) -> dict:
    email = (email or "").strip()
    if "@" not in email:
        raise CobrancaError("Informe um e-mail válido para a cobrança mensal.")
    cfg = load_acesso_config()
    valor = float(cfg.get("preco_mensal") or 39.9)
    if valor < 5:
        raise CobrancaError("Preço mensal inválido no admin.")
    motivo = f"xThemis · {(nome or 'assinatura').strip()[:80]}"
    corpo = {
        "reason": motivo,
        "external_reference": user_id,
        "payer_email": email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": round(valor, 2),
            "currency_id": "BRL",
        },
        "back_url": _back_url(),
        "status": "pending",
    }
    data = _pedir("POST", "/preapproval", corpo)
    sub_id = str(data.get("id") or "")
    if not sub_id:
        raise CobrancaError("Mercado Pago não devolveu a assinatura.")
    link = ""
    if _sandbox():
        link = (data.get("sandbox_init_point") or data.get("init_point") or "").strip()
    else:
        link = (data.get("init_point") or data.get("sandbox_init_point") or "").strip()
    if not link:
        raise CobrancaError("Mercado Pago não devolveu o link de pagamento.")
    return {
        "subscription_id": sub_id,
        "customer_id": "",
        "value": round(valor, 2),
        "checkout_url": link,
        "gateway": "mercadopago",
    }


def consultar_preapproval(preapproval_id: str) -> dict:
    return _pedir("GET", f"/preapproval/{preapproval_id}")


def iniciar_assinatura(
    *,
    user_id: str,
    nome: str,
    email: str,
    cpf_cnpj: str = "",
    customer_id: str = "",
) -> dict:
    del cpf_cnpj, customer_id  # MP pede e-mail no checkout; CPF fica no fluxo do Mercado Pago
    gateway = (load_acesso_config().get("gateway") or "mercadopago").strip().lower()
    if gateway != "mercadopago":
        raise CobrancaError(
            "PIX e cartão deste produto usam só Mercado Pago (igual à Sensor Tattoo Fix). "
            "No admin, deixe o gateway em Mercado Pago."
        )
    return criar_assinatura(user_id=user_id, nome=nome, email=email)
