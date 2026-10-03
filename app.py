from __future__ import annotations

import io
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import acordaos
import contas
import docx_out
import sumulas
import extractor
import llm
import memory
import organizer
import prazos
from organizer import DEFAULT_CONFIG, PRESETS, web_mode
import prompts

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CACHE_NAME = "extrato.json"
EXTRACT_VERSION = 9
PRODUCT = "xThemis"
SITE_PASSWORD = (os.environ.get("SITE_PASSWORD") or "").strip()
JOBS: dict[str, dict] = {}

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


@app.middleware("http")
async def login_advogada(request: Request, call_next):
    path = request.url.path
    public = path in ("/api/health", "/health", "/api/entrar") or not path.startswith("/api/")
    user = contas.user_from_request(request)
    request.state.user = user
    if not public and contas.tem_usuarios() and not user and request.method != "OPTIONS":
        return Response(
            '{"detail":"Entre com seu nome e senha."}',
            status_code=401,
            media_type="application/json",
        )
    return await call_next(request)


def _uid(request: Request) -> str | None:
    user = getattr(request.state, "user", None) or {}
    return user.get("id")


def _nome(request: Request) -> str:
    user = getattr(request.state, "user", None) or {}
    return user.get("nome") or "local"

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
    "tutela": ("Tutela de urgência", prompts.prompt_tutela, "Tutela_Urgencia"),
    "execucao": ("Execução", prompts.prompt_execucao, "Execucao"),
    "embargos_execucao": ("Embargos à execução", prompts.prompt_embargos_execucao, "Embargos_Execucao"),
    "agravo_peticao": ("Agravo de petição", prompts.prompt_agravo_peticao, "Agravo_Peticao"),
    "agravo_instrumento": ("Agravo de instrumento", prompts.prompt_agravo_instrumento, "Agravo_Instrumento"),
    "revista": ("Recurso de revista", prompts.prompt_revista, "Recurso_Revista"),
    "quesitos": ("Quesitos", prompts.prompt_quesitos, "Quesitos"),
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
        "xThemis — informe a senha (Authorization Basic).",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="xThemis"'},
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


@app.get("/logo-xthemis.png")
def logo_xthemis():
    return FileResponse(STATIC / "logo-xthemis.png", media_type="image/png")


@app.get("/config.js")
def config_js():
    """Mesma origem: apiBase vazio."""
    body = (
        "window.HARVEY=window.HARVEY||{};"
        "window.HARVEY.apiBase=window.HARVEY.apiBase||'';"
        "window.HARVEY.product='xThemis';"
    )
    return Response(body, media_type="application/javascript")


@app.get("/api/config")
def get_config():
    cfg = organizer.load_config()
    key = cfg.get("api_key") or cfg.get("openai_api_key") or ""
    masked = ("••••" + key[-4:]) if len(key) >= 4 else ""
    return {
        "product": PRODUCT,
        "has_key": bool(key.strip()),
        "masked_key": masked,
        "key_from_env": bool(cfg.get("key_from_env")),
        "provider": cfg.get("provider") or DEFAULT_CONFIG["provider"],
        "provider_label": cfg.get("provider_label") or DEFAULT_CONFIG["provider_label"],
        "model": cfg.get("model") or cfg.get("openai_model") or DEFAULT_CONFIG["model"],
        "base_url": cfg.get("base_url") or DEFAULT_CONFIG["base_url"],
        "presets": PRESETS,
        "processos_dir": str(organizer.PROCESSOS),
        "aprendizado_global": str(memory.GLOBAL_FILE),
        "web_mode": web_mode(),
        "pasta_editavel": not web_mode(),
        "escritorio": cfg.get("escritorio") or "",
        "oab": cfg.get("oab") or "",
        "advogada": cfg.get("advogada") or "",
        "custo_estimado": (
            "Tudo gratuito no plano padrão: hosting free + Groq free. "
            "Gemini/OpenAI só se você colar chave paga."
        ),
    }


@app.post("/api/config")
def set_config(payload: dict):
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
    for campo in ("escritorio", "oab", "advogada"):
        if campo in payload:
            allowed[campo] = (payload.get(campo) or "").strip()
    if "processos_dir" in payload and not web_mode():
        try:
            allowed["processos_dir"] = organizer.usar_pasta(payload.get("processos_dir") or "")
        except ValueError as e:
            raise HTTPException(400, str(e))
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


