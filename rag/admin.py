from django.contrib import admin
from .models import Document, DocumentChunk, Conversation, Message


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'user', 'status', 'chunk_count', 'file_size', 'created_at']
    list_filter = ['status', 'user']
    search_fields = ['filename', 'user__username']
    readonly_fields = ['created_at', 'updated_at', 'chunk_count']
    ordering = ['-created_at']


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ['document', 'chunk_index', 'content_preview']
    list_filter = ['document']
    readonly_fields = ['embedding']  # ne pas afficher un vecteur de 1024 dims dans l'admin

    def content_preview(self, obj):
        return obj.content[:100] + '…' if len(obj.content) > 100 else obj.content
    content_preview.short_description = 'Aperçu'


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'created_at', 'updated_at']
    list_filter = ['user']
    search_fields = ['title', 'user__username']
    ordering = ['-updated_at']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['conversation', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'conversation']
    ordering = ['-created_at']

    def content_preview(self, obj):
        return obj.content[:80] + '…' if len(obj.content) > 80 else obj.content
    content_preview.short_description = 'Contenu'
