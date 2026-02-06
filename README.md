# ChatBot RAG - Assistant Documentaire Intelligent

Application de chatbot RAG (Retrieval-Augmented Generation) permettant d'interroger des documents uploadés via une interface conversationnelle. Le système utilise la recherche vectorielle pour récupérer les passages pertinents et génère des réponses contextualisées via l'API Albert (DINUM).

## 🎯 Fonctionnalités

- **Upload multi-format** : PDF, DOCX, XLSX, TXT, Markdown
- **Recherche vectorielle** : Index HNSW avec pgvector pour une recherche rapide et précise
- **RAG intelligent** :
  - Consultation des métadonnées pour les questions statistiques (comptage, totaux)
  - Recherche vectorielle pour les questions sémantiques
  - Citation automatique des sources
- **Traitement asynchrone** : Vectorisation en tâche de fond via Celery
- **Métadonnées enrichies** :
  - XLSX : nombre de lignes, colonnes, statistiques par feuille
  - PDF : nombre de pages, table des matières
- **Interface web** : Authentification Django, chat en temps réel, gestion des documents
- **Architecture conteneurisée** : Déploiement Podman avec orchestration complète

## 🏗️ Architecture

### Stack Technique

- **Backend** : Django 4.2.7, Python 3.9
- **Base de données** : PostgreSQL 15 + extension pgvector
- **Recherche vectorielle** : pgvector avec index HNSW (Hierarchical Navigable Small World)
- **Queue de tâches** : Celery + Redis
- **Embeddings & LLM** : API Albert (DINUM) - Modèle BAAI/bge-m3 (1024 dimensions)
- **Serveur web** : Gunicorn + Nginx
- **Conteneurisation** : Podman / Docker
- **Extraction de texte** : PyMuPDF (PDF), python-docx (DOCX), openpyxl (XLSX)
- **Découpage de texte** : LangChain RecursiveCharacterTextSplitter

### Composants

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Nginx     │────▶│  Django App  │────▶│ PostgreSQL  │
│  (reverse   │     │  (Gunicorn)  │     │  + pgvector │
│   proxy)    │     └──────────────┘     └─────────────┘
└─────────────┘            │
                           │
                    ┌──────┴──────┐
                    ▼             ▼
              ┌──────────┐  ┌──────────┐
              │  Celery  │  │  Redis   │
              │  Worker  │  │  (broker)│
              └──────────┘  └──────────┘
                    │
                    ▼
              ┌──────────────┐
              │  Albert API  │
              │    (DINUM)   │
              └──────────────┘
```

## 📋 Prérequis

- Podman (ou Docker)
- PostgreSQL 15+ avec extension pgvector
- Accès API Albert (DINUM) - Token d'authentification
- 2 Go RAM minimum
- 10 Go espace disque pour les documents

## 🚀 Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/jedeth/ChatBotRag.git
cd ChatBotRag
```

### 2. Configuration

Créer un fichier `.env` à la racine du projet :

```env
# Django
SECRET_KEY=votre-secret-key-django-ultra-securisee
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,votre-domaine.fr

# Base de données
POSTGRES_DB=chatbot_rag
POSTGRES_USER=chatbot_user
POSTGRES_PASSWORD=votre-mot-de-passe-secure
DATABASE_URL=postgresql://chatbot_user:votre-mot-de-passe-secure@db:5432/chatbot_rag

# Redis
REDIS_URL=redis://redis:6379/0

# API Albert (DINUM)
ALBERT_API_URL=https://albert.api.etalab.gouv.fr/v1
ALBERT_API_TOKEN=votre-token-albert
ALBERT_MODEL=BAAI/bge-m3
```

### 3. Démarrage avec Podman

```bash
# Construire et démarrer tous les services
podman-compose up -d

# Attendre que PostgreSQL soit prêt (environ 10-15 secondes)
sleep 15

# Créer les tables et appliquer les migrations
podman exec chatbot-web python manage.py migrate

# Créer un super-utilisateur
podman exec -it chatbot-web python manage.py createsuperuser

# Collecter les fichiers statiques
podman exec chatbot-web python manage.py collectstatic --noinput
```

### 4. Accéder à l'application

- **Interface utilisateur** : http://localhost:8080
- **Admin Django** : http://localhost:8080/admin
- **API Albert** : configurée via variables d'environnement

## 📂 Structure du Projet

```
chatbot-rag/
├── chatbot_rag/           # Configuration Django
│   ├── settings.py        # Configuration principale
│   ├── urls.py            # URLs racine
│   ├── celery.py          # Configuration Celery
│   └── wsgi.py            # WSGI pour Gunicorn
│
├── rag/                   # Application principale
│   ├── models.py          # Document, DocumentChunk, Conversation, Message
│   ├── views.py           # Vues web (chat, documents, auth)
│   ├── forms.py           # Formulaires (upload, validation sécurité)
│   ├── tasks.py           # Tâche Celery de vectorisation
│   ├── services/
│   │   ├── albert_client.py      # Client API Albert
│   │   ├── rag_engine.py         # Moteur RAG principal
│   │   └── vectorization.py      # Extraction et découpage
│   ├── migrations/        # Migrations Django
│   └── templates/         # Templates HTML
│
├── nginx/                 # Configuration Nginx
├── docs/                  # Documentation technique
├── compose.yaml           # Orchestration Podman
├── Containerfile          # Image Django
└── requirements.txt       # Dépendances Python
```

## 🔧 Pipeline de Vectorisation

### Étapes pour chaque document uploadé

1. **Upload** → Document sauvegardé en base (statut: `pending`)
2. **Tâche Celery lancée** → Traitement asynchrone
3. **Extraction** :
   - PDF : PyMuPDF avec numéros de page
   - DOCX : python-docx paragraphe par paragraphe
   - XLSX : openpyxl avec statistiques (lignes, colonnes, feuilles)
   - TXT/MD : lecture brute UTF-8
