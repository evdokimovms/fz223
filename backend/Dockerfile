FROM python:3.11-slim

WORKDIR /app

# psycopg2 + конвертеры .doc (antiword/catdoc) + OCR для сканов PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    antiword \
    catdoc \
    tesseract-ocr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

# CPU-сборка torch (в контейнере без CUDA образ получается в разы меньше)
#RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu128

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# API:    uvicorn main:app --host 0.0.0.0 --port 8000
# Worker: python worker.py   (в compose: command: python worker.py)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
