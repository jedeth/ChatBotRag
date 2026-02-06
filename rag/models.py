from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from pgvector.django import VectorField


# ==============================================================================
# Documents uploadés et leur représentation vectorielle
# ==============================================================================

class Document(models.Model):
    """Document uploadé par un utilisateur, à vectoriser pour le RAG."""

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('vectorizing', 'Vectorisation en cours'),
        ('vectorized', 'Vectorisé'),
        ('failed', 'Échec'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='rag_documents'
    )
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to='rag/documents/')
    file_size = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    celery_task_id = models.CharField(max_length=255, null=True, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)  # Stats: lignes, colonnes, etc.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.get_status_display()})"

    def get_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)


class DocumentChunk(models.Model):
    """Chunk de texte issu d'un Document, avec son embedding vectoriel (pgvector)."""

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name='chunks'
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS)

    class Meta:
        ordering = ['chunk_index']
        unique_together = [('document', 'chunk_index')]
        # L'index HNSW sur embedding est créé dans la migration
        # 0002_documentchunk_hnsw_index (SQL brut — pgvector 0.4.x
        # n'expose pas HnswIndex via l'ORM).

    def __str__(self):
        return f"Chunk {self.chunk_index} — {self.document.filename}"


# ==============================================================================
# Conversations et messages
# ==============================================================================

class Conversation(models.Model):
    """Fil de conversation entre un utilisateur et l'assistant RAG."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='conversations'
    )
    title = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f"Conversation {self.id}"


class Message(models.Model):
    """Message individuel dans une conversation."""

    ROLE_CHOICES = [
        ('user', 'Utilisateur'),
        ('assistant', 'Assistant'),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    sources = models.JSONField(default=list)  # sources RAG citées dans la réponse
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role} : {self.content[:50]}…"
