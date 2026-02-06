"""
Tâches Celery pour le Chatbot RAG.

vectorize_document_task :
  Pipeline asynchrone de vectorisation d'un document uploadé.
  1. Extraction du texte    (VectorizationService)
  2. Découpage en chunks    (VectorizationService)
  3. Génération embeddings  (AlbertClient — lots de 64)
  4. Stockage en base       (bulk_create sur DocumentChunk / pgvector)
"""
import logging

from celery import shared_task

logger = logging.getLogger('rag')


@shared_task(bind=True, max_retries=3)
def vectorize_document_task(self, document_id: int):
    """
    Vectorise un Document déjà sauvegardé en base.

    La tâche met à jour régulièrement son état (PROGRESS) pour que
    l'interface puisse afficher une barre de progression via polling.
    """
    # Import tardif pour éviter les problèmes d'initialisation Django / Celery
    from .models import Document, DocumentChunk
    from .services.vectorization import VectorizationService
    from .services.albert_client import AlbertClient

    # ---------------------------------------------------------------
    # Récupérer le document
    # ---------------------------------------------------------------
    try:
        document = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} introuvable — tâche abandonnée")
        return

    vectorization = VectorizationService()

    try:
        # 1. Extraction du texte
        self.update_state(
            state='PROGRESS',
            meta={'progress': 10, 'message': 'Extraction du texte…'}
        )
        text = vectorization.extract_text(document.file.path, document.filename)
        logger.info(f"[doc {document_id}] Texte extrait : {len(text)} caractères")

        # Sauvegarder les métadonnées extraites (stats XLSX, nb pages PDF, etc.)
        if vectorization.extracted_metadata:
            document.metadata = vectorization.extracted_metadata
            document.save(update_fields=['metadata'])
            logger.info(f"[doc {document_id}] Métadonnées sauvegardées : {document.metadata}")

        # 2. Découpage en chunks
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': 'Découpage en chunks…'}
        )
        chunks = vectorization.chunk_text(text, document.filename)
        logger.info(f"[doc {document_id}] {len(chunks)} chunks créés")

        # 3. Génération des embeddings (Albert API, lots de 64)
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': 'Génération des embeddings…'}
        )
        albert = AlbertClient()
        texts = [chunk['content'] for chunk in chunks]
        embeddings = albert.generate_embeddings(texts)

        # 4. Stockage en base (pgvector)
        self.update_state(
            state='PROGRESS',
            meta={'progress': 75, 'message': 'Stockage en base de données…'}
        )
        chunk_objects = [
            DocumentChunk(
                document=document,
                chunk_index=i,
                content=chunk['content'],
                embedding=embedding,
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        DocumentChunk.objects.bulk_create(chunk_objects)

        # 5. Mise à jour du document
        document.status = 'vectorized'
        document.chunk_count = len(chunks)
        document.save()

        self.update_state(
            state='PROGRESS',
            meta={'progress': 100, 'message': 'Vectorisation terminée'}
        )
        logger.info(f"[doc {document_id}] Vectorisé avec succès ({len(chunks)} chunks)")
        return document_id

    except Exception as e:
        logger.error(f"[doc {document_id}] Erreur vectorisation : {e}", exc_info=True)

        # Marquer le document comme échoué
        try:
            document.status = 'failed'
            document.error_message = str(e)
            document.save()
        except Exception:
            pass

        # Réessai avec backoff exponentiel (60s, 120s, 240s)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

        raise
