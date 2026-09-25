from __future__ import annotations

import io
import json
import os
import secrets
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import docx_out
import extractor
import llm
import memory
import organizer
from organizer import DEFAULT_CONFIG, PRESETS, web_mode
import prompts

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE_NAME = "extrato.json"
EXTRACT_VERSION = 3
PRODUCT = "Harvey.ai"
SITE_PASSWORD = (os.environ.get("SITE_PASSWORD") or "").strip()

app = FastAPI(title=PRODUCT, version="1.0.0")

# Front em 3n20.com.br/harvey → API neste host (Render/HF)
_cors = os.environ.get("CORS_ORIGINS", "https://3n20.com.br,http://127.0.0.1:8765,http://localhost:8765")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors.split(",") if o.strip()] + ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ui", StaticFiles(directory=STATIC), name="static")

ACTION_MAP = {
    "resumo": ("Resumo do processo", prompts.prompt_resumo, "Resumo_Processo"),
    "jurisprudencia": ("Jurisprudência pertinente", prompts.prompt_jurisprudencia, "Jurisprudencia"),
    "recurso": ("Recurso Ordinário", prompts.prompt_recurso, "Recurso_Ordinario"),
    "defesa": ("Contestação", prompts.prompt_defesa, "Contestacao"),
    "contrarrazoes": ("Contrarrazões", prompts.prompt_contrarrazoes, "Contrarrazoes"),
    "replica": ("Réplica", prompts.prompt_replica, "Replica"),
    "alegacoes_finais": ("Alegações finais", prompts.prompt_alegacoes_finais, "Alegacoes_Finais"),
    "embargos": ("Embargos de declaração", prompts.prompt_embargos, "Embargos_Declaracao"),
    "impugnacao_laudo": ("Impugnação ao laudo", prompts.prompt_impugnacao_laudo, "Impugnacao_Laudo"),
    "impugnacao_calculos": ("Impugnação aos cálculos", prompts.prompt_impugnacao_calculos, "Impugnacao_Calculos"),
    "manifestacao": ("Manifestação", prompts.prompt_manifestacao, "Manifestacao"),
    "acordo": ("Minuta de acordo", prompts.prompt_acordo, "Minuta_Acordo"),
    "peticao": ("Petição intermediária", prompts.prompt_peticao, "Peticao"),
    "personalizado": ("Pedido personalizado", None, "Peca_Personalizada"),
}


@app.middleware("http")
async def optional_site_password(request: Request, call_next):
    if not SITE_PASSWORD:
        return await call_next(request)
    if request.url.path in ("/api/health", "/health"):
        return await call_next(request)
    auth = request.headers.get("Authorization") or ""
    cookie = request.cookies.get("harvey_gate") or ""
    expected = secrets.compare_digest(cookie, SITE_PASSWORD) if cookie else False
    if auth.startswith("Basic "):
        import base64

        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8")
            _user, pwd = decoded.split(":", 1)
            expected = secrets.compare_digest(pwd, SITE_PASSWORD)
        except Exception:
            expected = False
    if expected:
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return Response('{"detail":"senha do site"}', status_code=401, media_type="application/json")
    return Response(
        "Harvey.ai — informe a senha (Authorization Basic).",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Harvey.ai"'},
    )


@app.get("/health")
@app.get("/api/health")
def health():
    return {"ok": True, "product": PRODUCT, "web": web_mode()}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/styles.css")
def styles_css():
    return FileResponse(STATIC / "styles.css", media_type="text/css")


@app.get("/app.js")
def app_js():
    return FileResponse(STATIC / "app.js", media_type="application/javascript")


@app.get("/config.js")
def config_js():
    """Mesma origem: apiBase vazio."""
    body = (
        "window.HARVEY=window.HARVEY||{};"
        "window.HARVEY.apiBase=window.HARVEY.apiBase||'';"
        "window.HARVEY.product='Harvey.ai';"
    )
    return Response(body, media_type="application/javascript")


