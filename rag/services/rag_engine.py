"""
Moteur RAG (Retrieval-Augmented Generation).

Pipeline par requête :
  0. [OPTIONNEL] Analyse de la question avec Query Coach
  1. Embed la question via Albert  →  vecteur 1024 dims
  2. Recherche de similarité cosinus dans pgvector  →  top-k chunks
  3. Re-ranking avec bge-reranker-v2-m3 (si activé)
  4. Construction du prompt avec le contexte récupéré
  5. Génération de la réponse via Albert chat/completions
  6. Extraction + déduplication des sources citées

Query Coach (Phase 4):
  - Détection automatique du niveau utilisateur (novice/intermédiaire/expert)
  - Coaching adaptatif non-intrusif
  - Skip automatique pour questions expertes
"""
import logging
from typing import List, Dict, Optional

from django.contrib.auth.models import User
from django.conf import settings
from pgvector.django import CosineDistance

from .albert_client import AlbertClient
from .query_coach import QueryCoach, QueryAnalysis
from ..models import Document, DocumentChunk

logger = logging.getLogger('rag')

# Paramètres de recherche vectorielle (depuis settings.py)
SIMILARITY_THRESHOLD = settings.RAG_SIMILARITY_THRESHOLD
ENABLE_RERANKING = settings.RAG_ENABLE_RERANKING
INITIAL_TOP_K = settings.RAG_INITIAL_TOP_K
FINAL_TOP_K = settings.RAG_FINAL_TOP_K
TOP_K = FINAL_TOP_K


class RAGEngine:
    """Moteur de génération avec contexte documentaire (pgvector)."""

    def __init__(self):
        self.albert = AlbertClient()
        self.coach = QueryCoach()

    # ------------------------------------------------------------------
    # Query Coach (Phase 4)
    # ------------------------------------------------------------------

    def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyse une question avec le Query Coach.

        Détecte le niveau de l'utilisateur et identifie les améliorations possibles.

        Args:
            query: Question à analyser

        Returns:
            QueryAnalysis avec niveau et suggestions
        """
        return self.coach.analyze_query(query)

    def get_coaching_suggestions(self, query: str) -> Optional[Dict]:
        """
        Obtient les suggestions de coaching pour une question.

        Args:
            query: Question à analyser

        Returns:
            Dict avec message et suggestions, ou None si pas de coaching nécessaire
        """
        analysis = self.coach.analyze_query(query)

        if not analysis.needs_coaching:
            logger.info(f"Query Coach: Niveau '{analysis.level}' (score: {analysis.score:.2f}) - Pas de coaching nécessaire")
            return None

        coaching_message = self.coach.generate_coaching_message(analysis, query)

        if coaching_message:
            logger.info(
                f"Query Coach: Niveau '{analysis.level}' (score: {analysis.score:.2f}) - "
                f"Coaching proposé ({len(coaching_message.get('suggestions', []))} suggestions)"
            )

        return coaching_message

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    def generate_response(
        self,
        user: User,
        message: str,
        temperature: float = 0.7,
        max_tokens: int = 500,
        skip_coaching: bool = False,
    ) -> Dict:
        """
        Génère une réponse RAG pour un utilisateur.

        Args:
            user: Utilisateur Django
            message: Question de l'utilisateur
            temperature: Paramètre de créativité (0-1)
            max_tokens: Longueur maximale de la réponse
            skip_coaching: Si True, skip l'analyse par le Query Coach

        Returns:
            {
                "response": "texte",
                "sources": [{…}, …],
                "coaching": {...} (optionnel, si suggestions disponibles)
            }
        """
        logger.info(f"RAG query pour {user.username} : {message[:60]}…")

        # Phase 4: Analyse avec Query Coach (si non-skippé)
        coaching_result = None
        if not skip_coaching:
            analysis = self.coach.analyze_query(message)
            logger.info(
                f"Query Coach: Niveau '{analysis.level}' (score: {analysis.score:.2f})"
            )

            # Générer suggestions si nécessaire (mais ne pas bloquer la requête)
            if analysis.needs_coaching:
                coaching_result = self.coach.generate_coaching_message(analysis, message)
                if coaching_result:
                    logger.info(
                        f"Query Coach: {len(coaching_result.get('suggestions', []))} suggestions générées"
                    )

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

        # Construire la réponse
        result = {
            'response': response_text,
            'sources': sources,
        }

        # Ajouter les suggestions de coaching si disponibles
        if coaching_result:
            result['coaching'] = coaching_result

        return result

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
        Déduplique les sources par nom de fichier et agrège les scores.

        Pour chaque document :
        - Calcule un score agrégé (moyenne des chunks ou score de re-ranking)
        - Conserve l'extrait du chunk le plus pertinent
        - Compte le nombre de chunks utilisés par document

        Le score agrégé permet de privilégier les documents qui apparaissent
        plusieurs fois dans le top-k, indiquant une forte pertinence globale.
        """
        sources_by_doc: Dict[str, Dict] = {}

        for chunk in context_chunks:
            doc_name = chunk['source']

            # Utiliser le score de re-ranking si disponible, sinon calculer depuis distance
            if 'rerank_score' in chunk:
                relevance = chunk['rerank_score']
            else:
                relevance = 1.0 - chunk['distance']

            if doc_name not in sources_by_doc:
                sources_by_doc[doc_name] = {
                    'document': doc_name,
                    'excerpt': chunk['content'][:200] + '…',
                    'relevance': relevance,
                    'chunks_count': 1,
                    'total_relevance': relevance,  # Pour calcul de moyenne
                    'best_relevance': relevance,   # Meilleur score individuel
                }
            else:
                existing = sources_by_doc[doc_name]
                existing['chunks_count'] += 1
                existing['total_relevance'] += relevance

                # Garder l'extrait du chunk le plus pertinent
                if relevance > existing['best_relevance']:
                    existing['best_relevance'] = relevance
                    existing['excerpt'] = chunk['content'][:200] + '…'

                # Score agrégé = moyenne pondérée (favorise docs avec plusieurs chunks pertinents)
                # Utilise moyenne * (1 + 0.1 * nombre de chunks) pour récompenser la récurrence
                avg_relevance = existing['total_relevance'] / existing['chunks_count']
                recurrence_bonus = 1.0 + (0.1 * (existing['chunks_count'] - 1))
                existing['relevance'] = avg_relevance * min(recurrence_bonus, 1.5)  # Cap à +50%

        # Nettoyer les champs temporaires et trier par pertinence
        final_sources = []
        for source in sources_by_doc.values():
            final_sources.append({
                'document': source['document'],
                'excerpt': source['excerpt'],
                'relevance': source['relevance'],
                'chunks_count': source['chunks_count']
            })

        return sorted(final_sources, key=lambda s: s['relevance'], reverse=True)
