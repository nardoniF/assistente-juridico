from __future__ import annotations

import re

import httpx

from organizer import DEFAULT_CONFIG, load_config

_PAGINA = re.compile(r"===== PAGINA (\d+) =====")
_FIM = "===== FIM DOS AUTOS ====="
_LEITURA = (
    "Você lê um processo inteiro, em partes, porque ele não cabe numa única chamada. "
    "Não escreva peça. Não invente. Não pule página. "
    "Para cada página, escreva 'PÁGINA N:' e os fatos, nomes, datas, valores, pedidos e decisões. "
    "Se a página não tiver fato, escreva 'PÁGINA N: sem fato novo'. "
    "No máximo 15 linhas por página. Conserve folha, valor e nome como estão no texto."
)


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


def janela_tokens(model: str, base: str) -> int:
    """Tokens de contexto do modelo. A reserva da resposta sai em cabe()."""
    m = (model or "").lower()
    b = (base or "").lower()
    if "groq.com" in b:
        return 8_000
    if "gemini-2" in m or "gemini-1.5" in m:
        return 1_000_000
    if any(nome in m for nome in ("gpt-4.1", "gpt-4o", "gpt-5", "o1", "o3", "o4")):
        return 1_000_000
    if "gpt-4" in m:
        return 128_000
    return 128_000


