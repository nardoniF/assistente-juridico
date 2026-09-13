from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

HOME_APP = Path.home() / "Documents" / "Assistente Juridico"
PROCESSOS = HOME_APP / "Processos"
CONFIG = HOME_APP / "config.json"

# Padrão: Groq (gratuito) — chave em console.groq.com
DEFAULT_CONFIG = {
    "provider": "groq",
    "provider_label": "Groq (gratuito)",
    "api_key": "",
    "model": "llama-3.3-70b-versatile",
    "base_url": "https://api.groq.com/openai/v1",
}

PRESETS = {
    "groq_free": {
        "provider": "groq",
        "provider_label": "Groq — gratuito (recomendado sem cartão)",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
        "custo": "Grátis (com limites diários de uso)",
        "nota": "Crie chave em console.groq.com/keys. Bom para resumo e peças; processo muito grande pode exigir cortar texto.",
    },
    "google_flash": {
        "provider": "google",
        "provider_label": "Google Gemini Flash (pago / free limitado)",
        "model": "gemini-2.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "custo": "Free tier limitado ou ~US$ 0,30 entrada + US$ 2,50 saída / 1M tokens",
        "nota": "Só se ainda tiver conta Gemini ativa.",
    },
    "google_pro": {
        "provider": "google",
        "provider_label": "Google Gemini Pro (pago)",
        "model": "gemini-2.5-pro",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "custo": "~US$ 1,25 entrada + US$ 10 saída por 1M tokens",
        "nota": "Melhor qualidade, precisa faturamento.",
    },
    "google_lite": {
        "provider": "google",
        "provider_label": "Google Gemini Flash-Lite",
        "model": "gemini-2.5-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "custo": "Barato / free limitado",
        "nota": "Só rascunho simples.",
    },
    "openai_mini": {
        "provider": "openai",
        "provider_label": "OpenAI GPT-4.1 mini",
        "model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1",
        "custo": "~US$ 0,40 entrada + US$ 1,60 saída por 1M tokens",
        "nota": "Pago — precisa crédito OpenAI.",
    },
}


def ensure_dirs() -> None:
    PROCESSOS.mkdir(parents=True, exist_ok=True)
    HOME_APP.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load_config() -> dict:
    ensure_dirs()
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    # migra config antiga
    if data.get("openai_api_key") and not data.get("api_key"):
        data["api_key"] = data["openai_api_key"]
    if data.get("openai_model") and not data.get("model"):
        data["model"] = data["openai_model"]
    return data


def save_config(data: dict) -> None:
    ensure_dirs()
    current = load_config()
    current.update(data)
    # não guardar campos legados duplicados
    current.pop("openai_api_key", None)
    current.pop("openai_model", None)
    current.pop("openai_base_url", None)
    CONFIG.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def slug(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return (text or "parte")[:max_len]


def folder_name(reclamante: str, reclamado: str, numero: str) -> str:
    n = re.sub(r"[^\d\.\-]", "", numero or "sem-numero")
    return f"{slug(reclamante)}_x_{slug(reclamado)}_{n}"


def copy_into_case(src: Path, meta: dict) -> Path:
    ensure_dirs()
    dest_dir = PROCESSOS / folder_name(
        meta.get("reclamante") or "Reclamante",
        meta.get("reclamado") or "Reclamado",
        meta.get("numero") or "processo",
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_pdf = dest_dir / "processo.pdf"
    if src.resolve() != dest_pdf.resolve():
        shutil.copy2(src, dest_pdf)
    (dest_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return dest_dir


def list_cases() -> list[dict]:
    ensure_dirs()
    out = []
    for d in sorted(PROCESSOS.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        docs = sorted(
            p.name
            for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in {".docx", ".pdf"} and p.name != "processo.pdf"
        )
        has_processo = (d / "processo.pdf").exists()
        prompts_n = 0
        pp = d / "prompts_caso.json"
        if pp.exists():
            try:
                pdata = json.loads(pp.read_text(encoding="utf-8"))
                prompts_n = len(pdata.get("geral") or [])
            except Exception:
                prompts_n = 0
        out.append(
            {
                "id": d.name,
                "path": str(d),
                "meta": meta,
                "docx": [x for x in docs if x.endswith(".docx")],
                "pdfs": [x for x in docs if x.endswith(".pdf")],
                "arquivos": docs,
                "tem_processo": has_processo,
                "prompts_salvos": prompts_n,
            }
        )
    return out

def case_dir(case_id: str) -> Path:
    d = (PROCESSOS / case_id).resolve()
    if PROCESSOS.resolve() not in d.parents and d != PROCESSOS.resolve():
        raise ValueError("pasta invalida")
    if not d.is_dir():
        raise FileNotFoundError(case_id)
    return d
