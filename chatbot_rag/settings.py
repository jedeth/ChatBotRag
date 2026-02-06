"""
Django settings for chatbot_rag project.
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# ==============================================================================
# Chemins
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# ==============================================================================
# Sécurité
# ==============================================================================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Origines de confiance pour les requêtes CSRF (nécessaire pour Nginx)
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8182',
    'http://localhost:8183',
    'http://localhost:8002',
    'http://127.0.0.1:8182',
    'http://127.0.0.1:8183',
    'http://127.0.0.1:8002',
]

# ==============================================================================
# Applications
# ==============================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_results',
    'rag',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'chatbot_rag.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'chatbot_rag.wsgi.application'

# ==============================================================================
# Base de données - PostgreSQL + pgvector
# ==============================================================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'chatbot_rag'),
        'USER': os.getenv('DB_USER', 'chatbot'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'changeme'),
        'HOST': os.getenv('DB_HOST', 'db'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# ==============================================================================
# Authentification
# ==============================================================================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'chat'
LOGOUT_REDIRECT_URL = 'login'

# ==============================================================================
# Configuration des cookies de session (Partagée avec Portail IA)
# ==============================================================================
SESSION_COOKIE_NAME = 'portal_sessionid'  # ⚠️ Même nom que le portail
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'  # Partagé entre apps
SESSION_COOKIE_PATH = '/chatbot-rag/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG  # True en production (HTTPS)

# SAML — désactivé par défaut, activable via .env pour brancher l'IdP AC-Paris
SAML_ENABLED = os.getenv('SAML_ENABLED', 'False') == 'True'

# ==============================================================================
# Celery
# ==============================================================================
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'Europe/Paris'
CELERY_ENABLE_UTC = True
CELERY_RESULT_EXTENDED = True

# ==============================================================================
# API Albert (DINUM) — embeddings + génération
# ==============================================================================
ALBERT_API_URL = os.getenv('ALBERT_API_URL', '')
ALBERT_API_KEY = os.getenv('ALBERT_API_KEY', '')
ALBERT_EMBEDDING_MODEL = os.getenv('ALBERT_EMBEDDING_MODEL', 'BAAI/bge-m3')
ALBERT_CHAT_MODEL = os.getenv('ALBERT_CHAT_MODEL', 'albert-large')

# ==============================================================================
# Configuration pour sous-chemin /chatbot-rag/ (Portail IA)
# ==============================================================================
FORCE_SCRIPT_NAME = '/chatbot-rag'

# ==============================================================================
# Fichiers — upload et statiques
# ==============================================================================
MEDIA_URL = '/chatbot-rag/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Taille max d'un fichier uploadé (100 Mo par défaut)
MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 104857600))

STATIC_URL = '/chatbot-rag/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
}

# ==============================================================================
# pgvector — dimension des embeddings bge-m3
# ==============================================================================
EMBEDDING_DIMENSIONS = 1024

# ==============================================================================
# Logging
# ==============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'app.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'rag': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
