# Message pour Eric - Configuration Nginx Portail IA

**Date** : 2026-02-06
**Durée estimée** : 15-20 minutes

---

Bonjour Eric,

Le portail Django est prêt et toutes les applications sont configurées pour l'intégration.

## ✅ Ce qui est déjà fait de mon côté

- ✅ Portail Django opérationnel (port 8000)
- ✅ noScribe adapté pour `/noscribe/` (port 8001)
- ✅ ChatBot RAG adapté pour `/chatbot-rag/` (port 8002)
- ✅ Tous les conteneurs redémarrés et fonctionnels
- ✅ Configuration SAML partagée
- ✅ Sessions Redis partagées

## 🎯 Ce qu'il faut faire ensemble

### 1. Backup de la configuration actuelle (1 min)

```bash
sudo cp /etc/nginx/conf.d/noscribe.conf /etc/nginx/conf.d/noscribe.conf.backup.$(date +%Y%m%d)
```

### 2. Appliquer la nouvelle configuration Nginx (10 min)

**Fichier** : `/etc/nginx/conf.d/noscribe.conf`

**Changements principaux** :
- Portail IA à la racine `/` → `http://localhost:8000`
- noScribe déplacé sous `/noscribe/` → `http://localhost:8001`
- ChatBot RAG sous `/chatbot-rag/` → `http://localhost:8002`

**Configuration complète** : `/home/iarag/portal/docs/NGINX_CONFIGURATION.md`

**Copie rapide** : Je t'ai préparé la config complète dans le fichier ci-dessus. Tu peux :
- Soit copier-coller toute la config
- Soit juste ajouter les nouveaux blocs (portail et chatbot-rag)

### 3. Tester et recharger (5 min)

```bash
# Tester la syntaxe
sudo nginx -t

# Si OK, recharger
sudo systemctl reload nginx

# Vérifier les logs
sudo tail -f /var/log/nginx/portal_ssl_access.log
```

### 4. Tests de validation (5 min)

```bash
# Test 1 : Portail
curl -I https://noscribe.in.ac-paris.fr/
# Doit retourner 302 (redirect SAML) ou 200

# Test 2 : noScribe
curl -I https://noscribe.in.ac-paris.fr/noscribe/
# Doit retourner 302 ou 200

# Test 3 : ChatBot RAG
curl -I https://noscribe.in.ac-paris.fr/chatbot-rag/
# Doit retourner 302 ou 200

# Test 4 : Statiques
curl -I https://noscribe.in.ac-paris.fr/static/css/portal.css
# Doit retourner 200
```

## 📁 Fichiers de référence

- **Config Nginx complète** : `/home/iarag/portal/docs/NGINX_CONFIGURATION.md`
- **Guide complet** : `/home/iarag/ChatBotRag/ChatBotRag/docs/PROCHAINES_ETAPES_PORTAIL.md`

## 🎨 Résultat attendu

Une fois terminé :
```
https://noscribe.in.ac-paris.fr/
    ├─→ /              → 🎓 Landing page (choix d'app)
    ├─→ /noscribe/     → 🎙️ Transcription
    └─→ /chatbot-rag/  → 🤖 Assistant doc
```

## ⚠️ Points d'attention

1. **Ordre des locations** : Les locations spécifiques (`/noscribe/`, `/chatbot-rag/`) doivent être AVANT la location `/`

2. **Trailing slash** : Important dans `proxy_pass http://localhost:8001/` (avec slash final)

3. **Headers X-Script-Name** : Pour ChatBot RAG, ajouter `proxy_set_header X-Script-Name /chatbot-rag;`

## 🐛 Si problèmes

### Erreur 502 Bad Gateway

```bash
# Vérifier que les apps tournent
curl http://localhost:8000/health/  # Portal
curl http://localhost:8001/health/  # noScribe
curl http://localhost:8002/health/  # ChatBot RAG

# Redémarrer si besoin
podman restart portal-web noscribe-web chatbot-web
```

### Statiques 404

```bash
# Vérifier les chemins
ls -la /home/iarag/portal/staticfiles/
ls -la /home/iarag/noScribe_web/staticfiles/
ls -la /home/iarag/ChatBotRag/ChatBotRag/staticfiles/
```

### Logs Nginx

```bash
# Logs d'accès
sudo tail -f /var/log/nginx/portal_ssl_access.log

# Logs d'erreurs
sudo tail -f /var/log/nginx/portal_ssl_error.log
```

---

**Merci Eric !** 🙏

N'hésite pas si tu as des questions ou besoin de clarifications.

Je suis dispo pour tester ensemble une fois que tu as appliqué la config.

---

**PS** : Si tu préfères, on peut faire ça en visio/screenshare pour aller plus vite. À toi de voir !
