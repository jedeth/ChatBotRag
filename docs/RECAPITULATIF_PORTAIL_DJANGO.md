# Récapitulatif : Création du Portail Django

**Date** : 2026-02-06
**Statut** : ✅ Complet et prêt au déploiement

---

## 🎉 Ce qui a été créé

Une **application Django complète** servant de portail d'entrée unifié pour noScribe et ChatBot RAG.

### 📂 Emplacement

`/home/iarag/portal/`

### 🏗️ Structure Complète

```
portal/
├── manage.py                    ✅ Script Django
├── compose.yaml                 ✅ Orchestration Podman
├── Containerfile                ✅ Image Docker
├── requirements.txt             ✅ Dépendances Python
├── README.md                    ✅ Documentation complète
├── .env.example                 ✅ Template configuration
├── .gitignore                   ✅ Fichiers à exclure
│
├── portal_config/               ✅ Configuration Django
│   ├── __init__.py
│   ├── settings.py             ✅ Settings + SAML
│   ├── urls.py                 ✅ URLs racine
│   └── wsgi.py                 ✅ WSGI Gunicorn
│
├── portal/                      ✅ Application principale
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py
│   ├── admin.py
│   ├── views.py                ✅ Landing, profile, logout
│   ├── urls.py                 ✅ Routes
│   ├── templates/portal/
│   │   ├── base.html           ✅ Template de base
│   │   ├── landing.html        ✅ Page de choix
│   │   └── profile.html        ✅ Profil utilisateur
│   └── static/css/
│       └── portal.css          ✅ CSS moderne (700+ lignes)
│
├── saml/                        ✅ Configuration SAML
│   ├── README.md               ✅ Instructions SAML
│   └── attributemaps/
│       ├── __init__.py
│       └── basic.py
│
├── docs/
│   └── NGINX_CONFIGURATION.md   ✅ Guide Nginx complet
│
└── logs/                        ✅ Répertoire logs
```

---

## ✨ Fonctionnalités Implémentées

### 🎨 Interface Utilisateur
- ✅ Landing page moderne avec cartes cliquables
- ✅ Design responsive (desktop, tablette, mobile)
- ✅ Animations CSS fluides
- ✅ Gradient violet/bleu élégant
- ✅ Page de profil utilisateur
- ✅ Navigation sticky

### 🔐 Authentification
- ✅ Support SAML complet (djangosaml2)
- ✅ Configuration partageable avec noScribe
- ✅ Sessions Redis partagées
- ✅ Déconnexion globale

### 🚀 Déploiement
- ✅ Conteneurisation Podman/Docker
- ✅ Health check endpoint `/health/`
- ✅ Gunicorn avec 2 workers
- ✅ Whitenoise pour les statiques
- ✅ Logs configurés

### 📊 Architecture
- ✅ Configuration pour sous-chemins
- ✅ Support CSRF/sessions partagées
- ✅ Configuration DNS académie
- ✅ User UID 1001 (iarag)

---

## 📋 Prochaines Étapes de Déploiement

### Étape 1 : Configuration Initiale (5 min)

```bash
cd /home/iarag/portal

# Créer le fichier .env
cp .env.example .env
nano .env
# Configurer :
# - SECRET_KEY (générer une nouvelle)
# - SAML_ENABLED=True
# - REDIS_URL=redis://localhost:6379/0
```

### Étape 2 : Configuration SAML (10 min)

**Option A : Réutiliser la config de noScribe (Recommandé)**
```bash
cd /home/iarag/portal/saml
ln -s /home/iarag/noScribe_web/saml/sp_certificate.pem .
ln -s /home/iarag/noScribe_web/saml/sp_private_key.pem .
ln -s /home/iarag/noScribe_web/saml/idp_metadata.xml .
cp /home/iarag/noScribe_web/saml/attributemaps/basic.py attributemaps/
```

