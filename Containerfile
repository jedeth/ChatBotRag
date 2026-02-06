# ==============================================================================
# Containerfile — Chatbot RAG
# Django 4.2 + Gunicorn + pgvector
# Même patterns que le Containerfile de noScribe-portal
# ==============================================================================

# 1. Image de base
FROM python:3.11-slim

# 2. Métadonnées
LABEL maintainer="Rectorat de Paris"
LABEL description="Chatbot RAG — Django + pgvector"

# 3. Environnement Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. Dépendances système
#    gcc + libpq-dev      → compilation psycopg (adaptateur PostgreSQL)
#    postgresql-client    → pg_isready utilisé en healthcheck
#    curl                 → healthcheck conteneur
#    poppler-utils        → extraction PDF (PyMuPDF)
#    xmlsec1 + libxml*    → SAML (prêt à brancher)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    postgresql-client \
    curl \
    poppler-utils \
    xmlsec1 \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 5. Répertoire de travail
WORKDIR /app

# 6. Dépendances Python (cache optimisé : requirements séparé)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Code de l'application
COPY . .

# 8. Utilisateur non-root (UID 1001 = iarag sur l'hôte)
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app

# 9. Répertoires nécessaires à l'exécution
RUN mkdir -p /app/staticfiles /app/media /app/logs && \
    chown -R appuser:appuser /app/staticfiles /app/media /app/logs

# 10. Basculer vers l'utilisateur non-root
USER appuser

# 11. Collecter les fichiers statiques
#     collectstatic ne connecte pas à la DB — aucun problème même sans
#     PostgreSQL pendant le build.
RUN python manage.py collectstatic --noinput --clear 2>&1 || true

# 12. Port
EXPOSE 8000

# 13. Commande de démarrage (même signature que noScribe-portal)
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "chatbot_rag.wsgi:application"]
