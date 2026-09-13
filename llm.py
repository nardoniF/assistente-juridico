from __future__ import annotations

import httpx

from organizer import DEFAULT_CONFIG, load_config


class LlmError(RuntimeError):
    pass


def _cfg() -> dict:
    raw = load_config()
    defaults = DEFAULT_CONFIG
    provider = raw.get("provider") or defaults["provider"]
    # compatibilidade com configs antigas (só OpenAI)
    api_key = (raw.get("api_key") or raw.get("openai_api_key") or "").strip()
    model = raw.get("model") or raw.get("openai_model") or defaults["model"]
    base_url = (
        raw.get("base_url")
        or raw.get("openai_base_url")
        or defaults["base_url"]
    ).rstrip("/")
    return {
        "provider": provider,
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "provider_label": raw.get("provider_label") or defaults.get("provider_label", ""),
    }


def configured() -> bool:
    return bool(_cfg()["api_key"])


def complete(system: str, user: str, *, temperature: float = 0.2) -> str:
    cfg = _cfg()
    key = cfg["api_key"]
    if not key:
        raise LlmError(
            "Falta a chave da IA. Abra Ajustes, escolha Groq (gratuito), "
            "cole a chave de console.groq.com/keys e salve."
        )
    model = cfg["model"]
    base = cfg["base_url"]
    # Groq: contexto menor — corta entrada muito grande para não estourar
    max_chars = 100_000 if "groq.com" in base else 450_000
    if len(user) > max_chars:
        user = user[:max_chars] + "\n\n[…texto cortado por limite do modelo…]"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    with httpx.Client(timeout=240.0) as client:
        r = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            hint = ""
            if r.status_code in (401, 403):
                hint = " Verifique a chave (Groq: console.groq.com/keys)."
            elif r.status_code == 429:
                hint = " Limite gratuito esgotado — espere um pouco ou use outro plano."
            raise LlmError(f"A API devolveu erro {r.status_code}: {r.text[:400]}{hint}")
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise LlmError(f"Resposta inesperada da API: {exc}") from exc
