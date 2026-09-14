FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py docx_out.py extractor.py llm.py memory.py organizer.py prompts.py ./
COPY static ./static

ENV WEB_MODE=1
ENV DATA_DIR=/data
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /data

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
