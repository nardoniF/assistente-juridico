const lista = document.getElementById("lista");
const pdf = document.getElementById("pdf");
const dropzone = document.getElementById("dropzone");
const importStatus = document.getElementById("import-status");
const acoesWrap = document.getElementById("acoes-wrap");
const emptyState = document.getElementById("empty-state");
const casoAtual = document.getElementById("caso-atual");
const casoTitulo = document.getElementById("caso-titulo");
const stageEyebrow = document.getElementById("stage-eyebrow");
const stageActions = document.getElementById("stage-actions");
const chatWrap = document.getElementById("chat-wrap");
const chat = document.getElementById("chat");
const chatTitulo = document.getElementById("chat-titulo");
const arquivosGerados = document.getElementById("arquivos-gerados");
const metricsLine = document.getElementById("metrics-line");
const checklistWrap = document.getElementById("checklist-wrap");
const checklistEl = document.getElementById("checklist");
const diffWrap = document.getElementById("diff-wrap");
const diffBefore = document.getElementById("diff-before");
const diffAfter = document.getElementById("diff-after");
const ajustes = document.getElementById("ajustes");
const promptsBox = document.getElementById("prompts-box");
const busy = document.getElementById("busy");
const busyText = document.getElementById("busy-text");
const busySteps = document.getElementById("busy-steps");
const toastEl = document.getElementById("toast");
const busca = document.getElementById("busca-casos");

let selected = null;
let lastResult = null;
let lastTipo = null;
let configCache = null;
let allCasos = [];
let toastTimer = null;
let busyTimer = null;
let busyStepIdx = 0;

const STAGES = {
  importar: [
    "Recebendo o PDF…",
    "Lendo capa e partes…",
    "Criando pasta do processo…",
    "Gravando processo.pdf único…",
  ],
  atualizar: [
    "Recebendo autos novos…",
    "Sobrepondo processo.pdf…",
    "Limpando cache do extrato…",
    "Pronto para a próxima peça…",
  ],
  gerar: [
    "1/4 Lendo e indexando os autos…",
    "2/4 Montando o prompt forense…",
    "3/4 IA redigindo a peça…",
    "4/4 Gravando Word + PDF…",
  ],
  refinar: [
    "1/4 Lendo a peça atual…",
    "2/4 Incorporando seu feedback…",
    "3/4 IA reescrevendo (mesmo arquivo)…",
    "4/4 Sobrepondo Word + PDF…",
  ],
};

let pastaHandle = null;