def _adotar_nomes(case: Path, texto: str) -> Path:
    """Copia para a pasta o nome que a peça já leu nos autos."""
    path = case / "meta.json"
    meta: dict = {}
    if path.exists():
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    tem_a = bool(organizer.parte_real(meta.get("reclamante") or ""))
    tem_b = bool(organizer.parte_real(meta.get("reclamado") or ""))
    if tem_a and tem_b:
        return case
    ativo, passivo = extractor.partes_no_texto(texto or "")
    if not tem_a and ativo:
        meta["reclamante"] = ativo
    if not tem_b and passivo:
        meta["reclamado"] = passivo
    if (not tem_a and not ativo) and (not tem_b and not passivo):
        return case
    ex = meta.get("extrato")
    if not isinstance(ex, dict):
        ex = {}
        meta["extrato"] = ex
    if meta.get("reclamante"):
        ex["reclamante"] = meta["reclamante"]
    if meta.get("reclamado"):
        ex["reclamado"] = meta["reclamado"]
    numero = meta.get("numero") or ""
    if not numero:
        achado = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", case.name)
        if achado:
            numero = achado.group(0)
            meta["numero"] = numero
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    novo = organizer.rename_case(
        case,
        meta.get("reclamante") or "",
        meta.get("reclamado") or "",
        numero,
    )
    cache = novo / CACHE_NAME
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            cached.setdefault("meta", {}).update(
                {
                    "reclamante": meta.get("reclamante") or "",
                    "reclamado": meta.get("reclamado") or "",
                    "extrato": meta.get("extrato"),
                }
            )
            cache.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return novo


def _nomes_das_pecas() -> None:
    raiz = organizer.PROCESSOS
    if not raiz.exists():
        return
    for case in list(raiz.iterdir()):
        if not case.is_dir():
            continue
        ultima = memory.load_ultima(case) or {}
        if (ultima.get("texto") or "").strip():
            _adotar_nomes(case, ultima.get("texto") or "")


@app.get("/api/casos")
def casos(request: Request):
    _nomes_das_pecas()
    return organizer.list_cases(_uid(request))


