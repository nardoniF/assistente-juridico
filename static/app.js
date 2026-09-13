const lista = document.getElementById("lista");
const pdf = document.getElementById("pdf");
const importStatus = document.getElementById("import-status");
const acaoStatus = document.getElementById("acao-status");
const acoesWrap = document.getElementById("acoes-wrap");
const casoAtual = document.getElementById("caso-atual");
const chatWrap = document.getElementById("chat-wrap");
const chat = document.getElementById("chat");
const chatTitulo = document.getElementById("chat-titulo");
const arquivosGerados = document.getElementById("arquivos-gerados");
const ajustes = document.getElementById("ajustes");
const promptsBox = document.getElementById("prompts-box");

let selected = null;
let lastResult = null;
let lastTipo = null;
let configCache = null;

async function refreshConfig() {
  configCache = await (await fetch("/api/config")).json();
  document.getElementById("api-model").value = configCache.model;
  document.getElementById("pasta-info").textContent =
    "Pastas: " +
    configCache.processos_dir +
    (configCache.has_key ? " · chave OK" : " · ainda sem chave") +
    " · aprendizado: " +
    (configCache.aprendizado_global || "");
  document.getElementById("custo-info").textContent = configCache.custo_estimado || "";
  document.getElementById("api-key").placeholder = configCache.has_key
    ? configCache.masked_key
    : "AIza... ou sk-...";
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
  if (docs.length) bits.push(docs.slice(0, 4).join(", ") + (docs.length > 4 ? "…" : ""));
  if (c.prompts_salvos) bits.push(c.prompts_salvos + " prompt(s)");
  return bits.join(" · ") || "só o PDF por enquanto";
}

async function refreshCasos(selectId) {
  const casos = await (await fetch("/api/casos")).json();
  lista.innerHTML = "";
  if (!casos.length) {
    lista.innerHTML = "<p class='muted'>Nenhum processo ainda.</p>";
    return;
  }
  for (const c of casos) {
    const m = c.meta || {};
    const div = document.createElement("div");
    div.className = "caso" + (selectId === c.id ? " active" : "");
    div.innerHTML = `<div>
      <strong>${m.numero || c.id}</strong><br/>
      ${(m.reclamante || "").slice(0, 40)} × ${(m.reclamado || "").slice(0, 40)}
      <div class="muted">${filesLabel(c)}</div>
    </div>`;
    const b = document.createElement("button");
    b.className = "ghost";
    b.textContent = "Usar este";
    b.onclick = () => selectCase(c);
    div.appendChild(b);
    lista.appendChild(div);
  }
}

function selectCase(c) {
  selected = c;
  acoesWrap.hidden = false;
  promptsBox.hidden = true;
  const m = c.meta || {};
  casoAtual.textContent = `${m.numero || c.id} · pasta: ${c.path}`;
  refreshCasos(c.id);
}