@app.get("/api/config")
def get_config():
    cfg = organizer.load_config()
    key = cfg.get("api_key") or cfg.get("openai_api_key") or ""
    masked = ("••••" + key[-4:]) if len(key) >= 4 else ""
    env_locked = bool(
        (os.environ.get("API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip()
    )
    return {
        "product": PRODUCT,
        "has_key": bool(key.strip()),
        "masked_key": masked,
        "key_from_env": env_locked,
        "provider": cfg.get("provider") or DEFAULT_CONFIG["provider"],
        "provider_label": cfg.get("provider_label") or DEFAULT_CONFIG["provider_label"],
        "model": cfg.get("model") or cfg.get("openai_model") or DEFAULT_CONFIG["model"],
        "base_url": cfg.get("base_url") or DEFAULT_CONFIG["base_url"],
        "presets": PRESETS,
        "processos_dir": str(organizer.PROCESSOS),
        "aprendizado_global": str(memory.GLOBAL_FILE),
        "web_mode": web_mode(),
        "custo_estimado": (
            "Tudo gratuito no plano padrão: hosting free + Groq free. "
            "Gemini/OpenAI só se você colar chave paga."
        ),
    }


@app.post("/api/config")
def set_config(payload: dict):
    if (os.environ.get("API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip():
        # Em produção a chave fica no servidor; UI pode mudar só modelo/preset
        payload = {k: v for k, v in payload.items() if k != "api_key"}
    allowed = {}
    if "api_key" in payload:
        allowed["api_key"] = (payload.get("api_key") or "").strip()
    elif "openai_api_key" in payload:
        allowed["api_key"] = (payload.get("openai_api_key") or "").strip()
    if "model" in payload:
        allowed["model"] = payload.get("model") or DEFAULT_CONFIG["model"]
    if "provider" in payload:
        allowed["provider"] = payload.get("provider")
    if "provider_label" in payload:
        allowed["provider_label"] = payload.get("provider_label")
    if "base_url" in payload:
        allowed["base_url"] = (payload.get("base_url") or DEFAULT_CONFIG["base_url"]).rstrip("/")
    if "preset" in payload and payload["preset"] in PRESETS:
        p = PRESETS[payload["preset"]]
        allowed.update(
            {
                "provider": p["provider"],
                "provider_label": p["provider_label"],
                "model": p["model"],
                "base_url": p["base_url"],
            }
        )
    organizer.save_config(allowed)
    return get_config()


@app.get("/api/casos")
def casos():
    return organizer.list_cases()


def _load_or_extract(case: Path, *, refresh: bool = False) -> dict:
    cache = case / CACHE_NAME
    pdf = case / "processo.pdf"
    if not pdf.exists():
        raise HTTPException(400, "PDF do processo não está na pasta.")

    if not refresh and cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            ver = (cached.get("meta") or {}).get("extracao", {}).get("versao")
            if ver == EXTRACT_VERSION:
                return cached
        except Exception:
            pass

    data = extractor.extract_process(pdf)
    meta = data.setdefault("meta", {})
    extracao = meta.get("extracao") or {}
    extracao["versao"] = EXTRACT_VERSION
    meta["extracao"] = extracao
    try:
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return data


@app.post("/api/importar")
async def importar(arquivo: UploadFile = File(...)):
    """Novo processo (ou mesmo número): copia PDF → pasta nomeada → processo.pdf único."""
    organizer.ensure_dirs()
    tmp = organizer.HOME_APP / "_upload.pdf"
    raw = await arquivo.read()
    if len(raw) < 100:
        raise HTTPException(400, "Arquivo vazio.")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(400, "PDF grande demais para o plano gratuito (máx. ~80 MB).")
    tmp.write_bytes(raw)
    try:
        data = extractor.extract_process(tmp)
        dest = organizer.copy_into_case(tmp, data["meta"])
        extracao = data.setdefault("meta", {}).get("extracao") or {}
        extracao["versao"] = EXTRACT_VERSION
        data["meta"]["extracao"] = extracao
        (dest / CACHE_NAME).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if not (dest / memory.PROMPTS_CASE).exists():
            memory.save_case_prompts(dest, memory.load_case_prompts(dest))
        return {
            "ok": True,
            "id": dest.name,
            "path": str(dest),
            "meta": data["meta"],
            "processo_pdf": "processo.pdf",
            "modo": "unico_processo_pdf",
        }
    finally:
        if tmp.exists():
            tmp.unlink()


@app.post("/api/atualizar-processo")
async def atualizar_processo(case_id: str = Form(...), arquivo: UploadFile = File(...)):
    """Tribunal incluiu páginas: sobrepõe o processo.pdf desta pasta (sem segunda cópia)."""
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")

    raw = await arquivo.read()
    if len(raw) < 100:
        raise HTTPException(400, "Arquivo vazio.")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(400, "PDF grande demais (máx. ~80 MB).")

    tmp = organizer.HOME_APP / "_upload_update.pdf"
    tmp.write_bytes(raw)
    try:
        data = extractor.extract_process(tmp)
        meta = data.get("meta") or {}
        # mantém pasta atual; só troca os autos
        old_meta = {}
        meta_path = case / "meta.json"
        if meta_path.exists():
            try:
                old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                old_meta = {}
        merged = {**old_meta, **meta}
        organizer.overwrite_processo_pdf(case, tmp, merged)
        extracao = merged.setdefault("extracao", {})
        extracao["versao"] = EXTRACT_VERSION
        data["meta"] = merged
        (case / CACHE_NAME).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "id": case.name,
            "path": str(case),
            "meta": merged,
            "processo_pdf": "processo.pdf",
            "sobrescrito": True,
        }
    finally:
        if tmp.exists():
            tmp.unlink()


def _build_user_prompt(case: Path, tipo: str, meta: dict, texto: str, extra: str = "") -> str:
    learned = memory.combined_instructions(case, tipo, extra)
    _titulo, prompt_fn, _base = ACTION_MAP[tipo]
    if tipo == "personalizado":
        if not learned.strip():
            raise HTTPException(
                400,
                "No pedido personalizado, escreva no diálogo o que a IA deve fazer "
                "(ou use um aprendizado já salvo neste processo).",
            )
        return prompts.prompt_personalizado(meta, texto, learned)
    base = prompt_fn(meta, texto)
    return prompts.append_instrucoes(base, learned)


def _persist_peca(
    case: Path,
    tipo: str,
    titulo: str,
    body: str,
    base_name: str,
    instrucoes: str,
    *,
    segundos: float | None = None,
    refine: bool = False,
    texto_anterior: str | None = None,
) -> dict:
    files = docx_out.save_peca(body, case, base_name, title=titulo)
    prev = memory.load_ultima(case) or {}
    same = prev.get("tipo") == tipo and prev.get("base") == files["base"]
    refines = int(prev.get("refines") or 0)
    if refine and same:
        refines += 1
    elif not same:
        refines = 0
    geracoes = int(prev.get("geracoes") or 0)
    if not refine:
        geracoes = (geracoes + 1) if same else 1
    else:
        geracoes = geracoes or 1
    # limpa datetime gambiarra do persist
    payload = {
        "tipo": tipo,
        "titulo": titulo,
        "texto": body,
        "base": files["base"],
        "docx": files["docx"],
        "pdf": files["pdf"],
        "instrucoes": instrucoes,
        "refines": refines,
        "geracoes": geracoes,
        "segundos": segundos,
        "atualizado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    if texto_anterior is not None:
        payload["texto_anterior"] = texto_anterior
    memory.save_ultima(case, payload)
    return {**files, "refines": refines, "geracoes": geracoes, "segundos": segundos}


def _metrics_block(files: dict) -> dict:
    return {
        "refines": files.get("refines", 0),
        "geracoes": files.get("geracoes", 0),
        "segundos": files.get("segundos"),
    }


@app.post("/api/acao")
def acao(
    case_id: str = Form(...),
    tipo: str = Form(...),
    modo: str = Form("arquivos"),
    instrucoes_extra: str = Form(""),
    salvar_aprendizado: str = Form("1"),
):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")

    if tipo not in ACTION_MAP:
        raise HTTPException(400, "Ação desconhecida.")

    extra = (instrucoes_extra or "").strip()
    learn = salvar_aprendizado not in ("0", "false", "False")
    if extra and learn:
        memory.append_learning(case, tipo, extra, also_global=True)

    data = _load_or_extract(case, refresh=True)
    meta = data.get("meta") or {}
    texto = data.get("texto") or ""
    titulo, _, base_name = ACTION_MAP[tipo]
    user_prompt = _build_user_prompt(case, tipo, meta, texto, "" if learn else extra)
    learned = memory.combined_instructions(case, tipo, "" if learn else extra)

    t0 = time.perf_counter()
    try:
        body = llm.complete(prompts.SYSTEM, user_prompt)
    except llm.LlmError as e:
        raise HTTPException(400, str(e))
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, "Falha ao chamar o modelo.")
    segundos = round(time.perf_counter() - t0, 1)

    files = _persist_peca(
        case, tipo, titulo, body, base_name, learned, segundos=segundos, refine=False
    )
    metrics = _metrics_block(files)

    if modo == "chat":
        return {
            "ok": True,
            "modo": "chat",
            "titulo": titulo,
            "texto": body,
            "meta": meta,
            "pasta": str(case),
            "arquivos": files,
            "prompts_usados": learned,
            "sugestao_arquivo": files["docx"],
            **metrics,
        }

    return {
        "ok": True,
        "modo": "arquivos",
        "titulo": titulo,
        "texto": body,
        "arquivo_docx": files["docx"],
        "arquivo_pdf": files["pdf"],
        "pasta": str(case),
        "meta": meta,
        "prompts_usados": learned,
        **metrics,
    }


@app.post("/api/refinar")
def refinar(
    case_id: str = Form(...),
    feedback: str = Form(...),
    salvar_aprendizado: str = Form("1"),
):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")

    fb = (feedback or "").strip()
    if not fb:
        raise HTTPException(400, "Escreva o que faltou ou o que deve mudar.")

    ultima = memory.load_ultima(case)
    if not ultima or not ultima.get("texto"):
        raise HTTPException(400, "Não há peça gerada neste processo para refinar. Gere uma ação antes.")

    tipo = ultima.get("tipo") or "personalizado"
    titulo = ultima.get("titulo") or "Peça"
    base_name = ultima.get("base") or "Peca"

    if salvar_aprendizado not in ("0", "false", "False"):
        memory.append_learning(case, tipo, fb, also_global=True)

    data = _load_or_extract(case, refresh=False)
    meta = data.get("meta") or {}
    texto_autos = data.get("texto") or ""
    learned = memory.combined_instructions(case, tipo, "")

    refine_prompt = f"""Reescreva a peça abaixo aplicando o feedback do advogado.
Mantenha estrutura forense completa, pronta para protocolar.
Não invente fatos fora dos autos. Se precisar de prova não encontrada, diga NÃO CONSTA DO EXTRATO LIDO.

FEEDBACK DO ADVOGADO (obrigatório incorporar):
{fb}

APRENDIZADOS JÁ SALVOS PARA ESTE TIPO/PROCESSO:
{learned or "(nenhum)"}

PEÇA ATUAL:
{ultima["texto"]}

TRECHOS DOS AUTOS (para conferência):
{texto_autos[:180000]}

Capa/meta: {meta}

{prompts.CHECKLIST_HINT}
"""
    texto_anterior = ultima.get("texto") or ""
    t0 = time.perf_counter()
    try:
        body = llm.complete(prompts.SYSTEM, refine_prompt)
    except llm.LlmError as e:
        raise HTTPException(400, str(e))
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, "Falha ao refinar com o modelo.")
    segundos = round(time.perf_counter() - t0, 1)

    files = _persist_peca(
        case,
        tipo,
        titulo,
        body,
        base_name,
        learned,
        segundos=segundos,
        refine=True,
        texto_anterior=texto_anterior,
    )
    return {
        "ok": True,
        "titulo": titulo,
        "texto": body,
        "texto_anterior": texto_anterior,
        "arquivo_docx": files["docx"],
        "arquivo_pdf": files["pdf"],
        "pasta": str(case),
        "prompts_usados": learned,
        **_metrics_block(files),
    }


@app.get("/api/prompts")
def get_prompts(case_id: str):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    return {
        "caso": memory.load_case_prompts(case),
        "global": memory.load_global(),
        "ultima": memory.load_ultima(case),
        "combinado_exemplo": {
            t: memory.combined_instructions(case, t, "")
            for t in ("recurso", "defesa", "resumo")
        },
    }


@app.post("/api/prompts")
def post_prompts(payload: dict):
    case_id = payload.get("case_id")
    texto = (payload.get("texto") or "").strip()
    tipo = payload.get("tipo") or "geral"
    also_global = payload.get("also_global", True)
    if not case_id or not texto:
        raise HTTPException(400, "Informe case_id e texto.")
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    data = memory.append_learning(case, tipo, texto, also_global=bool(also_global))
    return {"ok": True, "caso": data, "global": memory.load_global()}


@app.post("/api/salvar-docx")
def salvar_docx(payload: dict):
    case_id = payload.get("case_id")
    texto = payload.get("texto") or ""
    nome = payload.get("nome") or "Peca.docx"
    titulo = payload.get("titulo") or ""
    tipo = payload.get("tipo") or "personalizado"
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    files = _persist_peca(case, tipo, titulo, texto, nome, "")
    return {"ok": True, "arquivo": files["docx"], "pdf": files["pdf"], "pasta": str(case)}


@app.get("/api/download")
def download(case_id: str, arquivo: str):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    name = Path(arquivo).name
    path = (case / name).resolve()
    if case.resolve() not in path.parents and path != case.resolve():
        raise HTTPException(400, "Arquivo inválido.")
    if not path.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(path, filename=name)


@app.get("/api/baixar-pasta")
def baixar_pasta(case_id: str):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in case.iterdir():
            if p.is_file() and p.name != CACHE_NAME:
                zf.write(p, arcname=p.name)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{case_id}.zip"'},
    )


@app.get("/api/abrir-pasta")
def abrir_pasta(case_id: str):
    """Local: abre Finder/Explorer. Web: use /api/baixar-pasta."""
    if web_mode():
        raise HTTPException(400, "Na web, use Baixar pasta (ZIP).")
    case = organizer.case_dir(case_id)
    if sys.platform.startswith("win"):
        os.startfile(case)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(case)])
    else:
        subprocess.Popen(["xdg-open", str(case)])
    return {"ok": True}


if __name__ == "__main__":
    import webbrowser

    import uvicorn

    organizer.ensure_dirs()
    port = int(os.environ.get("PORT", "8765"))
    if os.environ.get("NO_BROWSER") != "1" and not web_mode():
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
