# ==============================================================================
# Migration manuelle : index HNSW sur DocumentChunk.embedding
#
# pgvector 0.4.x (max sur PyPI) ne publie pas HnswIndex via l'ORM Django ;
# on crée l'index avec du SQL brut.  L'opérateur utilisé est <=> (cosine)
# pour correspondre aux requêtes dans rag_engine.py (CosineDistance).
# ==============================================================================

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rag', '0001_initial'),
    ]

    operations = [
        # S'assurer que l'extension vector est activée (idempotent)
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Index HNSW — optimise les recherches approximate nearest-neighbour
        # m=16, ef_construction=64 : bons par défaut pour < 1 M de vecteurs 1024-d
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS idx_documentchunk_embedding_hnsw
                ON rag_documentchunk
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_documentchunk_embedding_hnsw;
            """,
        ),
    ]
