"""
Client synchrone pour l'API Albert (DINUM).

- Génération d'embeddings  : BAAI/bge-m3  → vecteurs 1024 dims
- Génération de texte      : chat/completions (Mistral-7B-Instruct)

Porté depuis chatbot/services/albert_client.py — rendu synchrone pour
utilisation directe dans les tâches Celery et les vues Django.
"""
import logging
from typing import List

import httpx
from django.conf import settings

logger = logging.getLogger('rag')

# L'API Albert refuse les requêtes d'embeddings à plus de 64 textes
EMBEDDING_BATCH_SIZE = 64


class AlbertClient:
    """Client HTTP synchrone vers l'API Albert."""

    def __init__(self):
        self.api_url = settings.ALBERT_API_URL
        self.api_key = settings.ALBERT_API_KEY
        self.embedding_model = settings.ALBERT_EMBEDDING_MODEL
        self.chat_model = settings.ALBERT_CHAT_MODEL

        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Génère les embeddings pour une liste de textes.

        Découpe automatiquement en lots de 64 pour respecter la limite
        de l'API Albert.  Retourne des vecteurs de dimension 1024.
        """
        all_embeddings: List[List[float]] = []
        total_batches = (len(texts) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

        logger.info(f"Génération embeddings : {len(texts)} textes en {total_batches} lot(s)")

        with httpx.Client(timeout=120.0) as client:
            for batch_idx in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                batch = texts[batch_idx:batch_idx + EMBEDDING_BATCH_SIZE]
                batch_num = batch_idx // EMBEDDING_BATCH_SIZE + 1

                logger.info(f"Lot {batch_num}/{total_batches} ({len(batch)} textes)")

                response = client.post(
                    f"{self.api_url}/embeddings",
                    headers=self.headers,
                    json={
                        'model': self.embedding_model,
                        'input': batch,
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        f"Erreur API Albert embeddings (lot {batch_num}) : "
                        f"HTTP {response.status_code} — {response.text}"
                    )
                    raise Exception(
                        f"API Albert embeddings : HTTP {response.status_code}"
                    )

                data = response.json()
                all_embeddings.extend(item['embedding'] for item in data['data'])

        logger.info(f"Généré {len(all_embeddings)} embeddings au total")
        return all_embeddings

    # ------------------------------------------------------------------
    # Génération de texte
    # ------------------------------------------------------------------

    def generate_response(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> str:
        """
        Génère une réponse via l'endpoint chat/completions.

        Args:
            messages   : [{"role": "system|user", "content": "…"}]
            temperature: 0.0 (déterministe) → 1.0 (créatif)
            max_tokens : longueur maximale de la réponse

        Returns:
            Texte généré par le modèle.
        """
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.api_url}/chat/completions",
                headers=self.headers,
                json={
                    'model': self.chat_model,
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens,
                },
            )

            if response.status_code != 200:
                logger.error(f"Erreur API Albert chat : {response.text}")
                raise Exception(f"API Albert chat : HTTP {response.status_code}")

            content = response.json()['choices'][0]['message']['content']
            logger.info(f"Réponse générée ({len(content)} caractères)")
            return content
