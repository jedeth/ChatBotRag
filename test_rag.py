#!/usr/bin/env python
"""Script de test pour le RAG avec re-ranking"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_rag.settings')
django.setup()

from django.contrib.auth.models import User
from rag.services.rag_engine import RAGEngine
from rag.models import Document

def test_rag():
    # Récupérer un utilisateur avec des documents
    user = User.objects.filter(rag_documents__status='vectorized').first()

    if user:
        print(f"✅ Utilisateur trouvé: {user.username}")
        docs = Document.objects.filter(user=user, status='vectorized')
        print(f"✅ Documents vectorisés: {docs.count()}")

        if docs.exists():
            print(f"\nDocuments disponibles:")
            for doc in docs[:3]:
                print(f"  - {doc.filename} ({doc.chunk_count} chunks)")

            # Tester le RAG avec re-ranking
            print("\n🔍 Test RAG avec re-ranking...\n")
            engine = RAGEngine()
            result = engine.generate_response(
                user=user,
                message="Quels sont les exemples d'activités mentionnés ?",
                temperature=0.7,
                max_tokens=200
            )

            print("\n✅ Réponse générée:")
            print(f"  Texte: {result['response'][:150]}...")
            print(f"  Sources: {len(result['sources'])} document(s)")
            for src in result['sources']:
                print(f"    - {src['document']} (pertinence: {src['relevance']:.3f}, chunks: {src['chunks_count']})")
        else:
            print("❌ Aucun document vectorisé trouvé")
    else:
        print("❌ Aucun utilisateur avec documents trouvé")

if __name__ == '__main__':
    test_rag()
