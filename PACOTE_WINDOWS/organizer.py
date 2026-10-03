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
    "model": "openai/gpt-oss-120b",
    "base_url": "https://api.groq.com/openai/v1",
}

PRESETS = {
    "groq_free": {
        "provider": "groq",
        "provider_label": "Groq — gratuito (teste / rascunho)",
        "model": "openai/gpt-oss-120b",
        "base_url": "https://api.groq.com/openai/v1",
        "custo": "Grátis (limites diários)",
        "nota": "Bom pra testar. Para peça séria, use Gemini Pro ou OpenAI.",
    },
    "google_flash": {
        "provider": "google",
        "provider_label": "Google Gemini Flash (rápido)",
        "model": "gemini-2.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "custo": "Free limitado ou barato",
        "nota": "Resumos e peças médias.",
    },
    "google_pro": {
        "provider": "google",
        "provider_label": "Google Gemini Pro — qualidade (recomendado pago)",
        "model": "gemini-2.5-pro",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "custo": "Pago · melhor qualidade forense",
        "nota": "Use chave AIza... com faturamento. Ideal para recurso/contestação.",
    },
    "google_lite": {
        "provider": "google",
        "provider_label": "Google Gemini Flash-Lite",
        "model": "gemini-2.5-flash-lite",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "custo": "Barato",
        "nota": "Só rascunho simples.",
    },
    "openai_mini": {
        "provider": "openai",
        "provider_label": "OpenAI GPT-4.1 mini — qualidade paga",
        "model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1",
        "custo": "Pago · boa relação custo/qualidade",
        "nota": "Chave sk-... com crédito OpenAI.",
    },
}


def web_mode() -> bool:
    return os.environ.get("WEB_MODE", "").strip() in ("1", "true", "True", "yes") or bool(
        os.environ.get("DATA_DIR")
    )


def usar_pasta(path: str) -> str:
    """No programa local, a advogada escolhe onde as pastas dos processos ficam."""
    global PROCESSOS
    if web_mode():
        raise ValueError("No site, a pasta dos processos fica no servidor.")
    novo = Path(path or "").expanduser().resolve()
    if not novo.is_absolute():
        raise ValueError("Informe o caminho completo da pasta.")
    novo.mkdir(parents=True, exist_ok=True)
    PROCESSOS = novo
    return str(PROCESSOS)


def ensure_dirs() -> None:
    PROCESSOS.mkdir(parents=True, exist_ok=True)
    HOME_APP.mkdir(parents=True, exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _env_key() -> str:
    return (
        os.environ.get("API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()


def _read_config_file() -> dict:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_config() -> dict:
    ensure_dirs()
    data = _read_config_file()
    if data.get("openai_api_key") and not data.get("api_key"):
        data["api_key"] = data["openai_api_key"]
    if data.get("openai_model") and not data.get("model"):
        data["model"] = data["openai_model"]
    if data.get("model") in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        data["model"] = DEFAULT_CONFIG["model"]

    saved_key = (data.get("api_key") or "").strip()
    provider = (data.get("provider") or DEFAULT_CONFIG["provider"]).strip()
    env_key = _env_key()
    # Groq de teste usa a chave do servidor. OpenAI/Gemini usam a chave colada em Ajustes.
    data["key_from_env"] = False
    if provider == "groq" and env_key:
        data["api_key"] = env_key
        data["key_from_env"] = True
    elif saved_key:
        data["api_key"] = saved_key
    if os.environ.get("API_MODEL") and provider == "groq" and not saved_key:
        data["model"] = os.environ["API_MODEL"].strip()
    if os.environ.get("API_BASE_URL") and provider == "groq" and not saved_key:
        data["base_url"] = os.environ["API_BASE_URL"].rstrip("/")
    if not web_mode() and (data.get("processos_dir") or "").strip():
        try:
            usar_pasta(data["processos_dir"])
        except (ValueError, OSError):
            pass
    return data


def save_config(data: dict) -> None:
    ensure_dirs()
    current = _read_config_file()
    incoming = dict(data)
    incoming.pop("key_from_env", None)
    current.update(incoming)
    current.pop("openai_api_key", None)
    current.pop("openai_model", None)
    current.pop("openai_base_url", None)
    current.pop("key_from_env", None)
    env_key = _env_key()
    if (current.get("api_key") or "").strip() == env_key:
        current["api_key"] = ""
    CONFIG.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


_NOMES_FALSOS = {
    "reclamante",
    "reclamado",
    "reclamada",
    "parte",
    "autor",
    "autora",
    "reu",
    "re",
    "requerente",
    "requerido",
    "requerida",
}


def slug(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return (text or "parte")[:max_len]


def parte_real(nome: str) -> str:
    """Nome digitado ou lido no PDF. Rótulo genérico ou frase de lei não conta."""
    n = re.sub(r"\s+", " ", (nome or "").strip())
    token = slug(n).lower() if n else ""
    if not token or token in _NOMES_FALSOS or len(token) < 3:
        return ""
    baixo = n.lower()
    if any(marca in baixo for marca in (" art.", " art ", "§", "cpc", "clt", "com base", "pressupost")):
        return ""
    if n[:1].islower() or len(n.split()) > 8:
        return ""
    return n


def folder_name(reclamante: str, reclamado: str, numero: str) -> str:
    n = re.sub(r"[^\d\.\-]", "", numero or "sem-numero") or "sem-numero"
    left = slug(parte_real(reclamante)) if parte_real(reclamante) else ""
    right = slug(parte_real(reclamado)) if parte_real(reclamado) else ""
    if left and right:
        return f"{left}_x_{right}_{n}"
    if left or right:
        return f"{left or right}_{n}"
    return f"processo_{n}"


def preservar_nomes(destino: dict, anterior: dict) -> None:
    """Não deixa uma releitura do PDF apagar o nome que a advogada gravou."""
    for key in ("reclamante", "reclamado"):
        real = parte_real((anterior or {}).get(key) or "")
        if real:
            destino[key] = real
        elif not parte_real((destino or {}).get(key) or ""):
            destino[key] = ""


def rename_case(case: Path, reclamante: str, reclamado: str, numero: str) -> Path:
    """A pasta passa a ter o nome das partes. Sem nome real, fica onde está."""
    if not parte_real(reclamante) and not parte_real(reclamado):
        return case
    novo = folder_name(reclamante, reclamado, numero)
    if novo == case.name:
        return case
    dest = PROCESSOS / novo
    if dest.exists():
        return case
    case.rename(dest)
    return dest


def copy_into_case(src: Path, meta: dict) -> Path:
    """Cria (ou reusa) a pasta do processo e grava/sobrepoe sempre o mesmo processo.pdf."""
    ensure_dirs()
    dest_dir = PROCESSOS / folder_name(
        meta.get("reclamante") or "",
        meta.get("reclamado") or "",
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


def _estado_publico(case_dir: Path) -> dict:
    import memory

    return memory.estado_publico(case_dir)


def list_cases(user_id: str | None = None) -> list[dict]:
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
        dono = meta.get("dono") or ""
        segredo = bool(meta.get("segredo"))
        if user_id:
            if dono and dono != user_id:
                continue
            if segredo and dono != user_id:
                continue
        elif segredo:
            continue
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
                "estado_pecas": _estado_publico(d),
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