@app.post("/api/entrar")
def entrar(payload: dict):
    try:
        return contas.entrar(
            payload.get("nome") or "",
            payload.get("senha") or "",
            criar=bool(payload.get("criar")),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/sair")
def sair(request: Request):
    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    contas.sair(token)
    return {"ok": True}


def _pode_convidar(request: Request) -> bool:
    if not contas.tem_usuarios():
        return True
    user = getattr(request.state, "user", None) or {}
    return bool(user.get("id")) and contas.acesso(user["id"]) == "dono"


@app.get("/api/eu")
def eu(request: Request):
    user = getattr(request.state, "user", None)
    if user and user.get("id"):
        nivel = contas.acesso(user["id"])
    elif not contas.tem_usuarios():
        nivel = "dono"
    else:
        nivel = ""
    return {
        "logado": bool(user),
        "exige_login": contas.tem_usuarios(),
        "nome": (user or {}).get("nome") or "",
        "acesso": nivel,
        "cobranca": "por_acao",
        "paga_acao": nivel == "avulso",
    }


@app.get("/api/convidados")
def get_convidados(request: Request):
    if not _pode_convidar(request):
        raise HTTPException(403, "Só quem distribui o acesso gratuito vê essa lista.")
    return {"convidados": contas.listar_convidados()}


@app.post("/api/convidados")
def post_convidado(request: Request, payload: dict):
    if not _pode_convidar(request):
        raise HTTPException(403, "Só quem distribui o acesso gratuito inclui convidado.")
    try:
        item = contas.adicionar_convidado(payload.get("nome") or "", payload.get("nota") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "convidado": item, "convidados": contas.listar_convidados()}


@app.post("/api/convidados/remover")
def del_convidado(request: Request, payload: dict):
    if not _pode_convidar(request):
        raise HTTPException(403, "Só quem distribui o acesso gratuito tira alguém da lista.")
    try:
        contas.remover_convidado(payload.get("id") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "convidados": contas.listar_convidados()}


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
    _sync_case_meta(case, data)
    try:
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return data


def _sync_case_meta(case: Path, data: dict) -> None:
    """Grava meta.json e preserva extrato editado pela advogada."""
    path = case / "meta.json"
    saved = {}
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            saved = {}
    meta = data.setdefault("meta", {})
    if saved.get("extrato_manual") and isinstance(saved.get("extrato"), dict):
        meta["extrato"] = saved["extrato"]
        meta["extrato_manual"] = True
        meta["cruzamento"] = (saved.get("extrato") or {}).get("verbas") or meta.get("cruzamento")
        for key in ("numero", "valor_causa", "autuacao"):
            if saved.get(key):
                meta[key] = saved[key]
    organizer.preservar_nomes(meta, saved)
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


@app.post("/api/extrato")
def salvar_extrato(payload: dict):
    case_id = payload.get("case_id")
    extrato = payload.get("extrato")
    if not case_id or not isinstance(extrato, dict):
        raise HTTPException(400, "Informe case_id e extrato.")
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    path = case / "meta.json"
    meta = {}
    if path.exists():
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    extrato["numero"] = (extrato.get("numero") or "").strip()
    extrato["reclamante"] = (extrato.get("reclamante") or "").strip()
    extrato["reclamado"] = (extrato.get("reclamado") or "").strip()
    extrato["valor_causa"] = (extrato.get("valor_causa") or "").strip()
    extrato["autuacao"] = (extrato.get("autuacao") or "").strip()
    verbas = extrato.get("verbas") if isinstance(extrato.get("verbas"), list) else []
    clean = []
    for row in verbas:
        if not isinstance(row, dict):
            continue
        clean.append(
            {
                "id": row.get("id") or "",
                "verba": (row.get("verba") or "").strip(),
                "condenado": row.get("condenado") if row.get("condenado") in ("sim", "nao", "incerto") else "incerto",
                "pago": row.get("pago") if row.get("pago") in ("sim", "nao") else "nao",
                "folhas_sentenca": row.get("folhas_sentenca") or [],
                "folhas_pago": row.get("folhas_pago") or [],
                "tese": (row.get("tese") or "").strip(),
            }
        )
    extrato["verbas"] = clean
    meta["extrato"] = extrato
    meta["extrato_manual"] = True
    meta["cruzamento"] = clean
    for key in ("numero", "reclamante", "reclamado", "valor_causa", "autuacao"):
        if extrato.get(key):
            meta[key] = extrato[key]
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    case = organizer.rename_case(
        case,
        meta.get("reclamante") or "",
        meta.get("reclamado") or "",
        meta.get("numero") or "",
    )
    path = case / "meta.json"
    cache = case / CACHE_NAME
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            cached.setdefault("meta", {}).update(
                {
                    "extrato": extrato,
                    "extrato_manual": True,
                    "cruzamento": clean,
                    "numero": meta.get("numero"),
                    "reclamante": meta.get("reclamante"),
                    "reclamado": meta.get("reclamado"),
                }
            )
            cache.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return {"ok": True, "meta": meta, "id": case.name, "path": str(case)}


@app.post("/api/fechar-peca")
def fechar_peca(case_id: str = Form(...)):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    try:
        estado = memory.fechar_peca(case)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "estado_pecas": estado}


@app.post("/api/reabrir-peca")
def reabrir_peca(case_id: str = Form(...), tipo: str = Form(...)):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    try:
        estado = memory.reabrir_peca(case, tipo)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "estado_pecas": estado}


@app.post("/api/importar")
async def importar(request: Request, arquivo: UploadFile = File(...)):
    """Novo processo (ou mesmo número): copia PDF → pasta nomeada → processo.pdf único."""
    organizer.ensure_dirs()
    tmp = organizer.HOME_APP / "_upload.pdf"
    raw = await arquivo.read()
    if len(raw) < 100:
        raise HTTPException(400, "Arquivo vazio.")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(400, "PDF grande demais para o plano gratuito (máx. ~80 MB).")
    if len(raw) > 25 * 1024 * 1024:
        job = secrets.token_hex(8)
        uid = _uid(request)
        JOBS[job] = {"status": "lendo"}

        def _fila(raw=raw, uid=uid, job=job):
            path = organizer.HOME_APP / f"_job_{job}.pdf"
            try:
                path.write_bytes(raw)
                JOBS[job] = {"status": "ok", "result": _salvar_import(path, uid)}
            except Exception as e:
                JOBS[job] = {"status": "erro", "detail": str(e)[:400]}
            finally:
                if path.exists():
                    path.unlink()

        threading.Thread(target=_fila, daemon=True).start()
        return {"ok": True, "job": job, "fila": True, "aviso": "PDF grande entrou na fila. A leitura continua em segundo plano."}
    tmp.write_bytes(raw)
    try:
        return _salvar_import(tmp, _uid(request))
    finally:
        if tmp.exists():
            tmp.unlink()


