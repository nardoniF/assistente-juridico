from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

# Web/SaaS: DATA_DIR=/data (Docker). Local: ./data ou Documents legado.
_DEFAULT_LOCAL = Path(__file__).resolve().parent / "data"
_LEGACY = Path.home() / "Documents" / "Assistente Juridico"
if os.environ.get("DATA_DIR"):
    HOME_APP = Path(os.environ["DATA_DIR"]).expanduser().resolve()
elif os.environ.get("WEB_MODE", "").strip() in ("1", "true", "True", "yes"):
    HOME_APP = _DEFAULT_LOCAL
elif _LEGACY.exists():
    HOME_APP = _LEGACY
else:
    HOME_APP = _DEFAULT_LOCAL

PROCESSOS = HOME_APP / "Processos"
CONFIG = HOME_APP / "config.json"

# Padrão: Groq (gratuito) — chave em console.groq.com ou env GROQ_API_KEY / API_KEY
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


def web_mode() -> bool:
    return os.environ.get("WEB_MODE", "").strip() in ("1", "true", "True", "yes") or bool(
        os.environ.get("DATA_DIR")
    )


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
    if data.get("openai_api_key") and not data.get("api_key"):
        data["api_key"] = data["openai_api_key"]
    if data.get("openai_model") and not data.get("model"):
        data["model"] = data["openai_model"]

    # Env vence arquivo (deploy web)
    env_key = (
        os.environ.get("API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if env_key:
        data["api_key"] = env_key
    if os.environ.get("API_MODEL"):
        data["model"] = os.environ["API_MODEL"].strip()
    if os.environ.get("API_BASE_URL"):
        data["base_url"] = os.environ["API_BASE_URL"].rstrip("/")
    if os.environ.get("API_PROVIDER"):
        data["provider"] = os.environ["API_PROVIDER"].strip()
    return data


def save_config(data: dict) -> None:
    ensure_dirs()
    current = load_config()
    # Não sobrescrever chave só-de-env no arquivo com vazio
    current.update(data)
    current.pop("openai_api_key", None)
    current.pop("openai_model", None)
    current.pop("openai_base_url", None)
    # Se a chave veio só do ambiente, não gravar no disco em web
    if web_mode() and (os.environ.get("API_KEY") or os.environ.get("GROQ_API_KEY")):
        file_data = {k: v for k, v in current.items() if k != "api_key"}
        file_data["api_key"] = ""
        CONFIG.write_text(json.dumps(file_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return
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
    """Cria (ou reusa) a pasta do processo e grava/sobrepoe sempre o mesmo processo.pdf."""
    ensure_dirs()
    dest_dir = PROCESSOS / folder_name(
        meta.get("reclamante") or "Reclamante",
        meta.get("reclamado") or "Reclamado",
        meta.get("numero") or "processo",
    )
    dest_dir.mkdir(parents=True, exist_ok=True)
    overwrite_processo_pdf(dest_dir, src, meta)
    return dest_dir


def overwrite_processo_pdf(case_dir: Path, src: Path, meta: dict | None = None) -> Path:
    """Uma única cópia dos autos: processo.pdf. Versão antiga some (sobreposta)."""
    dest_pdf = case_dir / "processo.pdf"
    if src.resolve() != dest_pdf.resolve():
        shutil.copy2(src, dest_pdf)
    if meta is not None:
        (case_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    # força releitura dos autos na próxima ação
    cache = case_dir / "extrato.json"
    if cache.exists():
        try:
            cache.unlink()
        except OSError:
            pass
    return dest_pdf


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
