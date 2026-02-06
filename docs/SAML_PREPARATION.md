# Préparation SAML — État d'Avancement

**Date** : 2026-02-06
**Statut** : Structure prête, configuration IdP nécessaire

---

## ✅ Travaux Effectués

### 1. Structure et fichiers créés

```
saml/
├── attributemaps/
│   ├── __init__.py                 # Module Python
│   └── basic.py                    # Attribute map (TEMPLATE à adapter)
├── .gitkeep                        # Permet de tracker le répertoire vide
├── README.md                       # Instructions détaillées
└── saml_settings_template.py      # Configuration SAML (TEMPLATE à adapter)
```

### 2. Dépendances déjà présentes

**Python** (`requirements.txt`) :
- ✅ `djangosaml2==1.11.1` (intégration Django)
- ✅ `pysaml2==7.5.4` (bibliothèque SAML)
- ✅ `xmlsec>=1.0.0` (signatures XML)

**Système** (`Containerfile` lignes 30-33) :
- ✅ `xmlsec1` (signatures SAML)
- ✅ `libxml2-dev` (parsing XML)
- ✅ `libxmlsec1-dev` (développement xmlsec)
- ✅ `libxmlsec1-openssl` (backend OpenSSL)

### 3. Code Django préparé

**URLs** (`chatbot_rag/urls.py`) :
- ✅ Route SAML prête (commentée, à décommenter après config)
  ```python
  # path('saml2/', include('djangosaml2.urls')),
  ```

**Sécurité** (`.gitignore`) :
- ✅ Exclusion des secrets SAML :
  ```
  saml/sp_private_key.pem
  saml/idp_metadata.xml
  saml/sp_certificate.pem
  ```

### 4. Documentation

- ✅ Guide complet : `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md`
- ✅ Instructions locales : `saml/README.md`
- ✅ Template de configuration : `saml/saml_settings_template.py`

---

## 🔧 Prochaines Étapes (Avec Admin Système)

### Phase 1 : Collecte d'informations IdP

À obtenir de l'administrateur de l'Identity Provider :

- [ ] **Métadonnées IdP** : `idp_metadata.xml` (ou URL)
- [ ] **Liste des attributs SAML** : Noms exacts et NameFormat
  - Exemples : `mail`, `givenName`, `sn` (standard)
  - Exemples : `ctemail`, `ctfn`, `ctln` (personnalisés)
  - Exemples : `employeeID`, `department` (RH)
- [ ] **Valeurs de test** : Échantillons pour validation
- [ ] **Mode d'initiation** : SP-initiated ou IdP-initiated
- [ ] **URL de l'application** : URL publique à configurer dans l'IdP

### Phase 2 : Génération des certificats SP

```bash
cd saml/

# Génération (valide 10 ans)
openssl req -new -x509 -days 3652 -nodes \
    -out sp_certificate.pem \
    -keyout sp_private_key.pem \
    -subj "/C=FR/ST=IDF/L=Paris/O=Rectorat/CN=chatbot-rag.VOTRE-DOMAINE.fr"

# Sécurité
chmod 600 sp_private_key.pem
chmod 644 sp_certificate.pem
```

### Phase 3 : Configuration

#### A. Adapter l'attribute map (`saml/attributemaps/basic.py`)

Remplacer les exemples par les attributs réels :

```python
MAP = {
    "identifier": "urn:oasis:names:tc:SAML:2.0:attrname-format:basic",
    "fro": {
        'votre_attribut_email': 'votre_attribut_email',
        'votre_attribut_prenom': 'votre_attribut_prenom',
        # ...
    },
    # ...
}
```

#### B. Configurer Django (`chatbot_rag/settings.py`)

Copier depuis `saml/saml_settings_template.py` et adapter :

1. Ajouter `'djangosaml2'` dans `INSTALLED_APPS` (après `django.contrib.auth`)
2. Ajouter `'djangosaml2.middleware.SamlSessionMiddleware'` dans `MIDDLEWARE`
3. Copier la configuration SAML complète
4. Adapter les valeurs :
   - `SAML_BASE_URL`
   - `required_attributes`
   - `SAML_ATTRIBUTE_MAPPING`

#### C. Activer les URLs SAML (`chatbot_rag/urls.py`)

Décommenter la ligne :
```python
path('saml2/', include('djangosaml2.urls')),
```

### Phase 4 : Déploiement

```bash
# Reconstruire l'image (force la copie des nouveaux fichiers)
podman-compose build --no-cache web

# Vérifier la présence des attribute maps
podman-compose run --rm web ls -la /app/saml/attributemaps/

# Démarrer
podman-compose up -d

# Vérifier les logs
podman-compose logs -f web | grep -i saml
```

### Phase 5 : Tests

```bash
# 1. Vérifier les métadonnées SP
curl https://VOTRE-DOMAINE/saml2/metadata/ | xmllint --format -

# 2. Fournir ces métadonnées à l'admin IdP

# 3. Tester l'authentification SAML
# - SP-initiated : https://VOTRE-DOMAINE/saml2/login/
# - IdP-initiated : depuis le portail IdP

# 4. Vérifier la création de l'utilisateur
python manage.py shell
>>> from django.contrib.auth.models import User
>>> User.objects.all()
```

---

## 📚 Ressources

### Documentation locale
- Guide complet : `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md`
- Instructions : `saml/README.md`
- Template config : `saml/saml_settings_template.py`

### Sections clés du guide
- **Section 4** : Guide d'implémentation étape par étape
- **Section 5** : Configuration des attributs personnalisés ⚠️
- **Section 6** : Déploiement conteneurisé
- **Section 8** : Troubleshooting (erreurs courantes)
- **Section 9** : Checklist complète
- **Annexe B** : Script de validation `validate_saml_config.py`

### Commandes utiles

```bash
# Tester la configuration (après adaptation)
python validate_saml_config.py

# Vérifier un certificat
openssl x509 -in saml/sp_certificate.pem -text -noout

# Logs SAML en temps réel
tail -f logs/app.log | grep -i "saml\|assertion\|attribute"
```

---

## ⚠️ Points d'attention

### Sécurité
- Ne **jamais** committer `sp_private_key.pem` (déjà exclu)
- Ne **jamais** committer `idp_metadata.xml` s'il contient des secrets
- Renouveler les certificats avant expiration (10 ans)

### Attribute maps
- **Point critique** : L'attribute map `basic.py` DOIT correspondre au NameFormat de l'IdP
- Erreur fréquente : "Unknown attribute name" → attribute map manquant ou incorrect
- Fichier `basic.py` pour NameFormat `basic`, `uri.py` pour NameFormat `uri`

### Déploiement conteneurisé
- Toujours reconstruire **sans cache** : `--no-cache`
- Vérifier que `saml/attributemaps/` est copié dans l'image
- L'erreur peut réapparaître si les fichiers ne sont pas copiés

### Cohabitation SAML + Auth locale
- Les deux backends coexistent (`ModelBackend` + `Saml2Backend`)
- Connexion admin Django reste possible en local
- Utilisateurs SAML créés automatiquement avec `SAML_CREATE_UNKNOWN_USER`

---

## 🎯 Résumé

**État actuel** : Infrastructure SAML prête, configuration IdP nécessaire

**Bloquant** : Informations de l'IdP (métadonnées, attributs)

**Temps estimé** (après réception infos IdP) :
- Configuration : 30-60 minutes
- Tests et ajustements : 1-2 heures
- Total : ~2-3 heures

**Prêt pour** : Travail avec admin système sur serveur de production

---

**Dernière mise à jour** : 2026-02-06
**Responsable** : iarag + admin système