def _salvar_import(tmp: Path, uid: str | None) -> dict:
    data = extractor.extract_process(tmp)
    meta = data.setdefault("meta", {})
    meta["reclamante"] = organizer.parte_real(meta.get("reclamante") or "")
    meta["reclamado"] = organizer.parte_real(meta.get("reclamado") or "")
    meta["area"] = area_do_processo(meta, data.get("texto") or "")
    if meta["area"] != "trabalhista":
        meta["cruzamento"] = []
        if isinstance(meta.get("extrato"), dict):
            meta["extrato"]["verbas"] = []
            meta["extrato"]["reclamante"] = meta["reclamante"]
            meta["extrato"]["reclamado"] = meta["reclamado"]
    if uid:
        meta["dono"] = uid
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


@app.get("/api/job")
def job(id: str):
    item = JOBS.get(id)
    if not item:
        raise HTTPException(404, "Fila não encontrada.")
    return item


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
        organizer.preservar_nomes(merged, old_meta)
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


@app.post("/api/juntar-paginas")
async def juntar_paginas(case_id: str = Form(...), arquivo: UploadFile = File(...)):
    """Acrescenta só as páginas novas ao processo.pdf e relê o processo."""
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    base_pdf = case / "processo.pdf"
    if not base_pdf.exists():
        raise HTTPException(400, "Este processo ainda não tem processo.pdf.")
    raw = await arquivo.read()
    if len(raw) < 100:
        raise HTTPException(400, "Arquivo vazio.")
    extra = organizer.HOME_APP / "_paginas.pdf"
    merged = case / "_processo_junto.pdf"
    extra.write_bytes(raw)
    try:
        import fitz

        doc = fitz.open(base_pdf)
        novo = fitz.open(extra)
        antes = doc.page_count
        doc.insert_pdf(novo)
        doc.save(merged, garbage=4, deflate=True)
        doc.close()
        novo.close()
        merged.replace(base_pdf)
        data = extractor.extract_process(base_pdf)
        old = {}
        meta_path = case / "meta.json"
        if meta_path.exists():
            try:
                old = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                old = {}
        meta = {**old, **(data.get("meta") or {})}
        organizer.preservar_nomes(meta, old)
        meta["paginas"] = (data.get("meta") or {}).get("paginas")
        extracao = meta.setdefault("extracao", {})
        extracao["versao"] = EXTRACT_VERSION
        data["meta"] = meta
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (case / CACHE_NAME).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return {
            "ok": True,
            "id": case.name,
            "paginas_antes": antes,
            "paginas": meta.get("paginas"),
            "meta": meta,
        }
    finally:
        if extra.exists():
            extra.unlink()
        if merged.exists():
            merged.unlink()


def area_do_processo(meta: dict, texto: str) -> str:
    """Ramo da justiça pelo número CNJ e pelo texto do PDF. Sem escolha manual."""
    blob = " ".join(
        [
            str(meta.get("numero") or ""),
            str(meta.get("titulo") or ""),
            (texto or "")[:15000],
        ]
    )
    m = re.search(r"\d{7}-\d{2}\.\d{4}\.(\d)\.\d{2}\.\d{4}", blob)
    ramo = m.group(1) if m else ""
    u = blob.upper()
    if ramo == "5" or "VARA DO TRABALHO" in u or "RECLAMAÇÃO TRABALHISTA" in u or "RECLAMACAO TRABALHISTA" in u:
        return "trabalhista"
    if any(
        marca in u
        for marca in (
            "VARA DE FAMÍLIA",
            "VARA DE FAMILIA",
            "VARA DA FAMÍLIA",
            "VARA DA FAMILIA",
            "GUARDA COMPARTILHADA",
            "GUARDA UNILATERAL",
            "GUARDA DE FILH",
            "AÇÃO DE GUARDA",
            "ACAO DE GUARDA",
            "ALIMENTOS",
            "REGULAMENTAÇÃO DE CONVIV",
            "REGULAMENTACAO DE CONVIV",
            "DIVÓRCIO",
            "DIVORCIO",
        )
    ):
        return "familia"
    if "PREVIDENCI" in u or " INSS" in u:
        return "previdenciario"
    if ramo in ("4", "8"):
        return "civel"
    return "trabalhista"


