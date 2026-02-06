# ==============================================================================
# Configuration SAML pour ChatBot RAG
# ==============================================================================
#
# ⚠️ TEMPLATE À ADAPTER — Ne pas utiliser tel quel
#
# Ce fichier contient la configuration SAML à ajouter dans chatbot_rag/settings.py
# Adaptez les valeurs selon votre environnement et votre IdP.
#
# Référence complète : docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md
# ==============================================================================

import os
import saml2
from pathlib import Path
from saml2.saml import NAMEID_FORMAT_PERSISTENT

# BASE_DIR déjà défini dans settings.py

# ==============================================================================
# 1. URL de base de l'application
# ==============================================================================

# ⚠️ ADAPTER : URL publique de l'application (sans slash final)
SAML_BASE_URL = os.getenv('SAML_BASE_URL', 'https://chatbot-rag.example.com')

# ==============================================================================
# 2. Backends d'authentification (SAML + local)
# ==============================================================================

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # Authentification locale (admin, dev)
    'djangosaml2.backends.Saml2Backend',          # Authentification SAML (production)
)

# ==============================================================================
# 3. Middleware SAML
# ==============================================================================
#
# À ajouter dans MIDDLEWARE après SessionMiddleware :
#
# MIDDLEWARE = [
#     ...
#     'django.contrib.sessions.middleware.SessionMiddleware',
#     'djangosaml2.middleware.SamlSessionMiddleware',  # ← Ajouter cette ligne
#     ...
# ]

# ==============================================================================
# 4. Configuration SAML2 (pysaml2)
# ==============================================================================

SAML_CONFIG = {
    # Identifiant unique du Service Provider
    'entityid': f'{SAML_BASE_URL}/saml2/metadata/',

    'service': {
        'sp': {
            # Nom de l'application (affiché sur l'IdP)
            'name': 'ChatBot RAG - Rectorat de Paris',
            'name_format': NAMEID_FORMAT_PERSISTENT,

            # Endpoints SAML
            'endpoints': {
                # ACS : Assertion Consumer Service (reçoit les assertions SAML)
                'assertion_consumer_service': [
                    (f'{SAML_BASE_URL}/saml2/acs/', saml2.BINDING_HTTP_POST),
                ],
                # SLS : Single Logout Service (déconnexion)
                'single_logout_service': [
                    (f'{SAML_BASE_URL}/saml2/ls/', saml2.BINDING_HTTP_REDIRECT),
                ],
            },

            # ⚠️ Important pour IdP-initiated (si l'utilisateur clique sur l'app depuis le portail IdP)
            'allow_unsolicited': True,

            # Sécurité : exiger la signature des assertions et réponses
            'want_assertions_signed': True,
            'want_response_signed': True,

            # Algorithmes de signature modernes (recommandé)
            'signing_algorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
            'digest_algorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',

            # ⚠️ ADAPTER : Attributs SAML requis (selon votre IdP)
            # Exemples courants :
            #   - mail, givenName, sn (attributs standard)
            #   - ctemail, ctfn, ctln (attributs personnalisés)
            #   - employeeID, department (attributs RH)
            'required_attributes': ['ctemail', 'ctfn', 'ctln'],
            'optional_attributes': [],
        },
    },

    # Métadonnées IdP
    'metadata': {
        # Fichier local (à obtenir de l'admin IdP)
        'local': [str(BASE_DIR / 'saml' / 'idp_metadata.xml')],

        # OU URL distante (si l'IdP expose ses métadonnées publiquement)
        # 'remote': [
        #     {
        #         'url': 'https://idp.example.com/metadata',
        #         'cert': None,  # Ou chemin vers certificat de vérification
        #     }
        # ],
    },

    # Certificats SP (générés avec openssl, voir saml/README.md)
    'key_file': str(BASE_DIR / 'saml' / 'sp_private_key.pem'),
    'cert_file': str(BASE_DIR / 'saml' / 'sp_certificate.pem'),

    # ⚠️ CRUCIAL : Répertoire des attribute maps personnalisés
    # Sans cette directive, pysaml2 rejettera les attributs non-standard
    'attribute_map_dir': str(BASE_DIR / 'saml' / 'attributemaps'),

    # Debug (activer en dev, désactiver en prod)
    'debug': os.getenv('SAML_DEBUG', 'False').lower() == 'true',

    # Binaire xmlsec1 (généralement /usr/bin/xmlsec1)
    'xmlsec_binary': '/usr/bin/xmlsec1',
}

# ==============================================================================
# 5. Mapping attributs SAML → User Django
# ==============================================================================

# ⚠️ ADAPTER : Selon les attributs envoyés par votre IdP
# Format : 'nom_attribut_saml': ('champ_user_django',)

SAML_ATTRIBUTE_MAPPING = {
    # Exemples pour attributs personnalisés
    'ctemail': ('username', 'email',),  # Email va dans username ET email
    'ctfn': ('first_name',),            # Prénom
    'ctln': ('last_name',),             # Nom de famille

    # Exemples pour attributs standard SAML
    # 'mail': ('email',),
    # 'givenName': ('first_name',),
    # 'sn': ('last_name',),

    # Exemples pour attributs RH
    # 'employeeID': ('username',),
    # 'department': ('last_name',),  # Si pas de champ custom
}

# Champs User Django disponibles :
#   - username (obligatoire, unique)
#   - email
#   - first_name
#   - last_name
#   - is_staff (booléen)
#   - is_active (booléen)
#
# Pour des champs personnalisés, créer un modèle User custom Django.

# ==============================================================================
# 6. Options de gestion des utilisateurs
# ==============================================================================

# Créer automatiquement un utilisateur Django s'il n'existe pas
SAML_CREATE_UNKNOWN_USER = True

# Mettre à jour les attributs de l'utilisateur à chaque connexion
# (nom, prénom, email, etc. synchronisés depuis l'IdP)
SAML_ATTRIBUTE_AUTO_UPDATE = True

# Attribut principal pour identifier l'utilisateur
# 'email' ou 'username' selon votre cas d'usage
SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'

# Ne pas utiliser le NameID SAML comme username Django
# (préférer un attribut explicite comme email ou employeeID)
SAML_USE_NAME_ID_AS_USERNAME = False

# ==============================================================================
# 7. Configuration des redirections post-login
# ==============================================================================

# URL de redirection après connexion SAML réussie (optionnel)
# Par défaut : settings.LOGIN_REDIRECT_URL ou '/'
# SAML_LOGIN_REDIRECT = '/chat/'

# URL de redirection après déconnexion SAML (optionnel)
# Par défaut : '/'
# SAML_LOGOUT_REDIRECT = '/goodbye/'

# ==============================================================================
# FIN CONFIGURATION SAML
# ==============================================================================

# Notes importantes :
#
# 1. Ne pas oublier d'ajouter 'djangosaml2' dans INSTALLED_APPS
# 2. Ne pas oublier d'ajouter SamlSessionMiddleware dans MIDDLEWARE
# 3. Générer les certificats SP : voir saml/README.md
# 4. Obtenir idp_metadata.xml de l'admin IdP
# 5. Adapter saml/attributemaps/basic.py selon les attributs de l'IdP
# 6. Ajouter path('saml2/', include('djangosaml2.urls')) dans urls.py
# 7. Reconstruire l'image Docker/Podman après modifications
# 8. Tester avec : curl http://localhost:8000/saml2/metadata/
#
# Documentation complète : docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md