**Option B : Nouveaux certificats**
```bash
cd /home/iarag/portal/saml
openssl req -new -x509 -days 3652 -nodes \
    -out sp_certificate.pem -keyout sp_private_key.pem \
    -subj "/C=FR/ST=IDF/L=Paris/O=Academie-Paris/CN=noscribe.in.ac-paris.fr"
chmod 600 sp_private_key.pem
```

### Étape 3 : Construire et Démarrer (5 min)

```bash
cd /home/iarag/portal

# Construire l'image
podman-compose build

# Démarrer
podman-compose up -d

# Vérifier
podman logs -f portal-web

# Migrations Django
podman exec portal-web python manage.py migrate
```

### Étape 4 : Configuration Nginx (15 min)

**Avec Eric (admin système)** :

1. Sauvegarder la config actuelle :
   ```bash
   sudo cp /etc/nginx/conf.d/noscribe.conf /etc/nginx/conf.d/noscribe.conf.backup
   ```

2. Appliquer la nouvelle configuration :
   - Voir `/home/iarag/portal/docs/NGINX_CONFIGURATION.md`
   - Ou utiliser la config complète fournie

3. Tester et recharger :
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

### Étape 5 : Adapter noScribe et ChatBot RAG (20 min)

**noScribe** (`/home/iarag/noScribe_web/noscribe_portal/settings.py`) :
```python
# Ajouter/modifier :
FORCE_SCRIPT_NAME = '/noscribe'
STATIC_URL = '/noscribe/static/'
MEDIA_URL = '/noscribe/media/'
SESSION_COOKIE_NAME = 'portal_sessionid'
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'
SESSION_COOKIE_PATH = '/noscribe/'
```

**ChatBot RAG** (`/home/iarag/ChatBotRag/ChatBotRag/chatbot_rag/settings.py`) :
```python
# Ajouter/modifier :
FORCE_SCRIPT_NAME = '/chatbot-rag'
STATIC_URL = '/chatbot-rag/static/'
MEDIA_URL = '/chatbot-rag/media/'
SESSION_COOKIE_NAME = 'portal_sessionid'
SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'
SESSION_COOKIE_PATH = '/chatbot-rag/'
```

Puis redémarrer les conteneurs :
```bash
podman restart noscribe-web
podman restart chatbot-web
```

### Étape 6 : Tests (10 min)

```bash
# Test portail
curl -I https://noscribe.in.ac-paris.fr/
curl -I https://noscribe.in.ac-paris.fr/static/css/portal.css

# Test noScribe
curl -I https://noscribe.in.ac-paris.fr/noscribe/

# Test ChatBot RAG
curl -I https://noscribe.in.ac-paris.fr/chatbot-rag/

# Test SAML (dans navigateur)
https://noscribe.in.ac-paris.fr/saml2/login/
```

---

## 🎯 URLs Finales

| Service | URL | Port Backend |
|---------|-----|--------------|
| **Portail** (Landing) | `https://noscribe.in.ac-paris.fr/` | 8000 |
| **noScribe** | `https://noscribe.in.ac-paris.fr/noscribe/` | 8001 |
| **ChatBot RAG** | `https://noscribe.in.ac-paris.fr/chatbot-rag/` | 8002 |
| **SAML** | `https://noscribe.in.ac-paris.fr/saml2/` | 8000 |

---

## 📊 Temps Total Estimé

| Étape | Durée | Responsable |
|-------|-------|-------------|
| Config initiale + SAML | 15 min | Vous |
| Build + démarrage | 5 min | Vous |
| Config Nginx | 15 min | Eric (admin) |
| Adapter apps | 20 min | Vous |
| Tests | 10 min | Vous + Eric |
| **TOTAL** | **65 min** | |

---

## ✅ Checklist de Déploiement

### Avant le déploiement
- [ ] Fichier `.env` créé et configuré
- [ ] Configuration SAML en place
- [ ] Backup de la config Nginx actuelle

### Déploiement
- [ ] Portail construit et démarré
- [ ] Migrations Django appliquées
- [ ] Nginx configuré
- [ ] noScribe adapté (settings.py)
- [ ] ChatBot RAG adapté (settings.py)
- [ ] Tous les conteneurs redémarrés

