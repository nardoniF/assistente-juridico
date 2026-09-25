# Harvey.ai — Roadmap

Objetivo: melhor assistente jurídico prático do planeta — começando por **trabalhista BR**, com pasta limpa (1 `processo.pdf` + 1 peça por ação) e peça lapidada por diálogo.

---

## Norte do produto

| Princípio | Significado |
|-----------|-------------|
| Um processo | Só `processo.pdf` — atualizar = sobrepor |
| Uma peça por ação | Refinar = reescrever o mesmo Word/PDF |
| Não inventa | Fato fora do extrato = “não consta” |
| Advogada no comando | IA sugere; humana fecha e protocola |
| Tudo mensurável | Tempo até peça, taxa de refine, erros de fls. |

---

## Fase 0 — Fundação (agora → 2 semanas)

**Meta:** estável, claro, usável pela tia sem suporte.

| # | Item | Por quê |
|---|------|---------|
| 0.1 | Status de geração em etapas (“lendo PDF… IA… gravando…”) | Acaba a dúvida do “Gerando…” |
| 0.2 | IA paga roteada (resumo barato / peça cara) | Qualidade forense |
| 0.3 | Hosting sempre acordado (ou cold-start &lt; 5s) | URL pública confiável |
| 0.4 | Domínio próprio apontando pro mesmo app | Marca Harvey |
| 0.5 | Checklist pós-peça (tempestividade, pedidos, fls., valores) | Menos peça “bonita e errada” |
| 0.6 | Diff no refine (antes × depois) | Confiança ao sobrepor |
| 0.7 | Onboarding 60s + textos da regra de pasta | Zero ambiguidade |

**Saída:** Harvey web + local estáveis; peça trabalhista boa no 1º ciclo de refine.

---

## Fase 1 — MVP escritório (2 → 8 semanas)

**Meta:** escritório pequeno usa todo dia sem medo.

| # | Item | Por quê |
|---|------|---------|
| 1.1 | Login + processos por usuária | Multi-advogada / LGPD básico |
| 1.2 | OCR forte (TRCT, holerites, comprovantes) | Autos reais são imagem |
| 1.3 | Índice do processo com fls. | Navegação e citação |
| 1.4 | Citação verificável (“fl. 677”) amarrada ao trecho | Combate alucinação |
| 1.5 | Extrato estruturado editável (partes, valores, datas) | Advogada corrige a base |
| 1.6 | Cruzamento comprovante × condenação (bis in idem) | Diferencial já validado no case Fertin |
| 1.7 | Travar peça até “fechada”; só então nova ação | Pasta limpa de verdade |
| 1.8 | Export PJe-ready + backup opcional | Protocolo e soberania dos arquivos |
| 1.9 | Templates de diálogo (“cruzar TRCT”, “impugnar laudo”) | Velocidade |
| 1.10 | Auditoria simples (quem / quando / modelo) | Confiança do escritório |

**Saída:** 5–20 usuárias ativas; &lt; 3 refines médios por peça “boa”.

---

## Fase 2 — Melhor do Brasil trabalhista (2 → 5 meses)

**Meta:** referência em RO / contestação / impugnações.

| # | Item | Por quê |
|---|------|---------|
| 2.1 | Jurisprudência verificável (TST/TRT) com fonte | Sem acórdão inventado |
| 2.2 | Calendário / prazos / tempestividade | Operação real |
| 2.3 | Persona reclamada × reclamante | Dois lados do balcão |
| 2.4 | Atualizar autos por páginas novas (merge) | Tribunal manda complemento |
| 2.5 | PDF gigante em camadas + fila de jobs | Processos 200+ MB |
| 2.6 | WhatsApp: PDF in → peça out | Aquisição e retenção |
| 2.7 | App desktop (pasta local sem “upload” percebido) | Preferência da advogada |
| 2.8 | Planos free / escritório | Sustentabilidade |
| 2.9 | Testes cegos de qualidade + score | Melhoria contínua |
| 2.10 | LGPD completo (retenção, exclusão, DPA) | Escala B2B |

**Saída:** marca Harvey = “trabalhista que não inventa e fecha peça”.

---

## Fase 3 — Planeta (6 → 18 meses)

**Meta:** assistente jurídico generalista de elite.

| # | Item | Por quê |
|---|------|---------|
| 3.1 | Multi-área (cível, previdenciário, família…) | Mercado maior |
| 3.2 | Agente end-to-end (PDF → minuta protocolável) | “Faz o trampo” |
| 3.3 | Próxima peça sugerida + risco / valor | Estratégia |
| 3.4 | Acordo assistido | Resolução |
| 3.5 | Aprendizado por escritório (estilo da banca) | Moat |
| 3.6 | API pública + integrações PJe/escritório | Plataforma |
| 3.7 | Dados no BR + enterprise ACL | Grandes bancas |
| 3.8 | ES / EN + outros ordenamentos | Planeta |
| 3.9 | Mobile-first fórum | Campo |
| 3.10 | Simulação e analytics de carteira | Gestão |

**Saída:** Harvey como sistema operacional do contencioso — humano decide, agente executa.

---

## Prioridade imediata (próximos 7 dias)

1. Status de geração em etapas  
2. Diff no refine  
3. Preset IA paga (Gemini Pro / OpenAI) no deploy  
4. Checklist pós-peça  
5. Medir: tempo médio geração + nº de refines até “ok”

---

## Métricas de sucesso

| Métrica | MVP | Escritório | Planeta |
|---------|-----|------------|---------|
| Tempo até 1ª peça útil | &lt; 5 min | &lt; 3 min | &lt; 2 min |
| Refines até “boa” | ≤ 4 | ≤ 2 | ≤ 1,5 |
| Alucinação de fls./jurisprudência | baixar | ~0 em amostra | ~0 auditado |
| NPS advogada | &gt; 40 | &gt; 60 | &gt; 70 |
| Uptime URL | 95% | 99% | 99,9% |

---

## Fora de escopo (por enquanto)

- Substituir OAB / responsabilidade profissional  
- Garantir ganho de causa  
- Treinar LLM próprio do zero (usar APIs + rag/jurisp. primeiro)

---

*Documento vivo — atualizar a cada release. Produto: Harvey.ai · Instância teste: https://3n20.com.br/harvey/*
