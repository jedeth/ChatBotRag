# Mémoire de session — Chatbot RAG — 05 février 2026

**Rédigé par** : Claude Code (Sonnet 4.5)
**Projet** : chatbot-rag — application Django autonome de type RAG
**Répertoire** : `/home/iarag/noScribe_develop/chatbot-rag/`
**Branche** : `dev-ajout-chatbot` (dans le dépôt noScribe-portal)

---

## 1. Contexte et décision architecturale

### 1.1 Situation initiale

La session précédente avait mis en place un portail multi-applications Django
(noScribe-portal) avec deux « tuiles » : *Transcription Audio* et *Chatbot RAG*.
Le chatbot était à ce stade un service FastAPI + ChromaDB hébergé dans le même
réseau de conteneurs, accessible via le portail après authentification SAML.

### 1.2 Pivot vers une architecture séparée

En début de cette session, la décision a été prise de **repartir le chatbot
comme une application Django autonome**, pour les raisons suivantes :

- Même architecture que noScribe-portal (Django + Celery + PostgreSQL), donc
  opérabilité homogène.
- Authentification propre (login/register natif) avec un point d'extension SAML
  pour l'IdP AC-Paris, sans dépendance au portail.
- Base de données relationnelle + vectorielle dans une seule instance PostgreSQL
  via **pgvector**, en lieu de ChromaDB séparé.
- Conteneurisation autonome : l'application peut être déployée indépendamment.

Les trois décisions clés confirmées :

| Décision | Choix retenu |
|---|---|
| Framework web | Django 4.2.7 (même que noScribe-portal) |
| Stockage vectoriel | pgvector sur PostgreSQL (remplace ChromaDB) |
| Séparation physique | Nouveau répertoire `/home/iarag/noScribe_develop/chatbot-rag/` |

---

## 2. Architecture du projet

```
chatbot-rag/
├── manage.py
├── requirements.txt
├── .env                          # config développement (ne pas commiter)
├── .dockerignore
├── Containerfile                 # image Python 3.11-slim, user 1001
├── compose.yaml                  # 5 services : db, redis, web, celery, nginx
├── nginx/
│   └── default.conf              # proxy vers gunicorn, timeouts LLM
├── chatbot_rag/                  # package Django « projet »
│   ├── __init__.py               # import de l'appli Celery
│   ├── celery.py                 # configuration Celery
│   ├── settings.py               # toute la config Django
│   ├── urls.py                   # routing racine
│   └── wsgi.py
├── rag/                          # appli Django « rag »
│   ├── models.py                 # Document, DocumentChunk, Conversation, Message
│   ├── views.py                  # vues web + endpoints AJAX
│   ├── forms.py                  # DocumentUploadForm (validation magic-bytes)
│   ├── tasks.py                  # vectorize_document_task (Celery)
│   ├── admin.py                  # enregistrement des 4 modèles
│   ├── urls.py                   # routes de l'appli
│   ├── services/
│   │   ├── albert_client.py      # client HTTP synchrone vers l'API Albert
│   │   ├── vectorization.py      # extraction texte (PDF/DOCX/XLSX/TXT) + chunking
│   │   └── rag_engine.py         # pipeline retrieval → prompt → génération
│   ├── templates/rag/
│   │   ├── base.html             # navbar, Bootstrap 5.3, CSS commun
│   │   ├── login.html            # formulaire de connexion
│   │   ├── register.html         # formulaire d'inscription
│   │   ├── documents.html        # upload + liste + polling JS
│   │   └── chat.html             # interface chat (sidebar + zone messages)
│   └── migrations/
│       ├── 0001_initial.py       # CREATE EXTENSION vector + 4 tables
│       └── 0002_documentchunk_hnsw_index.py  # index HNSW (SQL brut)
├── logs/                         # logs Django + Celery
└── docs/
    └── memoire05_02_26.md        # ce fichier
```

### 2.1 Diagramme des services (conteneurs)

