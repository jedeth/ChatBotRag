# Plan d'Intégration ChatBot RAG avec noScribe

**Date** : 2026-02-06
**Objectif** : Rattacher ChatBot RAG à l'infrastructure noScribe existante
**Proposition** : Eric (admin système)

---

## 🎯 Stratégie d'Intégration

Utiliser le **Nginx système existant** (port 443) qui sert déjà noScribe pour servir également ChatBot RAG sur un sous-chemin.

### Avantages
✅ Pas de configuration réseau supplémentaire (port 443 déjà ouvert)
✅ Partage des certificats SSL existants
✅ Même domaine (`noscribe.in.ac-paris.fr`)
✅ Configuration SAML partageable
✅ Gestion centralisée par Eric

---

## 📊 Architecture Cible

```
Internet (port 443)
        ↓
   Nginx système
   (/etc/nginx/conf.d/noscribe.conf)
        ↓
        ├──→ / (racine)          → noScribe (localhost:8001)
        ├──→ /static/             → /home/iarag/noScribe_web/staticfiles/
        ├──→ /media/              → /home/iarag/noScribe_web/media/
        ├──→ /saml2/              → noScribe SAML (localhost:8001)
        │
        └──→ /chatbot-rag/        → ChatBot RAG (localhost:8002)
             /chatbot-rag/static/ → /home/iarag/ChatBotRag/ChatBotRag/staticfiles/
             /chatbot-rag/media/  → /home/iarag/ChatBotRag/ChatBotRag/media/
```

**URL d'accès** : `https://noscribe.in.ac-paris.fr/chatbot-rag/`

---

## 🔧 Modifications Nécessaires

### 1. Configuration Nginx Système

Ajouter dans `/etc/nginx/conf.d/noscribe.conf` (après les locations existantes) :

```nginx
# ===== CHATBOT RAG =====
# Fichiers statiques ChatBot RAG
location /chatbot-rag/static/ {
    alias /home/iarag/ChatBotRag/ChatBotRag/staticfiles/;
    expires 30d;
    add_header Cache-Control "public, immutable";

    gzip on;
    gzip_vary on;
    gzip_types text/css text/javascript application/javascript application/json;
}

# Fichiers media ChatBot RAG
location /chatbot-rag/media/ {
    alias /home/iarag/ChatBotRag/ChatBotRag/media/;
    expires 7d;

    # Sécurité: empêcher l'exécution de scripts uploadés
    location ~* \.(php|asp|aspx|jsp|cgi)$ {
        deny all;
    }
}

# Application ChatBot RAG
location /chatbot-rag/ {
    # Proxy vers Django/Gunicorn sur port 8002
    proxy_pass http://localhost:8002/;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $server_name;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Script-Name /chatbot-rag;

    # Support HTTP/1.1
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Timeouts pour requêtes RAG (embeddings, génération)
    proxy_connect_timeout 60s;
    proxy_send_timeout 600s;   # 10 minutes
    proxy_read_timeout 600s;   # 10 minutes

    # Buffers
    proxy_buffering on;
    proxy_buffer_size 128k;
    proxy_buffers 8 256k;
    proxy_busy_buffers_size 256k;
}
```

**Commandes pour appliquer** :
```bash
sudo nano /etc/nginx/conf.d/noscribe.conf
# [Ajouter le bloc ci-dessus avant le dernier bloc de sécurité]

# Vérifier la configuration
sudo nginx -t

# Recharger Nginx
sudo systemctl reload nginx
```

---

### 2. Configuration Django ChatBot RAG

Adapter `chatbot_rag/settings.py` pour fonctionner sous un sous-chemin :

```python
# URLs
FORCE_SCRIPT_NAME = '/chatbot-rag'
STATIC_URL = '/chatbot-rag/static/'
MEDIA_URL = '/chatbot-rag/media/'

# Hosts autorisés
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'noscribe.in.ac-paris.fr',
    'ia-raidf1.in.ac-paris.fr',
]

# CSRF - Ajouter le domaine noScribe
CSRF_TRUSTED_ORIGINS = [
    'https://noscribe.in.ac-paris.fr',
    'https://ia-raidf1.in.ac-paris.fr',
    'http://localhost:8002',
    'http://127.0.0.1:8002',
]

# Session cookies - Partager avec noScribe si SAML commun
SESSION_COOKIE_NAME = 'chatbot_rag_sessionid'  # Différent de noScribe
SESSION_COOKIE_PATH = '/chatbot-rag/'
SESSION_COOKIE_SECURE = True  # HTTPS uniquement
SESSION_COOKIE_HTTPONLY = True
```

---

### 3. Ajustements compose.yaml

Le port mapping reste le même (8002:8000), juste s'assurer que le conteneur écoute bien :

```yaml
web:
  # ...
  ports:
    - "8002:8000"   # Accessible sur localhost:8002 pour Nginx système
```

**Aucun changement nécessaire** si déjà configuré ainsi.

---

### 4. Configuration SAML (Optionnel - Phase 2)

Si on veut partager la configuration SAML de noScribe :

**Option A : SAML Commun**
- Utiliser `/saml2/` de noScribe pour les deux applications
- Configurer `SAML_ATTRIBUTE_MAPPING` identique
- Partager le même backend d'authentification

