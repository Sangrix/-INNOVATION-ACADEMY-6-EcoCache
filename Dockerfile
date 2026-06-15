FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first to keep the image lean (~600 MB vs ~2.5 GB GPU build)
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining deps (torch>=2.0.0 in rag/requirements.txt is already satisfied)
COPY api/requirements.txt     /tmp/req-api.txt
COPY rag/requirements.txt     /tmp/req-rag.txt
COPY carbon/requirements.txt  /tmp/req-carbon.txt
RUN pip install --no-cache-dir \
    -r /tmp/req-api.txt \
    -r /tmp/req-rag.txt \
    -r /tmp/req-carbon.txt

# Pre-download BGE-m3-ko so the first request isn't slow
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('dragonkue/BGE-m3-ko')"

# Copy source
COPY api/     ./api/
COPY rag/     ./rag/
COPY carbon/  ./carbon/
COPY index.html ./

EXPOSE 8000

WORKDIR /app/api
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
