# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChatBot RAG is a Django-based document question-answering system using Retrieval-Augmented Generation. Users upload documents (PDF, DOCX, XLSX, TXT, MD), which are vectorized asynchronously, then ask questions that are answered using semantic search over document chunks combined with LLM generation.

**Key Technologies:**
- Django 4.2.7 + PostgreSQL 15 with pgvector extension
- Celery + Redis for asynchronous vectorization
- Albert API (DINUM) for embeddings (BAAI/bge-m3, 1024 dimensions) and chat completion
- Containerized with Podman/Docker (5 services: db, redis, web, celery, nginx)

## Development Commands

### Running the Application

```bash
# Start all services (requires .env file configured)
podman-compose up -d

# Run migrations
podman exec chatbot-web python manage.py migrate

# Create superuser
podman exec -it chatbot-web python manage.py createsuperuser

# Collect static files
podman exec chatbot-web python manage.py collectstatic --noinput

# Restart a specific service
podman restart chatbot-web
podman restart chatbot-celery
```

### Testing and Debugging

```bash
# Django shell
podman exec -it chatbot-web python manage.py shell

# Check Celery logs
podman logs chatbot-celery -f

# Check web logs
podman logs chatbot-web -f

# Test Albert API connection
podman exec chatbot-web python manage.py shell
>>> from rag.services.albert_client import AlbertClient
>>> client = AlbertClient()
>>> client.generate_embeddings(["test"])

# Check pgvector extension
podman exec chatbot-db psql -U chatbot -d chatbot_rag -c "SELECT * FROM pg_extension WHERE extname='vector';"

# View all documents and their status
podman exec chatbot-web python manage.py shell
>>> from rag.models import Document
>>> Document.objects.all().values('id', 'filename', 'status', 'chunk_count')
```

### Database Operations

```bash
# Create new migration
podman exec chatbot-web python manage.py makemigrations

# Apply migrations
podman exec chatbot-web python manage.py migrate

# Reset app migrations (WARNING: data loss)
podman exec chatbot-web python manage.py migrate rag zero
podman exec chatbot-web python manage.py migrate
```

### Building and Deployment

```bash
# Rebuild without cache (important for SAML attribute maps)
podman-compose build --no-cache web

# Stop all services
podman-compose down

# Stop and remove volumes (WARNING: data loss)
podman-compose down -v
```

## Architecture

### Core Data Flow

1. **Document Upload** → User uploads file via `rag/views.py:upload_document`
2. **Async Vectorization** → Celery task `rag/tasks.py:vectorize_document_task` triggered
   - Extract text: `rag/services/vectorization.py:VectorizationService.extract_text()`
   - Chunk text: `VectorizationService.chunk_text()` (1000 chars, 200 overlap)
   - Generate embeddings: `rag/services/albert_client.py:AlbertClient.generate_embeddings()` (batches of 64)
   - Store chunks: Bulk insert `DocumentChunk` objects with pgvector embeddings
3. **Question** → User asks question in chat
4. **RAG Pipeline** → `rag/services/rag_engine.py:RAGEngine.generate_response()`
   - Detect if statistical question → try metadata-based response first
   - Otherwise: Embed query → Search similar chunks (pgvector cosine distance) → Build prompt → Generate answer
5. **Response** → Display answer with cited sources

### pgvector Integration

The system uses PostgreSQL's pgvector extension for vector similarity search:

- **Model**: `DocumentChunk.embedding` is a `VectorField(dimensions=1024)`
- **Index**: HNSW index created in migration `0002_documentchunk_hnsw_index` using raw SQL
- **Search**: Uses `CosineDistance` annotation in ORM queries (`rag_engine.py:_retrieve_context`)
- **Threshold**: Similarity threshold of 0.8 (cosine distance, 0=identical, 1=orthogonal)

### Two-Mode RAG Strategy

**Metadata Mode** (for statistical queries):
- Triggered by keywords: "combien", "nombre", "total", "count"
- Bypasses vector search, uses `Document.metadata` JSONField
- Best for XLSX files with row/column counts
- Lower temperature (0.3) for deterministic stats answers

**Vector Mode** (for semantic queries):
- Embeds question, searches TOP_K=5 chunks
- Filters by `distance__lte=SIMILARITY_THRESHOLD` (0.8)
- Scoped to user's documents only
- Extracts and deduplicates sources from retrieved chunks

### Service Layer

- `rag/services/albert_client.py`: HTTP client for Albert API (embeddings + chat)
- `rag/services/vectorization.py`: Text extraction (PDF/DOCX/XLSX/TXT/MD) and chunking
- `rag/services/rag_engine.py`: Main RAG orchestration (retrieval + generation)

### Models

- `Document`: Uploaded file metadata, status tracking, `metadata` JSONField for stats
- `DocumentChunk`: Text chunk with `embedding` (VectorField), linked to Document
- `Conversation`: Chat thread per user
- `Message`: Individual message (user/assistant) with sources JSONField

### Celery Tasks

Task: `vectorize_document_task(document_id)` in `rag/tasks.py`
- Max retries: 3 with exponential backoff (60s, 120s, 240s)
- Updates task state with progress (10%, 30%, 50%, 75%, 100%)
- Marks document as 'vectorized' or 'failed' on completion/error

