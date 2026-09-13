# Assistente Jurídico

Programa local (Windows/Mac) para organizar processos trabalhistas em PDF, gerar peças (Word + PDF) e guardar prompts por processo.

**Não precisa do Cursor.** Roda no navegador em `http://127.0.0.1:8765`.

## Baixar / clonar

```bash
git clone https://github.com/nardoniF/assistente-juridico.git
```

Ou no GitHub: botão verde **Code → Download ZIP**.

## Windows (máquina da advogada)

1. Extraia a pasta `PACOTE_WINDOWS` (ou o ZIP do GitHub).
2. Instale Python: https://www.python.org/downloads/  
   Marque **Add python.exe to PATH**.
3. Dois cliques em `Iniciar_janela_fixa.bat` (**sem** administrador).
4. Deixe a janela preta aberta.
5. No site: **Ajustes → Groq (gratuito)** → chave em https://console.groq.com/keys → Salvar.
6. Escolha o PDF do processo e gere a peça.

Se falhar: rode `Diagnostico.bat` e envie `diagnostico.txt`.

## Mac

```bash
cd assistente-juridico
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Ou duplo clique em `Iniciar.command`.

## IA

- **Groq (grátis):** https://console.groq.com/keys — chave `gsk_...`
- Gemini / OpenAI: opcionais (pagos)

## O que a pasta do processo contém

- `processo.pdf` — original  
- `NomeDaPeca.docx` — para editar  
- `NomeDaPeca.pdf` — para enviar  
- `prompts_caso.json` — aprendizado daquele processo  

Pastas: `Documentos/Assistente Juridico/Processos/`

## Segurança

Não grave chave de API no repositório. Use só em **Ajustes** no PC.
