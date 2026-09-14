# Harvey.ai

Produto da **3n20** — analisa processos em PDF e gera peças (Word + PDF) com IA.

- **Git do produto:** este repositório  
- **URL pública (instância 3n20):** https://3n20.com.br/harvey/  
- **IA gratuita:** [Groq](https://console.groq.com/keys)  
- **Hosting gratuito da API:** [Render](https://render.com) (plano free) ou Hugging Face Spaces

## Arquitetura (tudo grátis)

| Camada | Onde | Custo |
|--------|------|-------|
| Front | GitHub Pages em `3n20.com.br/harvey/` | Grátis |
| API | Render free (Docker deste repo) | Grátis* |
| IA | Groq | Grátis (limites) |

\*Render free “dorme” sem uso (~1 min no 1º acesso).

## Subir a API (uma vez)

1. Conta grátis em https://render.com (login com GitHub).
2. **New → Blueprint** → repo `nardoniF/assistente-juridico` → `render.yaml`.
3. Em Environment, cole `GROQ_API_KEY` (chave `gsk_...`).
4. Copie a URL tipo `https://harvey-ai.onrender.com`.
5. No site 3n20, pasta `harvey/config.js`, defina `apiBase` com essa URL.
6. Commit/push do `site-3n20`.

## Dev local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=gsk_...
python app.py
```

Abra http://127.0.0.1:8765

## Domínio próprio (depois)

Quando comprar o domínio, aponte o DNS para o mesmo serviço Render (ou mova o front).  
`ROOT`/`apiBase` vazio se front e API forem a mesma origem.
