# Proposition : Portail Django Unifié

**Date** : 2026-02-06
**Objectif** : Landing page commune pour choisir entre noScribe et ChatBot RAG

---

## 🎯 Concept

Créer une **mini-application Django légère** qui sert de portail d'entrée unique :
- URL racine : `https://noscribe.in.ac-paris.fr/`
- Authentification SAML unique et partagée
- Redirection vers l'application choisie avec session préservée
- Interface élégante avec cartes cliquables

---

## 🏗️ Architecture

```
Internet (port 443)
        ↓
   Nginx système
        ↓
        ├──→ /                    → Portail Django (localhost:8000)
        │                            - Landing page
        │                            - Authentification SAML commune
        │                            - Redirection intelligente
        │
        ├──→ /noscribe/           → noScribe (localhost:8001)
        │    /noscribe/static/
        │    /noscribe/media/
        │
        └──→ /chatbot-rag/        → ChatBot RAG (localhost:8002)
             /chatbot-rag/static/
             /chatbot-rag/media/
```

**Ports** :
- Portail : `8000` (nouveau)
- noScribe : `8001` (existant, déplacé sous `/noscribe/`)
- ChatBot RAG : `8002` (existant)

---

## ✨ Fonctionnalités du Portail

### Phase 1 : Fonctionnalités de Base
- ✅ **Landing page élégante** : Deux cartes (noScribe / ChatBot RAG)
- ✅ **Authentification SAML unique** : Une seule connexion pour tout
- ✅ **Informations utilisateur** : Afficher nom/prénom après connexion
- ✅ **Redirection automatique** : Vers l'app choisie avec session
- ✅ **Déconnexion globale** : Logout depuis n'importe quelle app

### Phase 2 : Fonctionnalités Avancées (Optionnel)
- 📊 **Tableau de bord** : Dernières activités sur chaque app
- 🔍 **Recherche unifiée** : Chercher dans les deux apps
- 📈 **Statistiques** : Nombre d'uploads, transcriptions, questions
- 👤 **Profil utilisateur** : Préférences, historique
- 🔔 **Notifications** : Alertes communes

---

## 📁 Structure de l'Application Portail

```
/home/iarag/portal/
├── manage.py
├── compose.yaml                # Configuration Podman
├── Containerfile               # Image Docker
├── requirements.txt            # Django minimal + djangosaml2
├── .env                        # Configuration (SECRET_KEY, SAML)
│
├── portal_config/              # Configuration Django
│   ├── __init__.py
│   ├── settings.py            # Settings + SAML
│   ├── urls.py                # URLs racine
│   └── wsgi.py
│
├── portal/                     # Application principale
│   ├── __init__.py
│   ├── models.py              # User profile (optionnel)
│   ├── views.py               # Landing page, redirections
│   ├── urls.py
│   └── templates/
│       ├── base.html
│       ├── landing.html       # Page de choix
│       └── profile.html       # Profil utilisateur (optionnel)
│
├── static/                     # CSS/JS du portail
│   ├── css/
│   │   └── portal.css
│   └── js/
│       └── portal.js
│
└── saml/                       # Configuration SAML partagée
    ├── sp_certificate.pem
    ├── sp_private_key.pem
    └── attributemaps/
        └── basic.py
```

---

## 💻 Code : Landing Page (views.py)

```python
# portal/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings

def index(request):
    """
    Page d'accueil - Si connecté : landing page, sinon : redirect SAML
    """
    if not request.user.is_authenticated:
        # Redirection vers SAML login
        return redirect('/saml2/login/')

    return render(request, 'portal/landing.html', {
        'user': request.user,
        'apps': [
            {
                'name': 'noScribe',
                'url': '/noscribe/',
                'description': 'Transcription automatique de réunions',
                'icon': '🎙️',
                'color': '#3498db',
            },
            {
                'name': 'ChatBot RAG',
                'url': '/chatbot-rag/',
                'description': 'Assistant documentaire intelligent',
                'icon': '🤖',
                'color': '#e74c3c',
            }
        ]
    })

@login_required
def redirect_to_app(request, app_name):
    """
    Redirection vers une application avec préservation de session.
    """
    app_urls = {
        'noscribe': '/noscribe/',
        'chatbot-rag': '/chatbot-rag/',
    }

    url = app_urls.get(app_name)
    if url:
        return redirect(url)

    return redirect('/')

@login_required
def profile(request):
    """
    Profil utilisateur (optionnel)
    """
    return render(request, 'portal/profile.html', {
        'user': request.user,
    })
```

---

## 🎨 Code : Template Landing Page

