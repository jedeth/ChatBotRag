# Répertoire SAML

Ce répertoire contient les fichiers de configuration SAML pour l'authentification SSO.

## 📁 Structure

```
saml/
├── attributemaps/          # Mappings d'attributs personnalisés (pysaml2)
│   ├── __init__.py
│   └── basic.py           # Attribute map pour NameFormat=basic (À ADAPTER)
├── idp_metadata.xml       # Métadonnées de l'Identity Provider (À OBTENIR)
├── sp_certificate.pem     # Certificat public du Service Provider (À GÉNÉRER)
├── sp_private_key.pem     # Clé privée du Service Provider (À GÉNÉRER)
└── README.md              # Ce fichier
```

## 🚀 Prochaines étapes

### 1. Obtenir les informations de l'IdP

Contactez l'administrateur de l'Identity Provider pour obtenir :

- [ ] `idp_metadata.xml` (ou URL des métadonnées)
- [ ] Liste des attributs SAML envoyés (noms et NameFormat)
- [ ] Valeurs de test pour validation
- [ ] Mode d'initiation (SP-initiated ou IdP-initiated)
- [ ] URL de l'application pour configuration (ex: https://monapp.example.com)

### 2. Générer les certificats du Service Provider

```bash
cd saml/

# Génération de la clé privée et du certificat (valide 10 ans)
openssl req -new -x509 -days 3652 -nodes \
    -out sp_certificate.pem \
    -keyout sp_private_key.pem \
    -subj "/C=FR/ST=IDF/L=Paris/O=Rectorat/CN=chatbot-rag.example.com"

# Sécuriser les permissions
chmod 600 sp_private_key.pem
chmod 644 sp_certificate.pem

# Vérification
openssl x509 -in sp_certificate.pem -text -noout | grep -A2 "Validity"
```

### 3. Adapter l'attribute map

Éditez `attributemaps/basic.py` en fonction des attributs fournis par votre IdP :

```python
MAP = {
    "identifier": "urn:oasis:names:tc:SAML:2.0:attrname-format:basic",
    "fro": {
        'votre_attribut_email': 'votre_attribut_email',
        'votre_attribut_prenom': 'votre_attribut_prenom',
        'votre_attribut_nom': 'votre_attribut_nom',
    },
    "to": { ... }
}
```

### 4. Configurer Django (settings.py)

Voir le guide complet dans : `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md`

Configuration minimale à ajouter dans `chatbot_rag/settings.py` :

```python
import saml2
from saml2.saml import NAMEID_FORMAT_PERSISTENT

SAML_BASE_URL = os.getenv('SAML_BASE_URL', 'https://chatbot-rag.example.com')

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',  # Auth locale
    'djangosaml2.backends.Saml2Backend',          # Auth SAML
)

SAML_CONFIG = {
    'entityid': f'{SAML_BASE_URL}/saml2/metadata/',
    'attribute_map_dir': str(BASE_DIR / 'saml' / 'attributemaps'),
    'metadata': {
        'local': [str(BASE_DIR / 'saml' / 'idp_metadata.xml')],
    },
    'key_file': str(BASE_DIR / 'saml' / 'sp_private_key.pem'),
    'cert_file': str(BASE_DIR / 'saml' / 'sp_certificate.pem'),
    # ... voir guide complet
}

SAML_ATTRIBUTE_MAPPING = {
    'votre_attribut_email': ('username', 'email',),
    'votre_attribut_prenom': ('first_name',),
    'votre_attribut_nom': ('last_name',),
}
```

### 5. Tester la configuration

```bash
# Vérifier les métadonnées SP
curl http://localhost:8000/saml2/metadata/

# Valider la configuration SAML
python docs/validate_saml_config.py
```

## 📚 Documentation

Consultez le guide complet : `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md`

## ⚠️ Sécurité

- **Ne jamais committer** `sp_private_key.pem` dans Git (déjà exclu par .gitignore)
- **Ne jamais committer** `idp_metadata.xml` s'il contient des secrets
- Les certificats doivent être générés spécifiquement pour chaque environnement (dev, prod)
- Renouveler les certificats avant expiration

## 🔗 URLs SAML disponibles

Une fois configuré, les URLs suivants seront disponibles :

- `/saml2/login/` - Initier l'authentification SAML (SP-initiated)
- `/saml2/acs/` - Assertion Consumer Service (callback IdP)
- `/saml2/logout/` - Déconnexion SAML
- `/saml2/metadata/` - Métadonnées SP (à fournir à l'IdP)
