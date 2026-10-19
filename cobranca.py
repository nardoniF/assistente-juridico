"""Assinatura recorrente via Asaas (menor taxa entre as opções do escritório)."""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

from contas import load_acesso_config


class CobrancaError(RuntimeError):
    pass


def _token() -> str:
    return (os.environ.get("ASAAS_API_KEY") or os.environ.get("ASAAS_ACCESS_TOKEN") or "").strip()


def _base() -> str:
    sandbox = (os.environ.get("ASAAS_SANDBOX") or "").strip().lower() in ("1", "true", "yes")
    if sandbox:
        return "https://sandbox.asaas.com/api/v3"
    return (os.environ.get("ASAAS_API_URL") or "https://api.asaas.com/v3").rstrip("/")


def configurado() -> bool:
    return bool(_token())


def _headers() -> dict:
    tok = _token()
    if not tok:
        raise CobrancaError(
            "Cobrança ainda não está ligada no servidor. Peça ao administrador para colocar a chave Asaas."
        )
    return {
        "access_token": tok,
        "Content-Type": "application/json",
        "User-Agent": "xThemis/1.0",
    }


def _pedir(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{_base()}{path}"
    with httpx.Client(timeout=60.0) as client:
        r = client.request(method, url, headers=_headers(), json=payload)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:400]}
        if r.status_code >= 400:
            erros = data.get("errors") if isinstance(data, dict) else None
            if isinstance(erros, list) and erros:
                msg = "; ".join(
                    str(e.get("description") or e.get("code") or e) for e in erros[:3]
                )
            else:
                msg = str(data)[:300]
            raise CobrancaError(f"Asaas respondeu {r.status_code}: {msg}")
        return data if isinstance(data, dict) else {"ok": True}


def garantir_cliente(*, customer_id: str, nome: str, email: str, cpf_cnpj: str = "") -> str:
    if customer_id:
        return customer_id
    email = (email or "").strip()
    nome = (nome or "").strip() or "Assinante xThemis"
    if "@" not in email:
        raise CobrancaError("Informe um e-mail válido para a cobrança mensal.")
    corpo = {"name": nome, "email": email, "notificationDisabled": False}
    doc = "".join(c for c in (cpf_cnpj or "") if c.isdigit())
    if len(doc) in (11, 14):
        corpo["cpfCnpj"] = doc
    data = _pedir("POST", "/customers", corpo)
    cid = data.get("id") or ""
    if not cid:
        raise CobrancaError("Asaas não devolveu o cliente.")
    return cid


def criar_assinatura(
    *,
    customer_id: str,
    user_id: str,
    nome: str,
) -> dict:
    cfg = load_acesso_config()
    valor = float(cfg.get("preco_mensal") or 39.9)
    if valor < 5:
        raise CobrancaError("Preço mensal inválido no admin.")
    amanha = (date.today() + timedelta(days=1)).isoformat()
    data = _pedir(
        "POST",
        "/subscriptions",
        {
            "customer": customer_id,
            "billingType": "UNDEFINED",
            "value": round(valor, 2),
            "nextDueDate": amanha,
            "cycle": "MONTHLY",
            "description": f"xThemis · assinatura mensal · {nome}",
            "externalReference": user_id,
        },
    )
    sub_id = data.get("id") or ""
    if not sub_id:
        raise CobrancaError("Asaas não devolveu a assinatura.")
    link = _link_pagamento(sub_id) or data.get("paymentLink") or ""
    return {
        "subscription_id": sub_id,
        "customer_id": customer_id,
        "value": round(valor, 2),
        "checkout_url": link,
        "gateway": "asaas",
    }


def _link_pagamento(subscription_id: str) -> str:
    data = _pedir("GET", f"/subscriptions/{subscription_id}/payments?limit=1")
    itens = data.get("data") if isinstance(data, dict) else None
    if not isinstance(itens, list) or not itens:
        return ""
    pag = itens[0] or {}
    return (
        pag.get("invoiceUrl")
        or pag.get("bankSlipUrl")
        or pag.get("transactionReceiptUrl")
        or ""
    )


def iniciar_assinatura(
    *,
    user_id: str,
    nome: str,
    email: str,
    cpf_cnpj: str = "",
    customer_id: str = "",
) -> dict:
    if (load_acesso_config().get("gateway") or "asaas") != "asaas":
        raise CobrancaError("O gateway configurado no admin ainda não está ligado neste servidor.")
    cid = garantir_cliente(
        customer_id=customer_id, nome=nome, email=email, cpf_cnpj=cpf_cnpj
    )
    return criar_assinatura(customer_id=cid, user_id=user_id, nome=nome)
