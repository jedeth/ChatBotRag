# -*- coding: utf-8 -*-
"""
Attribute map pour attributs SAML personnalisés
NameFormat: urn:oasis:names:tc:SAML:2.0:attrname-format:basic

⚠️ À ADAPTER selon les attributs fournis par votre IdP.
Coordonnez-vous avec l'administrateur système pour obtenir :
  - La liste exacte des attributs SAML
  - Le NameFormat utilisé (basic, uri, unspecified)
  - Des valeurs de test

Exemple d'attributs courants :
  - ctemail, ctfn, ctln (attributs personnalisés)
  - mail, givenName, sn (attributs standard SAML)
  - employeeID, department (attributs RH)
"""

MAP = {
    # Identifiant du format (doit correspondre EXACTEMENT au NameFormat de l'IdP)
    "identifier": "urn:oasis:names:tc:SAML:2.0:attrname-format:basic",

    # Mapping FROM SAML (assertion XML de l'IdP) vers nom interne pysaml2
    # Format: 'nom_dans_assertion_saml': 'nom_interne_pysaml2'
    "fro": {
        # ⚠️ EXEMPLE - À REMPLACER par vos attributs réels
        'ctemail': 'ctemail',      # Email personnalisé
        'ctfn': 'ctfn',            # First Name personnalisé
        'ctln': 'ctln',            # Last Name personnalisé

        # Autres exemples possibles (décommenter si nécessaire)
        # 'employeeID': 'employeeID',
        # 'department': 'department',
        # 'mail': 'mail',
        # 'givenName': 'givenName',
        # 'sn': 'sn',
    },

    # Mapping TO SAML (nom interne pysaml2 vers assertion XML)
    # Utilisé si le SP génère des requêtes SAML vers l'IdP
    # En général, mapping 1:1 identique à 'fro'
    "to": {
        # ⚠️ EXEMPLE - À REMPLACER par vos attributs réels
        'ctemail': 'ctemail',
        'ctfn': 'ctfn',
        'ctln': 'ctln',

        # Autres exemples possibles (décommenter si nécessaire)
        # 'employeeID': 'employeeID',
        # 'department': 'department',
        # 'mail': 'mail',
        # 'givenName': 'givenName',
        # 'sn': 'sn',
    }
}