function dbPasta() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("xthemis-pasta", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("kv");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function lerPastaHandle() {
  if (pastaHandle) return pastaHandle;
  try {
    const db = await dbPasta();
    pastaHandle = await new Promise((resolve, reject) => {
      const tx = db.transaction("kv", "readonly");
      const q = tx.objectStore("kv").get("dir");
      q.onsuccess = () => resolve(q.result || null);
      q.onerror = () => reject(q.error);
    });
  } catch (e) {
    pastaHandle = null;
  }
  return pastaHandle;
}

async function salvarPastaHandle(handle) {
  pastaHandle = handle;
  const db = await dbPasta();
  await new Promise((resolve, reject) => {
    const tx = db.transaction("kv", "readwrite");
    tx.objectStore("kv").put(handle, "dir");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

function mostrarPastaLocal(nome) {
  const caminho = document.getElementById("pasta-caminho");
  const campo = document.getElementById("pasta-processos");
  if (caminho) caminho.textContent = "Pasta neste Mac: " + nome;
  if (campo) campo.value = nome;
}

async function escolherPasta() {
  if (!window.showDirectoryPicker) {
    toast("Abra no Chrome para escolher a pasta.");
    return;
  }
  try {
    let handle;
    try {
      handle = await window.showDirectoryPicker({ mode: "readwrite", id: "xthemis-processos" });
    } catch (err) {
      if (err && err.name === "AbortError") return;
      handle = await window.showDirectoryPicker({ mode: "readwrite" });
    }
    await salvarPastaHandle(handle);
    mostrarPastaLocal(handle.name);
    toast("Pasta escolhida: " + handle.name);
  } catch (e) {
    if (e && e.name === "AbortError") return;
    toast("Não abri a pasta.");
  }
}

async function pastaComPermissao() {
  const handle = await lerPastaHandle();
  if (!handle) return null;
  let perm = "prompt";
  try {
    perm = await handle.queryPermission({ mode: "readwrite" });
    if (perm !== "granted") perm = await handle.requestPermission({ mode: "readwrite" });
  } catch (e) {
    return null;
  }
  return perm === "granted" ? handle : null;
}

async function gravarArquivoNaPasta(caseId, nomeArquivo) {
  const raiz = await pastaComPermissao();
  if (!raiz || !caseId || !nomeArquivo) return false;
  const r = await fetch(
    apiUrl(
      "/api/download?case_id=" +
        encodeURIComponent(caseId) +
        "&arquivo=" +
        encodeURIComponent(nomeArquivo)
    )
  );
  if (!r.ok) return false;
  const dir = await raiz.getDirectoryHandle(caseId, { create: true });
  const file = await dir.getFileHandle(nomeArquivo, { create: true });
  const w = await file.createWritable();
  await w.write(await r.blob());
  await w.close();
  return true;
}

async function espelharCaso(caseId, arquivos, silencioso) {
  const nomes = [...new Set(["processo.pdf", ...(arquivos || [])].filter(Boolean))];
  if (!(await lerPastaHandle())) return;
  try {
    let ok = 0;
    for (const nome of nomes) {
      if (await gravarArquivoNaPasta(caseId, nome)) ok += 1;
    }
    if (ok && !silencioso) toast("Copiado para a pasta do Mac.");
  } catch (e) {
    if (!silencioso) toast("A pasta do Mac não recebeu o arquivo.");
  }
}

async function espelharGlobal() {
  const raiz = await pastaComPermissao();
  if (!raiz) return false;
  const r = await fetch(apiUrl("/api/aprendizado-global"));
  if (!r.ok) return false;
  const file = await raiz.getFileHandle("Aprendizado_global.txt", { create: true });
  const w = await file.createWritable();
  await w.write(await r.blob());
  await w.close();
  return true;
}

function apiUrl(path) {
  const base = ((window.HARVEY && window.HARVEY.apiBase) || "").replace(/\/$/, "");
  return base + path;
}

const _fetch = window.fetch.bind(window);
window.fetch = (url, opts) => {
  opts = opts ? { ...opts } : {};
  const token = localStorage.getItem("harvey_token");
  if (token && String(url).includes("/api/")) {
    const headers = new Headers(opts.headers || {});
    if (!headers.has("Authorization")) headers.set("Authorization", "Bearer " + token);
    opts.headers = headers;
  }
  return _fetch(url, opts);
};

function toast(msg, ms = 4200) {
  toastEl.hidden = false;
  toastEl.textContent = msg;
  requestAnimationFrame(() => toastEl.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.classList.remove("show");
    setTimeout(() => {
      toastEl.hidden = true;
    }, 250);
  }, ms);
}

function renderBusySteps(stages, activeIdx) {
  busySteps.innerHTML = "";
  stages.forEach((label, i) => {
    const li = document.createElement("li");
    li.textContent = label;
    if (i < activeIdx) li.className = "done";
    if (i === activeIdx) li.className = "active";
    busySteps.appendChild(li);
  });
}

function setBusy(on, text, stageKey) {
  clearInterval(busyTimer);
  busyTimer = null;
  busy.hidden = !on;
  document.querySelectorAll("#comando button[data-tipo], #btn-refinar, #btn-conversar, #btn-guardar-aprendizado").forEach((b) => {
    b.disabled = on;
  });
  if (!on) {
    busySteps.innerHTML = "";
    if (selected) applyLock(selected.estado_pecas);
    return;
  }
  const stages = STAGES[stageKey] || [text || "Trabalhando…"];
  busyStepIdx = 0;
  busyText.textContent = text || stages[0];
  renderBusySteps(stages, 0);
  if (stages.length > 1) {
    busyTimer = setInterval(() => {
      busyStepIdx = Math.min(busyStepIdx + 1, stages.length - 1);
      busyText.textContent = stages[busyStepIdx];
      renderBusySteps(stages, busyStepIdx);
    }, 9000);
  }
}

function setStatus(el, text, kind = "") {
  el.textContent = text || "";
  el.classList.remove("ok", "error");
  if (kind) el.classList.add(kind);
}

async function refreshConfig() {
  configCache = await (await fetch(apiUrl("/api/config"))).json();
  document.getElementById("api-model").value = configCache.model;
  const pasta =
    "Dados: " +
    configCache.processos_dir +
    (configCache.has_key ? " · chave OK" : " · ainda sem chave");
  document.getElementById("pasta-info").textContent = pasta;
  const caminho = document.getElementById("pasta-caminho");
  if (caminho && !pastaHandle) caminho.textContent = "Nenhuma pasta escolhida neste Mac";
  const campoPasta = document.getElementById("pasta-processos");
  if (campoPasta && !pastaHandle) campoPasta.value = "";
  const notaPasta = document.getElementById("pasta-nota");
  if (notaPasta) {
    notaPasta.textContent =
      "Escolher pasta abre a janela do Mac. Cada processo vira uma subpasta ali, com o processo.pdf e um PDF por ação.";
  }
  document.getElementById("pasta-mini").textContent = configCache.has_key
    ? "xThemis · " + (configCache.provider_label || configCache.provider || "IA do perfil")
    : "Abra Ajustes e grave GPT ou Gemini neste perfil";
  document.getElementById("custo-info").textContent = configCache.custo_estimado || "";
  document.getElementById("escritorio").value = configCache.escritorio || "";
  document.getElementById("advogada").value = configCache.advogada || "";
  document.getElementById("oab").value = configCache.oab || "";
  const campoChave = document.getElementById("api-key");
  campoChave.disabled = false;
  campoChave.value = "";
  campoChave.placeholder = configCache.has_key
    ? "Chave gravada " + (configCache.masked_key || "")
    : "sk-... ou AIza...";
  const preset = document.getElementById("preset");
  const modelo = configCache.model || "";
  const prov = configCache.provider || "";
  if (modelo === "gemini-2.5-pro" || (prov === "google" && modelo.includes("pro"))) preset.value = "google_pro";
  else if (modelo === "gemini-2.5-flash") preset.value = "google_flash";
  else if (modelo === "gpt-4.1-mini" || prov === "openai") preset.value = "openai_mini";
  else preset.value = "openai_mini";
  const iaLocal = lerIaLocal();
  if (iaLocal && iaLocal.api_key && iaLocal.preset && iaLocal.preset !== "groq_free" && !configCache.has_key) {
    if ([...preset.options].some((opt) => opt.value === iaLocal.preset)) preset.value = iaLocal.preset;
    if (iaLocal.model) document.getElementById("api-model").value = iaLocal.model;
  }
  const preview = document.getElementById("logo-preview");
  if (preview) {
    if (configCache.has_logo) {
      preview.src = apiUrl("/api/perfil/logo") + "?t=" + Date.now();
      preview.hidden = false;
    } else if (!logoPendente) {
      preview.hidden = true;
      preview.removeAttribute("src");
    }
  }
}

function filesLabel(c) {
  const bits = [];
  if (c.tem_processo) bits.push("processo.pdf");
  const docs = c.arquivos || [];
  if (docs.length) bits.push(docs.slice(0, 3).join(", ") + (docs.length > 3 ? "…" : ""));
  if (c.prompts_salvos) bits.push(c.prompts_salvos + " prompt(s)");
  return bits.join(" · ") || "sem peças ainda";
}

function renderLista(selectId) {
  const q = (busca.value || "").trim().toLowerCase();
  lista.innerHTML = "";
  const filtered = allCasos.filter((c) => {
    if (!q) return true;
    const m = c.meta || {};
    const blob = [c.id, m.numero, m.reclamante, m.reclamado].join(" ").toLowerCase();
    return blob.includes(q);
  });
  if (!filtered.length) {
    lista.innerHTML = "<p class='micro'>Nenhum processo nesta lista.</p>";
    return;
  }
  for (const c of filtered) {
    const m = c.meta || {};
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "caso" + (selectId === c.id ? " active" : "");
    btn.innerHTML = `<strong>${m.numero || c.id}</strong>
      <div class="meta">${rotuloPartes(m).slice(0, 80)}</div>
      <div class="meta">${filesLabel(c)}</div>`;
    btn.onclick = () => selectCase(c);
    lista.appendChild(btn);
  }
}

async function refreshCasos(selectId) {
  allCasos = await (await fetch(apiUrl("/api/casos"))).json();
  renderLista(selectId || selected?.id);
}

function renderIndice(meta) {
  const box = document.getElementById("indice-lista");
  const info = document.getElementById("indice-meta");
  if (!box) return;
  const indice = (meta && meta.indice) || [];
  const pays = (meta && meta.paginas_pagamento) || [];
  const ocr = (meta && meta.ocr_paginas) || [];
  const extra = (meta && meta.extracao) || {};
  box.innerHTML = "";
  const bits = [];
  if (meta && meta.paginas) bits.push(meta.paginas + " págs.");
  if (indice.length) bits.push(indice.length + " marcos");
  if (pays.length) bits.push(pays.length + " com comprovante");
  if (ocr.length) bits.push(ocr.length + " via OCR");
  else if (extra.ocr_disponivel === false) bits.push("OCR indisponível neste PC");
  if (extra.ocr_puladas && extra.ocr_disponivel !== false) {
    bits.push(extra.ocr_puladas + " páginas-imagem ainda sem OCR");
  }
  info.textContent = bits.join(" · ") || "Atualize o processo para montar o índice.";
  const seen = new Set();
  for (const item of indice) {
    const key = item.tipo + ":" + item.page;
    if (seen.has(key)) continue;
    seen.add(key);
    const span = document.createElement("span");
    span.className = "indice-item fl";
    span.innerHTML = `${item.tipo} <em>fl. ${item.page}</em>${item.ocr ? " · OCR" : ""}`;
    span.onclick = () => abrirFolha(item.page);
    box.appendChild(span);
  }
  for (const p of pays.slice(0, 12)) {
    const key = "pay:" + p.page;
    if (seen.has(key)) continue;
    seen.add(key);
    const span = document.createElement("span");
    span.className = "indice-item fl";
    span.innerHTML = `Comprovante <em>fl. ${p.page}</em>`;
    span.onclick = () => abrirFolha(p.page);
    box.appendChild(span);
  }
  if (!box.children.length) {
    box.innerHTML = "<p class='micro'>Nenhum marco ainda. Anexe ou atualize o PDF.</p>";
  }
}

function warnFolhas(texto, meta) {
  const el = document.getElementById("fls-alerta");
  if (!el) return;
  const total = Number((meta && meta.paginas) || 0);
  if (!total || !texto) {
    el.hidden = true;
    return;
  }
  const nums = new Set();
  for (const m of texto.matchAll(/\bfls?\.?\s*(\d{1,5})\b/gi)) {
    const n = Number(m[1]);
    if (n > total) nums.add(n);
  }
  if (!nums.size) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const list = [...nums].sort((a, b) => a - b).slice(0, 12).join(", ");
  el.hidden = false;
  el.textContent = `Folhas citadas fora do processo (${total} págs.): ${list}. Peça para o xThemis corrigir.`;
}

function selectCase(c) {
  selected = c;
  emptyState.hidden = true;
  acoesWrap.hidden = false;
  stageActions.hidden = false;
  promptsBox.hidden = true;
  const m = c.meta || {};
  stageEyebrow.textContent = "Processo ativo";
  casoTitulo.textContent = m.numero || c.id;
  casoAtual.textContent = `${rotuloPartes(m)} · ${c.path}`;
  renderIndice(m);
  renderExtrato(m);
  carregarCamadas();
  carregarConversa();
  carregarAprendizado();
  applyLock(c.estado_pecas);
  renderLista(c.id);
}

function applyLock(estado) {
  const box = document.getElementById("peca-estado");
  const reabrir = document.getElementById("reabrir-box");
  const pjeBox = document.getElementById("pje-box");
  const aberta = estado && estado.aberta;
  const tipos = (estado && estado.tipos) || {};
  const atual = aberta ? tipos[aberta] : null;
  if (box) {
    if (atual) {
      box.textContent = `Aberta: ${atual.titulo}. Refine o mesmo arquivo ou marque Peça fechada.`;
    } else {
      box.textContent = "Nenhuma peça aberta. O PDF de protocolo nasce ao marcar Peça fechada.";
    }
  }
  document.querySelectorAll("#comando button[data-tipo]").forEach((btn) => {
    const tipo = btn.dataset.tipo;
    const info = tipos[tipo];
    btn.disabled = false;
    if (aberta && tipo !== aberta) btn.disabled = true;
    if (info && info.fechada && !aberta) btn.title = "Fechada. Reabra para editar o mesmo arquivo.";
    else btn.title = "";
  });
  if (!reabrir) return;
  reabrir.innerHTML = "";
  Object.values(tipos).forEach((info) => {
    if (!info.fechada || info.tipo === aberta) return;
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = "Reabrir " + (info.titulo || info.tipo);
    b.onclick = () => reabrirPeca(info.tipo);
    reabrir.appendChild(b);
  });
  if (!pjeBox) return;
  pjeBox.innerHTML = "";
  Object.values(tipos).forEach((info) => {
    if (!info.fechada || !info.pje_pdf) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "accent";
    b.textContent = "PJe · " + info.pje_pdf;
    b.onclick = () => {
      window.location.href = apiUrl(
        "/api/download?case_id=" +
          encodeURIComponent(selected.id) +
          "&arquivo=" +
          encodeURIComponent(info.pje_pdf)
      );
    };
    pjeBox.appendChild(b);
  });
}

async function syncSelected() {
  await refreshCasos(selected && selected.id);
  const fresh = allCasos.find((c) => c.id === (selected && selected.id));
  if (fresh) {
    selected = fresh;
    applyLock(fresh.estado_pecas);
  }
}

async function fecharPeca() {
  if (!selected) return;
  setBusy(true, "Fechando a peça…");
  const fd = new FormData();
  fd.append("case_id", selected.id);
  try {
    const r = await fetch(apiUrl("/api/fechar-peca"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    await syncSelected();
    const nome = Object.values((data.estado_pecas && data.estado_pecas.tipos) || {}).find(
      (info) => info.fechada && info.pje_pdf
    );
    toast(nome && nome.pje_pdf ? "PDF para o PJe: " + nome.pje_pdf : "Peça fechada.");
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
}

async function reabrirPeca(tipo) {
  if (!selected) return;
  setBusy(true, "Reabrindo a peça…");
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("tipo", tipo);
  try {
    const r = await fetch(apiUrl("/api/reabrir-peca"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    await syncSelected();
    toast("Peça reaberta. Refine o mesmo arquivo.");
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
}

function folhasTexto(arr) {
  return (arr || []).join(", ");
}

function folhasLista(text) {
  return String(text || "")
    .split(/[^\d]+/)
    .map((n) => Number(n))
    .filter((n) => n > 0);
}

function rotuloPartes(meta) {
  const a = pareceNome(meta && meta.reclamante);
  const b = pareceNome(meta && meta.reclamado);
  if (a && b) return `${a} × ${b}`;
  if (a || b) return a || b;
  return "Sem nome das partes";
}

function pareceNome(valor) {
  const s = String(valor || "").replace(/\s+/g, " ").trim();
  if (!s || s.length > 80) return "";
  const baixo = s.toLowerCase();
  if (/\bart\.?|§|cpc|clt|com base|pressupost|fls?\.|n[aã]o consta|n[aã]o identific/i.test(baixo)) return "";
  if (/^[a-záàâãéêíóôõúç]/.test(s)) return "";
  const palavras = s.split(" ");
  if (palavras.length > 8) return "";
  const lig = new Set(["da", "de", "do", "das", "dos", "e", "di"]);
  for (const p of palavras) {
    const n = p.replace(/[.,;]/g, "");
    if (!n) return "";
    if (lig.has(n.toLowerCase())) continue;
    if (n[0] !== n[0].toUpperCase()) return "";
  }
  return s;
}

function areaDoCaso(meta) {
  const marcada = (meta && meta.area) || "";
  if (["familia", "trabalhista", "civel", "previdenciario"].includes(marcada)) return marcada;
  const n = String((meta && meta.numero) || "");
  const m = n.match(/\d{7}-\d{2}\.\d{4}\.(\d)\./);
  if (m && m[1] === "5") return "trabalhista";
  if (m) return "civel";
  return "trabalhista";
}

function aplicarCapa(meta) {
  const temNumero = !!(meta && (meta.numero || meta.area));
  const area = temNumero ? areaDoCaso(meta) : "trabalhista";
  const trab = area === "trabalhista";
  document.querySelectorAll(".so-trabalhista").forEach((el) => {
    el.hidden = !trab;
  });
  const ativo = trab ? "Reclamante" : "Requerente";
  const passivo = trab ? "Reclamada" : "Requerido";
  const labA = document.getElementById("lab-reclamante");
  const labB = document.getElementById("lab-reclamado");
  if (labA) labA.textContent = langAtual === "en" ? (trab ? "Claimant" : "Petitioner") : ativo;
  if (labB) labB.textContent = langAtual === "en" ? (trab ? "Defendant" : "Respondent") : passivo;
  const capaLabA = document.getElementById("capa-lab-a");
  const capaLabB = document.getElementById("capa-lab-b");
  if (capaLabA) capaLabA.textContent = labA ? labA.textContent : ativo;
  if (capaLabB) capaLabB.textContent = labB ? labB.textContent : passivo;
  const persona = document.getElementById("persona");
  if (persona) {
    const juizo = langAtual === "en" ? "Court" : "Juízo";
    const map = { reclamada: labB ? labB.textContent : passivo, reclamante: labA ? labA.textContent : ativo, juizo };
    [...persona.options].forEach((opt) => {
      if (map[opt.value]) opt.textContent = map[opt.value];
    });
  }
  const ramo = document.getElementById("extrato-ramo");
  if (ramo) {
    ramo.textContent = !temNumero
      ? ""
      : trab
        ? "Trabalhista. A tabela cruza a verba da sentença com o pagamento. Confira antes de usar."
        : "Este processo não é trabalhista. Férias, horas extras e FGTS ficam de fora. O botão Resumo grava o resumo do caso em PDF na pasta.";
  }
  const rec = document.querySelector("[data-tipo=recurso]");
  if (rec) rec.textContent = trab ? (langAtual === "en" ? "Ordinary appeal" : "Recurso ordinário") : (langAtual === "en" ? "Appeal" : "Apelação");
}

function renderExtrato(meta) {
  const ex = (meta && meta.extrato) || {};
  document.getElementById("ex-numero").value = ex.numero || meta.numero || "";
  document.getElementById("ex-autuacao").value = ex.autuacao || meta.autuacao || "";
  document.getElementById("ex-valor").value = ex.valor_causa || meta.valor_causa || "";
  const nomeA = pareceNome(ex.reclamante || meta.reclamante);
  const nomeB = pareceNome(ex.reclamado || meta.reclamado);
  document.getElementById("ex-reclamante").value = nomeA;
  document.getElementById("ex-reclamado").value = nomeB;
  const capaA = document.getElementById("capa-nome-a");
  const capaB = document.getElementById("capa-nome-b");
  if (capaA) capaA.value = nomeA;
  if (capaB) capaB.value = nomeB;
  aplicarCapa(meta);
  const body = document.querySelector("#cruzamento tbody");
  body.innerHTML = "";
  const rows = ex.verbas || meta.cruzamento || [];
  rows.forEach((row, i) => {
    const tr = document.createElement("tr");
    const risco = row.condenado === "sim" && row.pago === "sim";
    tr.className = risco ? "risco" : row.pago === "sim" ? "ok" : "";
    tr.innerHTML = `
      <td><input data-k="verba" data-i="${i}" value="${escapeAttr(row.verba || "")}" /></td>
      <td><select data-k="condenado" data-i="${i}">
        <option value="sim">sim</option>
        <option value="nao">não</option>
        <option value="incerto">incerto</option>
      </select></td>
      <td><select data-k="pago" data-i="${i}">
        <option value="sim">sim</option>
        <option value="nao">não</option>
      </select></td>
      <td><input data-k="folhas_sentenca" data-i="${i}" value="${escapeAttr(folhasTexto(row.folhas_sentenca))}" /></td>
      <td><input data-k="folhas_pago" data-i="${i}" value="${escapeAttr(folhasTexto(row.folhas_pago))}" /></td>
      <td><input data-k="tese" data-i="${i}" value="${escapeAttr(row.tese || "")}" /></td>`;
    body.appendChild(tr);
    tr.querySelector('[data-k="condenado"]').value = row.condenado || "incerto";
    tr.querySelector('[data-k="pago"]').value = row.pago || "nao";
    tr.dataset.id = row.id || "";
  });
}

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function coletarExtrato() {
  const verbas = [];
  document.querySelectorAll("#cruzamento tbody tr").forEach((tr) => {
    const get = (k) => tr.querySelector(`[data-k="${k}"]`).value;
    verbas.push({
      id: tr.dataset.id || "",
      verba: get("verba"),
      condenado: get("condenado"),
      pago: get("pago"),
      folhas_sentenca: folhasLista(get("folhas_sentenca")),
      folhas_pago: folhasLista(get("folhas_pago")),
      tese: get("tese"),
    });
  });
  return {
    numero: document.getElementById("ex-numero").value,
    autuacao: document.getElementById("ex-autuacao").value,
    valor_causa: document.getElementById("ex-valor").value,
    reclamante: document.getElementById("ex-reclamante").value,
    reclamado: document.getElementById("ex-reclamado").value,
    verbas,
  };
}

function parseChecklist(texto) {
  const block = (texto || "").match(/CHECKLIST FORENSICO([\s\S]*?)(?:\n\n[A-ZÁÉÍÓÚ]|$)/i);
  const src = block ? block[1] : texto || "";
  const lines = src
    .split("\n")
    .map((l) => l.replace(/^[-*•]\s*/, "").trim())
    .filter((l) => /:\s*(SIM|NAO|NÃO|NA)\b/i.test(l));
  return lines.map((line) => {
    const m = line.match(/^(.*?):\s*(SIM|NAO|NÃO|NA)\b\s*[—\-–:]?\s*(.*)$/i);
    if (!m) return null;
    const val = m[2].toUpperCase().replace("NÃO", "NAO");
    return { label: m[1].trim(), value: val, note: (m[3] || "").trim() };
  }).filter(Boolean);
}

function renderChecklist(texto) {
  const items = parseChecklist(texto);
  checklistEl.innerHTML = "";
  if (!items.length) {
    checklistWrap.hidden = true;
    return;
  }
  checklistWrap.hidden = false;
  for (const it of items) {
    const li = document.createElement("li");
    li.className = it.value === "SIM" ? "ok" : it.value === "NA" ? "na" : "no";
    li.innerHTML = `<span class="tag">${it.value}</span><span><strong>${it.label}</strong>${
      it.note ? " — " + it.note : ""
    }</span>`;
    checklistEl.appendChild(li);
  }
}

function simpleDiffHtml(before, after) {
  const a = (before || "").split("\n");
  const b = (after || "").split("\n");
  const aSet = new Set(a);
  const bSet = new Set(b);
  const left = a
    .map((line) =>
      bSet.has(line)
        ? escapeHtml(line)
        : `<span class="del">${escapeHtml(line)}</span>`
    )
    .join("\n");
  const right = b
    .map((line) =>
      aSet.has(line)
        ? escapeHtml(line)
        : `<span class="add">${escapeHtml(line)}</span>`
    )
    .join("\n");
  return { left, right };
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showDiff(antes, depois) {
  if (!antes || !depois || antes === depois) {
    diffWrap.hidden = true;
    return;
  }
  const { left, right } = simpleDiffHtml(antes, depois);
  diffBefore.innerHTML = left;
  diffAfter.innerHTML = right;
  diffWrap.hidden = false;
}

function showMetrics(data) {
  const bits = [];
  if (data.segundos != null) bits.push(`${data.segundos}s IA`);
  if (data.refines != null) bits.push(`${data.refines} refine(s)`);
  if (data.geracoes != null) bits.push(`${data.geracoes} geração(ões)`);
  metricsLine.textContent = bits.length ? bits.join(" · ") : "";
}

function showResult(data, tituloExtra, { antes } = {}) {
  chatWrap.hidden = false;
  chatTitulo.textContent = (data.titulo || "Resultado") + (tituloExtra || "");
  renderPeca(data.texto || "");
  const dx = data.arquivo_docx || data.arquivos?.docx;
  const pf = data.arquivo_pdf || data.arquivos?.pdf;
  arquivosGerados.textContent =
    dx || pf ? `Arquivos: ${dx || "—"} + ${pf || "—"}` : "";
  showMetrics(data);
  const sug = document.getElementById("sugestao-proxima");
  const risco = document.getElementById("risco-acordo");
  const juris = document.getElementById("juris-avisos");
  if (sug) sug.textContent = data.sugestao_proxima || "";
  if (risco) risco.textContent = data.risco_acordo || "";
  if (juris) {
    const avisos = data.jurisprudencia_avisos || [];
    juris.hidden = !avisos.length;
    juris.textContent = avisos.join(" ");
  }
  renderJuris(data.jurisprudencia_conferidas || [], data.jurisprudencia_avisos || []);
  renderChecklist(data.texto || "");
  warnFolhas(data.texto || "", selected && selected.meta);
  const prev = antes || data.texto_anterior;
  if (prev) showDiff(prev, data.texto || "");
  else diffWrap.hidden = true;
  chat.scrollTop = 0;
}

function renderJuris(conferidas, avisos, acordaos, ausentes) {
  const box = document.getElementById("juris-lista");
  const alerta = document.getElementById("juris-avisos");
  if (alerta) {
    alerta.hidden = !avisos.length;
    alerta.textContent = (avisos || []).join(" ");
  }
  if (!box) return;
  box.innerHTML = "";
  (conferidas || []).forEach((item) => {
    const card = document.createElement("article");
    card.className = "juris-card" + (item.vigente ? "" : " cancelada");
    const estado = item.vigente ? "Vigente no Livro do TST" : "Cancelada no Livro do TST";
    card.innerHTML =
      `<p class="micro">${estado}${item.nota ? " · " + escapeHtml(item.nota) : ""}</p>` +
      `<h4>Súmula ${item.numero} — ${escapeHtml(item.titulo || "")}</h4>` +
      `<p>${escapeHtml(item.enunciado || "")}</p>` +
      `<p class="micro"><a href="${item.fonte}" target="_blank" rel="noopener">Livro de Súmulas do TST</a></p>`;
    box.appendChild(card);
  });
  (acordaos || []).forEach((item) => {
    const card = document.createElement("article");
    card.className = "juris-card";
    const trt = item.origem === "TRT";
    const onde = trt ? "na pesquisa da Justiça do Trabalho" : "na pesquisa do TST";
    const mais = item.total > 1 ? ` · ${item.total} decisões deste número` : "";
    const link = trt ? "Abrir na pesquisa da Justiça do Trabalho" : "Abrir na pesquisa do TST";
    card.innerHTML =
      `<p class="micro">Ementa lida ${onde}${mais}</p>` +
      `<h4>${escapeHtml(item.rotulo || item.numero)}</h4>` +
      `<p class="micro">${escapeHtml(item.turma || "")}${item.relator ? " · " + escapeHtml(item.relator) : ""}${item.julgamento ? " · julgamento " + escapeHtml(item.julgamento) : ""}</p>` +
      `<p>${escapeHtml(item.ementa || "")}</p>` +
      `<p class="micro"><a href="${item.fonte}" target="_blank" rel="noopener">${link}</a></p>`;
    box.appendChild(card);
  });
  (ausentes || []).forEach((item) => {
    const card = document.createElement("article");
    card.className = "juris-card ausente";
    const link = item.busca === "jt"
      ? "Abrir a busca deste número na Justiça do Trabalho"
      : "Abrir a busca deste número no TST";
    card.innerHTML =
      `<p class="micro">Sem ementa lida</p>` +
      `<h4>${escapeHtml(item.numero)}</h4>` +
      `<p>${escapeHtml(item.motivo || "")}</p>` +
      `<p class="micro"><a href="${item.fonte}" target="_blank" rel="noopener">${link}</a></p>`;
    box.appendChild(card);
  });
}

document.getElementById("btn-conferir-sumulas").onclick = async () => {
  const texto = (lastResult && lastResult.texto) || document.getElementById("instrucoes-extra").value;
  if (!texto.trim()) {
    toast("Gere a peça ou cole no diálogo a súmula ou o número do acórdão.");
    return;
  }
  chatWrap.hidden = false;
  setBusy(true, "Lendo a pesquisa do TST e do TRT…");
  const fd = new FormData();
  fd.append("texto", texto);
  try {
    const r = await fetch(apiUrl("/api/conferir-sumulas"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) return toast(data.detail || "falha");
    renderJuris(data.conferidas || [], data.avisos || [], data.acordaos || [], data.acordaos_ausentes || []);
    const tem =
      (data.conferidas || []).length ||
      (data.acordaos || []).length ||
      (data.acordaos_ausentes || []).length ||
      (data.avisos || []).length;
    if (!tem) toast("Nenhuma súmula nem número de acórdão nesse texto.");
  } finally {
    setBusy(false);
  }
};

function renderPeca(texto) {
  const lines = String(texto || "").split("\n");
  chat.innerHTML = lines
    .map((line) => {
      const t = line.trim();
      if (!t) return "<div class='gap'></div>";
      let html = escapeHtml(line).replace(
        /\b(fls?\.?\s*)(\d{1,5})\b/gi,
        (m, pre, n) => `<button type="button" class="fl" data-fl="${n}">${pre}${n}</button>`
      );
      if (/^#{1,3}\s/.test(t) || /^CHECKLIST/i.test(t)) {
        return `<h4>${html.replace(/^#+\s*/, "")}</h4>`;
      }
      return `<p>${html}</p>`;
    })
    .join("");
  chat.querySelectorAll("button.fl").forEach((b) => {
    b.onclick = () => abrirFolha(b.dataset.fl);
  });
}

async function abrirFolha(pagina) {
  if (!selected || !pagina) return;
  const dlg = document.getElementById("folha");
  const titulo = document.getElementById("folha-titulo");
  const trecho = document.getElementById("folha-trecho");
  titulo.textContent = "Folha " + pagina;
  trecho.textContent = "Abrindo o trecho…";
  dlg.showModal();
  try {
    const r = await fetch(
      apiUrl("/api/folha?case_id=" + encodeURIComponent(selected.id) + "&pagina=" + pagina)
    );
    const data = await r.json();
    trecho.textContent = data.trecho || "Esta folha não entrou no extrato lido.";
  } catch (e) {
    trecho.textContent = e.message;
  }
}

async function importFile(file) {
  if (!file) return;
  setStatus(importStatus, "Lendo o PDF e criando a pasta…");
  setBusy(true, "Importando processo…", "importar");
  const fd = new FormData();
  fd.append("arquivo", file);
  try {
    const r = await fetch(apiUrl("/api/importar"), { method: "POST", body: fd });
    let data = await r.json();
    if (!r.ok && !data.ok) throw new Error(data.detail || "falha");
    if (data.job) {
      setBusy(true, "PDF grande na fila…", "importar");
      for (let i = 0; i < 300; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const j = await (await fetch(apiUrl("/api/job?id=" + data.job))).json();
        if (j.status === "ok") {
          data = j.result;
          break;
        }
        if (j.status === "erro") throw new Error(j.detail || "fila");
        if (i === 299) throw new Error("A fila ainda está lendo. Atualize a página daqui a pouco.");
      }
    }
    setStatus(importStatus, "Pasta criada.", "ok");
    selected = { id: data.id, path: data.path, meta: data.meta };
    selectCase(selected);
    await refreshCasos(data.id);
    toast("Processo na pasta · processo.pdf único.");
    await espelharCaso(data.id, ["processo.pdf"]);
  } catch (e) {
    setStatus(importStatus, "Não consegui importar: " + e.message, "error");
    toast("Falha na importação");
  } finally {
    setBusy(false);
    pdf.value = "";
  }
}

async function updateProcessFile(file) {
  if (!file || !selected) return;
  setBusy(true, "Atualizando autos…", "atualizar");
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("arquivo", file);
  try {
    const r = await fetch(apiUrl("/api/atualizar-processo"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    selected = { id: data.id, path: data.path, meta: data.meta };
    selectCase(selected);
    await refreshCasos(data.id);
    toast("processo.pdf atualizado (versão única).");
  } catch (e) {
    toast("Falha ao atualizar: " + e.message);
  } finally {
    setBusy(false);
    const inp = document.getElementById("pdf-update");
    if (inp) inp.value = "";
  }
}

pdf.addEventListener("change", () => importFile(pdf.files[0]));

const pdfUpdate = document.getElementById("pdf-update");
if (pdfUpdate) {
  pdfUpdate.addEventListener("change", () => updateProcessFile(pdfUpdate.files[0]));
}

["dragenter", "dragover"].forEach((ev) => {
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});
["dragleave", "drop"].forEach((ev) => {
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) importFile(file);
});

busca.addEventListener("input", () => renderLista(selected?.id));

document.querySelectorAll("#prompt-chips button[data-prompt]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const box = document.getElementById("instrucoes-extra");
    const bit = btn.dataset.prompt || "";
    box.value = box.value.trim() ? box.value.trim() + "\n" + bit : bit;
    box.focus();
  });
});

function learnFlag() {
  return document.getElementById("salvar-aprendizado").checked ? "1" : "0";
}

function tambemGlobal() {
  const el = document.getElementById("aprendizado-global-flag");
  return !el || el.checked ? "1" : "0";
}

document.getElementById("btn-como").onclick = () => {
  const pop = document.getElementById("empty-state");
  const show = pop.hidden;
  pop.hidden = !show;
  document.getElementById("btn-como").setAttribute("aria-expanded", show ? "true" : "false");
};

document.querySelectorAll("#comando button[data-tipo]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!selected) {
      toast("Anexe o PDF do processo. A peça só nasce depois do arquivo.");
      document.getElementById("pdf").click();
      return;
    }
    const tipo = btn.dataset.tipo;
    const modo = btn.dataset.modo || "arquivos";
    const instrucoes = document.getElementById("instrucoes-extra").value.trim();
    if (tipo === "personalizado" && !instrucoes) {
      toast("No pedido personalizado, escreva no diálogo o que a IA deve fazer.");
      return;
    }
    lastTipo = tipo;
    setBusy(true, "Gerando peça…", "gerar");
    const fd = new FormData();
    fd.append("case_id", selected.id);
    fd.append("tipo", tipo);
    fd.append("modo", modo);
    fd.append("salvar_aprendizado", learnFlag());
    fd.append("tambem_global", tambemGlobal());
    if (instrucoes) fd.append("instrucoes_extra", instrucoes);
    fd.append("persona", document.getElementById("persona").value);
    fd.append("prazo", document.getElementById("prazo").value.trim());
    try {
      const r = await fetch(apiUrl("/api/acao"), { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "falha");
      lastResult = data;
      const dx = data.arquivo_docx || data.arquivos?.docx;
      const pf = data.arquivo_pdf || data.arquivos?.pdf;
      showResult(data);
      if (instrucoes && learnFlag() === "1") {
        document.getElementById("instrucoes-extra").value = "";
      }
      if (data.id) selected.id = data.id;
      if (data.pasta) selected.path = data.pasta;
      await syncSelected();
      const fresco = allCasos.find((c) => c.id === selected.id);
      if (fresco) selectCase(fresco);
      const copiar = [dx, pf];
      if (data.aprendizado_arquivo) copiar.push(data.aprendizado_arquivo);
      await espelharCaso(selected.id, copiar);
      if (data.aprendizado_arquivo) await espelharGlobal();
      await carregarAprendizado();
      toast(
        data.aprendizado_arquivo
          ? `Peça pronta: ${dx} · ${pf}. Aprendizado.txt na pasta do processo.`
          : `Peça pronta: ${dx} · ${pf}`
      );
    } catch (e) {
      toast(e.message);
    } finally {
      setBusy(false);
    }
  });
});

function pintarConversa(itens) {
  const box = document.getElementById("bate-papo");
  const limpar = document.getElementById("btn-limpar-conversa");
  if (!box) return;
  const lista = itens || [];
  if (!lista.length) {
    box.hidden = true;
    box.innerHTML = "";
    if (limpar) limpar.hidden = true;
    return;
  }
  box.hidden = false;
  if (limpar) limpar.hidden = false;
  box.innerHTML = lista
    .map((item) => {
      const quem = item.papel === "advogada" ? "Você" : "xThemis";
      const classe = item.papel === "advogada" ? "advogada" : "xthemis";
      return `<p class="${classe}"><strong>${quem}</strong><br>${escapeHtml(item.texto || "")}</p>`;
    })
    .join("");
  box.scrollTop = box.scrollHeight;
}

async function carregarConversa() {
  if (!selected) return;
  try {
    const r = await fetch(apiUrl("/api/conversa?case_id=" + encodeURIComponent(selected.id)));
    const data = await r.json();
    if (!r.ok) return;
    pintarConversa(data.mensagens || []);
  } catch (e) {
    pintarConversa([]);
  }
}

document.getElementById("btn-conversar").onclick = async () => {
  if (!selected) {
    toast("Abra um processo antes de conversar.");
    return;
  }
  const pergunta = document.getElementById("instrucoes-extra").value.trim();
  if (!pergunta) {
    toast("Escreva a pergunta. Conversar não cria peça.");
    return;
  }
  setBusy(true, "Consultando o processo…");
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("pergunta", pergunta);
  fd.append("prazo", document.getElementById("prazo").value.trim());
  try {
    const r = await fetch(apiUrl("/api/conversar"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    document.getElementById("instrucoes-extra").value = "";
    pintarConversa(data.mensagens || []);
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
};

document.getElementById("btn-limpar-conversa").onclick = async () => {
  if (!selected) return;
  const fd = new FormData();
  fd.append("case_id", selected.id);
  await fetch(apiUrl("/api/conversa/limpar"), { method: "POST", body: fd });
  pintarConversa([]);
};

document.getElementById("btn-refinar").onclick = async () => {
  if (!selected) return;
  const feedback = document.getElementById("instrucoes-extra").value.trim();
  if (!feedback) {
    toast("Escreva o que faltou; o xThemis reescreve a mesma peça.");
    return;
  }
  const antes = lastResult?.texto || "";
  setBusy(true, "Refinando peça…", "refinar");
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("feedback", feedback);
  fd.append("salvar_aprendizado", learnFlag());
  fd.append("tambem_global", tambemGlobal());
  fd.append("persona", document.getElementById("persona").value);
  try {
    const r = await fetch(apiUrl("/api/refinar"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    lastResult = data;
    showResult(data, " (refinado)", { antes: data.texto_anterior || antes });
    if (learnFlag() === "1") document.getElementById("instrucoes-extra").value = "";
    await syncSelected();
    const copiar = [data.arquivo_docx, data.arquivo_pdf];
    if (data.aprendizado_arquivo) copiar.push(data.aprendizado_arquivo);
    await espelharCaso(selected.id, copiar);
    if (data.aprendizado_arquivo) await espelharGlobal();
    await carregarAprendizado();
    toast(
      data.aprendizado_arquivo
        ? "Mesma peça sobrescrita. Aprendizado.txt atualizado na pasta."
        : "Mesma peça sobrescrita · veja o diff."
    );
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
};

document.getElementById("btn-toggle-diff")?.addEventListener("click", () => {
  const panes = diffWrap.querySelector(".diff-cols");
  if (!panes) return;
  const hidden = panes.hidden;
  panes.hidden = !hidden;
  document.getElementById("btn-toggle-diff").textContent = hidden
    ? "Ocultar diff"
    : "Mostrar diff";
});

document.getElementById("btn-fechar").onclick = () => fecharPeca();

let aprendCache = { caso: [], global: [] };

function textoVazioAprendizado() {
  return document.documentElement.dataset.lang === "en" ? "Nothing saved yet." : "Nada gravado ainda.";
}

function rotuloTirar() {
  return document.documentElement.dataset.lang === "en" ? "Remove" : "Tirar";
}

function linhasAprendizado(itens, onde) {
  if (!itens || !itens.length) return `<li class="micro vazio">${textoVazioAprendizado()}</li>`;
  return itens
    .map(
      (item, i) =>
        `<li><span>${escapeHtml(item)}</span><button type="button" class="ghost tirar" data-onde="${onde}" data-i="${i}">${rotuloTirar()}</button></li>`
    )
    .join("");
}

function itensGlobais(g) {
  const todos = (g && g.todos) || [];
  if (todos.length) return todos;
  const flat = [];
  Object.values((g && g.por_tipo) || {}).forEach((arr) => {
    (arr || []).forEach((item) => {
      if (!flat.includes(item)) flat.push(item);
    });
  });
  return flat;
}

function lerAprendLocal() {
  try {
    const data = JSON.parse(localStorage.getItem("harvey_aprendizado") || "{}");
    return data && typeof data === "object" ? data : {};
  } catch (e) {
    return {};
  }
}

function gravarAprendLocal(caseId, caso, global) {
  const data = lerAprendLocal();
  data.global = global || [];
  data.casos = data.casos || {};
  if (caseId) data.casos[caseId] = caso || [];
  localStorage.setItem("harvey_aprendizado", JSON.stringify(data));
}

function unirNotas(listas) {
  const saida = [];
  listas.forEach((lista) => {
    (lista || []).forEach((item) => {
      const texto = String(item || "").trim();
      if (texto && !saida.includes(texto)) saida.push(texto);
    });
  });
  return saida.slice(-40);
}

async function linhasDoArquivo(dir, nome) {
  try {
    const handle = await dir.getFileHandle(nome);
    const texto = await (await handle.getFile()).text();
    return texto
      .split(/\r?\n/)
      .map((linha) => linha.trim())
      .filter((linha) => linha.startsWith("- "))
      .map((linha) => linha.slice(2).trim())
      .filter((linha) => linha && linha !== "(nada gravado ainda)");
  } catch (e) {
    return [];
  }
}

async function lerAprendizadoDaPasta(caseId) {
  const raiz = await pastaComPermissao();
  if (!raiz) return { caso: [], global: [] };
  let caso = [];
  try {
    const dir = await raiz.getDirectoryHandle(caseId);
    caso = await linhasDoArquivo(dir, "Aprendizado.txt");
  } catch (e) {
    caso = [];
  }
  const global = await linhasDoArquivo(raiz, "Aprendizado_global.txt");
  return { caso, global };
}

function pintarAprendizado(caso, global) {
  aprendCache = { caso: caso || [], global: global || [] };
  const doCaso = document.getElementById("aprendizado-caso");
  const caixaGlobal = document.getElementById("aprendizado-global");
  if (doCaso) doCaso.innerHTML = linhasAprendizado(aprendCache.caso, "caso");
  if (caixaGlobal) caixaGlobal.innerHTML = linhasAprendizado(aprendCache.global, "global");
  if (selected) gravarAprendLocal(selected.id, aprendCache.caso, aprendCache.global);
}

async function carregarAprendizado() {
  const doCaso = document.getElementById("aprendizado-caso");
  const caixaGlobal = document.getElementById("aprendizado-global");
  if (!doCaso || !caixaGlobal) return;
  if (!selected) {
    pintarAprendizado([], []);
    return;
  }
  try {
    const r = await fetch(apiUrl("/api/prompts?case_id=" + encodeURIComponent(selected.id)));
    const data = await r.json();
    if (!r.ok) return;
    let caso = (data.caso && data.caso.geral) || [];
    let global = itensGlobais(data.global);
    const local = lerAprendLocal();
    const faltaCaso = !caso.length;
    const faltaGlobal = !global.length;
    if (faltaCaso || faltaGlobal) {
      const mac = await lerAprendizadoDaPasta(selected.id);
      const backupCaso = unirNotas([local.casos && local.casos[selected.id], mac.caso]);
      const backupGlobal = unirNotas([local.global, mac.global]);
      if ((faltaCaso && backupCaso.length) || (faltaGlobal && backupGlobal.length)) {
        const resp = await fetch(apiUrl("/api/prompts/restaurar"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            case_id: selected.id,
            caso: backupCaso,
            global: backupGlobal,
            restaurar_caso: faltaCaso && backupCaso.length > 0,
            restaurar_global: faltaGlobal && backupGlobal.length > 0,
          }),
        });
        const gravado = await resp.json();
        if (resp.ok) {
          caso = (gravado.caso && gravado.caso.geral) || caso;
          global = itensGlobais(gravado.global);
          await espelharCaso(selected.id, ["Aprendizado.txt"], true);
          await espelharGlobal();
        } else {
          if (faltaCaso) caso = backupCaso;
          if (faltaGlobal) global = backupGlobal;
        }
      }
    }
    pintarAprendizado(caso, global);
  } catch (e) {
    const local = lerAprendLocal();
    pintarAprendizado(
      (local.casos && local.casos[selected.id]) || [],
      local.global || []
    );
  }
}

document.getElementById("aprendizado-vivo").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button.tirar");
  if (!btn || !selected) return;
  const onde = btn.dataset.onde === "global" ? "global" : "caso";
  const lista = onde === "global" ? aprendCache.global : aprendCache.caso;
  const texto = lista[Number(btn.dataset.i)];
  if (!texto) return;
  btn.disabled = true;
  try {
    const r = await fetch(apiUrl("/api/prompts/remover"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: selected.id, texto, onde }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    pintarAprendizado((data.caso && data.caso.geral) || [], itensGlobais(data.global));
    await espelharCaso(selected.id, ["Aprendizado.txt"], true);
    await espelharGlobal();
  } catch (e) {
    toast(e.message);
    btn.disabled = false;
  }
});

document.getElementById("btn-guardar-aprendizado").onclick = async () => {
  if (!selected) {
    toast("Abra um processo antes de gravar o aprendizado.");
    return;
  }
  const texto = document.getElementById("instrucoes-extra").value.trim();
  if (!texto) {
    toast("Escreva o que deve ficar gravado para este processo e para os outros.");
    return;
  }
  setBusy(true, "Gravando aprendizado…");
  try {
    const r = await fetch(apiUrl("/api/prompts"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_id: selected.id,
        texto,
        tipo: lastTipo || "geral",
        also_global: tambemGlobal() === "1",
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    document.getElementById("instrucoes-extra").value = "";
    pintarAprendizado((data.caso && data.caso.geral) || [], itensGlobais(data.global));
    await espelharCaso(selected.id, ["Aprendizado.txt"], true);
    if (tambemGlobal() === "1") await espelharGlobal();
    toast(
      tambemGlobal() === "1"
        ? "Gravado neste processo e nos outros. Os dois arquivos foram atualizados."
        : "Gravado só neste processo, no arquivo Aprendizado.txt."
    );
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
};

document.getElementById("btn-ver-prompts").onclick = async () => {
  if (!selected) return;
  await carregarAprendizado();
  const vivo = document.getElementById("aprendizado-vivo");
  if (vivo) vivo.scrollIntoView({ behavior: "smooth", block: "nearest" });
};

document.getElementById("btn-salvar").onclick = async () => {
  if (!selected || !lastResult?.texto) return;
  setBusy(true, "Regravando Word + PDF…");
  try {
    const r = await fetch(apiUrl("/api/salvar-docx"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_id: selected.id,
        texto: lastResult.texto,
        nome: lastResult.sugestao_arquivo || lastResult.arquivo_docx || "Peca.docx",
        titulo: lastResult.titulo,
        tipo: lastTipo || "personalizado",
      }),
    });
    const data = await r.json();
    toast(data.ok ? `Regravado: ${data.arquivo} + ${data.pdf}` : "Não salvou.");
    refreshCasos(selected.id);
  } finally {
    setBusy(false);
  }
};

document.getElementById("btn-escolher-pasta").onclick = escolherPasta;
document.getElementById("btn-escolher-pasta-ajustes").onclick = escolherPasta;
lerPastaHandle().then((h) => {
  if (h) mostrarPastaLocal(h.name);
});

document.getElementById("btn-gravar-nomes").onclick = () => {
  if (!selected) {
    toast("Abra o processo antes de gravar os nomes.");
    return;
  }
  document.getElementById("ex-reclamante").value = document.getElementById("capa-nome-a").value.trim();
  document.getElementById("ex-reclamado").value = document.getElementById("capa-nome-b").value.trim();
  document.getElementById("btn-salvar-extrato").click();
};

document.getElementById("btn-salvar-extrato").onclick = async () => {
  if (!selected) return;
  setBusy(true, "Salvando extrato…");
  try {
    const r = await fetch(apiUrl("/api/extrato"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: selected.id, extrato: coletarExtrato() }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    selected.meta = data.meta;
    if (data.id) selected.id = data.id;
    if (data.path) selected.path = data.path;
    selectCase(selected);
    toast("Nomes gravados na pasta. A próxima peça usa esta versão.");
    await refreshCasos(selected.id);
    const atual = allCasos.find((c) => c.id === selected.id);
    if (atual) selectCase(atual);
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
};

document.getElementById("btn-pasta").onclick = async () => {
  if (!selected) return;
  window.location.href = apiUrl(
    "/api/baixar-pasta?case_id=" + encodeURIComponent(selected.id)
  );
};

document.getElementById("btn-ajustes").onclick = () => {
  refreshConfig();
  carregarConvidados();
  ajustes.showModal();
};

function renderConvidados(lista) {
  const box = document.getElementById("convidados-lista");
  if (!box) return;
  box.innerHTML = "";
  if (!lista.length) {
    box.innerHTML = "<li class='micro'>Ninguém na lista gratuita ainda.</li>";
    return;
  }
  lista.forEach((item) => {
    const li = document.createElement("li");
    const estado = item.entrou ? "já entrou" : "ainda não criou a conta";
    li.innerHTML = `${escapeHtml(item.nome)}${item.nota ? " · " + escapeHtml(item.nota) : ""} <span class="micro">(${estado})</span>`;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ghost";
    b.textContent = "Tirar";
    b.onclick = () => removerConvidado(item.id);
    li.appendChild(b);
    box.appendChild(li);
  });
}

function renderUsuarios(lista) {
  const box = document.getElementById("usuarios-lista");
  if (!box) return;
  box.innerHTML = "";
  if (!lista.length) {
    box.innerHTML = "<li class='micro'>Nenhum usuário além de você.</li>";
    return;
  }
  lista.forEach((item) => {
    const li = document.createElement("li");
    const papel = item.acesso === "dono" ? "administrador" : "gratuito";
    const ia = item.tem_chave ? item.ia || "IA gravada" : "ainda sem chave";
    li.textContent = `${item.nome} · ${papel} · ${ia}`;
    box.appendChild(li);
  });
}

async function carregarConvidados() {
  const box = document.getElementById("convidados-box");
  const r = await fetch(apiUrl("/api/usuarios"));
  if (r.status === 403) {
    if (box) box.hidden = true;
    toast("Entre na conta de administrador para criar perfis gratuitos.");
    return;
  }
  const data = await r.json();
  if (!r.ok) return;
  if (box) box.hidden = false;
  renderUsuarios(data.usuarios || []);
  const rex = await fetch(apiUrl("/api/exclusoes"));
  const lista = document.getElementById("exclusoes-lista");
  if (!lista || !rex.ok) return;
  const pacote = await rex.json();
  const itens = pacote.exclusoes || [];
  lista.innerHTML = "";
  if (!itens.length) {
    lista.innerHTML = "<li class='micro'>Nenhuma exclusão registrada.</li>";
    return;
  }
  itens.slice().reverse().forEach((item) => {
    const li = document.createElement("li");
    li.className = "micro";
    li.textContent = `${item.quando || ""} · ${item.numero || item.processo || "processo"} · ${item.usuario || ""}`;
    lista.appendChild(li);
  });
}

async function removerConvidado(id) {
  const r = await fetch(apiUrl("/api/convidados/remover"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "Não tirei.");
  renderConvidados(data.convidados || []);
}

document.getElementById("btn-novo-usuario").onclick = async () => {
  const r = await fetch(apiUrl("/api/usuarios"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nome: document.getElementById("novo-usuario-nome").value.trim(),
      senha: document.getElementById("novo-usuario-senha").value,
    }),
  });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "Não criei o usuário.");
  document.getElementById("novo-usuario-nome").value = "";
  document.getElementById("novo-usuario-senha").value = "";
  renderUsuarios(data.usuarios || []);
  toast("Perfil gratuito criado: " + (data.usuario && data.usuario.nome ? data.usuario.nome : "ok") + ". Passe o nome e a senha. A pessoa entra em www.xthemis.com.br.");
};

let logoPendente = null;
document.getElementById("logo-escritorio").addEventListener("change", () => {
  const file = document.getElementById("logo-escritorio").files?.[0];
  if (!file) return;
  if (file.size > 350000) {
    toast("Logo grande demais. Use um PNG ou JPG pequeno.");
    document.getElementById("logo-escritorio").value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const data = String(reader.result || "");
    const m = data.match(/^data:(image\/(?:png|jpeg));base64,(.+)$/);
    if (!m) {
      toast("Use PNG ou JPG.");
      return;
    }
    logoPendente = { tipo: m[1], b64: m[2] };
    const preview = document.getElementById("logo-preview");
    preview.src = data;
    preview.hidden = false;
  };
  reader.readAsDataURL(file);
});

document.getElementById("prazo-tipo").onchange = () => {
  document.getElementById("prazo-outro-wrap").hidden =
    document.getElementById("prazo-tipo").value !== "outro";
};

document.getElementById("btn-prazo").onclick = async () => {
  const fd = new FormData();
  fd.append("data", document.getElementById("prazo-data").value);
  fd.append("modo", document.getElementById("prazo-modo").value);
  fd.append("tipo", document.getElementById("prazo-tipo").value);
  fd.append("dias", document.getElementById("prazo-dias").value);
  if (selected) fd.append("case_id", selected.id);
  const r = await fetch(apiUrl("/api/prazo"), { method: "POST", body: fd });
  const data = await r.json();
  const out = document.getElementById("prazo-resultado");
  if (!r.ok) {
    out.hidden = false;
    out.textContent = data.detail || "Não calculei.";
    return;
  }
  document.getElementById("prazo").value = data.resumo;
  out.hidden = false;
  const pulados = (data.pulados || []).length ? " Dias fora da conta: " + data.pulados.join(", ") + "." : "";
  out.textContent = data.resumo + pulados;
};

document.getElementById("preset").addEventListener("change", async (ev) => {
  const preset = ev.target.value;
  const p = configCache?.presets?.[preset];
  if (p) {
    document.getElementById("api-model").value = p.model;
    document.getElementById("custo-info").textContent = p.custo + " — " + p.nota;
  }
});

function lerIaLocal() {
  try {
    const data = JSON.parse(localStorage.getItem("harvey_ia") || "null");
    return data && typeof data === "object" ? data : null;
  } catch (e) {
    return null;
  }
}

function gravarIaLocal(parcial) {
  const atual = lerIaLocal() || {};
  const prox = { ...atual, ...parcial };
  if (!prox.api_key) delete prox.api_key;
  localStorage.setItem("harvey_ia", JSON.stringify(prox));
}

async function restaurarIaNoServidor() {
  const salvo = lerIaLocal();
  if (!salvo || (!salvo.api_key && !salvo.preset)) return;
  if (salvo.preset === "groq_free" || String(salvo.api_key || "").startsWith("gsk_")) return;
  const body = {
    preset: salvo.preset,
    model: salvo.model,
    escritorio: salvo.escritorio || "",
    advogada: salvo.advogada || "",
    oab: salvo.oab || "",
  };
  if (salvo.api_key) body.api_key = salvo.api_key;
  if (salvo.logo_b64) {
    body.logo_b64 = salvo.logo_b64;
    body.logo_tipo = salvo.logo_tipo || "image/png";
  }
  await fetch(apiUrl("/api/config"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

document.getElementById("salvar-ajustes").onclick = async (ev) => {
  ev.preventDefault();
  const digitada = document.getElementById("api-key").value.trim();
  const salvo = lerIaLocal() || {};
  const chave = digitada && !digitada.startsWith("•") ? digitada : salvo.api_key || "";
  const body = {
    preset: document.getElementById("preset").value,
    model: document.getElementById("api-model").value,
    escritorio: document.getElementById("escritorio").value.trim(),
    advogada: document.getElementById("advogada").value.trim(),
    oab: document.getElementById("oab").value.trim(),
  };
  if (chave) body.api_key = chave;
  if (logoPendente) {
    body.logo_b64 = logoPendente.b64;
    body.logo_tipo = logoPendente.tipo;
  }
  gravarIaLocal({
    ...body,
    api_key: chave,
    logo_b64: body.logo_b64 || (lerIaLocal() || {}).logo_b64,
    logo_tipo: body.logo_tipo || (lerIaLocal() || {}).logo_tipo,
  });
  const r = await fetch(apiUrl("/api/config"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  ajustes.close();
  if (!r.ok) {
    toast("Guardei a IA neste computador. O servidor não confirmou.");
    return;
  }
  refreshConfig();
  toast("Ajustes salvos. A IA fica neste computador.");
};

restaurarIaNoServidor().finally(() => {
  refreshConfig();
  refreshCasos();
});

let camadaAtual = { capa: "", sentenca: "", provas: "" };

async function carregarCamadas() {
  const box = document.getElementById("camadas-texto");
  if (!selected || !box) return;
  const data = await (
    await fetch(apiUrl("/api/camadas?case_id=" + encodeURIComponent(selected.id)))
  ).json();
  camadaAtual = data || {};
  box.textContent = camadaAtual.capa || "Sem capa no extrato.";
}

document.querySelectorAll("#camadas-tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    const key = btn.dataset.camada;
    document.getElementById("camadas-texto").textContent =
      camadaAtual[key] || "Esta camada ainda não está no extrato. Atualize o PDF.";
  });
});

document.getElementById("pdf-juntar").addEventListener("change", async (ev) => {
  const file = ev.target.files && ev.target.files[0];
  ev.target.value = "";
  if (!file || !selected) return;
  setBusy(true, "Juntando páginas novas…", "atualizar");
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("arquivo", file);
  try {
    const r = await fetch(apiUrl("/api/juntar-paginas"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    selected.meta = data.meta;
    selectCase(selected);
    await refreshCasos(selected.id);
    toast(`Páginas juntadas: ${data.paginas_antes} → ${data.paginas}.`);
  } catch (e) {
    toast(e.message);
  } finally {
    setBusy(false);
  }
});

document.getElementById("btn-whatsapp").onclick = () => {
  const titulo = casoTitulo.textContent || "Processo";
  const trecho = (lastResult && lastResult.texto ? lastResult.texto : "").slice(0, 700);
  const msg = `xThemis · ${titulo}\n${trecho}`;
  window.open("https://wa.me/?text=" + encodeURIComponent(msg), "_blank", "noopener");
};

document.getElementById("btn-segredo").onclick = async () => {
  if (!selected) return;
  const ligado = !(selected.meta && selected.meta.segredo);
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("ligado", ligado ? "1" : "0");
  const r = await fetch(apiUrl("/api/segredo"), { method: "POST", body: fd });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "falha");
  selected.meta = { ...(selected.meta || {}), segredo: data.segredo };
  toast(data.segredo ? "Segredo de justiça: só a dona vê este processo." : "Segredo desligado.");
  refreshCasos(selected.id);
};

document.getElementById("btn-excluir").onclick = async () => {
  if (!selected) return;
  if (!confirm("Excluir este processo deste servidor? A pasta some daqui.")) return;
  const fd = new FormData();
  fd.append("case_id", selected.id);
  const r = await fetch(apiUrl("/api/excluir"), { method: "POST", body: fd });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "falha");
  selected = null;
  acoesWrap.hidden = true;
  emptyState.hidden = true;
  document.getElementById("btn-como").setAttribute("aria-expanded", "false");
  stageActions.hidden = true;
  toast("Processo excluído.");
  refreshCasos();
};

document.getElementById("btn-tema").onclick = () => {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("harvey_theme", next);
  aplicarIdioma(langAtual, false);
};

const I18N = {
  pt: {
    sub: "Processos em PDF → peças em Word e PDF",
    disc: "xThemis é assistente de redação. Não é advogado, não protocola e não garante prazo, jurisprudência nem resultado.",
    temaClaro: "Modo claro",
    temaEscuro: "Modo escuro",
    lados: { reclamada: "Reclamada", reclamante: "Reclamante", juizo: "Juízo" },
    ui: {
      "#btn-conta": "Entrar",
      "#btn-ajustes": "Ajustes da IA",
      "#dropzone strong": "Anexar PDF do processo",
      ".drop-hint": "Copia pra pasta do caso · vira o único processo.pdf",
      ".rail-head h2": "Processos",
      "#stage-eyebrow": "Selecione ou importe um processo",
      "#caso-titulo": "Nenhum caso ativo",
      "#empty-state p": "Anexe o PDF: o xThemis cria a pasta e grava processo.pdf (só um). Cada ação vira um Word e um PDF. Refinar sobrepõe a mesma peça. Quando o tribunal atualizar os autos, use Atualizar processo e o PDF principal é substituído.",
      "#btn-segredo": "Segredo",
      "#btn-excluir": "Excluir processo",
      "#btn-pasta": "Backup (ZIP)",
      "#btn-ver-prompts": "Aprendizado",
      "#btn-guardar-aprendizado": "Gravar aprendizado",
      "#empty-state .empty-kicker": "Como funciona",
      "#empty-state h3": "Um processo. Uma peça por ação.",
      "#titulo-dialogo": "Diálogo com a IA",
      "#titulo-aprendizado": "Aprendizado",
      "#rotulo-guardar": "Guardar aprendizado",
      "#btn-prazo": "Calcular prazo",
      "#btn-conversar": "Só conversar",
      "#btn-refinar": "Refinar esta peça (sobrepoe)",
      "#btn-fechar": "Peça fechada",
      "#btn-conferir-sumulas": "Conferir jurisprudência",
      "#peca-estado": "Sem peça aberta. A primeira ação cria o arquivo.",
      "#camadas-wrap h3": "Resumo em camadas",
      "#indice-wrap h3": "Índice dos autos",
      "#extrato-wrap h3": "Extrato do processo",
      "#btn-salvar-extrato": "Salvar extrato",
      ".actions h3": "Gerar peça",
      "#chat-titulo": "Resultado",
      "#btn-salvar": "Regravar Word + PDF",
      "#ajustes h2": "Ajustes",
      "#login h2": "Entrar",
      "#onb-title": "Quem vai usar",
      "#onb-pular": "Pular",
      "#onb-next": "Continuar",
      ".posicao-nome": "Posição",
      "[data-tipo=resumo]": "Resumo",
      "[data-tipo=jurisprudencia]": "Jurisprudência",
      "[data-tipo=defesa]": "Contestação",
      "[data-tipo=replica]": "Réplica",
      "[data-tipo=recurso]": "Recurso ordinário",
      "[data-tipo=contrarrazoes]": "Contrarrazões",
      "[data-tipo=alegacoes_finais]": "Alegações finais",
      "[data-tipo=embargos]": "Embargos",
      "[data-tipo=impugnacao_laudo]": "Impug. laudo",
      "[data-tipo=impugnacao_calculos]": "Impug. cálculos",
      "[data-tipo=manifestacao]": "Manifestação",
      "[data-tipo=peticao]": "Petição",
      "[data-tipo=acordo]": "Acordo",
      "[data-tipo=personalizado]": "Pedido personalizado",
      "[data-tipo=tutela]": "Tutela de urgência",
      "[data-tipo=execucao]": "Execução",
      "[data-tipo=embargos_execucao]": "Embargos à execução",
      "[data-tipo=agravo_peticao]": "Agravo de petição",
      "[data-tipo=agravo_instrumento]": "Agravo de instrumento",
      "[data-tipo=revista]": "Recurso de revista",
      "[data-tipo=quesitos]": "Quesitos",
    },
  },
  en: {
    sub: "Case PDF → Word and PDF drafts",
    disc: "xThemis drafts text. It is not a lawyer, does not file, and does not guarantee deadlines, case law, or outcome.",
    temaClaro: "Light mode",
    temaEscuro: "Dark mode",
    lados: { reclamada: "Defendant", reclamante: "Claimant", juizo: "Court" },
    ui: {
      "#btn-conta": "Sign in",
      "#btn-ajustes": "AI settings",
      "#dropzone strong": "Attach the case PDF",
      ".drop-hint": "Copies into the case folder · becomes the only processo.pdf",
      ".rail-head h2": "Cases",
      "#stage-eyebrow": "Select or import a case",
      "#caso-titulo": "No active case",
      "#empty-state p": "Attach the PDF: xThemis creates the folder and stores one processo.pdf. Each action becomes one Word file and one PDF. Refine overwrites that same draft. When the court adds pages, use Update case and the main PDF is replaced.",
      "#btn-segredo": "Confidential",
      "#btn-excluir": "Delete case",
      "#btn-pasta": "Backup (ZIP)",
      "#btn-ver-prompts": "What it learned",
      "#btn-guardar-aprendizado": "Save what I teach it",
      "#empty-state .empty-kicker": "How it works",
      "#empty-state h3": "One case. One draft per action.",
      "#titulo-dialogo": "Talk to the AI",
      "#titulo-aprendizado": "What it learned",
      "#rotulo-guardar": "Save what I teach it",
      "#btn-prazo": "Count the deadline",
      "#btn-conversar": "Just talk",
      "#btn-refinar": "Refine this draft (overwrites)",
      "#btn-fechar": "Draft closed",
      "#btn-conferir-sumulas": "Check case law",
      "#peca-estado": "No open draft. The first action creates the file.",
      "#camadas-wrap h3": "Layered reading",
      "#indice-wrap h3": "Case index",
      "#extrato-wrap h3": "Case extract",
      "#btn-salvar-extrato": "Save extract",
      ".actions h3": "Draft a filing",
      "#chat-titulo": "Result",
      "#btn-salvar": "Write Word + PDF again",
      "#ajustes h2": "Settings",
      "#login h2": "Sign in",
      "#onb-title": "Who will use it",
      "#onb-pular": "Skip",
      "#onb-next": "Continue",
      ".posicao-nome": "Side",
      "[data-tipo=resumo]": "Summary",
      "[data-tipo=jurisprudencia]": "Case law",
      "[data-tipo=defesa]": "Defense",
      "[data-tipo=replica]": "Reply",
      "[data-tipo=recurso]": "Appeal",
      "[data-tipo=contrarrazoes]": "Response brief",
      "[data-tipo=alegacoes_finais]": "Closing argument",
      "[data-tipo=embargos]": "Motion to clarify",
      "[data-tipo=impugnacao_laudo]": "Challenge expert report",
      "[data-tipo=impugnacao_calculos]": "Challenge calculations",
      "[data-tipo=manifestacao]": "Filing",
      "[data-tipo=peticao]": "Petition",
      "[data-tipo=acordo]": "Settlement",
      "[data-tipo=personalizado]": "Custom request",
      "[data-tipo=tutela]": "Emergency relief",
      "[data-tipo=execucao]": "Enforcement",
      "[data-tipo=embargos_execucao]": "Execution challenge",
      "[data-tipo=agravo_peticao]": "Execution appeal",
      "[data-tipo=agravo_instrumento]": "Interlocutory appeal",
      "[data-tipo=revista]": "Higher-court appeal",
      "[data-tipo=quesitos]": "Expert questions",
    },
  },
  es: {
    sub: "PDF del proceso → borradores en Word y PDF",
    disc: "xThemis redacta. No es abogado, no protocoliza y no garantiza plazo, jurisprudencia ni resultado.",
    temaClaro: "Modo claro",
    temaEscuro: "Modo oscuro",
  },
};

function hostAtual() {
  return (location.hostname || "").toLowerCase().replace(/^www\./, "");
}

function langDoDominio() {
  const host = hostAtual();
  if (host === "xthemis.com") return "en";
  if (host === "xthemis.com.br") return "pt";
  return null;
}

let langAtual = "pt";

function aplicarIdioma(lang) {
  const pack = I18N[lang] || I18N.pt;
  langAtual = lang;
  document.documentElement.dataset.lang = lang;
  document.getElementById("brand-sub").textContent = pack.sub;
  document.getElementById("disclaimer").textContent = pack.disc;
  document.documentElement.lang = lang === "pt" ? "pt-BR" : lang;
  const tema = document.documentElement.dataset.theme === "light";
  document.getElementById("btn-tema").textContent = tema
    ? pack.temaEscuro || "Modo escuro"
    : pack.temaClaro || "Modo claro";
  Object.entries(pack.ui || {}).forEach(([sel, texto]) => {
    document.querySelectorAll(sel).forEach((el) => {
      el.textContent = texto;
    });
  });
  document.querySelectorAll("[data-en]").forEach((el) => {
    if (!el.dataset.pt) el.dataset.pt = el.textContent;
    el.textContent = lang === "en" ? el.dataset.en : el.dataset.pt;
  });
  const persona = document.getElementById("persona");
  if (persona && pack.lados) {
    [...persona.options].forEach((opt) => {
      if (pack.lados[opt.value]) opt.textContent = pack.lados[opt.value];
    });
  }
  aplicarCapa(selected?.meta);
  const ir = document.getElementById("lang-go");
  if (ir && langDoDominio()) {
    ir.textContent = lang === "en" ? "Português" : "English";
    ir.href = lang === "en" ? "https://www.xthemis.com.br/" : "https://www.xthemis.com/";
  }
}

document.getElementById("btn-conta").onclick = () => document.getElementById("login").showModal();
document.getElementById("login-fechar").onclick = () => document.getElementById("login").close();
document.getElementById("form-login").onsubmit = async (ev) => {
  ev.preventDefault();
  const r = await fetch(apiUrl("/api/entrar"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nome: document.getElementById("login-nome").value.trim(),
      senha: document.getElementById("login-senha").value,
      criar: document.getElementById("login-criar").checked,
    }),
  });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "Não entrou.");
  localStorage.setItem("harvey_token", data.token);
  document.getElementById("btn-conta").textContent = data.nome;
  document.getElementById("login").close();
  toast("Entrou como " + data.nome);
  refreshCasos();
};

let onbStep = 1;
function pintarOnb() {
  document.getElementById("onb-kicker").textContent = onbStep + " de 3";
  document.getElementById("onb-1").hidden = onbStep !== 1;
  document.getElementById("onb-2").hidden = onbStep !== 2;
  document.getElementById("onb-3").hidden = onbStep !== 3;
  document.getElementById("onb-title").textContent =
    onbStep === 1 ? "Quem vai usar" : onbStep === 2 ? "Anexar o processo" : "Gerar a peça";
  document.getElementById("onb-next").textContent = onbStep === 3 ? "Começar" : "Continuar";
}
document.getElementById("onb-next").onclick = async () => {
  if (onbStep === 1) {
    const nome = document.getElementById("onb-nome").value.trim();
    const senha = document.getElementById("onb-senha").value;
    if (nome && senha.length >= 4) {
      const r = await fetch(apiUrl("/api/entrar"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome, senha, criar: true }),
      });
      const data = await r.json();
      if (!r.ok) return toast(data.detail || "Não criei a conta.");
      localStorage.setItem("harvey_token", data.token);
      document.getElementById("btn-conta").textContent = data.nome;
    }
  }
  if (onbStep === 2) document.getElementById("pdf").click();
  if (onbStep >= 3) {
    localStorage.setItem("harvey_onboard", "1");
    document.getElementById("onboarding").close();
    return;
  }
  onbStep += 1;
  pintarOnb();
};
document.getElementById("onb-pular").onclick = () => {
  localStorage.setItem("harvey_onboard", "1");
  document.getElementById("onboarding").close();
};

const tema = localStorage.getItem("harvey_theme") || "dark";
document.documentElement.dataset.theme = tema;
if (langDoDominio()) localStorage.removeItem("harvey_lang");
aplicarIdioma(document.documentElement.dataset.lang || langDoDominio() || localStorage.getItem("harvey_lang") || "pt");
if (!localStorage.getItem("harvey_onboard")) {
  pintarOnb();
  document.getElementById("onboarding").showModal();
}
fetch(apiUrl("/api/eu"))
  .then((r) => r.json())
  .then((eu) => {
    if (eu.nome) {
    const extra = eu.acesso === "dono" ? " · administrador" : eu.acesso === "cortesia" ? " · gratuito" : eu.acesso === "avulso" ? " · por ação" : "";
    document.getElementById("btn-conta").textContent = eu.nome + extra;
  }
  })
  .catch(() => {});