def _tokens(texto: str) -> int:
    # Português jurídico: 3 caracteres por token superestima e evita estourar a janela.
    return max(1, (len(texto) + 2) // 3)


def cabe(system: str, user: str, cfg: dict) -> bool:
    reserva = 32_000
    livre = max(4_000, janela_tokens(cfg.get("model") or "", cfg.get("base_url") or "") - reserva)
    return _tokens(system) + _tokens(user) <= livre


def partir_paginas(user: str) -> tuple[str, list[tuple[int, str]], str] | None:
    """Separa o preâmbulo, cada página e o que vier depois do fim dos autos."""
    fim = user.find(_FIM)
    miolo = user if fim < 0 else user[:fim]
    sufixo = "" if fim < 0 else user[fim + len(_FIM) :]
    marcas = list(_PAGINA.finditer(miolo))
    if not marcas:
        return None
    pre = miolo[: marcas[0].start()]
    paginas: list[tuple[int, str]] = []
    for n, marca in enumerate(marcas):
        ate = marcas[n + 1].start() if n + 1 < len(marcas) else len(miolo)
        paginas.append((int(marca.group(1)), miolo[marca.end() : ate].strip("\n")))
    return pre, paginas, sufixo


def montar_lotes(paginas: list[tuple[int, str]], limite: int) -> list[str]:
    """Blocos em ordem. Uma página maior que o lote entra sozinha, sem ser descartada."""
    lotes: list[str] = []
    atual: list[str] = []
    tamanho = 0
    teto = max(8_000, limite)

    def fecha() -> None:
        nonlocal atual, tamanho
        if atual:
            lotes.append("".join(atual))
        atual = []
        tamanho = 0

    for num, texto in paginas:
        pedaco = f"===== PAGINA {num} =====\n{texto}\n"
        if len(pedaco) > teto:
            fecha()
            resto = texto
            while resto:
                corte = resto[: teto - 40]
                lotes.append(f"===== PAGINA {num} =====\n{corte}\n")
                resto = resto[len(corte) :]
            continue
        if atual and tamanho + len(pedaco) > teto:
            fecha()
        atual.append(pedaco)
        tamanho += len(pedaco)
    fecha()
    return lotes


def _validar(cfg: dict) -> tuple[str, str, str]:
    key = cfg["api_key"]
    model = cfg["model"]
    base = cfg["base_url"]
    if not key:
        raise LlmError(
            "Falta a chave da IA paga. Abra Ajustes, escolha OpenAI ou Gemini "
            "e cole a chave (sk-... ou AIza...)."
        )
    if "api.openai.com" in base and not key.startswith("sk-"):
        raise LlmError(
            "Para o GPT, abra Ajustes, escolha OpenAI e cole a chave que começa com sk-."
        )
    if "generativelanguage.googleapis.com" in base and not key.startswith("AIza"):
        raise LlmError(
            "Para o Gemini, abra Ajustes e cole a chave que começa com AIza."
        )
    return key, model, base


def _chamar(system: str, user: str, cfg: dict, temperature: float) -> str:
    key, model, base = _validar(cfg)
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    espera = 600.0 if len(user) > 100_000 else 240.0
    with httpx.Client(timeout=espera) as client:
        r = client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            hint = ""
            if r.status_code in (401, 403):
                hint = " Verifique a chave em Ajustes."
            elif r.status_code == 429:
                hint = " Limite da API esgotado. Espere um pouco e tente de novo."
            elif r.status_code == 413:
                hint = " O texto passou do limite desta API. A leitura inteira pede GPT-4.1 ou Gemini 2.5."
            raise LlmError(f"A API devolveu erro {r.status_code}: {r.text[:400]}{hint}")
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise LlmError(f"Resposta inesperada da API: {exc}") from exc


def _pedido_final(pre: str, leitura: str, sufixo: str) -> str:
    return (
        pre
        + "\n\nLEITURA INTEGRAL DE TODAS AS PÁGINAS "
        "(nenhuma ficou de fora; use só esta leitura e a capa):\n"
        + leitura
        + "\n\n"
        + sufixo
    )


def _ler_em_partes(system: str, user: str, cfg: dict, temperature: float) -> str:
    partes = partir_paginas(user)
    if not partes:
        raise LlmError(
            "O processo não coube na janela do modelo e o texto não está paginado. "
            "O final não foi cortado."
        )
    pre, paginas, sufixo = partes
    livre = max(4_000, janela_tokens(cfg.get("model") or "", cfg.get("base_url") or "") - 32_000)
    limite = max(20_000, livre * 3 - len(system) - 2_000)
    lotes = montar_lotes(paginas, limite)
    notas = [
        _chamar(
            _LEITURA,
            f"Parte {i} de {len(lotes)}. Leia todas as páginas deste bloco.\n\n{lote}",
            cfg,
            0.0,
        )
        for i, lote in enumerate(lotes, 1)
    ]
    leitura = "\n\n".join(notas)
    pedido = _pedido_final(pre, leitura, sufixo)
    rodada = 0
    while not cabe(system, pedido, cfg) and rodada < 3 and len(notas) > 1:
        rodada += 1
        novos: list[str] = []
        grupo: list[str] = []
        grupo_len = 0

        def fecha() -> None:
            nonlocal grupo, grupo_len
            if not grupo:
                return
            novos.append(
                _chamar(
                    "Una estas leituras. Conserve toda linha que começa com PÁGINA. "
                    "Não invente. Não escreva peça.",
                    "\n\n".join(grupo),
                    cfg,
                    0.0,
                )
            )
            grupo = []
            grupo_len = 0

        for nota in notas:
            if grupo and grupo_len + len(nota) > limite:
                fecha()
            grupo.append(nota)
            grupo_len += len(nota)
        fecha()
        notas = novos or notas
        leitura = "\n\n".join(notas)
        pedido = _pedido_final(pre, leitura, sufixo)
    if not cabe(system, pedido, cfg):
        raise LlmError(
            "O processo foi lido por completo, mas a leitura ainda não cabe numa peça só neste modelo. "
            "Use GPT-4.1 ou Gemini 2.5."
        )
    return _chamar(system, pedido, cfg, temperature)


def complete(system: str, user: str, *, temperature: float = 0.2, cfg: dict | None = None) -> str:
    cfg = cfg or _cfg()
    _validar(cfg)
    if cabe(system, user, cfg):
        return _chamar(system, user, cfg, temperature)
    return _ler_em_partes(system, user, cfg, temperature)