4. **Métadonnées** : Sauvegarde des stats (Document.metadata)
5. **Découpage** : RecursiveCharacterTextSplitter (chunks 1000 char, overlap 200)
6. **Embeddings** : API Albert par lots de 64 → vecteurs 1024 dimensions
7. **Stockage** : Bulk insert des chunks avec embeddings dans pgvector
8. **Index HNSW** : Création automatique pour recherche rapide
9. **Finalisation** → Document en statut `vectorized`

## 💬 Pipeline de Requête RAG

### Traitement d'une question utilisateur

1. **Détection du type de question** :
   - Mots-clés statistiques (combien, nombre, total) → **Mode Métadonnées**
   - Autres questions → **Mode Vectoriel**

2. **Mode Métadonnées** (pour XLSX) :
   - Récupération des stats depuis Document.metadata
   - Prompt avec statistiques exactes
   - Génération réponse (température 0.3 pour déterminisme)

3. **Mode Vectoriel** (recherche sémantique) :
   - Embedding de la question (Albert API)
   - Recherche cosinus dans pgvector (TOP_K=5, seuil=0.8)
   - Construction du prompt avec contexte
   - Génération réponse avec citations
   - Extraction et déduplication des sources

## 🔐 Sécurité

- **Validation des uploads** :
  - Magic bytes vérifiés (avec exception pour DOCX/XLSX en ZIP)
  - Extensions whitelist
  - Taille limitée (configurable)
- **Authentification Django** : Obligatoire pour accès
- **Isolation utilisateur** : Chaque user voit uniquement ses documents
- **Secrets** : Variables d'environnement (.env exclu de Git)
- **Conteneurisation** : Isolation des services

## 📊 Modèle de Données

### Document
- `filename` : Nom du fichier
- `file` : FileField Django (stockage media/)
- `user` : ForeignKey vers User
- `status` : pending | vectorizing | vectorized | failed
- `chunk_count` : Nombre de chunks générés
- `metadata` : JSONField - statistiques (XLSX: lignes/colonnes, PDF: pages)
- `created_at`, `updated_at`

### DocumentChunk
- `document` : ForeignKey vers Document
- `chunk_index` : Position du chunk
- `content` : Texte du chunk
- `embedding` : VectorField(1024) - vecteur pgvector
- Index HNSW sur `embedding` pour recherche rapide

### Conversation
- `user` : ForeignKey vers User
- `title` : Titre généré depuis premier message
- `created_at`, `updated_at`

### Message
- `conversation` : ForeignKey vers Conversation
- `role` : user | assistant
- `content` : Texte du message
- `sources` : JSONField - sources citées (pour messages assistant)
- `created_at`

## 🎛️ Configuration Avancée

### Paramètres RAG (rag/services/rag_engine.py)

```python
TOP_K = 5                    # Nombre de chunks récupérés
SIMILARITY_THRESHOLD = 0.8   # Seuil distance cosinus (0=identique, 1=orthogonal)
```

### Paramètres de découpage (rag/services/vectorization.py)

```python
chunk_size = 1000            # Taille des chunks en caractères
chunk_overlap = 200          # Chevauchement entre chunks
min_chunk_size = 50          # Taille minimale (filtrage chunks vides)
```

### Paramètres Albert (rag/services/albert_client.py)

```python
BATCH_SIZE = 64              # Taille des lots pour embeddings
EMBEDDING_DIMENSION = 1024   # Dimension des vecteurs
```

## 🐛 Dépannage

### Les documents ne se vectorisent pas

```bash
# Vérifier les logs Celery
podman logs chatbot-celery -f

# Vérifier Redis
podman exec redis redis-cli ping

# Redémarrer Celery
podman restart chatbot-celery
```

### Erreurs API Albert

```bash
# Vérifier le token
podman exec chatbot-web python -c "import os; print(os.getenv('ALBERT_API_TOKEN'))"

# Tester l'API
podman exec chatbot-web python manage.py shell
>>> from rag.services.albert_client import AlbertClient
>>> client = AlbertClient()
>>> client.generate_embeddings(["test"])
```

### Base de données

```bash
# Vérifier pgvector
podman exec chatbot-db psql -U chatbot_user -d chatbot_rag -c "SELECT * FROM pg_extension WHERE extname='vector';"

# Réinitialiser les migrations (ATTENTION : perte de données)
podman exec chatbot-web python manage.py migrate rag zero
podman exec chatbot-web python manage.py migrate
```

## 📈 Performance

- **Index HNSW** : Recherche en O(log n) même avec millions de vecteurs
- **Bulk insert** : Chunks insérés par lots pour rapidité
- **Celery** : Vectorisation asynchrone, n'impacte pas l'UX
- **Select_related** : Optimisation requêtes Django (évite N+1)
- **Redis** : Cache et broker haute performance

## 🔮 Évolution Prévue

- [ ] Authentification SAML (prochaine étape)
- [ ] Support de formats additionnels (CSV, RTF)
- [ ] Amélioration UI (streaming des réponses)
- [ ] API REST pour intégration externe
- [ ] Gestion des conversations multiples
- [ ] Export des conversations

## 📝 Licence

Projet interne - Tous droits réservés

## 👥 Contributeurs

- **Développement** : iarag + Claude Opus 4.5
- **Architecture** : RAG avec Django + pgvector
- **API** : Albert (DINUM)

## 📞 Support

Pour toute question ou problème :
1. Consulter les logs : `podman logs [container-name]`
2. Vérifier la configuration `.env`
3. Consulter la documentation dans `docs/`

---

**Version** : 1.0.0
**Date** : Février 2025
**Statut** : Production-ready