### Configuration

Settings in `chatbot_rag/settings.py`:
- Database credentials from environment (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST)
- Albert API: `ALBERT_API_URL`, `ALBERT_API_KEY`, `ALBERT_EMBEDDING_MODEL`, `ALBERT_CHAT_MODEL`
- Celery: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` (Redis)
- Upload: `MAX_UPLOAD_SIZE` (default 100MB)
- SAML: `SAML_ENABLED` (default False, requires additional configuration)

## SAML Authentication (Prepared, Not Active)

SAML infrastructure is ready but **not activated by default**. To enable:

1. Obtain from Identity Provider admin:
   - IdP metadata XML or URL
   - SAML attribute names and NameFormat
   - Test user values

2. Generate SP certificates:
   ```bash
   cd saml/
   openssl req -new -x509 -days 3652 -nodes \
       -out sp_certificate.pem -keyout sp_private_key.pem \
       -subj "/C=FR/ST=IDF/L=Paris/O=Rectorat/CN=chatbot-rag.DOMAIN.fr"
   chmod 600 sp_private_key.pem
   ```

3. Adapt attribute map in `saml/attributemaps/basic.py` to match IdP attributes

4. Copy configuration from `saml/saml_settings_template.py` into `settings.py`

5. Uncomment `path('saml2/', include('djangosaml2.urls'))` in `chatbot_rag/urls.py`

6. Set `SAML_ENABLED=True` in `.env`

7. Rebuild: `podman-compose build --no-cache web`

**Critical**: The attribute map must match IdP's NameFormat. Common error: "Unknown attribute name" means mismatch between IdP attributes and `attributemaps/basic.py`.

See `docs/SAML_PREPARATION.md` and `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md` for complete instructions.

## File Upload Security

Security validation in `rag/forms.py:DocumentUploadForm`:
- Extension whitelist: .pdf, .docx, .xlsx, .txt, .md
- Magic bytes verification (DOCX/XLSX are ZIP, handled as exception)
- Size limit from `settings.MAX_UPLOAD_SIZE`

## Important Constraints

### When Modifying Vector Dimensions
If changing `EMBEDDING_DIMENSIONS` in settings.py:
1. Must create new migration to alter `DocumentChunk.embedding` field
2. Existing embeddings become invalid
3. All documents must be re-vectorized

### When Modifying pgvector Index
The HNSW index is created with raw SQL in migration `0002_documentchunk_hnsw_index`. Django ORM doesn't support pgvector indexes directly. If recreating:
```sql
CREATE INDEX documentchunk_hnsw_idx ON rag_documentchunk
USING hnsw (embedding vector_cosine_ops);
```

### When Adding Document Formats
1. Add extractor method in `VectorizationService` (e.g., `_extract_csv`)
2. Add to `extractors` dict in `extract_text()`
3. Add extension to `ALLOWED_EXTENSIONS` in `rag/forms.py`
4. Update magic bytes validation if needed

### Environment Variables Required
The application **requires** these environment variables in `.env`:
- `SECRET_KEY`: Django secret
- `ALBERT_API_URL`: Albert API endpoint
- `ALBERT_API_KEY`: Albert API authentication token
- `DB_PASSWORD`: PostgreSQL password

Without these, the application will fail to start or have broken functionality.

## Common Issues

**Documents stuck in 'pending' status:**
- Check Celery is running: `podman logs chatbot-celery`
- Check Redis: `podman exec chatbot-redis redis-cli ping`
- Restart Celery: `podman restart chatbot-celery`

**No results in vector search:**
- Verify chunks exist: Check `DocumentChunk` table
- Check similarity threshold: May be too strict (SIMILARITY_THRESHOLD=0.8 in rag_engine.py)
- Verify Albert embeddings are working: Test with `AlbertClient.generate_embeddings()`

**Albert API errors:**
- Verify token: `podman exec chatbot-web python -c "import os; print(os.getenv('ALBERT_API_KEY'))"`
- Check API endpoint reachable: `podman exec chatbot-web curl -I $ALBERT_API_URL`

**pgvector not available:**
- Verify extension enabled: `psql -c "CREATE EXTENSION IF NOT EXISTS vector;"`
- Check in Django: `python manage.py dbshell` then `\dx` to list extensions

## Performance Tuning

**Vectorization speed:**
- `BATCH_SIZE` in `albert_client.py` (default 64): Larger batches = fewer API calls but more memory
- Celery concurrency: `--concurrency=2` in compose.yaml (increase for multi-core systems)

**Search performance:**
- HNSW index provides O(log n) search time
- Adjust `TOP_K` in `rag_engine.py` (default 5): More chunks = better context but slower

**Chunking parameters** (`vectorization.py`):
- `chunk_size=1000`: Larger = more context per chunk, fewer chunks
- `chunk_overlap=200`: More overlap = better boundary handling, more redundancy
- `min_chunk_size=50`: Filters noise, adjust based on content

## Container Ports

- 8002: Django/Gunicorn (web service)
- 8182: Nginx reverse proxy (public access point)
- 5432: PostgreSQL (internal only)
- 6379: Redis (internal only)

Nginx proxies to Django, serves static files and media uploads.