**Option B : SAML Séparé**
- Créer `/chatbot-rag/saml2/` pour ChatBot RAG
- Configuration SAML indépendante
- Metadata SP séparés

**Recommandation** : Option A (SAML commun) pour simplifier l'administration.

---

## 📝 Checklist d'Installation

### Phase 1 : Tests en local
- [ ] Modifier `settings.py` avec `FORCE_SCRIPT_NAME = '/chatbot-rag'`
- [ ] Tester en local : `http://localhost:8002/` doit fonctionner
- [ ] Vérifier que les URLs Django sont correctes
- [ ] Collecter les fichiers statiques : `python manage.py collectstatic`

### Phase 2 : Intégration Nginx
- [ ] Ajouter le bloc `location /chatbot-rag/` dans `/etc/nginx/conf.d/noscribe.conf`
- [ ] Vérifier la configuration : `sudo nginx -t`
- [ ] Recharger Nginx : `sudo systemctl reload nginx`
- [ ] Tester l'accès : `https://noscribe.in.ac-paris.fr/chatbot-rag/`

### Phase 3 : Vérifications
- [ ] Page d'accueil accessible
- [ ] CSS/JS chargés correctement
- [ ] Upload de documents fonctionnel
- [ ] Celery vectorise les documents
- [ ] Questions/Réponses RAG fonctionnelles
- [ ] Logs propres (pas d'erreurs 404, 502)

### Phase 4 : SAML (si souhaité)
- [ ] Décider : SAML commun ou séparé ?
- [ ] Adapter la configuration selon le choix
- [ ] Tester l'authentification SSO
- [ ] Vérifier la création automatique des utilisateurs

---

## 🚀 Commandes de Déploiement

```bash
# 1. Aller dans le répertoire ChatBot RAG
cd /home/iarag/ChatBotRag/ChatBotRag

# 2. Modifier settings.py
nano chatbot_rag/settings.py
# Ajouter FORCE_SCRIPT_NAME = '/chatbot-rag'
# Modifier STATIC_URL, MEDIA_URL, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS

# 3. Collecter les statiques
podman exec chatbot-web python manage.py collectstatic --noinput

# 4. Modifier Nginx (avec sudo via Eric ou vous)
sudo nano /etc/nginx/conf.d/noscribe.conf
# Ajouter le bloc location /chatbot-rag/

# 5. Tester et recharger Nginx
sudo nginx -t
sudo systemctl reload nginx

# 6. Vérifier les logs
sudo tail -f /var/log/nginx/noscribe_ssl_access.log
podman logs -f chatbot-web
```

---

## 🔍 Tests de Validation

### Test 1 : Accès de base
```bash
curl -I https://noscribe.in.ac-paris.fr/chatbot-rag/
# Doit retourner 200 OK ou 302 (redirect login)
```

### Test 2 : Statiques
```bash
curl -I https://noscribe.in.ac-paris.fr/chatbot-rag/static/
# Doit retourner 200 OK
```

### Test 3 : Logs Nginx
```bash
sudo tail -f /var/log/nginx/noscribe_ssl_access.log | grep chatbot-rag
# Observer les requêtes en temps réel
```

### Test 4 : Logs Django
```bash
podman logs -f chatbot-web
# Vérifier qu'il n'y a pas d'erreurs 404 sur les statiques
```

---

## ⚠️ Points d'Attention

### Headers X-Script-Name
Le header `X-Script-Name: /chatbot-rag` est crucial pour que Django génère les bonnes URLs internes.

### Trailing Slash
- **Nginx** : `location /chatbot-rag/` (avec slash)
- **Proxy** : `proxy_pass http://localhost:8002/` (avec slash)
- Cela permet de retirer `/chatbot-rag` du chemin envoyé à Django

### Cookies et Sessions
- Utiliser `SESSION_COOKIE_NAME` différent de noScribe pour éviter les conflits
- `SESSION_COOKIE_PATH = '/chatbot-rag/'` pour isoler les sessions

### Logs
- Nginx système : `/var/log/nginx/noscribe_ssl_access.log`
- Django/Gunicorn : `podman logs chatbot-web`
- Celery : `podman logs chatbot-celery`

---

## 🎯 Résultat Final

**URLs d'accès** :
- noScribe : `https://noscribe.in.ac-paris.fr/`
- ChatBot RAG : `https://noscribe.in.ac-paris.fr/chatbot-rag/`

**Avantages obtenus** :
- ✅ Une seule URL publique (port 443)
- ✅ Un seul certificat SSL
- ✅ Une seule configuration réseau/firewall
- ✅ SAML potentiellement partagé
- ✅ Administration centralisée

---

## 📞 Coordination avec Eric

**Questions à lui poser** :
1. Préférence sur le nom du sous-chemin ? (`/chatbot-rag/`, `/rag/`, `/chatbot/`, autre ?)
2. Accès sudo pour modifier `/etc/nginx/conf.d/noscribe.conf` ?
3. SAML : configuration commune ou séparée ?
4. Besoin d'un environnement de test d'abord ?

**Temps estimé** :
- Configuration : 30 minutes
- Tests : 30 minutes
- **Total : 1 heure**

---

**Prêt à mettre en œuvre** : Oui, dès validation d'Eric sur le nom du sous-chemin.