### Tests
- [ ] Portail accessible (/)
- [ ] noScribe accessible (/noscribe/)
- [ ] ChatBot RAG accessible (/chatbot-rag/)
- [ ] Authentification SAML fonctionne
- [ ] Navigation entre apps préserve la session
- [ ] Statiques chargés correctement
- [ ] Déconnexion globale fonctionne

---

## 💡 Points Clés

### Sessions Partagées
**CRITIQUE** : Les 3 applications doivent utiliser :
- ✅ Même `SESSION_COOKIE_NAME = 'portal_sessionid'`
- ✅ Même `SESSION_COOKIE_DOMAIN = '.in.ac-paris.fr'`
- ✅ Même Redis (`REDIS_URL`)

### Configuration SAML
**RECOMMANDATION** : Réutiliser la config de noScribe (déjà testée et fonctionnelle)

### Nginx
**ATTENTION** : L'ordre des locations est important !
1. Locations spécifiques d'abord (`/noscribe/`, `/chatbot-rag/`)
2. Location `/` en dernier (catch-all)

---

## 📞 Support

### Logs à consulter
```bash
# Portal
podman logs -f portal-web

# Nginx
sudo tail -f /var/log/nginx/portal_ssl_access.log
sudo tail -f /var/log/nginx/portal_ssl_error.log

# noScribe
podman logs -f noscribe-web

# ChatBot RAG
podman logs -f chatbot-web
```

### Commandes utiles
```bash
# Redémarrer tout
podman restart portal-web noscribe-web chatbot-web

# Vérifier health checks
curl http://localhost:8000/health/
curl http://localhost:8001/health/
curl http://localhost:8002/health/

# Vérifier Redis
redis-cli ping
```

---

## 🎨 Aperçu Interface

La landing page affichera :

```
┌─────────────────────────────────────────────────────────┐
│  🎓 Portail IA                    👤 Jean Dupont [Déco] │
│     Académie de Paris                    [Profil]       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│              Bienvenue, Jean !                          │
│       Choisissez votre application :                    │
│                                                         │
│   ┌──────────────────────┐  ┌──────────────────────┐   │
│   │  🎙️ noScribe         │  │  🤖 ChatBot RAG      │   │
│   │                      │  │                      │   │
│   │  Transcription       │  │  Assistant           │   │
│   │  automatique de      │  │  documentaire        │   │
│   │  réunions avec       │  │  intelligent basé    │   │
│   │  génération de CR    │  │  sur vos documents   │   │
│   │                      │  │                      │   │
│   │  ✓ Transcription     │  │  ✓ Upload docs       │   │
│   │  ✓ Génération CR     │  │  ✓ Q&R intelligentes │   │
│   │  ✓ Export Word/PDF   │  │  ✓ Citations sources │   │
│   │                      │  │                      │   │
│   │  [Ouvrir]         →  │  │  [Ouvrir]         →  │   │
│   └──────────────────────┘  └──────────────────────┘   │
│                                                         │
│   ┌─────────────────────────────────────────────────┐  │
│   │  ❓ Besoin d'aide ?                              │  │
│   │  support@ac-paris.fr                            │  │
│   └─────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🎉 Résultat Final

Une architecture propre et professionnelle :

```
Internet (HTTPS 443)
        ↓
   Nginx système
        ↓
        ├─→ /                  → Portail (8000)
        │                        Landing élégante
        │                        Auth SAML unique
        │
        ├─→ /noscribe/         → noScribe (8001)
        │                        Transcription
        │
        └─→ /chatbot-rag/      → ChatBot RAG (8002)
                                 Assistant doc
```

**Avantages** :
- ✅ Expérience utilisateur unifiée
- ✅ Authentification SAML unique
- ✅ Navigation fluide (sessions partagées)
- ✅ Interface moderne et professionnelle
- ✅ Facile à étendre (nouvelles apps)

---

**Prêt à déployer !** 🚀

Contact : support@ac-paris.fr
