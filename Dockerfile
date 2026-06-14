# --------------------------------------------------------------------------
# Dockerfile — Multi-Modal Enterprise Agent
#
# Packages : agent LangGraph + FastAPI + modèle d'embedding local
# Expose un endpoint REST sur le port défini par $PORT (requis par Cloud Run)
# --------------------------------------------------------------------------

FROM python:3.11-slim

WORKDIR /app

# Dépendances système minimales (pdfplumber a besoin de libs pour le PDF parsing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python (mise en cache du layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Pré-télécharge le modèle d'embedding pour éviter de le faire au runtime
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"


COPY src/ ./src/
COPY data/finances.db ./data/finances.db

WORKDIR /app/src

# Cloud Run injecte la variable d'environnement PORT (par défaut 8080)
ENV PORT=8080
EXPOSE 8080

# uvicorn doit écouter sur 0.0.0.0 et sur $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]