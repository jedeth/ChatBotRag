# Message pour l'Administrateur Système - Configuration SAML

---

**Objet** : Configuration SAML pour ChatBot RAG - Informations IdP nécessaires

---

Bonjour,

Je reviens vers vous concernant l'intégration SAML (SSO) pour l'application **ChatBot RAG** que nous déployons.

## 📋 Contexte

L'application est un chatbot documentaire qui permettra aux utilisateurs de poser des questions sur des documents uploadés. Nous souhaitons intégrer l'authentification SSO via SAML avec l'Identity Provider de l'académie (même principe que pour l'application noScribe).

## ✅ Ce qui est déjà prêt côté application

L'infrastructure SAML est **entièrement préparée** dans le code :

- ✅ Bibliothèques Python installées (`djangosaml2`, `pysaml2`, `xmlsec`)
- ✅ Dépendances système configurées dans le conteneur
- ✅ Structure de fichiers créée (`saml/attributemaps/`, templates)
- ✅ Code Django préparé (URLs, middleware)
- ✅ Documentation complète (`docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md`)
- ✅ Fichiers secrets exclus de Git (`.gitignore`)

**Référence** : Nous utilisons la même stack technique que noScribe pour faciliter l'intégration (djangosaml2 1.11.1).

## 🔍 Informations nécessaires de votre côté

Pour finaliser la configuration, j'ai besoin des éléments suivants concernant l'**Identity Provider** :

### 1. Métadonnées IdP (PRIORITAIRE)

- **Fichier XML** : `idp_metadata.xml` (ou URL publique des métadonnées)
  - Ce fichier contient l'entityID, les certificats, les endpoints SSO/SLO

### 2. Attributs SAML (CRITIQUE)

Liste **exhaustive** des attributs SAML renvoyés par l'IdP avec leur format exact :

**Format attendu** :
```
Nom de l'attribut : <nom_technique>
NameFormat : <urn:oasis:names:tc:SAML:2.0:attrname-format:basic|uri|...>
Exemple de valeur : <valeur_test>
```

**Attributs minimum requis** :
- ✅ Email (ex: `mail`, `email`, `ctemail`)
- ✅ Prénom (ex: `givenName`, `firstName`, `ctfn`)
- ✅ Nom (ex: `sn`, `surname`, `lastName`, `ctln`)
- ✅ Identifiant unique (ex: `uid`, `employeeID`, `eduPersonPrincipalName`)

**Exemple réel souhaité** : Si possible, un dump d'une assertion SAML réelle (anonymisée) pour voir exactement la structure des attributs.

### 3. Configuration applicative

- **URL de l'application** : Quelle URL publique sera utilisée ?
  - Exemple : `https://chatbot-rag.ac-paris.fr`
  - Nécessaire pour générer les métadonnées SP (Service Provider)

- **Mode d'initiation** :
  - SP-initiated (l'utilisateur clique "Se connecter avec SSO" sur notre appli) ?
  - IdP-initiated (l'utilisateur clique depuis le portail académique) ?
  - Les deux ?

- **Gestion des groupes/rôles** :
  - L'IdP renvoie-t-il des attributs de groupes/rôles ?
  - Si oui, noms techniques de ces attributs ?

### 4. Environnement de test

- **Environnement de test IdP disponible** ?
  - URL de test
  - Compte utilisateur de test (pour valider l'intégration)

## 📝 Prochaines étapes proposées

Une fois ces informations reçues :

1. **De mon côté** (30-60 min) :
   - Génération des certificats SP (clé privée + certificat public)
   - Adaptation de l'attribute map selon vos attributs SAML
   - Configuration finale dans Django
   - Génération des métadonnées SP à vous fournir

2. **De votre côté** :
   - Enregistrement de l'application dans l'IdP avec nos métadonnées SP
   - Configuration du mapping d'attributs côté IdP (si nécessaire)

3. **Tests conjoints** (1-2h) :
   - Test d'authentification SP-initiated
   - Vérification de la réception des attributs
   - Test de déconnexion (SLO)
   - Validation de la création automatique des utilisateurs

**Temps total estimé** : 2-3h une fois les informations reçues

## 🎯 Point critique : Attribute Mapping

L'expérience sur d'autres projets Django/SAML montre que **90% des problèmes** viennent du mapping d'attributs. C'est pourquoi j'insiste sur :
- Les noms **exacts** des attributs (sensible à la casse)
- Le **NameFormat** précis (basic vs uri vs unspecified)
- Des **exemples de valeurs** réelles pour valider

## 📚 Documentation disponible

Si vous souhaitez consulter :
- Guide complet : `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md` (73 pages)
- État d'avancement : `docs/SAML_PREPARATION.md`

## ❓ Questions

N'hésitez pas si :
- Vous avez besoin de précisions techniques
- Vous souhaitez une réunion de travail pour avancer ensemble
- Vous préférez procéder par étapes (test en local d'abord, puis production)

Je reste disponible pour coordonner cette intégration.

Cordialement,

---

**Pièces jointes recommandées** :
- [ ] `docs/SAML_PREPARATION.md` (résumé technique)
- [ ] `docs/GUIDE_ADMINISTRATION_SAML_DJANGO_ATTRIBUTS_PERSONNALISES.md` (si l'admin veut les détails)

**Modèle de réponse suggéré** :
```
Merci pour ces informations. Voici les éléments demandés :

1. Métadonnées IdP : [fichier joint / URL]
2. Attributs SAML :
   - Email : mail (NameFormat: basic) - ex: "jean.dupont@ac-paris.fr"
   - Prénom : givenName (NameFormat: basic) - ex: "Jean"
   - Nom : sn (NameFormat: basic) - ex: "Dupont"
   - UID : employeeID (NameFormat: basic) - ex: "12345"
3. URL application : https://chatbot-rag.ac-paris.fr
4. Mode : SP-initiated + IdP-initiated
5. Environnement test : https://idp-test.ac-paris.fr (compte: test@ac-paris.fr)
```