```
┌────────────┐     ┌───────────┐     ┌─────────────┐
│   Nginx    │────▶│  Web      │────▶│  PostgreSQL │
│ port 8182  │     │ (Gunicorn)│     │  + pgvector │
└────────────┘     │ port 8002 │     └─────────────┘
                   └───────────┘            ▲
                         │                  │
                         ▼                  │
                   ┌───────────┐     ┌──────┴──────┐
                   │  Celery   │────▶│   Redis     │
                   │  worker   │     │ (broker)    │
                   └───────────┘     └─────────────┘

                   ┌───────────────────────────┐
                   │  API Albert (DINUM)       │
                   │  embeddings + chat        │
                   └───────────────────────────┘
                         ▲              ▲
                         │              │
              albert_client.py    rag_engine.py
```

---

## 3. Modèles de données

| Modèle | Rôle | Champs principaux |
|---|---|---|
| `Document` | Document uploadé par un utilisateur | user (FK), filename, file, status, celery_task_id, chunk_count |
| `DocumentChunk` | Morceau de texte avec son embedding | document (FK), chunk_index, content, embedding (VectorField 1024) |
| `Conversation` | Fil de discussion utilisateur ↔ assistant | user (FK), title, created_at, updated_at |
| `Message` | Message individuel dans une conversation | conversation (FK), role (user/assistant), content, sources (JSON) |

### 3.1 Index HNSW

L'index HNSW sur `DocumentChunk.embedding` est créé par SQL brut dans
`0002_documentchunk_hnsw_index.py` parce que la version maximale du package
Python `pgvector` disponible sur PyPI est **0.4.2**, qui ne publie pas
`HnswIndex` via l'ORM Django (feature ajoutée en 0.5+).

```sql
CREATE INDEX idx_documentchunk_embedding_hnsw
ON rag_documentchunk
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

## 4. Pipeline de vectorisation (upload → base)

```
Utilisateur uploade un fichier
        │
        ▼
  DocumentUploadForm          ← validation extension + magic-bytes
        │
        ▼
  Document créé (status=pending)
        │
        ▼
  vectorize_document_task     ← tâche Celery (max_retries=3, backoff 60/120/240s)
        │
        ├── 1. Extraction texte   (VectorizationService)
        │       PDF  → PyMuPDF (avec numéros de page)
        │       DOCX → python-docx
        │       XLSX → openpyxl (avec noms de feuilles)
        │       TXT/MD → lecture UTF-8
        │
        ├── 2. Découpage en chunks
        │       RecursiveCharacterTextSplitter
        │       chunk_size=1000, chunk_overlap=200
        │
        ├── 3. Génération embeddings
        │       AlbertClient → POST /embeddings
        │       modèle BAAI/bge-m3 → vecteurs 1024 dims
        │       lots de 64 textes max (limite API Albert)
        │
        └── 4. Stockage en base
                bulk_create sur DocumentChunk (pgvector)
                Document.status → 'vectorized'
```

### 4.1 Suivi de progression

La tâche Celery met à jour son état (`PROGRESS`) à chaque étape (10 → 30 → 50
→ 75 → 100 %). Le frontend (`documents.html`) fait du **polling toutes les 3 s**
sur l'endpoint `/api/upload/status/<task_id>/` pour rafraîchir les badges.

---

## 5. Pipeline RAG (question → réponse)

```
Utilisateur pose une question (AJAX POST /api/chat/send/)
        │
        ▼
  RAGEngine.generate_response()
        │
        ├── 1. Embed la question       → Albert /embeddings (1 vecteur 1024-d)
        │
        ├── 2. Recherche vectorielle   → pgvector CosineDistance
        │       filtre : document__user = utilisateur courant
        │       seuil : distance ≤ 0.8
        │       top-k : 5 chunks
        │       utilise l'index HNSW créé dans 0002
        │
        ├── 3. Construction du prompt
        │       system : « réponds en citant tes sources »
        │       user   : contexte (chunks récupérés) + question
        │       si aucun chunk : invite à uploader des documents
        │
        ├── 4. Génération             → Albert /chat/completions
        │       modèle : albert-large
        │       temperature=0.7, max_tokens=500
        │
        └── 5. Sources dédupliquées
                une entrée par fichier source, meilleur score de pertinence
                        │
                        ▼
              JSON retourné au frontend
              { response, sources, conversation_id }