def _build_user_prompt(
    case: Path,
    tipo: str,
    meta: dict,
    texto: str,
    extra: str = "",
    persona: str = "",
    area: str = "",
    prazo: str = "",
) -> str:
    learned = memory.combined_instructions(case, tipo, extra)
    area = area or area_do_processo(meta, texto)
    meta["area"] = area
    rows = ((meta.get("extrato") or {}).get("verbas")) or meta.get("cruzamento") or []
    cruz = ""
    if area == "trabalhista" and rows:
        cruz = "\n\n" + extractor.cruzamento_texto(rows)
        if meta.get("extrato_manual"):
            cruz += "\nExtrato corrigido pela advogada: priorize estes dados de capa e verbas.\n"
    cruz += prompts.bloco_lado(persona, area)
    if prazo:
        cruz += (
            f"\nPrazo informado: {prazo}. Trate como lembrete. "
            "A tempestividade se confere no PJe. Não garanta o prazo.\n"
        )
    cruz += "\n\n" + sumulas.bloco_biblioteca(texto) + "\n"
    _titulo, prompt_fn, _base = ACTION_MAP[tipo]
    if tipo == "personalizado":
        if not learned.strip() and not cruz:
            raise HTTPException(
                400,
                "No pedido personalizado, escreva no diálogo o que a IA deve fazer "
                "(ou use um aprendizado já salvo neste processo).",
            )
        return prompts.append_instrucoes(prompts.prompt_personalizado(meta, texto, learned) + cruz, "")
    base = prompt_fn(meta, texto) + cruz
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
        "fechada": False,
    }
    if texto_anterior is not None:
        payload["texto_anterior"] = texto_anterior
    memory.save_ultima(case, payload)
    memory.registrar_peca_aberta(case, payload)
    case = _adotar_nomes(case, body)
    return {
        **files,
        "refines": refines,
        "geracoes": geracoes,
        "segundos": segundos,
        "fechada": False,
        "case_id": case.name,
        "pasta": str(case),
    }


def _metrics_block(files: dict) -> dict:
    return {
        "refines": files.get("refines", 0),
        "geracoes": files.get("geracoes", 0),
        "segundos": files.get("segundos"),
    }


def _guard_nova_acao(case: Path, tipo: str) -> None:
    estado = memory.load_estado(case)
    aberta = estado.get("aberta")
    info_tipo = (estado.get("tipos") or {}).get(tipo) or {}
    if aberta:
        atual = (estado.get("tipos") or {}).get(aberta) or {}
        titulo = atual.get("titulo") or aberta
        if aberta == tipo:
            raise HTTPException(
                400,
                f"“{titulo}” ainda está aberta. Use Refinar para mudar o mesmo arquivo, "
                "ou marque Peça fechada.",
            )
        raise HTTPException(
            400,
            f"Feche “{titulo}” antes de começar outra ação.",
        )
    if info_tipo.get("fechada"):
        titulo = info_tipo.get("titulo") or tipo
        raise HTTPException(
            400,
            f"“{titulo}” já está fechada. Reabra essa peça para editar o mesmo arquivo.",
        )


