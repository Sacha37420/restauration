"""Noms canoniques des entités de référence (statuts, canaux, méthodes).

Centralisés ici pour éviter les divergences de libellés entre le webhook
Stripe, le paiement public et les ViewSets (ex. 'paye' vs 'payé').
Les libellés doivent rester alignés avec la migration de seed 0004.
"""

# Canaux de commande
CANAL_SUR_PLACE = 'sur_place'

# Statuts de commande
STATUT_CMD_EN_ATTENTE = 'en_attente'
STATUT_CMD_EN_PREPARATION = 'en_preparation'

# Statuts de paiement
STATUT_PAIEMENT_EN_ATTENTE = 'en_attente'
STATUT_PAIEMENT_PAYE = 'paye'

# Descriptions par défaut (utilisées par get_or_create si l'entité manque)
DESC_CANAL_SUR_PLACE = 'Commande passée en salle'
DESC_CMD_EN_ATTENTE = 'Commande en attente de traitement'
DESC_CMD_EN_PREPARATION = 'Commande prise en charge en cuisine'
DESC_PAIEMENT_EN_ATTENTE = 'Paiement non encore effectué'
DESC_PAIEMENT_PAYE = 'Paiement validé'

# Méthodes de paiement encaissées sur place (flux public hors ligne).
# Le paiement par carte passe obligatoirement par Stripe.
METHODES_SUR_PLACE = frozenset({'espèces', 'ticket_restaurant'})

# Rôles applicatifs = groupes Keycloak/LDAP gérables depuis l'app.
# Doit rester aligné avec api.permissions et les groupes LDAP (init.ldif).
ROLES_RESTAURATION = ('manager', 'cuisinier', 'serveur')
