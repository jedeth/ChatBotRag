#!/usr/bin/env python
"""Script de test pour le Query Coach"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_rag.settings')
django.setup()

from rag.services.query_coach import QueryCoach

def test_query_coach():
    coach = QueryCoach()

    # Test cases
    test_queries = [
        # Novice
        ("informations sur la paie", "novice"),
        ("aide", "novice"),
        ("comment ça marche", "novice"),

        # Intermédiaire
        ("Quel est le montant de la prime attractivité pour un PE ?", "intermediate"),
        ("Quelles sont les conditions pour bénéficier de la prime ?", "intermediate"),

        # Expert
        ("Comparer échelon 6 vs 7 PE avec prime attractivité, calculer différentiel net", "expert"),
        ("Si un enseignant est échelon 5 avec 10 ans d'ancienneté, alors quel est son traitement brut mensuel ?", "expert"),
        ("Étape par étape : 1) extraire le montant de base, 2) ajouter les primes, 3) calculer le net", "expert"),
    ]

    print("=" * 80)
    print("🧪 TEST QUERY COACH")
    print("=" * 80)

    for query, expected_level in test_queries:
        print(f"\n📝 Question : {query}")
        print(f"   Niveau attendu : {expected_level}")

        analysis = coach.analyze_query(query)

        print(f"   ✅ Niveau détecté : {analysis.level} (score: {analysis.score:.2f})")
        print(f"   Coaching nécessaire : {'Oui' if analysis.needs_coaching else 'Non'}")

        if analysis.issues:
            print(f"   ⚠️  Problèmes : {', '.join(analysis.issues)}")

        if analysis.suggestions:
            print(f"   💡 Suggestions :")
            for i, suggestion in enumerate(analysis.suggestions, 1):
                print(f"      {i}. {suggestion}")

        # Test message de coaching
        if analysis.needs_coaching:
            coaching_msg = coach.generate_coaching_message(analysis, query)
            if coaching_msg:
                print(f"\n   📨 Message de coaching :")
                print(f"   {coaching_msg['message'][:200]}...")

        # Vérifier niveau attendu
        if analysis.level != expected_level:
            print(f"   ❌ ERREUR : Attendu '{expected_level}', obtenu '{analysis.level}'")
        else:
            print(f"   ✓ Niveau correct")

        print("-" * 80)

if __name__ == '__main__':
    test_query_coach()