@app.post("/api/acao")
def acao(
    request: Request,
    case_id: str = Form(...),
    tipo: str = Form(...),
    modo: str = Form("arquivos"),
    instrucoes_extra: str = Form(""),
    salvar_aprendizado: str = Form("1"),
    persona: str = Form(""),
    prazo: str = Form(""),
):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")

    if tipo not in ACTION_MAP:
        raise HTTPException(400, "Ação desconhecida.")
    _guard_nova_acao(case, tipo)

    extra = (instrucoes_extra or "").strip()
    learn = salvar_aprendizado not in ("0", "false", "False")
    if extra and learn:
        memory.append_learning(case, tipo, extra, also_global=True)

    data = _load_or_extract(case, refresh=True)
    meta = data.get("meta") or {}
    texto = data.get("texto") or ""
    titulo, _, base_name = ACTION_MAP[tipo]
    user_prompt = _build_user_prompt(
        case, tipo, meta, texto, "" if learn else extra, persona, area_do_processo(meta, texto), prazo
    )
    learned = memory.combined_instructions(case, tipo, "" if learn else extra)

    t0 = time.perf_counter()
    try:
        body = llm.complete(prompts.system_para(area_do_processo(meta, texto)), user_prompt)
    except llm.LlmError as e:
        raise HTTPException(400, str(e))
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, "Falha ao chamar o modelo.")
    segundos = round(time.perf_counter() - t0, 1)

    files = _persist_peca(
        case, tipo, titulo, body, base_name, learned, segundos=segundos, refine=False
    )
    if files.get("pasta"):
        case = Path(files["pasta"])
        try:
            gravado = json.loads((case / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            gravado = {}
        if gravado.get("reclamante"):
            meta["reclamante"] = gravado["reclamante"]
        if gravado.get("reclamado"):
            meta["reclamado"] = gravado["reclamado"]
    memory.auditar(case, _nome(request), "gerar", titulo)
    extra_resp = _sinais(body, meta, case)
    metrics = _metrics_block(files)

    pasta = files.get("pasta") or str(case)
    case_id = files.get("case_id") or case.name
    if modo == "chat":
        return {
            "ok": True,
            "modo": "chat",
            "titulo": titulo,
            "texto": body,
            "meta": meta,
            "id": case_id,
            "pasta": pasta,
            "arquivos": files,
            "prompts_usados": learned,
            "sugestao_arquivo": files["docx"],
            **metrics,
            **extra_resp,
        }

    return {
        "ok": True,
        "modo": "arquivos",
        "titulo": titulo,
        "texto": body,
        "arquivo_docx": files["docx"],
        "arquivo_pdf": files["pdf"],
        "id": case_id,
        "pasta": pasta,
        "meta": meta,
        "prompts_usados": learned,
        **metrics,
        **extra_resp,
    }


@app.post("/api/refinar")
def refinar(
    request: Request,
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
    if memory.load_estado(case).get("aberta") != (ultima.get("tipo") or ""):
        raise HTTPException(
            400,
            "Essa peça está fechada. Reabra para continuar no mesmo arquivo.",
        )

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
        body = llm.complete(prompts.system_para(area_do_processo(meta, texto_autos)), refine_prompt)
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
    if files.get("pasta"):
        case = Path(files["pasta"])
    memory.auditar(case, _nome(request), "refinar", titulo)
    return {
        "ok": True,
        "titulo": titulo,
        "texto": body,
        "texto_anterior": texto_anterior,
        "arquivo_docx": files["docx"],
        "arquivo_pdf": files["pdf"],
        "id": case.name,
        "pasta": str(case),
        "prompts_usados": learned,
        **_metrics_block(files),
        **_sinais(body, meta, case),
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
    if files.get("pasta"):
        case = Path(files["pasta"])
    return {"ok": True, "arquivo": files["docx"], "pdf": files["pdf"], "id": case.name, "pasta": str(case)}


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


@app.post("/api/conferir-sumulas")
def conferir_sumulas(texto: str = Form(...)):
    base = sumulas.conferir(texto)
    ac = acordaos.conferir(texto)
    base["acordaos"] = ac["encontrados"]
    base["acordaos_ausentes"] = ac["ausentes"]
    base["avisos"] = (base.get("avisos") or []) + ac["avisos"]
    return base


@app.post("/api/prazo")
def prazo_calc(
    data: str = Form(...),
    modo: str = Form("ciencia"),
    tipo: str = Form("recurso"),
    dias: str = Form(""),
    comarca: str = Form(""),
    case_id: str = Form(""),
):
    try:
        n = int(dias) if (dias or "").strip() else None
    except ValueError:
        raise HTTPException(400, "Dias úteis inválidos.")
    if (case_id or "").strip():
        try:
            case = organizer.case_dir(case_id.strip())
            loaded = _load_or_extract(case, refresh=False)
            comarca = prazos.comarca_do_processo(loaded.get("meta") or {}, loaded.get("texto") or "")
        except Exception:
            comarca = ""
    if comarca not in prazos.COMARCAS:
        comarca = "regional"
    try:
        return prazos.calcular(data, modo, tipo, n, comarca)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _sinais(texto: str, meta: dict, case: Path) -> dict:
    checagem = sumulas.conferir(texto or "")
    avisos = checagem["avisos"]
    indice = meta.get("indice") or []
    tipos = " ".join(
        (item.get("tipo") if isinstance(item, dict) else str(item)) for item in indice
    ).upper()
    estado = memory.estado_publico(case)
    fechadas = {k for k, v in (estado.get("tipos") or {}).items() if v.get("fechada")}
    sugestao = ""
    if "SENTEN" in tipos and "recurso" not in fechadas and not estado.get("aberta"):
        sugestao = "Há sentença no índice e o recurso ainda não está fechado. Próxima peça sugerida: Recurso Ordinário."
    rows = ((meta.get("extrato") or {}).get("verbas")) or meta.get("cruzamento") or []
    risco = extractor.estrategia_acordo(rows) if rows else ""
    camadas = meta.get("camadas") or {}
    return {
        "jurisprudencia_avisos": avisos,
        "jurisprudencia_conferidas": checagem["conferidas"],
        "sugestao_proxima": sugestao,
        "risco_acordo": risco,
        "camadas": camadas,
    }


@app.get("/api/folha")
def folha(case_id: str, pagina: int):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    cache = case / CACHE_NAME
    if not cache.exists():
        return {"ok": False, "trecho": "Ainda não há extrato. Gere ou importe de novo."}
    data = json.loads(cache.read_text(encoding="utf-8"))
    texto = data.get("texto") or ""
    marker = f"===== PAGINA {pagina} ====="
    if marker not in texto:
        return {"ok": False, "pagina": pagina, "trecho": "Esta folha não entrou no extrato lido."}
    part = texto.split(marker, 1)[1]
    nxt = part.find("===== PAGINA ")
    trecho = (part[:nxt] if nxt > 0 else part)[:2200].strip()
    return {"ok": True, "pagina": pagina, "trecho": trecho}


@app.get("/api/camadas")
def camadas(case_id: str):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    cache = case / CACHE_NAME
    if not cache.exists():
        return {"capa": "", "sentenca": "", "provas": ""}
    data = json.loads(cache.read_text(encoding="utf-8"))
    meta = data.get("meta") or {}
    layers = meta.get("camadas") or {}
    if layers:
        return layers
    texto = data.get("texto") or ""

    def _apos(titulo: str) -> str:
        if titulo not in texto:
            return ""
        return texto.split(titulo, 1)[1][:1800]

    return {
        "capa": texto[:1400],
        "sentenca": _apos("SENTENÇA"),
        "provas": _apos("COMPROVANTES"),
    }


@app.post("/api/segredo")
def segredo(case_id: str = Form(...), ligado: str = Form("1")):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    meta_path = case / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["segredo"] = ligado not in ("0", "false", "False")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "segredo": meta["segredo"]}


@app.post("/api/excluir")
def excluir(request: Request, case_id: str = Form(...)):
    """Apaga a pasta do processo neste servidor (LGPD: exclusão a pedido)."""
    import shutil

    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    numero = ""
    meta_path = case / "meta.json"
    if meta_path.exists():
        try:
            numero = json.loads(meta_path.read_text(encoding="utf-8")).get("numero") or ""
        except Exception:
            numero = ""
    memory.registrar_exclusao(_nome(request), case.name, numero)
    memory.auditar(case, _nome(request), "excluir", case.name)
    shutil.rmtree(case)
    return {"ok": True}


@app.get("/api/exclusoes")
def exclusoes(request: Request):
    if not _pode_convidar(request):
        raise HTTPException(403, "Só quem distribui o acesso vê o registro de exclusões.")
    return {"exclusoes": memory.listar_exclusoes()}


@app.get("/api/auditoria")
def auditoria(case_id: str):
    try:
        case = organizer.case_dir(case_id)
    except Exception:
        raise HTTPException(404, "Processo não encontrado.")
    path = case / "auditoria.jsonl"
    if not path.exists():
        return {"linhas": []}
    linhas = []
    for line in path.read_text(encoding="utf-8").splitlines()[-40:]:
        try:
            linhas.append(json.loads(line))
        except Exception:
            continue
    return {"linhas": linhas}


if __name__ == "__main__":
    import webbrowser

    import uvicorn

    organizer.ensure_dirs()
    port = int(os.environ.get("PORT", "8765"))
    if os.environ.get("NO_BROWSER") != "1" and not web_mode():
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
