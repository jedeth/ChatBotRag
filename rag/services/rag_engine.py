"""
Moteur RAG (Retrieval-Augmented Generation).

Pipeline par requête :
  1. Embed la question via Albert  →  vecteur 1024 dims
  2. Recherche de similarité cosinus dans pgvector  →  top-k chunks
  3. Construction du prompt avec le contexte récupéré
  4. Génération de la réponse via Albert chat/completions
  5. Extraction + déduplication des sources citées

Porté depuis chatbot/services/rag_engine.py :
  - ChromaDB remplacé par une requête Django ORM + pgvector
  - La persistance des conversations (ex-TODO) est désormais triviale
    via les modèles Conversation / Message
"""
import logging
from typing import List, Dict

from django.contrib.auth.models import User
from pgvector.django import CosineDistance

from .albert_client import AlbertClient
from ..models import Document, DocumentChunk

logger = logging.getLogger('rag')

# Paramètres de recherche vectorielle
SIMILARITY_THRESHOLD = 0.8  # Seuil de distance cosinus (0 = identique, 1 = orthogonal)

# Paramètres de re-ranking (si activé)
ENABLE_RERANKING = True    # Active le re-ranking avec bge-reranker-v2-m3
INITIAL_TOP_K = 20         # Nombre de chunks récupérés avant re-ranking
FINAL_TOP_K = 5            # Nombre de chunks finaux après re-ranking

# Si re-ranking désactivé, récupère directement FINAL_TOP_K chunks
TOP_K = FINAL_TOP_K