pdf.addEventListener("change", async () => {
  const file = pdf.files[0];
  if (!file) return;
  importStatus.textContent = "Lendo o PDF e criando a pasta. PDFs grandes podem levar um minuto…";
  const fd = new FormData();
  fd.append("arquivo", file);
  try {
    const r = await fetch("/api/importar", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok && !data.ok) throw new Error(data.detail || "falha");
    importStatus.textContent = "Pronto. Pasta criada: " + data.path;
    selected = { id: data.id, path: data.path, meta: data.meta };
    acoesWrap.hidden = false;
    casoAtual.textContent = `${data.meta.numero} · ${data.meta.reclamante} × ${data.meta.reclamado}`;
    await refreshCasos(data.id);
  } catch (e) {
    importStatus.textContent = "Não consegui importar: " + e.message;
  }
});

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
      acaoStatus.textContent =
        "No pedido personalizado, escreva no diálogo o que a IA deve fazer.";
      return;
    }
    lastTipo = tipo;
    acaoStatus.textContent =
      "Lendo o PDF, gerando a peça e gravando Word + PDF… (1–3 min no Gemini Pro)";
    chatWrap.hidden = modo !== "chat";
    const fd = new FormData();
    fd.append("case_id", selected.id);
    fd.append("tipo", tipo);
    fd.append("modo", modo);
    fd.append("salvar_aprendizado", learnFlag());
    if (instrucoes) fd.append("instrucoes_extra", instrucoes);
    try {
      const r = await fetch("/api/acao", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "falha");
      lastResult = data;
      const dx = data.arquivo_docx || data.arquivos?.docx;
      const pf = data.arquivo_pdf || data.arquivos?.pdf;
      acaoStatus.textContent =
        "Pronto. Word: " + dx + " · PDF: " + pf + " · pasta: " + data.pasta;
      if (modo === "chat") {
        chatWrap.hidden = false;
        chatTitulo.textContent = data.titulo;
        chat.textContent = data.texto;
        arquivosGerados.textContent = "Arquivos: " + dx + " + " + pf;
      }
      if (instrucoes && learnFlag() === "1") {
        document.getElementById("instrucoes-extra").value = "";
      }
      await refreshCasos(selected.id);
    } catch (e) {
      acaoStatus.textContent = e.message;
    }
  });
});

document.getElementById("btn-refinar").onclick = async () => {
  if (!selected) return;
  const feedback = document.getElementById("instrucoes-extra").value.trim();
  if (!feedback) {
    acaoStatus.textContent =
      "Escreva no diálogo o que faltou (ex.: analisar férias do TRCT) e clique em Refinar.";
    return;
  }
  acaoStatus.textContent = "Refinando a última peça e atualizando Word + PDF…";
  const fd = new FormData();
  fd.append("case_id", selected.id);
  fd.append("feedback", feedback);
  fd.append("salvar_aprendizado", learnFlag());
  try {
    const r = await fetch("/api/refinar", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "falha");
    lastResult = data;
    chatWrap.hidden = false;
    chatTitulo.textContent = data.titulo + " (refinado)";
    chat.textContent = data.texto;
    arquivosGerados.textContent =
      "Atualizados: " + data.arquivo_docx + " + " + data.arquivo_pdf;
    acaoStatus.textContent =
      "Peça refinada. Word e PDF atualizados. Prompt guardado no processo" +
      (learnFlag() === "1" ? " e no aprendizado global." : ".");
    if (learnFlag() === "1") document.getElementById("instrucoes-extra").value = "";
    await refreshCasos(selected.id);
  } catch (e) {
    acaoStatus.textContent = e.message;
  }
};

document.getElementById("btn-ver-prompts").onclick = async () => {
  if (!selected) return;
  const data = await (await fetch("/api/prompts?case_id=" + encodeURIComponent(selected.id))).json();
  const geral = (data.caso?.geral || []).map((x) => "• " + x).join("\n") || "(nenhum)";
  const glob = Object.entries(data.global?.por_tipo || {})
    .map(([k, arr]) => k + ":\n" + arr.map((x) => "  • " + x).join("\n"))
    .join("\n\n") || "(nenhum)";
  promptsBox.hidden = false;
  promptsBox.textContent =
    "PROMPTS DESTE PROCESSO\n" +
    geral +
    "\n\nAPRENDIZADO GLOBAL (por tipo de ação)\n" +
    glob;
};

document.getElementById("btn-salvar").onclick = async () => {
  if (!selected || !lastResult?.texto) return;
  const r = await fetch("/api/salvar-docx", {
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
  acaoStatus.textContent = data.ok
    ? "Regravado: " + data.arquivo + " + " + data.pdf
    : "Não salvou.";
  refreshCasos(selected.id);
};

document.getElementById("btn-pasta").onclick = async () => {
  if (!selected) return;
  await fetch("/api/abrir-pasta?case_id=" + encodeURIComponent(selected.id));
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
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  ajustes.close();
  refreshConfig();
};

refreshConfig();
refreshCasos();
