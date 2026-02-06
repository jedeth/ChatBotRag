# Guide d'Administration - Intégration SAML avec Attributs Personnalisés
## Django + pysaml2 + djangosaml2 + Déploiement Conteneurisé

**Version** : 1.0
**Date** : 2026-01-28
**Auteur** : Documentation basée sur l'expérience noScribe Portal
**Public cible** : Administrateurs système, Développeurs DevOps, Architectes

---

## 📋 Table des matières

1. [Introduction et cas d'usage](#introduction)
2. [Pré-requis techniques](#prerequis)
3. [Architecture et principes](#architecture)
4. [Guide d'implémentation étape par étape](#implementation)
5. [Configuration des attributs personnalisés](#attributs-personnalises)
6. [Déploiement conteneurisé](#deploiement)
7. [Tests et validation](#tests)
8. [Troubleshooting](#troubleshooting)
9. [Checklist complète](#checklist)
10. [Annexes et exemples](#annexes)

---

<a name="introduction"></a>
## 1. Introduction et cas d'usage

### Objectif de ce guide

Ce guide détaille l'intégration complète de l'authentification SAML dans une application Django, avec un **focus particulier sur la gestion des attributs SAML personnalisés** (non-standard).

### Cas d'usage principal

**Problème typique** : Votre Identity Provider (IdP) utilise des attributs SAML personnalisés (comme `ctemail`, `ctfn`, `employeeID`, etc.) qui ne font pas partie des attributs SAML standard. La bibliothèque `pysaml2` rejette ces attributs avec l'erreur :

```log
[ERROR] Unknown attribute name: <ns0:Attribute Name="ctemail" ...>
```

**Solution documentée** : Création d'attribute maps personnalisés pour `pysaml2`.

### Stack technique couverte

- **Framework backend** : Django 4.x+
- **Bibliothèque SAML** : `pysaml2` 7.x+ et `djangosaml2` 1.5+
- **Déploiement** : Podman/Docker avec `podman-compose`/`docker-compose`
- **Serveur web** : Gunicorn + Nginx
- **Python** : 3.9+

### Ce que vous allez apprendre

✅ Configurer SAML dans Django (SP - Service Provider)
✅ Gérer les attributs SAML personnalisés avec attribute maps
✅ Mapper les attributs SAML vers le modèle User Django
✅ Déployer en conteneurs (Podman/Docker)
✅ Tester et valider l'intégration
✅ Diagnostiquer et résoudre les problèmes courants

---

<a name="prerequis"></a>
## 2. Pré-requis techniques

### 2.1 Informations à obtenir de l'IdP

Avant de commencer, contactez l'administrateur de l'IdP pour obtenir :

| Information | Description | Exemple |
|------------|-------------|---------|
| **Métadonnées IdP** | Fichier XML ou URL | `idp_metadata.xml` |
| **Liste des attributs** | Noms et NameFormat | `ctemail` (NameFormat=basic) |
| **Valeurs de test** | Échantillons de données | `email@example.com` |
| **Mode d'initiation** | SP-initiated ou IdP-initiated | IdP-initiated |
| **Certificat IdP** | Certificat public | `idp_certificate.pem` |

### 2.2 Logiciels requis

**Serveur** :
```bash
# Ubuntu/Debian
apt-get install xmlsec1 libxml2-dev libxmlsec1-dev libxmlsec1-openssl

# RHEL/CentOS
yum install xmlsec1 xmlsec1-openssl libxml2-devel xmlsec1-devel
```

**Python** :
```bash
pip install pysaml2>=7.0.0 djangosaml2>=1.5.0 Django>=4.0
```

### 2.3 Connaissances recommandées

- Bases de SAML 2.0 (assertion, NameID, AttributeStatement)
- Administration Django (modèle User, authentification)
- Docker/Podman (si déploiement conteneurisé)
- XML et XPath (pour déboguer les assertions SAML)

---

<a name="architecture"></a>
## 3. Architecture et principes

### 3.1 Flux SAML simplifié

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│              │    1    │              │    4    │              │
│   Navigateur │────────▶│     IdP      │────────▶│      SP      │
│              │         │  (fournit    │         │  (Django)    │
│              │◀────────│   identité)  │◀────────│              │
└──────────────┘    6    └──────────────┘    5    └──────────────┘
                              │    ▲
                           2  │    │ 3
                              ▼    │
                         ┌──────────────┐
                         │ Authentifi-  │
                         │   cation     │
                         └──────────────┘
```

1. L'utilisateur clique sur "Se connecter via SAML"
2. Redirection vers l'IdP pour authentification
3. Authentification de l'utilisateur (login/password, certificat, etc.)
4. L'IdP génère une **assertion SAML** avec les attributs
5. Le SP (Django) valide l'assertion et extrait les attributs
6. Création/mise à jour de l'utilisateur Django et connexion

### 3.2 Chaîne de traitement des attributs

**Point crucial** : Comprendre comment les attributs SAML sont transformés en attributs User Django.

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. ASSERTION SAML (XML de l'IdP)                                   │
├─────────────────────────────────────────────────────────────────────┤
│  <saml:Attribute Name="ctemail"                                     │
│                  NameFormat="urn:...:attrname-format:basic">        │
│      <saml:AttributeValue>user@example.com</saml:AttributeValue>    │
│  </saml:Attribute>                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│  2. ATTRIBUTE MAP (saml/attributemaps/basic.py)                     │
├─────────────────────────────────────────────────────────────────────┤
│  MAP = {                                                            │
│      "identifier": "urn:...:attrname-format:basic",                 │
│      "fro": {'ctemail': 'ctemail'},  # Nom SAML → Nom interne      │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│  3. SAML_ATTRIBUTE_MAPPING (settings.py)                            │
├─────────────────────────────────────────────────────────────────────┤
│  SAML_ATTRIBUTE_MAPPING = {                                         │
│      'ctemail': ('email',),  # Nom interne → Champ User Django     │
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│  4. MODÈLE USER DJANGO                                              │
├─────────────────────────────────────────────────────────────────────┤
│  user.email = "user@example.com"  ✅                                │
└─────────────────────────────────────────────────────────────────────┘
```

**Étape critique** : L'**Attribute Map** (étape 2) est souvent oubliée et cause l'erreur "Unknown attribute name". C'est le cœur de ce guide.

---

<a name="implementation"></a>
## 4. Guide d'implémentation étape par étape

### Étape 1 : Installation des dépendances

**Fichier : `requirements.txt`**

```txt
Django>=4.2.0
pysaml2>=7.5.0
djangosaml2>=1.11.0
gunicorn>=21.0.0  # Si déploiement production
```

```bash
pip install -r requirements.txt
```

### Étape 2 : Création de la structure SAML

```bash
# À la racine du projet Django
mkdir -p saml/attributemaps
touch saml/attributemaps/__init__.py
```

### Étape 3 : Génération des certificats SP

```bash
cd saml/

# Génération de la clé privée (2048 bits minimum)
openssl req -new -x509 -days 3652 -nodes -out sp_certificate.pem \
    -keyout sp_private_key.pem \
    -subj "/C=FR/ST=IDF/L=Paris/O=MonOrganisation/CN=monapp.example.com"

# Vérification
openssl x509 -in sp_certificate.pem -text -noout
```

**Sécurité** :
```bash
chmod 600 sp_private_key.pem
chmod 644 sp_certificate.pem
```

### Étape 4 : Obtention des métadonnées IdP

Demandez le fichier `idp_metadata.xml` à l'administrateur IdP, ou téléchargez-le :

```bash
curl -o saml/idp_metadata.xml https://idp.example.com/metadata
```

### Étape 5 : Configuration Django (settings.py)

**Ajout dans `INSTALLED_APPS`** :

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    # ... autres apps ...
    'djangosaml2',  # ⚠️ Important : placer après django.contrib.auth
]
```

**Ajout du middleware SAML** :

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # ... autres middlewares ...
    'djangosaml2.middleware.SamlSessionMiddleware',  # Après SessionMiddleware
]
```

**Configuration des backends d'authentification** :

```python
AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # Authentification locale
    'djangosaml2.backends.Saml2Backend',          # Authentification SAML
)
```

**Configuration SAML** :

```python
import saml2
from saml2.saml import NAMEID_FORMAT_PERSISTENT

# URL de base de l'application (à adapter)
SAML_BASE_URL = os.getenv('SAML_BASE_URL', 'https://monapp.example.com')

SAML_CONFIG = {
    # Identifiant unique du Service Provider
    'entityid': f'{SAML_BASE_URL}/saml2/metadata/',

    'service': {
        'sp': {
            'name': 'Mon Application',
            'name_format': NAMEID_FORMAT_PERSISTENT,

            # Endpoints SAML
            'endpoints': {
                # ACS : reçoit les assertions SAML
                'assertion_consumer_service': [
                    (f'{SAML_BASE_URL}/saml2/acs/', saml2.BINDING_HTTP_POST),
                ],
                # SLS : déconnexion
                'single_logout_service': [
                    (f'{SAML_BASE_URL}/saml2/ls/', saml2.BINDING_HTTP_REDIRECT),
                ],
            },

            # ⚠️ Important pour IdP-initiated
            'allow_unsolicited': True,

            # Sécurité (recommandé)
            'want_assertions_signed': True,
            'want_response_signed': True,

            # Algorithmes de signature modernes
            'signing_algorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
            'digest_algorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',

            # ⚠️ ATTRIBUTS REQUIS (à adapter selon votre IdP)
            'required_attributes': ['ctemail', 'ctfn', 'ctln'],
            'optional_attributes': [],
        },
    },

    # Métadonnées IdP
    'metadata': {
        'local': [str(BASE_DIR / 'saml' / 'idp_metadata.xml')],
    },

    # Certificats SP
    'key_file': str(BASE_DIR / 'saml' / 'sp_private_key.pem'),
    'cert_file': str(BASE_DIR / 'saml' / 'sp_certificate.pem'),

    # ⚠️ CRUCIAL : Répertoire des attribute maps personnalisés
    'attribute_map_dir': str(BASE_DIR / 'saml' / 'attributemaps'),

    # Debug (à désactiver en production)
    'debug': True,
    'xmlsec_binary': '/usr/bin/xmlsec1',
}

# Mapping attributs SAML → User Django (à adapter)
SAML_ATTRIBUTE_MAPPING = {
    'ctemail': ('username', 'email',),  # Multiple mapping possible
    'ctfn': ('first_name',),
    'ctln': ('last_name',),
}

# Créer automatiquement les utilisateurs
SAML_CREATE_UNKNOWN_USER = True

# Mettre à jour les attributs à chaque connexion
SAML_ATTRIBUTE_AUTO_UPDATE = True

# Attribut principal pour identifier l'utilisateur
SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'  # ou 'username'

# Ne pas utiliser le NameID comme username
SAML_USE_NAME_ID_AS_USERNAME = False
```

### Étape 6 : URLs Django (urls.py)

**Fichier : `monprojet/urls.py`**

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('saml2/', include('djangosaml2.urls')),  # Routes SAML
    # ... autres URLs ...
]
```

**URLs SAML disponibles** :
- `/saml2/login/` : Initier la connexion SAML (SP-initiated)
- `/saml2/acs/` : Assertion Consumer Service (endpoint de callback)
- `/saml2/logout/` : Déconnexion SAML
- `/saml2/ls/` : Logout Service (callback de déconnexion)
- `/saml2/metadata/` : Métadonnées SP (à fournir à l'IdP)

---

<a name="attributs-personnalises"></a>
## 5. Configuration des attributs personnalisés

### 5.1 Pourquoi les attribute maps sont nécessaires

**Problème** : `pysaml2` ne connaît que les attributs SAML **standard** définis par OASIS (comme `eduPersonPrincipalName`, `mail`, `givenName`, `sn`, etc.).

Si votre IdP utilise des attributs **personnalisés** (comme `ctemail`, `employeeID`, `department`, etc.), `pysaml2` les ignore et loge :

```log
[ERROR] Unknown attribute name: <ns0:Attribute Name="ctemail" ...>
```

**Solution** : Créer un fichier de mapping qui **déclare** ces attributs à `pysaml2`.

### 5.2 Déterminer le NameFormat de vos attributs

Demandez à l'administrateur IdP le NameFormat utilisé, ou inspectez une assertion SAML de test :

```xml
<saml:Attribute Name="ctemail"
                NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:basic"
                FriendlyName="Email">
    <saml:AttributeValue>user@example.com</saml:AttributeValue>
</saml:Attribute>
```

**NameFormats courants** :
- `urn:oasis:names:tc:SAML:2.0:attrname-format:basic` → **basic**
- `urn:oasis:names:tc:SAML:2.0:attrname-format:uri` → **uri**
- `urn:oasis:names:tc:SAML:2.0:attrname-format:unspecified` → **unspecified**

### 5.3 Création de l'attribute map personnalisé

**Fichier : `saml/attributemaps/basic.py`** (ou `uri.py`, selon votre NameFormat)

```python
# -*- coding: utf-8 -*-
"""
Attribute map pour attributs SAML personnalisés
NameFormat: urn:oasis:names:tc:SAML:2.0:attrname-format:basic
"""

MAP = {
    # Identifiant du format (doit correspondre au NameFormat de l'IdP)
    "identifier": "urn:oasis:names:tc:SAML:2.0:attrname-format:basic",

    # Mapping FROM SAML (assertion XML) vers nom interne pysaml2
    "fro": {
        'ctemail': 'ctemail',      # Email personnalisé
        'ctfn': 'ctfn',            # First Name personnalisé
        'ctln': 'ctln',            # Last Name personnalisé
        'employeeID': 'employeeID',  # Exemple d'autre attribut
        'department': 'department',  # Exemple d'autre attribut
    },

    # Mapping TO SAML (nom interne vers assertion XML)
    # Utilisé si le SP génère des requêtes SAML
    "to": {
        'ctemail': 'ctemail',
        'ctfn': 'ctfn',
        'ctln': 'ctln',
        'employeeID': 'employeeID',
        'department': 'department',
    }
}
```

**Fichier : `saml/attributemaps/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""
Attribute maps personnalisés pour pysaml2
"""
```

**⚠️ Points importants** :
1. Le nom du fichier doit correspondre au NameFormat : `basic.py`, `uri.py`, etc.
2. L'`identifier` dans `MAP` **doit correspondre exactement** au NameFormat de l'IdP
3. Les dictionnaires `fro` et `to` peuvent avoir les mêmes valeurs pour un mapping 1:1

### 5.4 Exemple pour NameFormat URI

Si votre IdP utilise `NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"` :

**Fichier : `saml/attributemaps/uri.py`**

```python
MAP = {
    "identifier": "urn:oasis:names:tc:SAML:2.0:attrname-format:uri",

    "fro": {
        'http://schemas.example.com/identity/claims/emailaddress': 'email',
        'http://schemas.example.com/identity/claims/givenname': 'first_name',
        'http://schemas.example.com/identity/claims/surname': 'last_name',
    },

    "to": {
        'email': 'http://schemas.example.com/identity/claims/emailaddress',
        'first_name': 'http://schemas.example.com/identity/claims/givenname',
        'last_name': 'http://schemas.example.com/identity/claims/surname',
    }
}
```

### 5.5 Mapping vers le modèle User Django

Une fois les attributs reconnus par `pysaml2` (grâce à l'attribute map), mappez-les vers les champs Django dans `settings.py` :

```python
SAML_ATTRIBUTE_MAPPING = {
    # Format : 'nom_interne_pysaml2': ('champ_user_django',)

    'ctemail': ('email',),           # Simple mapping
    'ctfn': ('first_name',),
    'ctln': ('last_name',),
    'employeeID': ('username',),     # Mapping vers username

    # ⚠️ Attention : Multiple mapping possible mais délicat
    # 'ctemail': ('username', 'email',),  # email va dans username ET email
}
```

**Champs User Django standard disponibles** :
- `username` (obligatoire, unique)
- `email`
- `first_name`
- `last_name`
- `is_staff` (booléen)
- `is_active` (booléen)

**Pour des champs personnalisés** : Créez un modèle User custom Django.

---

<a name="deploiement"></a>
## 6. Déploiement conteneurisé

### 6.1 Dockerfile / Containerfile

**Fichier : `Containerfile`**

```dockerfile
FROM python:3.11-slim

# Dépendances système pour SAML
RUN apt-get update && apt-get install -y \
    xmlsec1 \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code de l'application
COPY . .

# ⚠️ IMPORTANT : Vérifier que saml/attributemaps/ est copié
RUN ls -la /app/saml/attributemaps/ || echo "ATTENTION: attributemaps manquant!"

# Utilisateur non-root
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Collecte des fichiers statiques
RUN python manage.py collectstatic --noinput --clear

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "monprojet.wsgi:application"]
```

### 6.2 docker-compose.yml / compose.yaml

```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: Containerfile
    container_name: monapp-web
    restart: unless-stopped

    ports:
      - "8001:8000"

    env_file:
      - .env

    environment:
      SAML_BASE_URL: https://monapp.example.com

    volumes:
      # ⚠️ Ne pas monter saml/ en volume si vous avez des secrets
      # Laisser les certificats dans l'image
      - ./media:/app/media:U
      - ./logs:/app/logs:U

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    container_name: monapp-nginx
    restart: unless-stopped

    ports:
      - "8080:80"
      - "8443:443"

    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./staticfiles:/app/staticfiles:ro
      - ./ssl:/etc/nginx/ssl:ro  # Certificats HTTPS

    depends_on:
      web:
        condition: service_healthy
```

### 6.3 Build et déploiement

```bash
# Build de l'image (sans cache pour forcer la copie des nouveaux fichiers)
podman-compose build --no-cache web

# Vérification que les attributemaps sont bien présents
podman-compose run --rm web ls -la /app/saml/attributemaps/
# Doit afficher : basic.py, __init__.py

# Démarrage
podman-compose up -d

# Vérification des logs
podman-compose logs -f web
```

### 6.4 ⚠️ Erreur fréquente : Attributemaps manquants

**Symptôme** : Après rebuild, l'erreur "Unknown attribute name" réapparaît.

**Cause** : Les fichiers `saml/attributemaps/*.py` n'ont pas été copiés dans l'image.

**Solution** :

1. Vérifiez que `.dockerignore` / `.containerignore` n'exclut pas `saml/` :
   ```bash
   cat .dockerignore | grep -i saml
   # Si présent, commentez ou supprimez la ligne
   ```

2. Forcez la reconstruction sans cache :
   ```bash
   podman-compose build --no-cache web
   ```

3. Vérifiez la présence des fichiers dans le conteneur :
   ```bash
   podman exec monapp-web ls -la /app/saml/attributemaps/
   ```

---

<a name="tests"></a>
## 7. Tests et validation

### 7.1 Checklist pré-test

Avant de tester avec l'IdP, vérifiez :

```bash
# 1. Métadonnées SP accessibles
curl https://monapp.example.com/saml2/metadata/

# 2. Format XML valide
curl https://monapp.example.com/saml2/metadata/ | xmllint --format -

# 3. Vérification de la configuration SAML dans Django
python manage.py shell
>>> from django.conf import settings
>>> print(settings.SAML_CONFIG['attribute_map_dir'])
/app/saml/attributemaps

# 4. Vérification des attribute maps
>>> import os
>>> os.listdir(settings.SAML_CONFIG['attribute_map_dir'])
['__init__.py', 'basic.py']

# 5. Vérification du mapping d'attributs
>>> print(settings.SAML_ATTRIBUTE_MAPPING)
{'ctemail': ('email',), 'ctfn': ('first_name',), 'ctln': ('last_name',)}
```

### 7.2 Test d'authentification SAML

**Scénario 1 : SP-initiated (initié par le Service Provider)**

1. Accédez à : `https://monapp.example.com/saml2/login/`
2. Vous êtes redirigé vers l'IdP pour authentification
3. Authentifiez-vous sur l'IdP
4. Vous êtes redirigé vers `/saml2/acs/` puis vers l'application

**Scénario 2 : IdP-initiated (initié par l'Identity Provider)**

1. Connectez-vous au portail de l'IdP
2. Cliquez sur l'icône de votre application
3. L'IdP envoie une assertion SAML vers `/saml2/acs/`
4. Vous êtes connecté à l'application

### 7.3 Vérification des logs

**Logs Django (avec DEBUG=True)** :

```bash
# Logs de réception d'assertion SAML
tail -f logs/django.log | grep -i saml
```

**Log attendu (succès)** :
```log
[INFO] djangosaml2: Attributs SAML reçus: {'ctemail': ['user@example.com'], 'ctfn': ['Jean'], 'ctln': ['Dupont']}
[INFO] djangosaml2: User 'user@example.com' created successfully
[INFO] djangosaml2: User authenticated via SAML
```

**Log problématique (attributs non reconnus)** :
```log
[ERROR] saml2.attribute_converter: Unknown attribute name: <Attribute Name="ctemail" ...>
[WARNING] djangosaml2: No attributes received from IdP
```

### 7.4 Vérification en base de données

```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> user = User.objects.get(email='user@example.com')
>>> print(user.username, user.first_name, user.last_name)
user@example.com Jean Dupont
```

### 7.5 Test de déconnexion

```bash
# Accès à la page de déconnexion
curl -I https://monapp.example.com/saml2/logout/
# Doit rediriger vers l'IdP pour logout
```

---

<a name="troubleshooting"></a>
## 8. Troubleshooting

### Problème 1 : "Unknown attribute name"

**Symptôme** :
```log
[ERROR] Unknown attribute name: <ns0:Attribute Name="ctemail" ...>
```

**Causes possibles** :

1. ❌ Attribute map manquant ou mal configuré
2. ❌ `attribute_map_dir` absent de `SAML_CONFIG`
3. ❌ NameFormat incorrect dans l'attribute map
4. ❌ Fichier attribute map non copié dans le conteneur

**Diagnostic** :

```bash
# Vérifier la présence de attribute_map_dir
python manage.py shell
>>> from django.conf import settings
>>> print(settings.SAML_CONFIG.get('attribute_map_dir'))
/app/saml/attributemaps  # Doit afficher le chemin

# Vérifier les fichiers présents
>>> import os
>>> os.listdir(settings.SAML_CONFIG['attribute_map_dir'])
['__init__.py', 'basic.py']  # Au minimum

# Vérifier le contenu de basic.py
>>> with open(os.path.join(settings.SAML_CONFIG['attribute_map_dir'], 'basic.py')) as f:
...     print(f.read())
# Doit afficher le MAP avec identifier, fro, to
```

**Solution** :

1. Créer/corriger `saml/attributemaps/basic.py` (voir section 5)
2. Ajouter `'attribute_map_dir': str(BASE_DIR / 'saml' / 'attributemaps')` dans `SAML_CONFIG`
3. Reconstruire l'image : `podman-compose build --no-cache web`
4. Redémarrer : `podman-compose restart web`

### Problème 2 : "No attributes received from IdP"

**Symptôme** :
```log
[WARNING] djangosaml2: attributes: {}
[ERROR] User authentication failed: No email attribute
```

**Causes possibles** :

1. ❌ L'IdP n'envoie pas les attributs (problème côté IdP)
2. ❌ `required_attributes` mal configuré dans `SAML_CONFIG`
3. ❌ Attributs envoyés avec un NameFormat différent

**Diagnostic** :

1. Demander à l'admin IdP de vérifier que les attributs sont bien inclus dans l'assertion
2. Capturer une assertion SAML complète :

```python
# Dans djangosaml2/backends.py, ajouter temporairement :
import logging
logger = logging.getLogger(__name__)

def authenticate(self, request, session_info=None, **kwargs):
    logger.error(f"SAML Assertion complète: {session_info}")
    # ... reste du code
```

3. Redémarrer et consulter les logs

**Solution** :

- Coordonner avec l'admin IdP pour corriger la configuration
- Vérifier que `required_attributes` correspond aux noms exacts envoyés par l'IdP

### Problème 3 : "Signature verification failed"

**Symptôme** :
```log
[ERROR] Signature verification failed
[ERROR] Invalid SAML response
```

**Causes possibles** :

1. ❌ Certificat IdP incorrect ou expiré
2. ❌ Métadonnées IdP obsolètes
3. ❌ Algorithme de signature non supporté

**Solution** :

1. Télécharger les métadonnées IdP à jour :
   ```bash
   curl -o saml/idp_metadata.xml https://idp.example.com/metadata
   ```

2. Vérifier le certificat IdP :
   ```bash
   openssl x509 -in saml/idp_certificate.pem -text -noout
   # Vérifier la date d'expiration
   ```

3. Reconstruire et redémarrer

### Problème 4 : Utilisateur créé avec username vide

**Symptôme** :
```log
[ERROR] IntegrityError: duplicate key value violates unique constraint "auth_user_username_key"
```

**Cause** : Le champ `username` n'est pas rempli par les attributs SAML.

**Solution** :

1. Assurez-vous qu'un attribut SAML est mappé vers `username` :
   ```python
   SAML_ATTRIBUTE_MAPPING = {
       'ctemail': ('username', 'email',),  # email va aussi dans username
   }
   ```

2. Ou configurez Django pour utiliser `email` comme identifiant principal :
   ```python
   SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'
   SAML_USE_NAME_ID_AS_USERNAME = False
   ```

### Problème 5 : Certificats SP non valides

**Symptôme** :
```log
[ERROR] unable to load certificate
```

**Solution** :

Régénérer les certificats avec une durée de validité suffisante :

```bash
cd saml/
openssl req -new -x509 -days 3652 -nodes \
    -out sp_certificate.pem -keyout sp_private_key.pem \
    -subj "/C=FR/ST=IDF/L=Paris/O=MonOrg/CN=monapp.example.com"

# Permissions
chmod 600 sp_private_key.pem
chmod 644 sp_certificate.pem
```

---

<a name="checklist"></a>
## 9. Checklist complète

### Phase 1 : Préparation (avec l'admin IdP)

- [ ] Obtenir `idp_metadata.xml` ou URL des métadonnées
- [ ] Obtenir la liste des attributs SAML et leurs NameFormat
- [ ] Obtenir des valeurs d'exemple pour les attributs
- [ ] Clarifier le mode d'initiation (SP ou IdP-initiated)
- [ ] Obtenir le certificat IdP (si métadonnées non signées)

### Phase 2 : Configuration application Django

- [ ] Installer `pysaml2`, `djangosaml2`
- [ ] Créer la structure `saml/` et `saml/attributemaps/`
- [ ] Générer les certificats SP (`sp_certificate.pem`, `sp_private_key.pem`)
- [ ] Placer `idp_metadata.xml` dans `saml/`
- [ ] Ajouter `djangosaml2` dans `INSTALLED_APPS`
- [ ] Ajouter `SamlSessionMiddleware` dans `MIDDLEWARE`
- [ ] Configurer `AUTHENTICATION_BACKENDS`
- [ ] Configurer `SAML_CONFIG` dans `settings.py`
- [ ] Créer l'attribute map `saml/attributemaps/basic.py` (ou autre)
- [ ] Ajouter `'attribute_map_dir'` dans `SAML_CONFIG`
- [ ] Configurer `SAML_ATTRIBUTE_MAPPING`
- [ ] Définir `SAML_DJANGO_USER_MAIN_ATTRIBUTE`
- [ ] Inclure `path('saml2/', include('djangosaml2.urls'))` dans `urls.py`

### Phase 3 : Tests en local

- [ ] Lancer le serveur : `python manage.py runserver`
- [ ] Accéder aux métadonnées SP : `http://localhost:8000/saml2/metadata/`
- [ ] Vérifier le format XML avec `xmllint`
- [ ] Tester l'authentification SAML (si possible en local avec IdP de test)
- [ ] Vérifier les logs Django pour les attributs SAML reçus
- [ ] Vérifier la création de l'utilisateur en base de données

### Phase 4 : Déploiement conteneurisé

- [ ] Créer `Containerfile` / `Dockerfile` avec dépendances SAML
- [ ] Créer `compose.yaml` / `docker-compose.yml`
- [ ] Vérifier que `.dockerignore` n'exclut pas `saml/`
- [ ] Builder l'image : `podman-compose build --no-cache web`
- [ ] Vérifier la présence des attributemaps dans l'image
- [ ] Lancer les conteneurs : `podman-compose up -d`
- [ ] Tester l'accès aux métadonnées : `curl https://monapp.example.com/saml2/metadata/`

### Phase 5 : Configuration IdP et tests en production

- [ ] Fournir les métadonnées SP à l'admin IdP
- [ ] Demander à l'admin IdP de configurer l'application SP dans l'IdP
- [ ] Tester l'authentification SAML en production
- [ ] Vérifier les logs de production
- [ ] Vérifier la création/mise à jour des utilisateurs
- [ ] Tester la déconnexion SAML
- [ ] Tester avec plusieurs utilisateurs

### Phase 6 : Sécurité et monitoring

- [ ] Désactiver `DEBUG = False` en production
- [ ] Retirer `'debug': True` de `SAML_CONFIG`
- [ ] Configurer HTTPS avec certificats valides
- [ ] Restreindre `ALLOWED_HOSTS`
- [ ] Mettre en place un monitoring des connexions SAML
- [ ] Configurer la rotation des logs
- [ ] Planifier le renouvellement des certificats SP (avant expiration)

---

<a name="annexes"></a>
## 10. Annexes et exemples

### Annexe A : Exemple complet de settings.py (section SAML)

```python
# ============================================================================
# CONFIGURATION SAML / SSO
# ============================================================================

import os
import saml2
from pathlib import Path
from saml2.saml import NAMEID_FORMAT_PERSISTENT

BASE_DIR = Path(__file__).resolve().parent.parent

# URL de base de l'application (production)
SAML_BASE_URL = os.getenv('SAML_BASE_URL', 'https://monapp.example.com')

# Backends d'authentification
AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # Authentification locale
    'djangosaml2.backends.Saml2Backend',          # Authentification SAML
)

# Configuration SAML2
SAML_CONFIG = {
    'entityid': f'{SAML_BASE_URL}/saml2/metadata/',

    'service': {
        'sp': {
            'name': 'Mon Application',
            'name_format': NAMEID_FORMAT_PERSISTENT,

            'endpoints': {
                'assertion_consumer_service': [
                    (f'{SAML_BASE_URL}/saml2/acs/', saml2.BINDING_HTTP_POST),
                ],
                'single_logout_service': [
                    (f'{SAML_BASE_URL}/saml2/ls/', saml2.BINDING_HTTP_REDIRECT),
                ],
            },

            'allow_unsolicited': True,
            'want_assertions_signed': True,
            'want_response_signed': True,
            'signing_algorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
            'digest_algorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',

            'required_attributes': ['ctemail', 'ctfn', 'ctln'],
            'optional_attributes': [],
        },
    },

    'metadata': {
        'local': [str(BASE_DIR / 'saml' / 'idp_metadata.xml')],
    },

    'key_file': str(BASE_DIR / 'saml' / 'sp_private_key.pem'),
    'cert_file': str(BASE_DIR / 'saml' / 'sp_certificate.pem'),

    # CRUCIAL pour attributs personnalisés
    'attribute_map_dir': str(BASE_DIR / 'saml' / 'attributemaps'),

    'debug': False,  # True en dev, False en prod
    'xmlsec_binary': '/usr/bin/xmlsec1',
}

# Mapping attributs SAML → User Django
SAML_ATTRIBUTE_MAPPING = {
    'ctemail': ('username', 'email',),
    'ctfn': ('first_name',),
    'ctln': ('last_name',),
}

SAML_CREATE_UNKNOWN_USER = True
SAML_ATTRIBUTE_AUTO_UPDATE = True
SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'
SAML_USE_NAME_ID_AS_USERNAME = False

# ============================================================================
# FIN CONFIGURATION SAML
# ============================================================================
```

### Annexe B : Script de validation de configuration

**Fichier : `validate_saml_config.py`**

```python
#!/usr/bin/env python
"""
Script de validation de la configuration SAML
Usage: python validate_saml_config.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'monprojet.settings')
django.setup()

from django.conf import settings
from pathlib import Path

def validate():
    errors = []
    warnings = []

    # Vérification 1 : SAML_CONFIG existe
    if not hasattr(settings, 'SAML_CONFIG'):
        errors.append("SAML_CONFIG n'est pas défini dans settings.py")
        return errors, warnings

    # Vérification 2 : attribute_map_dir
    if 'attribute_map_dir' not in settings.SAML_CONFIG:
        errors.append("'attribute_map_dir' manquant dans SAML_CONFIG")
    else:
        attr_dir = Path(settings.SAML_CONFIG['attribute_map_dir'])
        if not attr_dir.exists():
            errors.append(f"Répertoire attribute_map_dir n'existe pas: {attr_dir}")
        else:
            # Vérifier les fichiers
            py_files = list(attr_dir.glob('*.py'))
            py_files = [f for f in py_files if f.name != '__init__.py']
            if not py_files:
                warnings.append(f"Aucun fichier .py trouvé dans {attr_dir}")
            else:
                print(f"✅ Attribute maps trouvés: {[f.name for f in py_files]}")

    # Vérification 3 : Certificats SP
    for key in ['key_file', 'cert_file']:
        if key in settings.SAML_CONFIG:
            path = Path(settings.SAML_CONFIG[key])
            if not path.exists():
                errors.append(f"{key} n'existe pas: {path}")
            else:
                print(f"✅ {key}: {path}")

    # Vérification 4 : Métadonnées IdP
    if 'metadata' in settings.SAML_CONFIG:
        if 'local' in settings.SAML_CONFIG['metadata']:
            for metadata_file in settings.SAML_CONFIG['metadata']['local']:
                path = Path(metadata_file)
                if not path.exists():
                    errors.append(f"Métadonnées IdP n'existent pas: {path}")
                else:
                    print(f"✅ Métadonnées IdP: {path}")

    # Vérification 5 : SAML_ATTRIBUTE_MAPPING
    if not hasattr(settings, 'SAML_ATTRIBUTE_MAPPING'):
        warnings.append("SAML_ATTRIBUTE_MAPPING non défini")
    elif not settings.SAML_ATTRIBUTE_MAPPING:
        warnings.append("SAML_ATTRIBUTE_MAPPING est vide")
    else:
        print(f"✅ SAML_ATTRIBUTE_MAPPING: {list(settings.SAML_ATTRIBUTE_MAPPING.keys())}")

    # Vérification 6 : required_attributes vs SAML_ATTRIBUTE_MAPPING
    if 'service' in settings.SAML_CONFIG:
        sp_config = settings.SAML_CONFIG['service'].get('sp', {})
        required = sp_config.get('required_attributes', [])
        mapped = list(settings.SAML_ATTRIBUTE_MAPPING.keys())

        for attr in required:
            if attr not in mapped:
                warnings.append(f"Attribut requis '{attr}' non mappé dans SAML_ATTRIBUTE_MAPPING")

    return errors, warnings

if __name__ == '__main__':
    print("🔍 Validation de la configuration SAML...\n")

    errors, warnings = validate()

    if warnings:
        print("\n⚠️  Avertissements:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\n❌ Erreurs:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n✅ Configuration SAML valide!")
        sys.exit(0)
```

**Usage** :

```bash
python validate_saml_config.py
```

### Annexe C : Commandes utiles

```bash
# Tester les métadonnées SP
curl https://monapp.example.com/saml2/metadata/ | xmllint --format - | less

# Vérifier la validité du certificat SP
openssl x509 -in saml/sp_certificate.pem -text -noout | grep -A2 "Validity"

# Vérifier la concordance clé privée / certificat SP
openssl x509 -modulus -noout -in saml/sp_certificate.pem | openssl md5
openssl rsa -modulus -noout -in saml/sp_private_key.pem | openssl md5
# Les hash MD5 doivent être identiques

# Inspecter le certificat IdP
openssl x509 -in saml/idp_certificate.pem -text -noout

# Décoder une assertion SAML (base64)
echo "PHNhbWw6QXNzZXJ0aW9uLi4u..." | base64 -d | xmllint --format -

# Logs SAML en temps réel
tail -f logs/django.log | grep -i "saml\|assertion\|attribute"

# Vérifier la configuration pysaml2 depuis Python
python -c "from saml2.config import Config; c = Config(); c.load_file('saml_config.py'); print(c)"
```

---

## Conclusion

Ce guide couvre l'intégration complète de SAML dans Django avec un focus sur les **attributs personnalisés**, un point souvent mal documenté et source de nombreux problèmes.

### Points clés à retenir

1. **Attribute maps personnalisés** : Indispensables pour les attributs SAML non-standard
2. **NameFormat** : Doit correspondre exactement entre IdP, attribute map, et SAML_CONFIG
3. **Déploiement conteneurisé** : Attention à la copie des fichiers `saml/attributemaps/`
4. **Tests progressifs** : Local d'abord, puis conteneurs, puis production
5. **Coordination avec l'IdP** : Communication étroite avec l'administrateur IdP

### Ressources complémentaires

- **pysaml2** : https://pysaml2.readthedocs.io/
- **djangosaml2** : https://github.com/IdentityPython/djangosaml2
- **SAML 2.0 Spec** : http://docs.oasis-open.org/security/saml/
- **Attribute Maps examples** : https://github.com/IdentityPython/pysaml2/tree/master/src/saml2/attributemaps

---

**Version** : 1.0
**Dernière mise à jour** : 2026-01-28
**Licence** : CC BY-SA 4.0
**Retours** : N'hésitez pas à améliorer ce guide !