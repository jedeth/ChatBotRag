# Prochaines Étapes - Portail Django

**Date** : 2026-02-06
**État** : ✅ Portail opérationnel en local

---

## ✅ Réalisé

- [x] Application Django créée et fonctionnelle
- [x] Configuration SAML (liens vers noScribe)
- [x] Conteneur construit et démarré
- [x] Migrations appliquées
- [x] Health check : http://localhost:8000/health/ → `200 OK`
- [x] Redirection SAML fonctionnelle

---

## 🎯 Options pour la Suite

### Option A : Déploiement Complet (Avec Eric)

**Durée estimée** : 30-45 minutes
**Nécessite** : Accès sudo pour Nginx

#### Étapes :

1. **Adapter noScribe** (5 min - Vous)
   ```bash
   # Modifier /home/iarag/noScribe_web/noscribe_portal/settings.py
   FORCE_SCRIPT_NAME = '/noscribe'
   STATIC_URL = '/noscribe/static/'
   MEDIA_URL = '/noscribe/media/'
   SESSION_COOKIE_NAME = 'portal_sessionid'
   SESSION_COOKIE_PATH = '/noscribe/'

   # Redémarrer
   podman restart noscribe-web
   ```

2. **Adapter ChatBot RAG** (5 min - Vous)
   ```bash
   # Modifier /home/iarag/ChatBotRag/ChatBotRag/chatbot_rag/settings.py
   FORCE_SCRIPT_NAME = '/chatbot-rag'
   STATIC_URL = '/chatbot-rag/static/'
   MEDIA_URL = '/chatbot-rag/media/'
   SESSION_COOKIE_NAME = 'portal_sessionid'
   SESSION_COOKIE_PATH = '/chatbot-rag/'

   # Redémarrer
   podman restart chatbot-web
   ```

3. **Configuration Nginx** (15 min - Eric)
   ```bash
   # Sauvegarder la config actuelle
   sudo cp /etc/nginx/conf.d/noscribe.conf /etc/nginx/conf.d/noscribe.conf.backup

   # Appliquer la nouvelle config (voir NGINX_CONFIGURATION.md)
   sudo nano /etc/nginx/conf.d/noscribe.conf

   # Tester et recharger
   sudo nginx -t
   sudo systemctl reload nginx
   ```

4. **Tests** (10 min - Vous + Eric)
   ```bash
   # Test des 3 applications
   curl -I https://noscribe.in.ac-paris.fr/
   curl -I https://noscribe.in.ac-paris.fr/noscribe/
   curl -I https://noscribe.in.ac-paris.fr/chatbot-rag/
   ```

---

### Option B : Test Temporaire (Sans Nginx)

Pour tester le portail **maintenant** sans attendre Eric :

#### 1. Désactiver temporairement SAML

```bash
# Modifier /home/iarag/portal/.env
nano /home/iarag/portal/.env
# Changer : SAML_ENABLED=False

# Redémarrer
podman-compose restart portal
```

#### 2. Créer un utilisateur de test

```bash
podman exec -it portal-web python manage.py createsuperuser
# Username: test
# Email: test@test.fr
# Password: (votre mot de passe)
```

#### 3. Tester dans le navigateur

```
http://localhost:8000/
# Login avec test / password
# Vous verrez la landing page !
```

---

## 📋 Pour Eric (Admin Système)

### Fichier Nginx à Modifier

`/etc/nginx/conf.d/noscribe.conf`

### Configuration Complète

**Voir** : `/home/iarag/portal/docs/NGINX_CONFIGURATION.md`

### Résumé des Changements

1. **Portail à la racine** `/` → `localhost:8000`
2. **noScribe déplacé** sous `/noscribe/` → `localhost:8001`
3. **ChatBot RAG** sous `/chatbot-rag/` → `localhost:8002`

### Commandes

```bash
# Sauvegarde
sudo cp /etc/nginx/conf.d/noscribe.conf /etc/nginx/conf.d/noscribe.conf.backup

# Édition (voir NGINX_CONFIGURATION.md pour le contenu complet)
sudo nano /etc/nginx/conf.d/noscribe.conf

# Test
sudo nginx -t

# Application
sudo systemctl reload nginx

# Vérification
sudo tail -f /var/log/nginx/portal_ssl_access.log
```

---

## 🎨 Aperçu de la Landing Page

Une fois déployé, les utilisateurs verront :

```
┌──────────────────────────────────────────────────────┐
│  🎓 Portail IA               👤 Jean Dupont  [Déco] │
│     Académie de Paris              [Profil]          │
├──────────────────────────────────────────────────────┤
│                                                      │
│           Bienvenue, Jean !                          │
│      Choisissez votre application :                  │
│                                                      │
│  ┌─────────────────┐  ┌─────────────────┐          │
│  │  🎙️ noScribe    │  │  🤖 ChatBot RAG │          │
│  │  Transcription  │  │  Assistant doc  │          │
│  │  [Ouvrir]    →  │  │  [Ouvrir]    →  │          │
│  └─────────────────┘  └─────────────────┘          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 📞 Coordination avec Eric

### Message suggéré

```
Bonjour Eric,

Le portail Django est prêt et fonctionnel en local.

Pouvons-nous planifier 30-45 minutes ensemble pour :
1. Adapter la configuration Nginx (j'ai la config complète)
2. Tester l'intégration des 3 applications

De mon côté, j'ai juste besoin d'adapter les settings.py de
noScribe et ChatBot RAG (5-10 min chacun).

Quand es-tu disponible ?

Merci !
```

---

## 🐛 Si Problèmes

### Portail ne démarre pas

```bash
podman logs -f portal-web
podman restart portal-web
```

### Erreur SAML

```bash
# Vérifier les liens symboliques
ls -la /home/iarag/portal/saml/

# Vérifier la config
podman exec portal-web python manage.py shell
>>> from portal_config import settings
>>> settings.SAML_ENABLED
>>> settings.SAML_CONFIG
```

### Base de données corrompue

```bash
podman exec portal-web rm /app/db/db.sqlite3
podman exec portal-web python manage.py migrate
```

---

## ✅ Checklist Finale

### Avant Déploiement
- [x] Portail construit et démarré
- [x] Health check fonctionne
- [x] SAML configuré
- [ ] Settings.py de noScribe adaptés
- [ ] Settings.py de ChatBot RAG adaptés
- [ ] Configuration Nginx prête

### Avec Eric
- [ ] Nginx configuré
- [ ] Test portail (/)
- [ ] Test noScribe (/noscribe/)
- [ ] Test ChatBot RAG (/chatbot-rag/)
- [ ] Test SAML login
- [ ] Test navigation entre apps
- [ ] Logs propres

---

**Documentation complète** :
- Configuration Nginx : `/home/iarag/portal/docs/NGINX_CONFIGURATION.md`
- Récapitulatif : `/home/iarag/ChatBotRag/ChatBotRag/docs/RECAPITULATIF_PORTAIL_DJANGO.md`

**Prêt à déployer !** 🚀
