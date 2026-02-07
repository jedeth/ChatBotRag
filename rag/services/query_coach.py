"""
Query Coach Adaptatif - Système de coaching conversationnel intelligent.

Détecte automatiquement le niveau de l'utilisateur et propose un coaching
non-intrusif pour améliorer les questions vagues ou imprécises.

Niveaux détectés:
  - Novice: question vague, manque de contexte (ex: "informations sur la paie")
  - Intermédiaire: question structurée mais peut être améliorée
  - Expert: utilise des techniques de prompting avancées → skip coaching

Le coaching s'adapte:
  - Questions de clarification (max 2-3)
  - Suggestions de reformulation
  - Skip automatique pour experts
"""
import logging
import re
from typing import Dict, Optional, List
from dataclasses import dataclass

logger = logging.getLogger('rag')


@dataclass
class QueryAnalysis:
    """Résultat de l'analyse d'une question."""
    level: str  # 'novice', 'intermediate', 'expert'
    score: float  # Score de complexité (0-1)
    needs_coaching: bool
    issues: List[str]  # Problèmes détectés
    suggestions: List[str]  # Suggestions d'amélioration


class QueryCoach:
    """
    Coach conversationnel pour améliorer les questions des utilisateurs.

    Détecte automatiquement le niveau et propose un coaching adaptatif.
    """

    # Patterns de techniques avancées (experts)
    EXPERT_PATTERNS = [
        r'compar(er|aison)',  # Comparaisons explicites
        r'calcul(er|e)',      # Demandes de calcul
        r'différentiel',      # Analyse comparative
        r'si .+ alors',       # Logique conditionnelle
        r'étape par étape',   # Chain-of-thought
        r'exemple.*:',        # Few-shot learning
        r'selon (le|la|les)', # Référence à sources spécifiques
        r'\d+\s*(vs|versus)', # Comparaisons numériques
    ]

    # Mots-clés de questions vagues (novices)
    VAGUE_KEYWORDS = [
        'informations', 'renseignements', 'données',
        'tout', 'quoi', 'comment ça marche',
        'aide', 'besoin', 'je cherche',
    ]

    # Mots-clés de questions structurées (intermédiaires/experts)
    STRUCTURED_KEYWORDS = [
        'quel est', 'quelle est', 'quels sont', 'quelles sont',
        'montant', 'taux', 'pourcentage',
        'conditions', 'critères', 'exigences',
        'procédure', 'démarche', 'étapes',
    ]

    def __init__(self):
        """Initialise le coach."""
        self.expert_regex = re.compile('|'.join(self.EXPERT_PATTERNS), re.IGNORECASE)

    def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyse une question et détermine le niveau de l'utilisateur.

        Args:
            query: Question de l'utilisateur

        Returns:
            QueryAnalysis avec niveau détecté et recommandations
        """
        query_lower = query.lower()
        issues = []
        suggestions = []

        # 1. Détection niveau expert (skip coaching)
        if self._is_expert_query(query):
            return QueryAnalysis(
                level='expert',
                score=0.9,
                needs_coaching=False,
                issues=[],
                suggestions=[]
            )

        # 2. Analyse de la structure
        word_count = len(query.split())
        has_question_mark = '?' in query
        has_structured_keywords = any(kw in query_lower for kw in self.STRUCTURED_KEYWORDS)
        has_vague_keywords = any(kw in query_lower for kw in self.VAGUE_KEYWORDS)

        # Calcul du score de complexité
        complexity_score = 0.0

        # Longueur (questions trop courtes ou trop longues)
        if word_count < 3:
            issues.append('Question très courte')
            suggestions.append('Ajoutez plus de détails sur ce que vous cherchez')
        elif word_count > 50:
            complexity_score += 0.2
        elif word_count >= 10:
            complexity_score += 0.4

        # Structure grammaticale
        if has_question_mark:
            complexity_score += 0.2
        else:
            issues.append('Pas de point d\'interrogation')

        if has_structured_keywords:
            complexity_score += 0.3

        if has_vague_keywords:
            complexity_score -= 0.2
            issues.append('Question vague ou générale')
            suggestions.append('Précisez ce que vous voulez savoir exactement')

        # Présence de contexte spécifique
        has_numbers = bool(re.search(r'\d+', query))
        has_specific_terms = len(re.findall(r'\b[A-Z][a-z]+\b', query)) > 2

        if has_numbers:
            complexity_score += 0.15
        if has_specific_terms:
            complexity_score += 0.15

        # Détection de contexte absent
        generic_starters = ['comment', 'quoi', 'pourquoi']
        if any(query_lower.startswith(starter) for starter in generic_starters):
            if word_count < 5:
                issues.append('Question trop générale')
                suggestions.append('Indiquez le sujet ou document précis')

        # 3. Détermination du niveau
        complexity_score = max(0.0, min(1.0, complexity_score))  # Clamp 0-1

        if complexity_score >= 0.6:
            level = 'intermediate'
            needs_coaching = len(issues) > 0
        else:
            level = 'novice'
            needs_coaching = True
            if not suggestions:
                suggestions.append('Reformulez votre question de manière plus précise')

        return QueryAnalysis(
            level=level,
            score=complexity_score,
            needs_coaching=needs_coaching,
            issues=issues,
            suggestions=suggestions
        )

    def _is_expert_query(self, query: str) -> bool:
        """
        Détecte si la question utilise des techniques avancées.

        Args:
            query: Question à analyser

        Returns:
            True si l'utilisateur est expert
        """
        # Recherche de patterns avancés
        if self.expert_regex.search(query):
            return True

        # Détection de structure complexe (propositions multiples)
        subordinate_clauses = query.count(',') + query.count(';')
        if subordinate_clauses >= 3:
            return True

        # Questions avec plusieurs parties
        if query.count('?') >= 2:
            return True

        return False

    def generate_coaching_message(self, analysis: QueryAnalysis, query: str) -> Optional[Dict]:
        """
        Génère un message de coaching adapté au niveau détecté.

        Args:
            analysis: Résultat de l'analyse
            query: Question originale

        Returns:
            Dict avec message et suggestions, ou None si pas de coaching nécessaire
        """
        if not analysis.needs_coaching:
            return None

        # Message adapté au niveau
        if analysis.level == 'novice':
            intro = "👋 Je peux vous aider à affiner votre question pour de meilleurs résultats."
        else:
            intro = "💡 Quelques précisions pourraient améliorer ma réponse."

        # Construction du message
        message_parts = [intro]

        # Ajouter les suggestions
        if analysis.suggestions:
            message_parts.append("\n**Suggestions :**")
            for i, suggestion in enumerate(analysis.suggestions[:3], 1):  # Max 3
                message_parts.append(f"{i}. {suggestion}")

        # Questions de clarification selon le contexte
        clarification_questions = self._generate_clarification_questions(query, analysis)
        if clarification_questions:
            message_parts.append("\n**Questions de clarification :**")
            for i, question in enumerate(clarification_questions[:2], 1):  # Max 2
                message_parts.append(f"• {question}")

        message_parts.append("\n*Vous pouvez ignorer ce message et continuer directement si vous préférez.*")

        return {
            'message': '\n'.join(message_parts),
            'level': analysis.level,
            'score': analysis.score,
            'suggestions': analysis.suggestions,
            'clarification_questions': clarification_questions
        }

    def _generate_clarification_questions(self, query: str, analysis: QueryAnalysis) -> List[str]:
        """
        Génère des questions de clarification contextuelles.

        Args:
            query: Question originale
            analysis: Analyse de la question

        Returns:
            Liste de questions de clarification (max 2-3)
        """
        questions = []
        query_lower = query.lower()

        # Contexte temporel manquant
        if any(word in query_lower for word in ['salaire', 'paie', 'traitement', 'rémunération']):
            if not any(year in query for year in ['2024', '2025', '2026']):
                questions.append("Pour quelle année ou période ?")

        # Document spécifique
        if 'vague' in [issue.lower() for issue in analysis.issues]:
            questions.append("Dans quel document dois-je chercher ?")

        # Type d'information
        if any(word in query_lower for word in ['informations', 'données', 'renseignements']):
            questions.append("Quel type d'information exactement ? (montant, conditions, procédure...)")

        # Comparaison implicite
        if any(word in query_lower for word in ['différence', 'mieux', 'plus']):
            questions.append("Entre quoi et quoi souhaitez-vous comparer ?")

        return questions[:3]  # Max 3 questions

    def should_skip_coaching(self, query: str, user_history: Optional[Dict] = None) -> bool:
        """
        Détermine si le coaching doit être skippé.

        Args:
            query: Question actuelle
            user_history: Historique utilisateur (optionnel)

        Returns:
            True si le coaching doit être skippé
        """
        analysis = self.analyze_query(query)

        # Skip pour experts
        if analysis.level == 'expert':
            return True

        # Skip si question déjà bonne
        if not analysis.needs_coaching:
            return True

        # Skip si utilisateur a déjà été coaché récemment (à implémenter avec user_history)
        if user_history and user_history.get('coaching_count', 0) >= 3:
            return True

        return False