```html
<!-- portal/templates/portal/landing.html -->
{% load static %}
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portail IA - Académie de Paris</title>
    <link rel="stylesheet" href="{% static 'css/portal.css' %}">
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <div class="nav-brand">
                <h1>🎓 Portail IA</h1>
            </div>
            <div class="nav-user">
                <span>👤 {{ user.get_full_name|default:user.username }}</span>
                <a href="{% url 'logout' %}" class="btn-logout">Déconnexion</a>
            </div>
        </div>
    </nav>

    <main class="container">
        <section class="welcome">
            <h2>Bienvenue, {{ user.first_name|default:user.username }} !</h2>
            <p>Choisissez l'application que vous souhaitez utiliser :</p>
        </section>

        <section class="apps-grid">
            {% for app in apps %}
            <a href="{{ app.url }}" class="app-card" style="--card-color: {{ app.color }}">
                <div class="app-icon">{{ app.icon }}</div>
                <h3>{{ app.name }}</h3>
                <p>{{ app.description }}</p>
                <div class="app-arrow">→</div>
            </a>
            {% endfor %}
        </section>

        <section class="help">
            <p>
                <strong>Besoin d'aide ?</strong>
                Contactez le support : <a href="mailto:support@ac-paris.fr">support@ac-paris.fr</a>
            </p>
        </section>
    </main>

    <footer>
        <div class="container">
            <p>&copy; 2026 Académie de Paris - Portail IA</p>
        </div>
    </footer>
</body>
</html>
```

---

## 🎨 Code : CSS Moderne

```css
/* static/css/portal.css */
:root {
    --primary: #2c3e50;
    --secondary: #3498db;
    --success: #27ae60;
    --danger: #e74c3c;
    --light: #ecf0f1;
    --dark: #34495e;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    color: var(--dark);
}

.navbar {
    background: white;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    padding: 1rem 0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 2rem;
}

.navbar .container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.nav-brand h1 {
    color: var(--primary);
    font-size: 1.5rem;
}

.nav-user {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.btn-logout {
    padding: 0.5rem 1rem;
    background: var(--danger);
    color: white;
    text-decoration: none;
    border-radius: 5px;
    transition: background 0.3s;
}

.btn-logout:hover {
    background: #c0392b;
}

main {
    padding: 3rem 0;
}

.welcome {
    background: white;
    padding: 2rem;
    border-radius: 10px;
    margin-bottom: 2rem;
    text-align: center;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.welcome h2 {
    color: var(--primary);
    margin-bottom: 0.5rem;
}

.apps-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
    margin-bottom: 2rem;
}

.app-card {
    background: white;
    padding: 2rem;
    border-radius: 15px;
    text-decoration: none;
    color: var(--dark);
    transition: all 0.3s ease;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    border-left: 5px solid var(--card-color);
    position: relative;
    overflow: hidden;
}

.app-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(135deg, var(--card-color) 0%, transparent 100%);
    opacity: 0;
    transition: opacity 0.3s;
}

.app-card:hover::before {
    opacity: 0.1;
}

.app-card:hover {
    transform: translateY(-10px);
    box-shadow: 0 15px 30px rgba(0,0,0,0.2);
}

.app-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
}

.app-card h3 {
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
    color: var(--card-color);
}

.app-card p {
    color: #666;
    margin-bottom: 1rem;
}

.app-arrow {
    position: absolute;
    bottom: 1rem;
    right: 1rem;
    font-size: 2rem;
    color: var(--card-color);
    transition: transform 0.3s;
}

.app-card:hover .app-arrow {
    transform: translateX(10px);
}

.help {
    background: white;
    padding: 1.5rem;
    border-radius: 10px;
    text-align: center;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.help a {
    color: var(--secondary);
    text-decoration: none;
}

footer {
    background: rgba(255,255,255,0.1);
    color: white;
    padding: 2rem 0;
    text-align: center;
    margin-top: 3rem;
}

/* Responsive */
@media (max-width: 768px) {
    .apps-grid {
        grid-template-columns: 1fr;
    }

    .navbar .container {
        flex-direction: column;
        gap: 1rem;
    }
}
```

---

## ⚙️ Configuration SAML Commune

Le portail gère l'authentification SAML pour les deux applications.

### settings.py (Portail)

```python
# portal_config/settings.py

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'djangosaml2',  # Authentification SAML
    'portal',       # App principale
]

# Configuration SAML (identique à noScribe)
SAML_ENABLED = True
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'djangosaml2.backends.Saml2Backend',
]

# URLs de redirection
LOGIN_URL = '/saml2/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Session partagée entre apps (même domaine)
SESSION_COOKIE_NAME = 'portal_sessionid'
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'  # Partagé avec sous-domaines
SESSION_COOKIE_PATH = '/'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

# SAML Configuration (copier depuis noScribe)
# ... [Configuration SAML complète]
```

---