class RAGEngine:
    """Moteur de génération avec contexte documentaire (pgvector)."""

    def __init__(self):
        self.albert = AlbertClient()

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    def generate_response(
        self,
        user: User,
        message: str,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> Dict:
        """
        Génère une réponse RAG pour un utilisateur.

        Returns:
            {"response": "texte", "sources": [{…}, …]}
        """
        logger.info(f"RAG query pour {user.username} : {message[:60]}…")

        # 0. Vérifier si la question concerne des statistiques de documents
        metadata_response = self._try_metadata_response(user, message)
        if metadata_response:
            logger.info("Réponse générée depuis les métadonnées")
            return metadata_response

        # 1. Récupération du contexte
        context_chunks = self._retrieve_context(user, message)

        # 2. Prompt
        prompt_messages = self._build_prompt(message, context_chunks)

        # 3. Génération
        response_text = self.albert.generate_response(
            messages=prompt_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 4. Sources
        sources = self._extract_sources(context_chunks)

        return {
            'response': response_text,
            'sources': sources,
        }

    # ------------------------------------------------------------------
    # Consultation des métadonnées (pour questions statistiques)
    # ------------------------------------------------------------------

    def _try_metadata_response(self, user: User, query: str) -> Dict:
        """
        Tente de répondre à partir des métadonnées des documents.

        Utilisé pour les questions statistiques (combien, nombre, total)
        sur des fichiers XLSX avec beaucoup de lignes.

        Returns:
            Dict avec response et sources, ou None si pas applicable
        """
        # Mots-clés indiquant une question statistique
        counting_keywords = [
            'combien', 'nombre', 'total', 'count',
            'quantité', 'effectif', 'liste',
            'compter', 'compte', 'dénombre', 'dénombrer'
        ]

        query_lower = query.lower()
        is_counting_query = any(keyword in query_lower for keyword in counting_keywords)

        if not is_counting_query:
            return None

        # Récupérer les documents de l'utilisateur avec métadonnées
        documents = Document.objects.filter(
            user=user,
            status='vectorized'
        ).exclude(metadata={}).order_by('-created_at')

        if not documents.exists():
            return None

        # Construire un contexte depuis les métadonnées
        metadata_context = []
        sources = []

        for doc in documents:
            metadata = doc.metadata
            if not metadata:
                continue

            # Traiter les métadonnées XLSX
            if metadata.get('format') == 'xlsx':
                total_data_rows = metadata.get('total_data_rows', 0)
                sheets_info = metadata.get('sheets', [])

                context_parts = [
                    f"Document : {doc.filename}",
                    f"Type : Fichier Excel",
                    f"Nombre total de lignes de données : {total_data_rows}"
                ]

                for sheet in sheets_info:
                    context_parts.append(
                        f"  - Feuille '{sheet['name']}' : {sheet['data_rows']} ligne(s) de données"
                    )

                metadata_context.append("\n".join(context_parts))

                sources.append({
                    'document': doc.filename,
                    'excerpt': f"Statistiques : {total_data_rows} ligne(s) de données",
                    'relevance': 1.0,
                    'chunks_count': 1
                })

            # Traiter les métadonnées PDF
            elif metadata.get('format') == 'pdf':
                page_count = metadata.get('page_count', 0)
                context_parts = [
                    f"Document : {doc.filename}",
                    f"Type : PDF",
                    f"Nombre de pages : {page_count}"
                ]

                metadata_context.append("\n".join(context_parts))

                sources.append({
                    'document': doc.filename,
                    'excerpt': f"Document PDF de {page_count} page(s)",
                    'relevance': 1.0,
                    'chunks_count': 1
                })

        if not metadata_context:
            return None

        # Construire le prompt avec les métadonnées
        system_message = (
            "Tu es un assistant spécialisé dans l'analyse de documents. "
            "Réponds aux questions en te basant sur les statistiques des documents fournis. "
            "Sois précis et cite toujours tes sources."
        )

        user_message = (
            f"Statistiques des documents :\n\n"
            f"{chr(10).join(metadata_context)}\n\n"
            f"Question : {query}\n\n"
            "Réponds de manière précise en utilisant les statistiques ci-dessus."
        )

        # Générer la réponse
        response_text = self.albert.generate_response(
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,  # Plus déterministe pour les stats
            max_tokens=500
        )

        return {
            'response': response_text,
            'sources': sources
        }

    # ------------------------------------------------------------------
    # Recherche vectorielle (pgvector)
    # ------------------------------------------------------------------

    def _retrieve_context(self, user: User, query: str) -> List[Dict]:
        """
        Recherche les chunks les plus proches de la requête via pgvector.

        Pipeline en 2 étapes (si re-ranking activé) :
          1. Récupération large : TOP 20 chunks via similarité cosinus (pgvector)
          2. Re-ranking : bge-reranker-v2-m3 sélectionne les 5 meilleurs

        Si re-ranking désactivé, récupère directement les 5 meilleurs chunks.

        Seuls les documents appartenant à l'utilisateur sont interrogés.
        """
        # Embed la requête
        query_embedding = self.albert.generate_embeddings([query])[0]

        # Déterminer combien de chunks récupérer
        retrieve_k = INITIAL_TOP_K if ENABLE_RERANKING else FINAL_TOP_K

        # Requête pgvector — select_related pour éviter une requête supplémentaire
        # sur document.filename
        chunks_qs = (
            DocumentChunk.objects
            .select_related('document')
            .filter(document__user=user)
            .annotate(distance=CosineDistance('embedding', query_embedding))
            .filter(distance__lte=SIMILARITY_THRESHOLD)
            .order_by('distance')
            [:retrieve_k]
        )

        # Convertir en liste avec filtrage des chunks vides
        initial_results = [
            {
                'content':  chunk.content,
                'source':   chunk.document.filename,
                'distance': float(chunk.distance),
            }
            for chunk in chunks_qs
            if len(chunk.content.strip()) >= 50
        ]

        logger.info(f"Récupéré {len(initial_results)} chunks via pgvector (similarité cosinus)")

        # Si re-ranking activé et qu'on a des résultats, re-classer avec bge-reranker-v2-m3
        if ENABLE_RERANKING and initial_results:
            try:
                # Extraire les contenus pour le re-ranking
                documents = [chunk['content'] for chunk in initial_results]

                # Appeler le re-ranker
                rerank_results = self.albert.rerank(
                    query=query,
                    documents=documents,
                    top_k=FINAL_TOP_K
                )

                # Reconstruire les résultats avec les chunks re-classés
                reranked_chunks = []
                for item in rerank_results:
                    original_chunk = initial_results[item['index']]
                    reranked_chunks.append({
                        'content': original_chunk['content'],
                        'source': original_chunk['source'],
                        'distance': 1.0 - item['score'],  # Convertir score → distance
                        'rerank_score': item['score']     # Conserver score original
                    })

                logger.info(
                    f"Re-ranking terminé : {len(reranked_chunks)} chunks finaux "
                    f"(score max: {rerank_results[0]['score']:.3f})"
                    if rerank_results else "Re-ranking : aucun résultat"
                )

                return reranked_chunks

            except Exception as e:
                logger.warning(f"Échec re-ranking, utilisation des résultats initiaux : {e}")
                # Fallback : retourner les premiers FINAL_TOP_K chunks sans re-ranking
                return initial_results[:FINAL_TOP_K]

        # Si re-ranking désactivé, retourner les résultats directs
        return initial_results

    # ------------------------------------------------------------------
    # Construction du prompt
    # ------------------------------------------------------------------

    def _build_prompt(self, query: str, context_chunks: List[Dict]) -> List[Dict]:
        """
        Construit les messages system + user pour l'API chat.

        Si des chunks ont été trouvés, le contexte est inséré dans le
        message utilisateur avec une instruction de citation des sources.
        Sinon, le modèle est instruit de demander un upload de documents.
        """
        if context_chunks:
            context_text = "\n\n".join(
                f"[Source : {chunk['source']}]\n{chunk['content']}"
                for chunk in context_chunks
            )

            system_message = (
                "Tu es un assistant spécialisé dans l'analyse de documents. "
                "Réponds aux questions en te basant UNIQUEMENT sur le contexte fourni. "
                "Si l'information n'est pas dans le contexte, dis-le clairement. "
                "Cite toujours tes sources."
            )

            user_message = (
                f"Contexte :\n{context_text}\n\n"
                f"Question : {query}\n\n"
                "Réponds de manière concise et précise en citant tes sources."
            )
        else:
            system_message = (
                "Tu es un assistant. L'utilisateur n'a pas encore uploadé de documents. "
                "Explique-lui qu'il doit d'abord ajouter des documents pour poser des questions."
            )
            user_message = query

        return [
            {"role": "system", "content": system_message},
            {"role": "user",   "content": user_message},
        ]

    # ------------------------------------------------------------------
    # Extraction des sources citées
    # ------------------------------------------------------------------

    def _extract_sources(self, context_chunks: List[Dict]) -> List[Dict]:
        """
        Déduplique les sources par nom de fichier.

        Pour chaque document, garde le meilleur score de pertinence
        et l'extrait correspondant.  Porté tel quel depuis chatbot/.
        """
        sources_by_doc: Dict[str, Dict] = {}

        for chunk in context_chunks:
            doc_name  = chunk['source']
            relevance = 1.0 - chunk['distance']

            if doc_name not in sources_by_doc:
                sources_by_doc[doc_name] = {
                    'document':    doc_name,
                    'excerpt':     chunk['content'][:200] + '…',
                    'relevance':   relevance,
                    'chunks_count': 1,
                }
            else:
                existing = sources_by_doc[doc_name]
                existing['chunks_count'] += 1
                if relevance > existing['relevance']:
                    existing['relevance'] = relevance
                    existing['excerpt']   = chunk['content'][:200] + '…'

        # Trier par pertinence décroissante
        return sorted(sources_by_doc.values(), key=lambda s: s['relevance'], reverse=True)
