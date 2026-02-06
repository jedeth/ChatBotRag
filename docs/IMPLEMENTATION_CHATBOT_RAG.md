# Documentation d'implémentation - Chatbot RAG pour noScribe Portal

**Date de création** : 2026-02-04
**Version** : 1.0
**Statut** : En développement
**Branche** : `feature/chatbot-rag-test`

---

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture cible](#architecture-cible)
3. [Prérequis](#prérequis)
4. [Phase 1 : Préparation de l'environnement](#phase-1--préparation-de-lenvironnement)
5. [Phase 2 : Développement du chatbot](#phase-2--développement-du-chatbot)
6. [Phase 3 : Configuration Nginx](#phase-3--configuration-nginx)
7. [Phase 4 : Adaptation Django](#phase-4--adaptation-django)
8. [Phase 5 : Portail d'accueil](#phase-5--portail-daccueil)
9. [Phase 6 : Intégration Docker](#phase-6--intégration-docker)
10. [Phase 7 : Tests et validation](#phase-7--tests-et-validation)
11. [Phase 8 : Déploiement production](#phase-8--déploiement-production)
12. [Troubleshooting](#troubleshooting)
13. [Rollback et récupération](#rollback-et-récupération)

---

## Vue d'ensemble

### Objectif

Intégrer un **chatbot RAG (Retrieval-Augmented Generation)** comme second service à côté de l'application de transcription noScribe existante, en préservant l'authentification SAML actuelle.

### Principes directeurs

1. **Non-régression** : La production noScribe ne doit jamais être impactée
2. **Isolation** : Le chatbot est un service indépendant
3. **Gateway Pattern** : Django sert de passerelle d'authentification pour le chatbot
4. **Sécurité** : Réutilisation de la session SAML existante

### Estimation de charge

- **Développement** : 40-55 heures
- **Tests** : 10-15 heures
- **Documentation** : 5 heures
- **Total** : 55-75 heures

---

## Architecture cible

### Schéma global

```
┌─────────────────────────────────────────────────────────┐
│  SAML Authentication (IdP AC-Paris) - INCHANGÉ         │
└────────────┬────────────────────────────────────────────┘
             ↓
    ┌────────────────────┐
    │ Nginx Système      │
    │ Port 443 (HTTPS)   │
    │ /etc/nginx/conf.d/ │
    └────────┬───────────┘
             │
             ├─→ /home      → Portail HTML statique (Nginx direct)
             │                /var/www/html/portal/
             │
             ├─→ /app        → Django noScribe (INCHANGÉ logiquement)
             │                proxy_pass http://localhost:8001
             │                │
             │                ├─→ SAML (/saml2/)
             │                ├─→ Transcriptions
             │                └─→ Comptes rendus
             │
             └─→ /chatbot    → Chatbot RAG (NOUVEAU)
                              proxy_pass http://127.0.0.1:8000
                              │
                              └─→ Service FastAPI
                                  ├─→ ChromaDB (Base vectorielle)
                                  ├─→ API Albert (DINUM)
                                  ├─→ Workers async (Celery/Redis)
                                  └─→ Stockage documents (20 Go/user)
```

### Composants

| Composant | Port | Rôle | Statut |
|-----------|------|------|--------|
| **Nginx système** | 443 | Reverse proxy HTTPS | Existant (à modifier) |
| **Django noScribe** | 8001 | App transcription + Auth SAML | Existant (à adapter) |
| **Portail HTML** | N/A | Page d'accueil avec liens apps | Nouveau |
| **Chatbot RAG** | 8000 | Service chatbot + vectorisation | Nouveau |
| **ChromaDB** | N/A | Base vectorielle (dans conteneur) | Nouveau |
| **Redis** | 6379 | File d'attente workers | Existant (réutilisé) |

---

## Prérequis

### Environnement de développement

```bash
# Vérifier environnement actif
./scripts/env-status.sh

# Basculer vers TEST
./scripts/env-switch.sh test

# Vérifier que les ports nécessaires sont libres
netstat -tlnp | grep -E '8000|8001|6379'

# Port 8000 : doit être LIBRE (pour chatbot)
# Port 8001 : doit être utilisé par Django
# Port 6379 : doit être utilisé par Redis
```

### Dépendances système

```bash
# Installer dépendances supplémentaires
sudo dnf install -y \
  python3-devel \
  gcc \
  g++ \
  poppler-utils \
  tesseract \
  tesseract-langpack-fra

# Pour extraction PDF/Word
pip install pymupdf python-docx openpyxl
```

### Variables d'environnement requises

Ajouter dans `.env.test` :

```env
# ===== Chatbot RAG Configuration =====
CHATBOT_ENABLED=True
CHATBOT_PORT=8000
CHATBOT_MAX_UPLOAD_SIZE=104857600  # 100 Mo
CHATBOT_USER_QUOTA=21474836480     # 20 Go par utilisateur

# ChromaDB
CHROMADB_HOST=chromadb
CHROMADB_PORT=8001
CHROMADB_PERSIST_DIR=/data/chromadb

# API Albert (déjà existant, vérifier)
ALBERT_API_URL=https://albert.api.etalab.gouv.fr/v1
ALBERT_API_KEY=sk-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
ALBERT_EMBEDDING_MODEL=intfloat/multilingual-e5-large
ALBERT_CHAT_MODEL=mistralai/Mistral-7B-Instruct-v0.2

# Workers asynchrones
CHATBOT_WORKERS=4
CELERY_BROKER_URL=redis://redis:6379/1  # DB 1 pour chatbot, DB 0 pour noScribe
```

---

## Phase 1 : Préparation de l'environnement

### 1.1 Créer la branche de travail

```bash
cd /home/iarag/noScribe_web

# Créer branche depuis main
git checkout main
git pull origin main
git checkout -b feature/chatbot-rag-test

# Vérifier
git status
git branch
```

### 1.2 Créer l'arborescence du chatbot

```bash
# Structure du projet chatbot
mkdir -p chatbot/{app,models,services,workers,templates,static}
mkdir -p chatbot/data/{chromadb,documents}
mkdir -p chatbot/logs

# Créer fichiers de base
touch chatbot/__init__.py
touch chatbot/app/__init__.py
touch chatbot/app/main.py
touch chatbot/requirements.txt
touch chatbot/Dockerfile
```

### 1.3 Sauvegarder la configuration actuelle

```bash
# Backup Nginx
sudo cp /etc/nginx/conf.d/noscribe.conf \
       /etc/nginx/conf.d/noscribe.conf.backup.$(date +%Y%m%d-%H%M%S)

# Backup settings Django
cp noscribe_portal/settings.py \
   noscribe_portal/settings.py.backup.$(date +%Y%m%d-%H%M%S)

# Backup docker-compose
cp compose.yaml compose.yaml.backup.$(date +%Y%m%d-%H%M%S)
```

---

## Phase 2 : Développement du chatbot

### 2.1 Structure du service FastAPI

Créer `chatbot/app/main.py` :

```python
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import logging
import os

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/chatbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialisation FastAPI
app = FastAPI(
    title="Chatbot RAG - noScribe Portal",
    description="Service de chatbot avec RAG (Retrieval-Augmented Generation)",
    version="1.0.0",
    root_path="/chatbot"  # Important pour sous-chemin Nginx
)

# CORS pour permettre requêtes depuis Django
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://noscribe.in.ac-paris.fr", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import des services
from services.vectorization import VectorizationService
from services.rag_engine import RAGEngine
from services.quota_manager import QuotaManager

# Initialisation des services
vectorization_service = VectorizationService()
rag_engine = RAGEngine()
quota_manager = QuotaManager()


# ===== Dépendances =====

def get_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """
    Récupère l'identifiant utilisateur depuis les headers.
    Nginx passe X-User-ID depuis la session SAML.
    """
    if not x_user_id:
        logger.warning("Tentative d'accès sans X-User-ID")
        raise HTTPException(status_code=401, detail="Authentication required")
    return x_user_id


# ===== Endpoints =====

@app.get("/health")
async def health_check():
    """Endpoint de santé pour monitoring"""
    return {
        "status": "healthy",
        "service": "chatbot-rag",
        "version": "1.0.0"
    }


@app.get("/api/quota")
async def get_quota(user_id: str = Depends(get_user_id)):
    """
    Récupère le quota de stockage de l'utilisateur.

    Returns:
        {
            "used": 1073741824,      # Octets utilisés (1 Go)
            "total": 21474836480,    # Quota total (20 Go)
            "percentage": 5.0        # Pourcentage utilisé
        }
    """
    quota = await quota_manager.get_user_quota(user_id)
    return quota


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_user_id)
):
    """
    Upload et vectorisation d'un document.

    Formats supportés: PDF, DOCX, XLSX, TXT, MD
    Taille max: 100 Mo
    """
    logger.info(f"Upload document pour utilisateur {user_id}: {file.filename}")

    # Vérifier quota
    quota_ok = await quota_manager.check_quota(user_id, file.size)
    if not quota_ok:
        raise HTTPException(
            status_code=507,
            detail="Quota de stockage dépassé (20 Go maximum)"
        )

    # Vérifier taille fichier
    max_size = int(os.getenv('CHATBOT_MAX_UPLOAD_SIZE', 104857600))  # 100 Mo
    if file.size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"Fichier trop volumineux (max {max_size / 1024 / 1024} Mo)"
        )

    # Envoyer tâche de vectorisation asynchrone
    task_id = await vectorization_service.process_document(
        user_id=user_id,
        file=file
    )

    return {
        "status": "processing",
        "task_id": task_id,
        "filename": file.filename
    }


@app.get("/api/upload/status/{task_id}")
async def upload_status(
    task_id: str,
    user_id: str = Depends(get_user_id)
):
    """
    Vérifie le statut d'une tâche de vectorisation.

    Returns:
        {
            "status": "completed|processing|failed",
            "progress": 75,
            "message": "Extraction du texte...",
            "document_id": "abc123"  # Si completed
        }
    """
    status = await vectorization_service.get_task_status(task_id, user_id)
    return status


@app.get("/api/documents")
async def list_documents(user_id: str = Depends(get_user_id)):
    """
    Liste les documents vectorisés de l'utilisateur.

    Returns:
        [
            {
                "id": "abc123",
                "filename": "rapport.pdf",
                "size": 1048576,
                "chunks": 42,
                "uploaded_at": "2026-02-04T10:30:00Z"
            }
        ]
    """
    documents = await vectorization_service.list_user_documents(user_id)
    return documents


@app.delete("/api/documents/{document_id}")
async def delete_document(
    document_id: str,
    user_id: str = Depends(get_user_id)
):
    """
    Supprime un document et ses embeddings.
    """
    await vectorization_service.delete_document(user_id, document_id)
    return {"status": "deleted", "document_id": document_id}


@app.post("/api/chat")
async def chat(
    request: dict,
    user_id: str = Depends(get_user_id)
):
    """
    Endpoint principal de conversation.

    Body:
        {
            "message": "Question de l'utilisateur",
            "conversation_id": "optional-uuid",
            "temperature": 0.7,
            "max_tokens": 500
        }

    Returns:
        {
            "response": "Réponse générée",
            "sources": [
                {
                    "document": "rapport.pdf",
                    "page": 5,
                    "excerpt": "Extrait pertinent..."
                }
            ],
            "conversation_id": "uuid"
        }
    """
    message = request.get('message')
    conversation_id = request.get('conversation_id')

    if not message:
        raise HTTPException(status_code=400, detail="Message requis")

    logger.info(f"Chat pour utilisateur {user_id}: {message[:50]}...")

    # Générer réponse avec RAG
    response = await rag_engine.generate_response(
        user_id=user_id,
        message=message,
        conversation_id=conversation_id,
        temperature=request.get('temperature', 0.7),
        max_tokens=request.get('max_tokens', 500)
    )

    return response


@app.get("/api/conversations")
async def list_conversations(user_id: str = Depends(get_user_id)):
    """
    Liste les conversations de l'utilisateur.
    """
    conversations = await rag_engine.list_conversations(user_id)
    return conversations


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_user_id)
):
    """
    Supprime une conversation.
    """
    await rag_engine.delete_conversation(user_id, conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}


# ===== Point d'entrée =====

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
```

### 2.2 Service de vectorisation

Créer `chatbot/services/vectorization.py` :

```python
import os
import uuid
import hashlib
from typing import Optional
from datetime import datetime
import logging

import fitz  # PyMuPDF
from docx import Document
import openpyxl
from langchain.text_splitter import RecursiveCharacterTextSplitter
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)


class VectorizationService:
    """
    Service de vectorisation de documents.

    - Extraction du texte (PDF, DOCX, XLSX, TXT)
    - Découpage en chunks intelligents
    - Génération d'embeddings via API Albert
    - Stockage dans ChromaDB
    """

    def __init__(self):
        # Connexion ChromaDB
        chroma_host = os.getenv('CHROMADB_HOST', 'localhost')
        chroma_port = int(os.getenv('CHROMADB_PORT', 8001))

        self.client = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            settings=Settings(anonymized_telemetry=False)
        )

        # Text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        # Répertoire de stockage temporaire
        self.upload_dir = "/documents"
        os.makedirs(self.upload_dir, exist_ok=True)


    async def process_document(self, user_id: str, file) -> str:
        """
        Traite un document uploadé de manière asynchrone.

        Returns:
            task_id: Identifiant de la tâche Celery
        """
        # Générer ID unique
        document_id = str(uuid.uuid4())

        # Sauvegarder fichier temporairement
        file_path = os.path.join(
            self.upload_dir,
            user_id,
            f"{document_id}_{file.filename}"
        )
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, 'wb') as f:
            content = await file.read()
            f.write(content)

        # Lancer tâche Celery asynchrone
        from workers.tasks import vectorize_document_task

        task = vectorize_document_task.delay(
            user_id=user_id,
            document_id=document_id,
            file_path=file_path,
            filename=file.filename
        )

        logger.info(f"Tâche de vectorisation lancée: {task.id}")
        return task.id


    def extract_text(self, file_path: str, filename: str) -> str:
        """
        Extrait le texte d'un document selon son format.
        """
        ext = os.path.splitext(filename)[1].lower()

        try:
            if ext == '.pdf':
                return self._extract_pdf(file_path)
            elif ext == '.docx':
                return self._extract_docx(file_path)
            elif ext == '.xlsx':
                return self._extract_xlsx(file_path)
            elif ext in ['.txt', '.md']:
                return self._extract_text(file_path)
            else:
                raise ValueError(f"Format non supporté: {ext}")
        except Exception as e:
            logger.error(f"Erreur extraction {filename}: {e}")
            raise


    def _extract_pdf(self, file_path: str) -> str:
        """Extrait texte d'un PDF avec PyMuPDF"""
        doc = fitz.open(file_path)
        text = ""
        for page_num, page in enumerate(doc, start=1):
            text += f"\n\n--- Page {page_num} ---\n\n"
            text += page.get_text()
        doc.close()
        return text


    def _extract_docx(self, file_path: str) -> str:
        """Extrait texte d'un DOCX"""
        doc = Document(file_path)
        return "\n\n".join([para.text for para in doc.paragraphs])


    def _extract_xlsx(self, file_path: str) -> str:
        """Extrait texte d'un XLSX"""
        wb = openpyxl.load_workbook(file_path)
        text = ""
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            text += f"\n\n--- Feuille: {sheet_name} ---\n\n"
            for row in sheet.iter_rows(values_only=True):
                text += " | ".join([str(cell) for cell in row if cell]) + "\n"
        return text


    def _extract_text(self, file_path: str) -> str:
        """Lit fichier texte brut"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()


    def chunk_text(self, text: str, filename: str) -> list[dict]:
        """
        Découpe le texte en chunks avec métadonnées.

        Returns:
            [
                {
                    "content": "Texte du chunk",
                    "metadata": {
                        "source": "filename.pdf",
                        "chunk_index": 0,
                        "char_count": 950
                    }
                }
            ]
        """
        chunks = self.text_splitter.split_text(text)

        return [
            {
                "content": chunk,
                "metadata": {
                    "source": filename,
                    "chunk_index": i,
                    "char_count": len(chunk)
                }
            }
            for i, chunk in enumerate(chunks)
        ]


    async def store_embeddings(
        self,
        user_id: str,
        document_id: str,
        chunks: list[dict]
    ):
        """
        Génère les embeddings et stocke dans ChromaDB.
        """
        # Récupérer ou créer collection utilisateur
        collection_name = f"user_{user_id}"

        try:
            collection = self.client.get_collection(collection_name)
        except:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={"user_id": user_id}
            )

        # Générer embeddings via API Albert
        from services.albert_client import AlbertClient
        albert = AlbertClient()

        texts = [chunk["content"] for chunk in chunks]
        embeddings = await albert.generate_embeddings(texts)

        # Stocker dans ChromaDB
        collection.add(
            ids=[f"{document_id}_{i}" for i in range(len(chunks))],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    **chunk["metadata"],
                    "document_id": document_id,
                    "user_id": user_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                for chunk in chunks
            ]
        )

        logger.info(f"Stocké {len(chunks)} chunks pour document {document_id}")


    async def get_task_status(self, task_id: str, user_id: str) -> dict:
        """
        Récupère le statut d'une tâche Celery.
        """
        from celery.result import AsyncResult

        result = AsyncResult(task_id)

        return {
            "status": result.state.lower(),
            "progress": result.info.get('progress', 0) if result.info else 0,
            "message": result.info.get('message', '') if result.info else '',
            "document_id": result.result if result.successful() else None
        }


    async def list_user_documents(self, user_id: str) -> list[dict]:
        """
        Liste les documents vectorisés d'un utilisateur.
        """
        collection_name = f"user_{user_id}"

        try:
            collection = self.client.get_collection(collection_name)
            results = collection.get()

            # Grouper par document_id
            documents = {}
            for metadata in results['metadatas']:
                doc_id = metadata.get('document_id')
                if doc_id not in documents:
                    documents[doc_id] = {
                        "id": doc_id,
                        "filename": metadata.get('source'),
                        "chunks": 0,
                        "uploaded_at": metadata.get('timestamp')
                    }
                documents[doc_id]["chunks"] += 1

            return list(documents.values())

        except:
            return []


    async def delete_document(self, user_id: str, document_id: str):
        """
        Supprime un document et ses embeddings.
        """
        collection_name = f"user_{user_id}"

        try:
            collection = self.client.get_collection(collection_name)

            # Récupérer tous les IDs du document
            results = collection.get(
                where={"document_id": document_id}
            )

            if results['ids']:
                collection.delete(ids=results['ids'])
                logger.info(f"Document {document_id} supprimé ({len(results['ids'])} chunks)")

        except Exception as e:
            logger.error(f"Erreur suppression document {document_id}: {e}")
            raise
```

### 2.3 Client API Albert

Créer `chatbot/services/albert_client.py` :

```python
import os
import httpx
import logging
from typing import List

logger = logging.getLogger(__name__)


class AlbertClient:
    """
    Client pour l'API Albert (DINUM).

    - Génération d'embeddings (multilingual-e5-large)
    - Génération de texte (Mistral-7B-Instruct)
    """

    def __init__(self):
        self.api_url = os.getenv('ALBERT_API_URL')
        self.api_key = os.getenv('ALBERT_API_KEY')
        self.embedding_model = os.getenv('ALBERT_EMBEDDING_MODEL')
        self.chat_model = os.getenv('ALBERT_CHAT_MODEL')

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }


    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Génère les embeddings pour une liste de textes.

        Args:
            texts: Liste de textes à vectoriser

        Returns:
            Liste d'embeddings (vecteurs de dimension 1024)
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_url}/embeddings",
                headers=self.headers,
                json={
                    "model": self.embedding_model,
                    "input": texts
                }
            )

            if response.status_code != 200:
                logger.error(f"Erreur API Albert embeddings: {response.text}")
                raise Exception(f"API Albert error: {response.status_code}")

            data = response.json()
            embeddings = [item['embedding'] for item in data['data']]

            logger.info(f"Généré {len(embeddings)} embeddings")
            return embeddings


    async def generate_response(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> str:
        """
        Génère une réponse via l'API de chat.

        Args:
            messages: Liste de messages [{"role": "user", "content": "..."}]
            temperature: Créativité (0.0 = déterministe, 1.0 = créatif)
            max_tokens: Longueur maximale de la réponse

        Returns:
            Texte généré
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.api_url}/chat/completions",
                headers=self.headers,
                json={
                    "model": self.chat_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )

            if response.status_code != 200:
                logger.error(f"Erreur API Albert chat: {response.text}")
                raise Exception(f"API Albert error: {response.status_code}")

            data = response.json()
            content = data['choices'][0]['message']['content']

            logger.info(f"Réponse générée ({len(content)} caractères)")
            return content
```

### 2.4 Moteur RAG

Créer `chatbot/services/rag_engine.py` :

```python
import os
import uuid
import logging
from typing import Optional, List, Dict
from datetime import datetime

import chromadb
from chromadb.config import Settings

from services.albert_client import AlbertClient

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Moteur de génération avec RAG (Retrieval-Augmented Generation).

    Pipeline:
    1. Requête utilisateur → Embedding
    2. Recherche similarité dans ChromaDB → Top K chunks
    3. Construction du prompt avec contexte
    4. Génération réponse via Albert
    5. Post-traitement et extraction des sources
    """

    def __init__(self):
        # Connexion ChromaDB
        chroma_host = os.getenv('CHROMADB_HOST', 'localhost')
        chroma_port = int(os.getenv('CHROMADB_PORT', 8001))

        self.client = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
            settings=Settings(anonymized_telemetry=False)
        )

        # Client Albert
        self.albert = AlbertClient()

        # Paramètres RAG
        self.top_k = 5  # Nombre de chunks à récupérer
        self.similarity_threshold = 0.7  # Seuil de pertinence


    async def generate_response(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> Dict:
        """
        Génère une réponse avec contexte RAG.

        Returns:
            {
                "response": "Réponse générée",
                "sources": [{"document": "...", "excerpt": "..."}],
                "conversation_id": "uuid"
            }
        """
        # Créer ou récupérer conversation
        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        logger.info(f"RAG query pour user {user_id}: {message[:50]}...")

        # 1. Recherche de contexte pertinent
        context_chunks = await self._retrieve_context(user_id, message)

        # 2. Construction du prompt
        prompt_messages = self._build_prompt(message, context_chunks)

        # 3. Génération de la réponse
        response_text = await self.albert.generate_response(
            messages=prompt_messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # 4. Extraction des sources
        sources = self._extract_sources(context_chunks)

        # 5. Sauvegarder dans historique de conversation
        await self._save_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            response=response_text,
            sources=sources
        )

        return {
            "response": response_text,
            "sources": sources,
            "conversation_id": conversation_id
        }


    async def _retrieve_context(self, user_id: str, query: str) -> List[Dict]:
        """
        Recherche les chunks pertinents dans ChromaDB.

        Returns:
            [
                {
                    "content": "Texte du chunk",
                    "metadata": {"source": "doc.pdf", "chunk_index": 5},
                    "distance": 0.25
                }
            ]
        """
        collection_name = f"user_{user_id}"

        try:
            collection = self.client.get_collection(collection_name)
        except:
            logger.warning(f"Aucun document pour user {user_id}")
            return []

        # Générer embedding de la requête
        query_embedding = await self.albert.generate_embeddings([query])

        # Recherche similarité
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=self.top_k
        )

        # Filtrer par seuil de similarité
        chunks = []
        for i, distance in enumerate(results['distances'][0]):
            if distance < self.similarity_threshold:
                chunks.append({
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": distance
                })

        logger.info(f"Récupéré {len(chunks)} chunks pertinents")
        return chunks


    def _build_prompt(self, query: str, context_chunks: List[Dict]) -> List[Dict]:
        """
        Construit le prompt avec le contexte RAG.
        """
        # Contexte concaténé
        context_text = "\n\n".join([
            f"[Source: {chunk['metadata']['source']}]\n{chunk['content']}"
            for chunk in context_chunks
        ])

        # Messages pour l'API
        if context_text:
            system_message = (
                "Tu es un assistant spécialisé dans l'analyse de documents. "
                "Réponds aux questions en te basant UNIQUEMENT sur le contexte fourni. "
                "Si l'information n'est pas dans le contexte, dis-le clairement. "
                "Cite toujours tes sources."
            )

            user_message = f"""Contexte:
{context_text}

Question: {query}

Réponds de manière concise et précise en citant tes sources."""

        else:
            system_message = (
                "Tu es un assistant. L'utilisateur n'a pas encore uploadé de documents. "
                "Explique-lui qu'il doit d'abord ajouter des documents pour pouvoir poser des questions."
            )
            user_message = query

        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]


    def _extract_sources(self, context_chunks: List[Dict]) -> List[Dict]:
        """
        Extrait les sources citées pour affichage.
        """
        sources = []
        seen = set()

        for chunk in context_chunks:
            source_key = (
                chunk['metadata']['source'],
                chunk['metadata'].get('chunk_index', 0)
            )

            if source_key not in seen:
                seen.add(source_key)
                sources.append({
                    "document": chunk['metadata']['source'],
                    "excerpt": chunk['content'][:200] + "...",
                    "relevance": 1.0 - chunk['distance']  # Convertir distance en score
                })

        return sources


    async def _save_conversation(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        response: str,
        sources: List[Dict]
    ):
        """
        Sauvegarde l'échange dans l'historique (Redis ou DB).
        """
        # TODO: Implémenter persistance des conversations
        pass


    async def list_conversations(self, user_id: str) -> List[Dict]:
        """
        Liste les conversations de l'utilisateur.
        """
        # TODO: Implémenter récupération depuis Redis/DB
        return []


    async def delete_conversation(self, user_id: str, conversation_id: str):
        """
        Supprime une conversation.
        """
        # TODO: Implémenter suppression
        pass
```

### 2.5 Gestionnaire de quotas

Créer `chatbot/services/quota_manager.py` :

```python
import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class QuotaManager:
    """
    Gestionnaire de quotas de stockage par utilisateur.

    - Limite: 20 Go par utilisateur
    - Calcul de l'espace utilisé
    - Suggestions de nettoyage
    """

    def __init__(self):
        self.quota_limit = int(os.getenv('CHATBOT_USER_QUOTA', 21474836480))  # 20 Go
        self.documents_dir = "/documents"


    async def get_user_quota(self, user_id: str) -> Dict:
        """
        Calcule le quota utilisé par un utilisateur.

        Returns:
            {
                "used": 1073741824,      # Octets
                "total": 21474836480,
                "percentage": 5.0,
                "files_count": 15
            }
        """
        user_dir = os.path.join(self.documents_dir, user_id)

        if not os.path.exists(user_dir):
            return {
                "used": 0,
                "total": self.quota_limit,
                "percentage": 0.0,
                "files_count": 0
            }

        # Calculer taille totale
        total_size = 0
        files_count = 0

        for root, dirs, files in os.walk(user_dir):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    total_size += os.path.getsize(file_path)
                    files_count += 1
                except:
                    pass

        percentage = (total_size / self.quota_limit) * 100 if self.quota_limit > 0 else 0

        return {
            "used": total_size,
            "total": self.quota_limit,
            "percentage": round(percentage, 2),
            "files_count": files_count
        }


    async def check_quota(self, user_id: str, file_size: int) -> bool:
        """
        Vérifie si l'utilisateur peut uploader un fichier.

        Returns:
            True si quota disponible, False sinon
        """
        quota = await self.get_user_quota(user_id)

        remaining = quota['total'] - quota['used']

        return file_size <= remaining


    async def suggest_cleanup(self, user_id: str) -> list:
        """
        Suggère des fichiers à supprimer (anciens, volumineux).
        """
        # TODO: Implémenter logique de suggestion
        return []
```

### 2.6 Workers Celery

Créer `chatbot/workers/tasks.py` :

```python
from celery import Celery
import os
import logging

logger = logging.getLogger(__name__)

# Initialisation Celery
celery_app = Celery(
    'chatbot_workers',
    broker=os.getenv('CELERY_BROKER_URL'),
    backend='redis://redis:6379/1'
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Paris',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 heure max
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50
)


@celery_app.task(bind=True)
def vectorize_document_task(self, user_id: str, document_id: str, file_path: str, filename: str):
    """
    Tâche asynchrone de vectorisation d'un document.
    """
    from services.vectorization import VectorizationService

    vectorization = VectorizationService()

    try:
        # Mise à jour progression: Extraction
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': 'Extraction du texte...'}
        )

        text = vectorization.extract_text(file_path, filename)
        logger.info(f"Texte extrait: {len(text)} caractères")

        # Mise à jour progression: Découpage
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': 'Découpage en chunks...'}
        )

        chunks = vectorization.chunk_text(text, filename)
        logger.info(f"Document découpé en {len(chunks)} chunks")

        # Mise à jour progression: Vectorisation
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': 'Génération des embeddings...'}
        )

        # Fonction async appelée depuis contexte sync
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            vectorization.store_embeddings(user_id, document_id, chunks)
        )

        # Mise à jour progression: Terminé
        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': 'Vectorisation terminée'}
        )

        # Supprimer fichier temporaire
        os.remove(file_path)

        logger.info(f"Document {document_id} vectorisé avec succès")
        return document_id

    except Exception as e:
        logger.error(f"Erreur vectorisation {document_id}: {e}")
        self.update_state(
            state='FAILURE',
            meta={'progress': 0, 'message': f'Erreur: {str(e)}'}
        )
        raise
```

### 2.7 Fichier requirements.txt

Créer `chatbot/requirements.txt` :

```
# Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0

# Base vectorielle
chromadb==0.4.18

# Extraction de documents
PyMuPDF==1.23.8
python-docx==1.1.0
openpyxl==3.1.2

# Processing texte
langchain==0.0.340
langchain-text-splitters==0.0.1

# API client
httpx==0.25.2

# Workers asynchrones
celery==5.3.4
redis==5.0.1

# Monitoring
prometheus-client==0.19.0

# Logging
python-json-logger==2.0.7
```

### 2.8 Dockerfile

Créer `chatbot/Dockerfile` :

```dockerfile
FROM python:3.9-slim

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Copier requirements et installer
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copier le code
COPY . .

# Créer répertoires nécessaires
RUN mkdir -p /app/logs /documents /data/chromadb

# Exposer port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Commande de démarrage
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

---

## Phase 3 : Configuration Nginx

### 3.1 Créer la nouvelle configuration

Créer `nginx/noscribe-with-chatbot.conf` :

```nginx
# Configuration Nginx Système - noScribe Portal + Chatbot RAG
# noScribe Portal avec Chatbot RAG intégré
# Domaine : noscribe.in.ac-paris.fr
#
# Architecture:
#   - /home     → Portail HTML statique (Nginx direct)
#   - /app      → Django noScribe (proxy :8001)
#   - /chatbot  → Chatbot RAG (proxy :8000)
#
# Installation:
#   sudo cp nginx/noscribe-with-chatbot.conf /etc/nginx/conf.d/noscribe.conf
#   sudo nginx -t
#   sudo systemctl reload nginx

# ===== Redirection HTTP → HTTPS =====
server {
    listen 80;
    listen [::]:80;
    server_name noscribe.in.ac-paris.fr ia-raidf1.in.ac-paris.fr;

    access_log /var/log/nginx/noscribe_access.log;
    error_log /var/log/nginx/noscribe_error.log;

    return 301 https://$server_name$request_uri;
}

# ===== Configuration HTTPS Principale =====
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name noscribe.in.ac-paris.fr ia-raidf1.in.ac-paris.fr;

    # ===== Certificats SSL =====
    ssl_certificate /etc/pki/tls/certs/noscribe.in.ac-paris.fr.crt;
    ssl_certificate_key /etc/pki/tls/private/noscribe.in.ac-paris.fr.key;

    # Configuration SSL sécurisée (Mozilla Intermediate)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    ssl_session_timeout 1d;
    ssl_session_cache shared:MozSSL:10m;
    ssl_session_tickets off;

    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/pki/tls/certs/noscribe-fullchain.crt;

    resolver 10.222.200.100 172.30.8.20 valid=300s;
    resolver_timeout 5s;

    # ===== En-têtes de sécurité =====
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ===== Logs =====
    access_log /var/log/nginx/noscribe_ssl_access.log;
    error_log /var/log/nginx/noscribe_ssl_error.log;

    # ===== Taille des uploads =====
    client_max_body_size 2G;
    client_body_timeout 3600s;

    # ===== REDIRECTION RACINE → PORTAIL =====
    location = / {
        return 301 /home;
    }

    # ===== PORTAIL HTML STATIQUE (Page d'accueil) =====
    location /home {
        alias /var/www/html/portal;
        index index.html;

        # Cache
        expires 1h;
        add_header Cache-Control "public";

        # Gzip
        gzip on;
        gzip_types text/html text/css application/javascript;
    }

    # ===== APPLICATION DJANGO (noScribe) =====
    # Fichiers statiques Django
    location /app/static/ {
        alias /home/iarag/noScribe_web/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";

        gzip on;
        gzip_vary on;
        gzip_types text/css text/javascript application/javascript application/json;
    }

    # Fichiers media Django
    location /app/media/ {
        alias /home/iarag/noScribe_web/media/;
        expires 7d;

        # Sécurité: empêcher exécution scripts
        location ~* \.(php|asp|aspx|jsp|cgi)$ {
            deny all;
        }
    }

    # Endpoints SAML (authentification SSO)
    location /app/saml2/ {
        proxy_pass http://localhost:8001;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header SCRIPT_NAME /app;

        # Buffers pour assertions SAML (XML volumineux)
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;

        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # Application Django principale
    location /app/ {
        proxy_pass http://localhost:8001/;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header SCRIPT_NAME /app;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Timeouts pour transcriptions longues
        proxy_connect_timeout 60s;
        proxy_send_timeout 3600s;
        proxy_read_timeout 3600s;

        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 8 256k;
        proxy_busy_buffers_size 256k;
    }

    # Health check Django
    location /app/health/ {
        proxy_pass http://localhost:8001/health/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header SCRIPT_NAME /app;
        access_log off;
    }

    # ===== CHATBOT RAG (Nouveau service) =====
    location /chatbot/ {
        # Proxy vers conteneur chatbot
        proxy_pass http://127.0.0.1:8000/;

        # Transmission de l'identité utilisateur (depuis session SAML)
        proxy_set_header X-User-ID $remote_user;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_set_header X-Forwarded-Port 443;

        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Timeouts pour vectorisation longue
        proxy_connect_timeout 60s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;

        # Buffers pour réponses volumineuses
        proxy_buffering on;
        proxy_buffer_size 64k;
        proxy_buffers 8 128k;
        proxy_busy_buffers_size 256k;
    }

    # Health check chatbot
    location /chatbot/health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
        access_log off;
    }

    # ===== Sécurité: Bloquer fichiers sensibles =====
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    location ~ \.(env|ini|log|sh|sql|bak|swp)$ {
        deny all;
        access_log off;
        log_not_found off;
    }
}
```

### 3.2 Procédure de migration Nginx

```bash
# 1. Tester la nouvelle configuration SANS l'appliquer
sudo nginx -t -c /home/iarag/noScribe_web/nginx/noscribe-with-chatbot.conf

# 2. Si OK, copier la config
sudo cp /home/iarag/noScribe_web/nginx/noscribe-with-chatbot.conf \
       /etc/nginx/conf.d/noscribe.conf

# 3. Tester à nouveau
sudo nginx -t

# 4. Si OK, recharger Nginx (SANS interruption de service)
sudo systemctl reload nginx

# 5. Vérifier les logs
sudo tail -f /var/log/nginx/noscribe_ssl_error.log
```

---

## Phase 4 : Adaptation Django

### 4.1 Modifications settings.py

Éditer `noscribe_portal/settings.py` :

```python
# ===== Configuration des chemins d'URL (Pour sous-chemin /app) =====

# Forcer le préfixe /app pour toutes les URLs Django
FORCE_SCRIPT_NAME = '/app'

# Adapter les URLs statiques
STATIC_URL = '/app/static/'
MEDIA_URL = '/app/media/'

# Configuration des cookies pour domaine racine (partage session SAML)
SESSION_COOKIE_PATH = '/'
SESSION_COOKIE_SECURE = True  # HTTPS uniquement
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

CSRF_COOKIE_PATH = '/'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Redirection après login SAML → Portail d'accueil
LOGIN_REDIRECT_URL = '/home'
LOGOUT_REDIRECT_URL = '/home'

# ===== Configuration SAML (inchangée) =====
# ... (garder la config SAML existante)
```

### 4.2 Vérifier les templates Django

**Audit des URLs codées en dur** :

```bash
# Rechercher les URLs absolues dans les templates
grep -r "href=\"/[^a]" transcriptions/templates/
grep -r "action=\"/[^a]" transcriptions/templates/
grep -r "src=\"/[^a]" transcriptions/templates/

# Rechercher les URLs relatives potentiellement problématiques
grep -r "{% url" transcriptions/templates/ | grep -v "as "
```

**Correction type** :

```django
{# AVANT (cassé avec /app) #}
<a href="/transcriptions/">Mes transcriptions</a>
<form action="/upload/" method="post">

{# APRÈS (fonctionne avec FORCE_SCRIPT_NAME) #}
<a href="{% url 'transcription_list' %}">Mes transcriptions</a>
<form action="{% url 'upload_audio' %}" method="post">
```

### 4.3 Tester Django avec FORCE_SCRIPT_NAME

```bash
# Activer l'environnement
cd /home/iarag/noScribe_web
source venv/bin/activate

# Lancer serveur de développement
python manage.py runserver 0.0.0.0:8001

# Tester depuis un autre terminal
curl -I http://localhost:8001/
curl -I http://localhost:8001/health/

# Vérifier les fichiers statiques
python manage.py collectstatic --noinput --clear
ls -la staticfiles/
```

---

## Phase 5 : Portail d'accueil

### 5.1 Créer le portail HTML

```bash
# Créer répertoire
sudo mkdir -p /var/www/html/portal
sudo chown iarag:iarag /var/www/html/portal
```

Créer `/var/www/html/portal/index.html` :

```html
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>noScribe Portal - Accueil</title>

    <!-- Bootstrap 5.3 -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">

    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .portal-card {
            background: white;
            border-radius: 20px;
            padding: 3rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 800px;
            width: 100%;
        }

        .app-tile {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 15px;
            padding: 2rem;
            text-align: center;
            transition: transform 0.3s, box-shadow 0.3s;
            cursor: pointer;
            text-decoration: none;
            color: inherit;
            display: block;
            height: 100%;
        }

        .app-tile:hover {
            transform: translateY(-10px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }

        .app-tile i {
            font-size: 4rem;
            margin-bottom: 1rem;
            color: #667eea;
        }

        .app-tile h3 {
            color: #2d3748;
            margin-bottom: 0.5rem;
        }

        .app-tile p {
            color: #718096;
            margin: 0;
            font-size: 0.9rem;
        }

        .header-logo {
            text-align: center;
            margin-bottom: 2rem;
        }

        .header-logo h1 {
            color: #2d3748;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }

        .header-logo p {
            color: #718096;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="portal-card">
            <div class="header-logo">
                <h1><i class="bi bi-house-door"></i> noScribe Portal</h1>
                <p>Bienvenue sur la plateforme noScribe - Sélectionnez une application</p>
            </div>

            <div class="row g-4">
                <!-- Application 1: Transcription -->
                <div class="col-md-6">
                    <a href="/app/" class="app-tile">
                        <i class="bi bi-mic"></i>
                        <h3>Transcription</h3>
                        <p>Transcrivez vos fichiers audio avec noScribe</p>
                        <p class="mt-2"><small class="text-muted">Diarisation • GPU • Comptes rendus IA</small></p>
                    </a>
                </div>

                <!-- Application 2: Chatbot RAG -->
                <div class="col-md-6">
                    <a href="/chatbot/" class="app-tile">
                        <i class="bi bi-chat-dots"></i>
                        <h3>Chatbot RAG</h3>
                        <p>Posez des questions sur vos documents</p>
                        <p class="mt-2"><small class="text-muted">Vectorisation • IA Albert • Citations</small></p>
                    </a>
                </div>
            </div>

            <div class="text-center mt-4">
                <p class="text-muted mb-0">
                    <i class="bi bi-shield-check"></i>
                    Authentification SSO SAML •
                    <i class="bi bi-lock"></i>
                    Données sécurisées
                </p>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
```

### 5.2 Tester le portail

```bash
# Démarrer un serveur web temporaire
cd /var/www/html/portal
python3 -m http.server 8888

# Accéder depuis un navigateur
# http://10.222.200.35:8888/
```

---

## Phase 6 : Intégration Docker

### 6.1 Ajouter le service chatbot dans compose.yaml

Éditer `compose.yaml` :

```yaml
version: '3.8'

services:
  # ===== Redis (partagé entre Django et Chatbot) =====
  redis:
    image: redis:7-alpine
    container_name: noscribe_redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - noscribe_network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

  # ===== ChromaDB (Base vectorielle) =====
  chromadb:
    image: chromadb/chroma:latest
    container_name: noscribe_chromadb
    ports:
      - "8002:8001"  # Port 8002 externe, 8001 interne
    volumes:
      - chromadb_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE
    networks:
      - noscribe_network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/api/v1/heartbeat"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ===== Chatbot RAG (Nouveau service) =====
  chatbot-rag:
    build:
      context: ./chatbot
      dockerfile: Dockerfile
    container_name: noscribe_chatbot
    ports:
      - "8000:8000"  # Exposition vers Nginx système
    volumes:
      - ./chatbot:/app
      - chatbot_documents:/documents
      - chatbot_logs:/app/logs
    environment:
      # API Albert
      - ALBERT_API_URL=${ALBERT_API_URL}
      - ALBERT_API_KEY=${ALBERT_API_KEY}
      - ALBERT_EMBEDDING_MODEL=${ALBERT_EMBEDDING_MODEL}
      - ALBERT_CHAT_MODEL=${ALBERT_CHAT_MODEL}

      # ChromaDB
      - CHROMADB_HOST=chromadb
      - CHROMADB_PORT=8001

      # Celery
      - CELERY_BROKER_URL=redis://redis:6379/1

      # Configuration
      - CHATBOT_MAX_UPLOAD_SIZE=${CHATBOT_MAX_UPLOAD_SIZE}
      - CHATBOT_USER_QUOTA=${CHATBOT_USER_QUOTA}
    depends_on:
      - redis
      - chromadb
    networks:
      - noscribe_network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # ===== Workers Celery Chatbot =====
  chatbot-worker:
    build:
      context: ./chatbot
      dockerfile: Dockerfile
    container_name: noscribe_chatbot_worker
    command: celery -A workers.tasks worker --loglevel=info --concurrency=4
    volumes:
      - ./chatbot:/app
      - chatbot_documents:/documents
      - chatbot_logs:/app/logs
    environment:
      - ALBERT_API_URL=${ALBERT_API_URL}
      - ALBERT_API_KEY=${ALBERT_API_KEY}
      - ALBERT_EMBEDDING_MODEL=${ALBERT_EMBEDDING_MODEL}
      - CHROMADB_HOST=chromadb
      - CHROMADB_PORT=8001
      - CELERY_BROKER_URL=redis://redis:6379/1
    depends_on:
      - redis
      - chromadb
    networks:
      - noscribe_network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  # ===== Django Web (Existant - inchangé logiquement) =====
  web:
    build: .
    container_name: noscribe_web
    # ... (configuration existante inchangée)

  # ===== Celery Worker Django (Existant - inchangé) =====
  celery:
    build: .
    container_name: noscribe_celery
    # ... (configuration existante inchangée)

networks:
  noscribe_network:
    driver: bridge

volumes:
  redis_data:
  chromadb_data:
  chatbot_documents:
  chatbot_logs:
  # ... (volumes existants)
```

### 6.2 Construire et démarrer les conteneurs

```bash
# Sur serveur TEST
cd /home/iarag/noScribe_web

# Construire l'image du chatbot
podman-compose build chatbot-rag chatbot-worker

# Démarrer uniquement les nouveaux services
podman-compose up -d chromadb chatbot-rag chatbot-worker

# Vérifier les logs
podman-compose logs -f chatbot-rag
podman-compose logs -f chatbot-worker

# Vérifier santé des conteneurs
podman-compose ps
```

---

## Phase 7 : Tests et validation

### 7.1 Tests unitaires

**Test extraction de texte** :

```bash
cd /home/iarag/noScribe_web/chatbot

# Créer fichier de test
cat > test_extraction.py <<'EOF'
import sys
sys.path.insert(0, '/app')

from services.vectorization import VectorizationService

def test_pdf_extraction():
    service = VectorizationService()
    text = service.extract_text('/tmp/test.pdf', 'test.pdf')
    print(f"Texte extrait ({len(text)} caractères):")
    print(text[:500])

if __name__ == '__main__':
    test_pdf_extraction()
EOF

# Exécuter dans conteneur
podman exec -it noscribe_chatbot python /app/test_extraction.py
```

**Test API Albert** :

```bash
# Test embeddings
curl -X POST http://localhost:8000/api/test/embeddings \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test_user" \
  -d '{"texts": ["Bonjour", "Hello"]}'

# Test chat
curl -X POST http://localhost:8000/api/test/chat \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test_user" \
  -d '{"message": "Quelle est la capitale de la France?"}'
```

### 7.2 Tests d'intégration

**Scénario complet** :

```bash
#!/bin/bash
# test_integration.sh

USER_ID="test_user_$(date +%s)"
BASE_URL="https://noscribe.in.ac-paris.fr"

echo "===== Test d'intégration Chatbot RAG ====="
echo "Utilisateur de test: $USER_ID"

# 1. Health check
echo -e "\n1. Health check..."
curl -s "${BASE_URL}/chatbot/health" | jq

# 2. Vérifier quota
echo -e "\n2. Quota initial..."
curl -s "${BASE_URL}/chatbot/api/quota" \
  -H "X-User-ID: $USER_ID" | jq

# 3. Upload document PDF
echo -e "\n3. Upload document..."
UPLOAD_RESPONSE=$(curl -s "${BASE_URL}/chatbot/api/upload" \
  -H "X-User-ID: $USER_ID" \
  -F "file=@/tmp/test_document.pdf")

TASK_ID=$(echo $UPLOAD_RESPONSE | jq -r '.task_id')
echo "Task ID: $TASK_ID"

# 4. Attendre fin de vectorisation (max 2 minutes)
echo -e "\n4. Attente vectorisation..."
for i in {1..24}; do
    STATUS=$(curl -s "${BASE_URL}/chatbot/api/upload/status/${TASK_ID}" \
      -H "X-User-ID: $USER_ID")

    STATE=$(echo $STATUS | jq -r '.status')
    PROGRESS=$(echo $STATUS | jq -r '.progress')

    echo "  État: $STATE ($PROGRESS%)"

    if [ "$STATE" == "completed" ]; then
        DOC_ID=$(echo $STATUS | jq -r '.document_id')
        echo "  ✅ Document vectorisé: $DOC_ID"
        break
    elif [ "$STATE" == "failed" ]; then
        echo "  ❌ Échec de vectorisation"
        echo $STATUS | jq
        exit 1
    fi

    sleep 5
done

# 5. Lister documents
echo -e "\n5. Liste des documents..."
curl -s "${BASE_URL}/chatbot/api/documents" \
  -H "X-User-ID: $USER_ID" | jq

# 6. Poser une question
echo -e "\n6. Question au chatbot..."
CHAT_RESPONSE=$(curl -s "${BASE_URL}/chatbot/api/chat" \
  -H "X-User-ID: $USER_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Résume le contenu du document",
    "temperature": 0.7,
    "max_tokens": 300
  }')

echo $CHAT_RESPONSE | jq

# 7. Vérifier quota final
echo -e "\n7. Quota final..."
curl -s "${BASE_URL}/chatbot/api/quota" \
  -H "X-User-ID: $USER_ID" | jq

# 8. Supprimer le document
echo -e "\n8. Nettoyage..."
if [ ! -z "$DOC_ID" ]; then
    curl -X DELETE -s "${BASE_URL}/chatbot/api/documents/${DOC_ID}" \
      -H "X-User-ID: $USER_ID" | jq
fi

echo -e "\n===== Test terminé ====="
```

Exécuter :

```bash
chmod +x test_integration.sh
./test_integration.sh
```

### 7.3 Tests SAML + Routing

**Test manuel** :

1. Accéder à `https://noscribe.in.ac-paris.fr/` → Doit rediriger vers `/home`
2. Cliquer sur "Transcription" → Doit afficher `/app/` et demander login SAML
3. Se connecter via SAML → Doit afficher l'app Django
4. Revenir au portail (`/home`) → Cliquer sur "Chatbot RAG"
5. Vérifier que `/chatbot/` s'affiche ET que l'utilisateur est identifié (X-User-ID)

**Test automatisé** :

```bash
# Vérifier routing Nginx
curl -I https://noscribe.in.ac-paris.fr/
curl -I https://noscribe.in.ac-paris.fr/home
curl -I https://noscribe.in.ac-paris.fr/app/
curl -I https://noscribe.in.ac-paris.fr/chatbot/health

# Vérifier fichiers statiques Django
curl -I https://noscribe.in.ac-paris.fr/app/static/css/style.css

# Vérifier transmission X-User-ID (nécessite session SAML valide)
# → Test manuel requis
```

---

## Phase 8 : Déploiement production

### 8.1 Checklist pré-déploiement

```bash
#!/bin/bash
# pre_deploy_checklist.sh

echo "===== Checklist pré-déploiement Chatbot RAG ====="

# 1. Backup
echo -e "\n1. Backups..."
BACKUP_DIR="/home/iarag/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup base de données
cp /home/iarag/noScribe_web/db.sqlite3 "$BACKUP_DIR/"

# Backup config Nginx
sudo cp /etc/nginx/conf.d/noscribe.conf "$BACKUP_DIR/"

# Backup settings Django
cp /home/iarag/noScribe_web/noscribe_portal/settings.py "$BACKUP_DIR/"

# Backup docker-compose
cp /home/iarag/noScribe_web/compose.yaml "$BACKUP_DIR/"

echo "  ✅ Backups créés dans: $BACKUP_DIR"

# 2. Vérifier Git
echo -e "\n2. État Git..."
cd /home/iarag/noScribe_web
git status --porcelain

if [ -n "$(git status --porcelain)" ]; then
    echo "  ⚠️  Modifications non commitées"
    git status -s
else
    echo "  ✅ Répertoire propre"
fi

# 3. Vérifier environnement
echo -e "\n3. Environnement..."
source venv/bin/activate
python --version
pip list | grep -E "django|celery|fastapi"

# 4. Vérifier ports
echo -e "\n4. Ports..."
netstat -tlnp | grep -E ':8000|:8001|:6379|:8002'

# 5. Tester config Nginx
echo -e "\n5. Configuration Nginx..."
sudo nginx -t

# 6. Vérifier espace disque
echo -e "\n6. Espace disque..."
df -h /home/iarag/noScribe_web
df -h /var/lib/containers

# 7. Vérifier certificats SSL
echo -e "\n7. Certificats SSL..."
sudo openssl x509 -in /etc/pki/tls/certs/noscribe.in.ac-paris.fr.crt \
  -noout -dates

# 8. Vérifier services Docker
echo -e "\n8. Services Docker..."
podman-compose ps

echo -e "\n===== Checklist terminée ====="
echo "Procéder au déploiement? (y/n)"
read -r CONFIRM

if [ "$CONFIRM" != "y" ]; then
    echo "Déploiement annulé"
    exit 1
fi
```

### 8.2 Script de déploiement

Créer `scripts/deploy_chatbot.sh` :

```bash
#!/bin/bash
# deploy_chatbot.sh - Déploiement du chatbot RAG en production

set -e  # Arrêter en cas d'erreur

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "===== Déploiement Chatbot RAG - Production ====="
echo "Répertoire: $PROJECT_DIR"
echo "Date: $(date)"
echo

# Charger environnement
cd "$PROJECT_DIR"
source venv/bin/activate

# Fonction de rollback
rollback() {
    echo -e "\n❌ ERREUR DÉTECTÉE - ROLLBACK"

    # Restaurer Nginx
    if [ -f "$BACKUP_DIR/noscribe.conf" ]; then
        sudo cp "$BACKUP_DIR/noscribe.conf" /etc/nginx/conf.d/
        sudo systemctl reload nginx
    fi

    # Restaurer settings
    if [ -f "$BACKUP_DIR/settings.py" ]; then
        cp "$BACKUP_DIR/settings.py" noscribe_portal/
    fi

    # Redémarrer Django
    sudo systemctl restart noscribe_web

    echo "Rollback effectué. Vérifier les logs."
    exit 1
}

trap rollback ERR

# ===== 1. Préparation =====
echo "1. Création des backups..."
BACKUP_DIR="/home/iarag/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

cp db.sqlite3 "$BACKUP_DIR/" 2>/dev/null || true
sudo cp /etc/nginx/conf.d/noscribe.conf "$BACKUP_DIR/"
cp noscribe_portal/settings.py "$BACKUP_DIR/"
cp compose.yaml "$BACKUP_DIR/"

echo "  ✅ Backups: $BACKUP_DIR"

# ===== 2. Tests pré-déploiement =====
echo -e "\n2. Tests pré-déploiement..."

# Test configuration Nginx
sudo nginx -t

# Test settings Django
python manage.py check --deploy

echo "  ✅ Tests OK"

# ===== 3. Déploiement Nginx =====
echo -e "\n3. Déploiement Nginx..."

sudo cp nginx/noscribe-with-chatbot.conf /etc/nginx/conf.d/noscribe.conf
sudo nginx -t
sudo systemctl reload nginx

echo "  ✅ Nginx rechargé"

# ===== 4. Déploiement Django =====
echo -e "\n4. Adaptation Django..."

# Collecter fichiers statiques
python manage.py collectstatic --noinput --clear

# Appliquer migrations (si nécessaire)
python manage.py migrate --noinput

# Redémarrer service Django
sudo systemctl restart noscribe_web
sudo systemctl restart noscribe_celery

sleep 5

# Vérifier service Django
curl -f http://localhost:8001/health/ || rollback

echo "  ✅ Django déployé"

# ===== 5. Déploiement conteneurs chatbot =====
echo -e "\n5. Déploiement conteneurs..."

# Construire images
podman-compose build chatbot-rag chatbot-worker

# Démarrer services
podman-compose up -d chromadb
sleep 10

podman-compose up -d chatbot-rag chatbot-worker
sleep 15

# Vérifier santé
curl -f http://localhost:8000/health || rollback

echo "  ✅ Conteneurs déployés"

# ===== 6. Tests post-déploiement =====
echo -e "\n6. Tests post-déploiement..."

# Test portail
curl -f -I https://noscribe.in.ac-paris.fr/home || rollback

# Test Django
curl -f -I https://noscribe.in.ac-paris.fr/app/ || rollback

# Test chatbot
curl -f https://noscribe.in.ac-paris.fr/chatbot/health || rollback

echo "  ✅ Tests réussis"

# ===== 7. Monitoring =====
echo -e "\n7. Monitoring actif (30 secondes)..."

for i in {1..6}; do
    echo "  Check $i/6..."

    # Vérifier services
    systemctl is-active noscribe_web >/dev/null || rollback
    curl -f http://localhost:8001/health/ >/dev/null || rollback
    curl -f http://localhost:8000/health >/dev/null || rollback

    sleep 5
done

echo "  ✅ Monitoring OK"

# ===== 8. Résumé =====
echo -e "\n===== ✅ DÉPLOIEMENT RÉUSSI ====="
echo "Services déployés:"
echo "  - Nginx: https://noscribe.in.ac-paris.fr/"
echo "  - Portail: https://noscribe.in.ac-paris.fr/home"
echo "  - Django: https://noscribe.in.ac-paris.fr/app/"
echo "  - Chatbot: https://noscribe.in.ac-paris.fr/chatbot/"
echo
echo "Backup: $BACKUP_DIR"
echo
echo "Surveiller les logs:"
echo "  sudo tail -f /var/log/nginx/noscribe_ssl_error.log"
echo "  podman-compose logs -f chatbot-rag"
echo

# Afficher état des services
podman-compose ps
systemctl status noscribe_web --no-pager -l

echo -e "\n===== Déploiement terminé ====="
```

Rendre exécutable :

```bash
chmod +x scripts/deploy_chatbot.sh
```

### 8.3 Exécution du déploiement

```bash
# Sur le serveur TEST d'abord
cd /home/iarag/noScribe_web
./scripts/deploy_chatbot.sh

# Surveiller logs pendant 5 minutes
sudo tail -f /var/log/nginx/noscribe_ssl_error.log &
podman-compose logs -f chatbot-rag &

# Si OK, déployer en PRODUCTION (après la démo)
./scripts/env-switch.sh production
./scripts/deploy_chatbot.sh
```

---

## Troubleshooting

### Problème: Erreur 502 Bad Gateway sur /chatbot

**Symptômes** :
```
502 Bad Gateway
nginx
```

**Diagnostic** :
```bash
# 1. Vérifier que le conteneur tourne
podman ps | grep chatbot

# 2. Vérifier les logs
podman-compose logs chatbot-rag

# 3. Vérifier le port
netstat -tlnp | grep 8000

# 4. Tester en direct
curl http://localhost:8000/health
```

**Causes possibles** :
- Conteneur non démarré → `podman-compose up -d chatbot-rag`
- Port 8000 utilisé par autre process → `sudo lsof -i :8000`
- Erreur dans le code Python → Voir logs conteneur

---

### Problème: URLs Django cassées après migration vers /app

**Symptômes** :
```
404 Not Found sur /static/
500 Internal Server Error
```

**Diagnostic** :
```bash
# 1. Vérifier FORCE_SCRIPT_NAME
python manage.py shell
>>> from django.conf import settings
>>> settings.FORCE_SCRIPT_NAME
'/app'

# 2. Vérifier fichiers statiques
ls -la staticfiles/
curl -I http://localhost:8001/static/css/style.css

# 3. Vérifier URLs templates
grep -r "href=\"/" transcriptions/templates/
```

**Solution** :
```bash
# Recollect static
python manage.py collectstatic --clear --noinput

# Corriger templates
# Remplacer URLs hardcodées par {% url %}
```

---

### Problème: X-User-ID non transmis au chatbot

**Symptômes** :
```json
{"detail": "Authentication required"}
```

**Diagnostic** :
```bash
# Vérifier headers Nginx
sudo tail -f /var/log/nginx/noscribe_ssl_error.log

# Tester avec curl
curl https://noscribe.in.ac-paris.fr/chatbot/api/quota \
  -H "X-User-ID: test_user"
```

**Cause** :
Session SAML non établie ou header non passé par Nginx

**Solution** :
```nginx
# Dans /etc/nginx/conf.d/noscribe.conf
location /chatbot/ {
    proxy_set_header X-User-ID $remote_user;  # Ajouter cette ligne
    # ...
}
```

---

### Problème: ChromaDB inaccessible

**Symptômes** :
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Diagnostic** :
```bash
# Vérifier conteneur
podman ps | grep chromadb

# Vérifier logs
podman-compose logs chromadb

# Tester API
curl http://localhost:8002/api/v1/heartbeat
```

**Solution** :
```bash
# Redémarrer ChromaDB
podman-compose restart chromadb

# Vérifier réseau Docker
podman network inspect noscribe_network
```

---

### Problème: Vectorisation bloquée

**Symptômes** :
Tâche reste en "processing" indéfiniment

**Diagnostic** :
```bash
# Vérifier workers Celery
podman-compose logs chatbot-worker

# Vérifier Redis
redis-cli -h localhost -p 6379
> SELECT 1
> KEYS *
> LLEN celery
```

**Solution** :
```bash
# Redémarrer workers
podman-compose restart chatbot-worker

# Purger file d'attente Redis
redis-cli -h localhost -p 6379 FLUSHDB
```

---

### Problème: Quota dépassé alors qu'espace disponible

**Diagnostic** :
```bash
# Vérifier espace réel
du -sh /documents/user_*

# Vérifier calcul quota
curl http://localhost:8000/api/quota -H "X-User-ID: user123"
```

**Solution** :
```bash
# Nettoyer fichiers temporaires
find /documents -name "*.tmp" -delete

# Recalculer quotas
# TODO: Implémenter commande de maintenance
```

---

## Rollback et récupération

### Procédure de rollback complet

```bash
#!/bin/bash
# rollback.sh - Restauration de la configuration pré-chatbot

BACKUP_DIR="$1"

if [ -z "$BACKUP_DIR" ]; then
    echo "Usage: ./rollback.sh /path/to/backup"
    exit 1
fi

echo "===== ROLLBACK vers $BACKUP_DIR ====="

# 1. Arrêter nouveaux services
echo "1. Arrêt services chatbot..."
podman-compose stop chatbot-rag chatbot-worker chromadb

# 2. Restaurer Nginx
echo "2. Restauration Nginx..."
sudo cp "$BACKUP_DIR/noscribe.conf" /etc/nginx/conf.d/
sudo nginx -t
sudo systemctl reload nginx

# 3. Restaurer settings Django
echo "3. Restauration Django..."
cp "$BACKUP_DIR/settings.py" noscribe_portal/
python manage.py collectstatic --noinput --clear

# 4. Redémarrer Django
echo "4. Redémarrage Django..."
sudo systemctl restart noscribe_web
sudo systemctl restart noscribe_celery

# 5. Tests
echo "5. Tests..."
curl -f http://localhost:8001/health/
curl -f https://noscribe.in.ac-paris.fr/

echo "===== Rollback terminé ====="
```

### Sauvegardes automatiques

Ajouter dans crontab :

```bash
# Backup quotidien de la config
0 2 * * * /home/iarag/noScribe_web/scripts/backup_daily.sh

# Backup hebdomadaire complet
0 3 * * 0 /home/iarag/noScribe_web/scripts/backup_weekly.sh
```

---

## Résumé des commandes clés

```bash
# ===== Développement =====
./scripts/env-switch.sh test
git checkout -b feature/chatbot-rag-test
podman-compose build chatbot-rag
podman-compose up -d chatbot-rag chatbot-worker

# ===== Tests =====
curl http://localhost:8000/health
./test_integration.sh

# ===== Déploiement =====
./scripts/deploy_chatbot.sh

# ===== Monitoring =====
podman-compose logs -f chatbot-rag
sudo tail -f /var/log/nginx/noscribe_ssl_error.log
curl https://noscribe.in.ac-paris.fr/chatbot/health

# ===== Rollback =====
./rollback.sh /home/iarag/backups/20260204_100000
```

---

## Contacts et ressources

### Documentation de référence

- **FastAPI** : https://fastapi.tiangolo.com/
- **ChromaDB** : https://docs.trychroma.com/
- **API Albert** : https://albert.api.gouv.fr/
- **Celery** : https://docs.celeryq.dev/

### Support

- **Équipe Albert** : Email demande de fonctionnalités (timestamps mots)
- **Documentation projet** : `/home/iarag/noScribe_web/docs/`

---

**FIN DE LA DOCUMENTATION D'IMPLÉMENTATION**

**Dernière mise à jour** : 2026-02-04
**Auteur** : Claude Code
**Version** : 1.0
