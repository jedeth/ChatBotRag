"""
Middleware pour partager l'authentification entre applications
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User


class SharedAuthMiddleware:
    """
    Middleware qui auto-crée les utilisateurs locaux basés sur la session partagée.

    Utilisé par noScribe et ChatBot RAG pour synchroniser les utilisateurs
    créés par le portail via SAML.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Si l'utilisateur est dans la session mais pas authentifié localement
        if request.session.get('_auth_user_id') and not request.user.is_authenticated:
            user_id = request.session.get('_auth_user_id')
            backend = request.session.get('_auth_user_backend')

            # Récupérer les infos utilisateur de la session
            username = request.session.get('_auth_user_username')
            email = request.session.get('_auth_user_email')
            first_name = request.session.get('_auth_user_first_name', '')
            last_name = request.session.get('_auth_user_last_name', '')

            if username:
                User = get_user_model()

                # Créer l'utilisateur s'il n'existe pas
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'email': email or '',
                        'first_name': first_name,
                        'last_name': last_name,
                    }
                )

                # Mettre à jour l'ID de session
                request.session['_auth_user_id'] = user.id

                # Forcer la réauthentification
                from django.contrib.auth import login
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        response = self.get_response(request)
        return response