## 🔐 Partage de Session entre Applications

Pour que la session SAML soit partagée :

### 1. Configuration des Cookies de Session

**Portail** (`settings.py`) :
```python
SESSION_COOKIE_NAME = 'portal_sessionid'
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'
SESSION_COOKIE_PATH = '/'
```

**noScribe** (`settings.py`) :
```python
# Utiliser la session du portail
SESSION_COOKIE_NAME = 'portal_sessionid'  # ⚠️ Même nom !
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'
SESSION_COOKIE_PATH = '/noscribe/'
```

**ChatBot RAG** (`settings.py`) :
```python
# Utiliser la session du portail
SESSION_COOKIE_NAME = 'portal_sessionid'  # ⚠️ Même nom !
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'
SESSION_COOKIE_PATH = '/chatbot-rag/'
```

### 2. Backend de Session Partagé

**Option A : Redis partagé** (Recommandé)
```python
# Toutes les apps utilisent le même Redis
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://localhost:6379/0',
    }
}
```

**Option B : Base de données partagée**
```python
# Toutes les apps utilisent la même table de sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
# Connecter à une DB commune (PostgreSQL)
```

---

## 🚀 Avantages de cette Solution

### ✅ Expérience Utilisateur
- **Une seule connexion** : SAML unique pour tout
- **Navigation fluide** : Passage d'une app à l'autre sans re-login
- **Interface moderne** : Design professionnel et responsive
- **Personnalisation** : Affichage du nom de l'utilisateur

### ✅ Technique
- **Architecture propre** : Séparation des responsabilités
- **Scalabilité** : Facile d'ajouter de nouvelles apps
- **Maintenance** : Configuration SAML centralisée
- **Sécurité** : Gestion d'authentification unique

### ✅ Administration
- **Gestion centralisée** : Un seul point d'entrée
- **Logs unifiés** : Traçabilité des connexions
- **Statistiques** : Utilisation de chaque app
- **Support** : Plus simple pour les utilisateurs

---

## 📦 Déploiement

### 1. Créer l'Application Portail

```bash
# Créer le répertoire
mkdir -p /home/iarag/portal
cd /home/iarag/portal

# Créer le projet Django
django-admin startproject portal_config .
python manage.py startapp portal

# Copier la configuration SAML depuis noScribe
cp -r /home/iarag/noScribe_web/saml ./

# Installer les dépendances
pip install django djangosaml2 pysaml2 gunicorn
pip freeze > requirements.txt
```

### 2. Containeriser

```yaml
# compose.yaml
version: '3.8'

services:
  portal:
    build: .
    container_name: portal-web
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./static:/app/staticfiles:ro
    restart: unless-stopped
```

### 3. Configuration Nginx

```nginx
# /etc/nginx/conf.d/noscribe.conf

# Portail à la racine
location / {
    proxy_pass http://localhost:8000;
    # ... [headers]
}

# noScribe déplacé sous /noscribe/
location /noscribe/ {
    proxy_pass http://localhost:8001/;
    # ... [headers]
}

# ChatBot RAG sous /chatbot-rag/
location /chatbot-rag/ {
    proxy_pass http://localhost:8002/;
    # ... [headers]
}
```

---

## 🎯 Plan d'Implémentation

### Phase 1 : Portail Basique (2-3 heures)
1. Créer l'application Django portail
2. Implémenter la landing page
3. Configurer SAML
4. Tester l'authentification

### Phase 2 : Intégration (1-2 heures)
1. Déplacer noScribe sous `/noscribe/`
2. Adapter les configurations
3. Configurer le partage de session
4. Tests d'intégration

### Phase 3 : Tests et Déploiement (1 heure)
1. Tests complets
2. Mise en production
3. Documentation utilisateur

**Total estimé : 4-6 heures**

---

## 🤔 Comparaison avec Option 1 (HTML Statique)

| Critère | HTML Statique | Portail Django |
|---------|--------------|----------------|
| **Complexité** | Simple | Moyenne |
| **Temps mise en place** | 30 min | 4-6h |
| **Maintenance** | Minimale | Moyenne |
| **Fonctionnalités** | Basiques | Riches |
| **Authentification** | Séparée par app | Unique SAML |
| **Évolutivité** | Limitée | Excellente |
| **Personnalisation** | Statique | Dynamique |

---

## 💡 Recommandation

**Si vous avez le temps (4-6h)** : Le portail Django est la **meilleure solution long terme**.

**Si vous voulez du rapide (30min)** : HTML statique suffit pour commencer, migration possible plus tard.

**Mon conseil** : Commencer par HTML statique, puis migrer vers Django si besoin de fonctionnalités avancées.

---

Que préférez-vous ? Portail Django complet ou commencer simple avec HTML statique ?
