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
  document.querySelectorAll("#comando button[data-tipo], #btn-refinar").forEach((b) => {
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
  document.getElementById("pasta-info").textContent =
    pasta + " · aprendizado: " + (configCache.aprendizado_global || "");
  document.getElementById("pasta-mini").textContent = configCache.has_key
    ? "xThemis · IA pronta · " + (configCache.provider_label || configCache.provider || "")
    : "Configure a IA em Ajustes (Gemini Pro recomendado)";
  document.getElementById("custo-info").textContent = configCache.custo_estimado || "";
  document.getElementById("escritorio").value = configCache.escritorio || "";
  document.getElementById("advogada").value = configCache.advogada || "";
  document.getElementById("oab").value = configCache.oab || "";
  const campoChave = document.getElementById("api-key");
  campoChave.disabled = false;
  campoChave.placeholder = configCache.key_from_env
    ? "Cole a chave paga (sk-... ou AIza...). O teste grátis continua no servidor."
    : configCache.has_key
      ? configCache.masked_key
      : "AIza... / sk-... / gsk_...";
  const preset = document.getElementById("preset");
  if (configCache.model === "openai/gpt-oss-120b" || configCache.provider === "groq")
    preset.value = "groq_free";
  else if (configCache.model === "gemini-2.5-pro") preset.value = "google_pro";
  else if (configCache.model === "gemini-2.5-flash-lite") preset.value = "google_lite";
  else if (configCache.model === "gpt-4.1-mini") preset.value = "openai_mini";
  else if (configCache.model === "gemini-2.5-flash") preset.value = "google_flash";
  else preset.value = "groq_free";
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
      <div class="meta">${(m.reclamante || "—").slice(0, 36)} × ${(m.reclamado || "—").slice(0, 36)}</div>
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
  casoAtual.textContent = `${(m.reclamante || "—").slice(0, 60)} × ${(m.reclamado || "—").slice(0, 60)} · ${c.path}`;
  renderIndice(m);
  renderExtrato(m);
  carregarCamadas();
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

function renderExtrato(meta) {
  const ex = (meta && meta.extrato) || {};
  document.getElementById("ex-numero").value = ex.numero || meta.numero || "";
  document.getElementById("ex-autuacao").value = ex.autuacao || meta.autuacao || "";
  document.getElementById("ex-valor").value = ex.valor_causa || meta.valor_causa || "";
  document.getElementById("ex-reclamante").value = ex.reclamante || meta.reclamante || "";
  document.getElementById("ex-reclamado").value = ex.reclamado || meta.reclamado || "";
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
      for (let i = 0; i < 80; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const j = await (await fetch(apiUrl("/api/job?id=" + data.job))).json();
        if (j.status === "ok") {
          data = j.result;
          break;
        }
        if (j.status === "erro") throw new Error(j.detail || "fila");
        if (i === 79) throw new Error("A fila ainda está lendo. Atualize a página daqui a pouco.");
      }
    }
    setStatus(importStatus, "Pasta criada.", "ok");
    selected = { id: data.id, path: data.path, meta: data.meta };
    selectCase(selected);
    await refreshCasos(data.id);
    toast("Processo na pasta · processo.pdf único.");
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
      await syncSelected();
      toast(`Peça pronta: ${dx} · ${pf}`);
    } catch (e) {
      toast(e.message);
    } finally {
      setBusy(false);
    }
  });
});

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
  try {
    const r = await fetch(apiUrl("/api/refinar"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    lastResult = data;
    showResult(data, " (refinado)", { antes: data.texto_anterior || antes });
    if (learnFlag() === "1") document.getElementById("instrucoes-extra").value = "";
    await syncSelected();
    toast("Mesma peça sobrescrita · veja o diff.");
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

document.getElementById("btn-ver-prompts").onclick = async () => {
  if (!selected) return;
  const data = await (
    await fetch(apiUrl("/api/prompts?case_id=" + encodeURIComponent(selected.id)))
  ).json();
  const geral = (data.caso?.geral || []).map((x) => "• " + x).join("\n") || "(nenhum)";
  const glob =
    Object.entries(data.global?.por_tipo || {})
      .map(([k, arr]) => k + ":\n" + arr.map((x) => "  • " + x).join("\n"))
      .join("\n\n") || "(nenhum)";
  const u = data.ultima || {};
  const met =
    u.refines != null
      ? `\n\nÚLTIMA PEÇA · refines: ${u.refines} · gerações: ${u.geracoes || "—"} · ${
          u.segundos != null ? u.segundos + "s" : ""
        }`
      : "";
  const hist = (data.caso?.historico || [])
    .slice(-12)
    .reverse()
    .map((x) => `${x.quando || ""} · ${x.tipo || ""}\n${x.texto || ""}`)
    .join("\n\n") || "(nenhum pedido ainda)";
  const aud = await (
    await fetch(apiUrl("/api/auditoria?case_id=" + encodeURIComponent(selected.id)))
  ).json();
  const auditTxt = (aud.linhas || [])
    .slice(-12)
    .reverse()
    .map((x) => `${x.quando || ""} · ${x.usuario || ""} · ${x.acao || ""} ${x.detalhe || ""}`)
    .join("\n") || "(ainda sem registro)";
  promptsBox.hidden = false;
  promptsBox.textContent =
    "O QUE MUDOU\n" +
    hist +
    "\n\nAUDITORIA\n" +
    auditTxt +
    "\n\nPROMPTS DESTE PROCESSO\n" +
    geral +
    "\n\nAPRENDIZADO GLOBAL (por tipo de ação)\n" +
    glob +
    met;
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
    renderExtrato(data.meta);
    toast("Extrato salvo. A próxima peça usa esta versão.");
    await refreshCasos(selected.id);
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

async function carregarConvidados() {
  const box = document.getElementById("convidados-box");
  const r = await fetch(apiUrl("/api/convidados"));
  if (r.status === 403) {
    if (box) box.hidden = true;
    return;
  }
  const data = await r.json();
  if (!r.ok) return;
  if (box) box.hidden = false;
  renderConvidados(data.convidados || []);
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

document.getElementById("btn-convidado").onclick = async () => {
  const r = await fetch(apiUrl("/api/convidados"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nome: document.getElementById("convidado-nome").value.trim(),
      nota: document.getElementById("convidado-nota").value.trim(),
    }),
  });
  const data = await r.json();
  if (!r.ok) return toast(data.detail || "Não incluí.");
  document.getElementById("convidado-nome").value = "";
  document.getElementById("convidado-nota").value = "";
  renderConvidados(data.convidados || []);
  toast("Convidado na lista gratuita.");
};

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

document.getElementById("salvar-ajustes").onclick = async (ev) => {
  ev.preventDefault();
  const key = document.getElementById("api-key").value.trim();
  const body = {
    preset: document.getElementById("preset").value,
    model: document.getElementById("api-model").value,
    escritorio: document.getElementById("escritorio").value.trim(),
    advogada: document.getElementById("advogada").value.trim(),
    oab: document.getElementById("oab").value.trim(),
  };
  if (key && !key.startsWith("•")) body.api_key = key;
  await fetch(apiUrl("/api/config"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  ajustes.close();
  refreshConfig();
  toast("Ajustes salvos.");
};

refreshConfig();
refreshCasos();

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
  aplicarIdioma(document.getElementById("idioma").value, false);
};

const I18N = {
  pt: {
    sub: "Processos em PDF → peças em Word e PDF",
    disc: "xThemis é assistente de redação. Não é advogado, não protocola e não garante prazo, jurisprudência nem resultado.",
    temaClaro: "Modo claro",
    temaEscuro: "Modo escuro",
  },
  en: {
    sub: "Case PDF → Word and PDF drafts",
    disc: "xThemis drafts text. It is not a lawyer, does not file, and does not guarantee deadlines, case law, or outcome.",
    temaClaro: "Light mode",
    temaEscuro: "Dark mode",
    ui: {
      "#btn-conta": "Sign in",
      "#btn-ajustes": "AI settings",
      "#dropzone strong": "Attach the case PDF",
      "#dropzone span": "Copies into the case folder · becomes the only processo.pdf",
      ".rail-head h2": "Cases",
      "#stage-eyebrow": "Select or import a case",
      "#caso-titulo": "No active case",
      "#empty-state p": "Attach the PDF: xThemis creates the folder and stores one processo.pdf. Each action becomes one Word file and one PDF. Refine overwrites that same draft. When the court adds pages, use Update case and the main PDF is replaced.",
      "#btn-segredo": "Confidential",
      "#btn-excluir": "Delete case",
      "#btn-pasta": "Backup (ZIP)",
      "#btn-ver-prompts": "Prompts",
      "#empty-state .empty-kicker": "How it works",
      "#empty-state h3": "One case. One draft per action.",
      ".dialogue h3": "Talk to the AI",
      ".dialogue .switch span": "Save what I teach it",
      "#btn-prazo": "Count the deadline",
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

function langDoDominio() {
  const host = (location.hostname || "").toLowerCase().replace(/^www\./, "");
  if (host === "xthemis.com") return "en";
  if (host === "xthemis.com.br") return "pt";
  return null;
}

function aplicarIdioma(lang, gravar) {
  const pack = I18N[lang] || I18N.pt;
  if (gravar) localStorage.setItem("harvey_lang", lang);
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
}

document.getElementById("idioma").onchange = (ev) => {
  aplicarIdioma(ev.target.value, true);
};

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
const lang = localStorage.getItem("harvey_lang") || langDoDominio() || "pt";
document.getElementById("idioma").value = lang;
aplicarIdioma(lang, false);
if (!localStorage.getItem("harvey_onboard")) {
  pintarOnb();
  document.getElementById("onboarding").showModal();
}
fetch(apiUrl("/api/eu"))
  .then((r) => r.json())
  .then((eu) => {
    if (eu.nome) {
    const extra = eu.acesso === "cortesia" ? " · gratuito" : eu.acesso === "avulso" ? " · por ação" : "";
    document.getElementById("btn-conta").textContent = eu.nome + extra;
  }
  })
  .catch(() => {});

