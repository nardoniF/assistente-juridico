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
  document.querySelectorAll("#acoes-wrap button[data-tipo], #btn-refinar").forEach((b) => {
    b.disabled = on;
  });
  if (!on) {
    busySteps.innerHTML = "";
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
    ? "Harvey · IA pronta · " + (configCache.provider_label || configCache.provider || "")
    : "Configure a IA em Ajustes (Gemini Pro recomendado)";
  document.getElementById("custo-info").textContent = configCache.custo_estimado || "";
  document.getElementById("api-key").placeholder = configCache.has_key
    ? configCache.masked_key
    : "AIza... / sk-... / gsk_...";
  document.getElementById("api-key").disabled = !!configCache.key_from_env;
  if (configCache.key_from_env) {
    document.getElementById("api-key").placeholder = configCache.masked_key + " (servidor)";
  }
  const preset = document.getElementById("preset");
  if (configCache.model === "llama-3.3-70b-versatile" || configCache.provider === "groq")
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
  renderLista(c.id);
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
  chat.textContent = data.texto || "";
  const dx = data.arquivo_docx || data.arquivos?.docx;
  const pf = data.arquivo_pdf || data.arquivos?.pdf;
  arquivosGerados.textContent =
    dx || pf ? `Arquivos: ${dx || "—"} + ${pf || "—"}` : "";
  showMetrics(data);
  renderChecklist(data.texto || "");
  const prev = antes || data.texto_anterior;
  if (prev) showDiff(prev, data.texto || "");
  else diffWrap.hidden = true;
  chat.scrollTop = 0;
}

async function importFile(file) {
  if (!file) return;
  setStatus(importStatus, "Lendo o PDF e criando a pasta…");
  setBusy(true, "Importando processo…", "importar");
  const fd = new FormData();
  fd.append("arquivo", file);
  try {
    const r = await fetch(apiUrl("/api/importar"), { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok && !data.ok) throw new Error(data.detail || "falha");
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

function learnFlag() {
  return document.getElementById("salvar-aprendizado").checked ? "1" : "0";
}

document.querySelectorAll("#acoes-wrap button[data-tipo]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!selected) return;
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
      await refreshCasos(selected.id);
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
    toast("Escreva o que faltou; o Harvey reescreve a mesma peça.");
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
    await refreshCasos(selected.id);
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
  promptsBox.hidden = false;
  promptsBox.textContent =
    "PROMPTS DESTE PROCESSO\n" +
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

document.getElementById("btn-pasta").onclick = async () => {
  if (!selected) return;
  window.location.href = apiUrl(
    "/api/baixar-pasta?case_id=" + encodeURIComponent(selected.id)
  );
};

document.getElementById("btn-ajustes").onclick = () => {
  refreshConfig();
  ajustes.showModal();
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