```

---

## 6. Services portés depuis le chatbot FastAPI

Les trois fichiers du répertoire `rag/services/` sont issus du chatbot
FastAPI/ChromaDB qui existait avant le pivot. Adaptations effectuées :

| Fichier | Adaptations |
|---|---|
| `albert_client.py` | Rendu **synchrone** (`httpx.Client` au lieu de `AsyncClient`). Config lue depuis `django.conf.settings`. |
| `vectorization.py` | Partie ChromaDB retirée. Seules l'extraction et le chunking restent. Le `bulk_create` est dans `tasks.py`. |
| `rag_engine.py` | Recherche ChromaDB remplacée par une requête Django ORM + `CosineDistance` (pgvector). La persistance des conversations, qui était un TODO, est désormais triviale via les modèles `Conversation` / `Message`. |

---

## 7. Problèmes rencontrés et résolutions

Tous les problèmes ci-dessous ont été rencontrés et résolus dans cette session.

### 7.1 Image pgvector — résolution de nom court

**Symptôme** : `podman-compose up` ne démarrait pas le conteneur `db`.
`podman pull pgvector/pgvector:pg16` échouait avec *« short-name resolution
enforced »*.

**Cause** : Podman en mode rootless rejette les noms d'images courts sans
préfixe de registre.

**Solution** : Préfixer par `docker.io/` dans compose.yaml et dans la commande
de pull :
```yaml
image: docker.io/pgvector/pgvector:pg16
```

### 7.2 WhiteNoise 6.6 — classe de stockage supprimée

**Symptôme** : `collectstatic` échouait avec *« Module whitenoise.storage does
not define a WhiteNoiseStaticFilesStorage »*.

**Cause** : WhiteNoise 6.x a supprimé cette classe. Le bon nom est
`CompressedManifestStaticFilesStorage`, et Django 4.2 utilise le dictionnaire
`STORAGES` au lieu de la variable `STATICFILES_STORAGE` (dépréciée).

**Solution** dans `settings.py` :
```python
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}
```

### 7.3 Extension pgvector — type `vector` inconnu lors de la migration

**Symptôme** : `rag.0001_initial` échouait avec *« type "vector" does not
exist »* lors de la création de la colonne `embedding vector(1024)`.

**Cause** : L'extension PostgreSQL `vector` n'était pas activée avant la
création de la table. Django génère les `CREATE TABLE` dans l'ordre des modèles
; il n'y a aucune garantie que l'extension soit déjà présente.

**Solution** : Insérer un `RunSQL("CREATE EXTENSION IF NOT EXISTS vector;")`
comme **première opération** de `0001_initial`, avant tous les `CreateModel`.

### 7.4 Index HNSW — syntaxe SQL incorrecte

**Symptôme** : `rag.0002` échouait avec *« syntax error at or near "<=>" »*.
La syntaxe utilisée était :
```sql
USING hnsw (embedding <=> 'vector')
```

**Cause** : Le littéral `'vector'` n'a pas de sens dans cette position. La
syntaxe pgvector pour spécifier l'opérateur de distance dans un index HNSW est
le nom de la classe d'opérateurs.

**Solution** :
```sql
USING hnsw (embedding vector_cosine_ops)
```

### 7.5 Migration `sessions` non appliquée

**Symptôme** : Login retournait une erreur 500 *« relation django_session does
not exist »*.

**Cause** : Le premier `migrate` avait crashé à mi-chemin sur `rag.0002`
(syntaxe HNSW). La migration `sessions.0001_initial` appartenait au même lot
mais n'avait pas encore été atteinte. Django avait bien rollbacké `rag.0002`
mais n'avait jamais exécuté `sessions.0001`.

**Solution** : Re-lancer `manage.py migrate` après la correction de `0002`.

### 7.6 `createsuperuser --password` — argument invalide

**Symptôme** : `manage.py createsuperuser --password=admin123` échouait.

**Cause** : Django 4.2 n'expose pas d'option `--password` sur cette commande.

**Solution** : Créer l'utilisateur via le shell Python :
```python
User.objects.create_superuser('admin', 'admin@…', 'admin123')
```

---

## 8. État final — vérifications effectuées

| Vérification | Résultat |
|---|---|
| Image `chatbot-rag:v1` | Built, `collectstatic` OK (125 fichiers, 375 post-processed) |
| Conteneur `chatbot-db` | Up, healthy (`pg_isready` OK) |
| Conteneur `chatbot-redis` | Up, healthy (`redis-cli ping` OK) |
| Conteneur `chatbot-web` | Up, healthy (`/health/` → 200) |
| Conteneur `chatbot-celery` | Up, worker *ready* |
| Conteneur `chatbot-nginx` | Up, proxy vers web OK |
| Migration `rag.0001_initial` | Applied — extension vector + 4 tables |
| Migration `rag.0002` | Applied — index HNSW confirmé dans `pg_indexes` |
| `GET /health/` | `{"status":"healthy","checks":{"database":"ok","redis":"ok"}}` |
| `GET /` (non auth) | 302 → `/login/` |
| `POST /login/` (admin) | 302 → `/` (chat) |
| `GET /` (auth) | 200 — page chat rendue (sidebar + zone messages) |
| `GET /documents/` | 200 — page documents rendue |
| Nginx (port 8182) | Proxy vers web fonctionnel |
| Superuser | `admin` / `admin123` créé |

---

## 9. Ports réseau

| Service | Port hôte | Port conteneur | Remarque |
|---|---|---|---|
| Web (Gunicorn) | 8002 | 8000 | Accès direct sans nginx |
| Nginx | 8182 | 80 | Point d'entrée recommandé |
| PostgreSQL | — | 5432 | Interne au réseau compose |
| Redis | — | 6379 | Interne au réseau compose |

noScribe-portal occupe les ports 8001 (web) et 8180/8180 (nginx) — pas de
conflit.

---

## 10. Prochaines étapes

Les éléments suivants restent à valider dans une session future :

1. **Test end-to-end complet** : uploader un document réel, attendre la
   vectorisation via Celery, puis poser une question dans le chat et vérifier
   que la réponse RAG est cohérente avec le contenu du document.
2. **Vérification des appels Albert** : les embeddings et la génération de texte
   n'ont pas encore été testés contre l'API réelle dans cette session (la clé
   API est en place dans `.env`).
3. **Titre de conversation** : actuellement mis à jour avec le texte du premier
   message (tronqué à 100 caractères). À améliorer si nécessaire.
4. **Messages d'erreur utilisateur** : les erreurs de vectorisation sont
   loguées mais ne sont pas encore affichées clairement dans l'interface.
5. **Intégration SAML** : `djangosaml2` est dans les dépendances et
   `SAML_ENABLED` est un toggle dans `.env`. La configuration IdP AC-Paris
   (certificats, metadata) à copier depuis noScribe-portal quand prêt.
6. **Sécurisation production** : SECRET_KEY, DEBUG=False, ALLOWED_HOSTS
   explicites, HTTPS.

---

## 11. Aide-mémoire — commandes utiles

```bash
# Statut des conteneurs
podman ps -a --format "table {{.Names}}\t{{.Status}}"

# Logs d'un service
podman logs chatbot-web
podman logs chatbot-celery

# Exécuter une commande dans le conteneur web
podman exec chatbot-web python manage.py <commande>

# Redéployer après modif du code (sans reconstruire l'image)
podman cp fichier.py chatbot-web:/app/chemin/fichier.py

# Reconstruire l'image (modif requirements, Containerfile, templates…)
podman-compose build web
podman-compose stop web && podman rm chatbot-web
podman-compose up -d

# Relancer tous les services
podman-compose down && podman-compose up -d
```
