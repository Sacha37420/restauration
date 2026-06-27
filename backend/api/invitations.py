"""Construction des emails d'invitation, au contenu adapté au(x) rôle(s).

- manager : pitch « application en test » + tour des fonctionnalités actuelles ;
- cuisinier / serveur : parties utiles de l'app + pipeline d'actions.
Tous reçoivent le lien, le mot de passe provisoire et la consigne de le changer.
"""
from __future__ import annotations

import secrets

from .constants import ROLES_RESTAURATION

# Alphabet sans caractères ambigus (0/O, 1/l/I) pour un mot de passe lisible.
_ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def generer_mot_de_passe(longueur: int = 14) -> str:
    return ''.join(secrets.choice(_ALPHABET) for _ in range(longueur))


_INTRO_MANAGER = (
    "Cette application de gestion de restaurant est en phase de TEST. "
    "L'idée est que vous la preniez en main et l'utilisiez un peu, afin qu'on "
    "puisse l'adapter à vos besoins réels. Vos retours sont précieux.\n\n"
    "En tant que manager, vous avez accès à l'ensemble des fonctionnalités "
    "actuelles :\n"
    "  • Cuisine & stocks : ingrédients, recettes, plats, catégories, unités, "
    "fournisseurs, mouvements de stock.\n"
    "  • Service & commandes : plan de tables, prise de commandes, encaissement "
    "(espèces, ticket-restaurant, ou carte via Stripe) et factures PDF.\n"
    "  • Planning : organisation des plages de travail du personnel.\n"
    "  • Analyse économique : événements, météo, ventes et régressions pour "
    "comprendre ce qui influence la fréquentation.\n"
    "  • Paramétrage : email/SMTP, Stripe, agents IA, et gestion des utilisateurs "
    "(c'est ici que vous pourrez inviter cuisiniers et serveurs)."
)

_SECTION_CUISINIER = (
    "En tant que cuisinier, votre espace est la partie Cuisine. Votre pipeline :\n"
    "  1. Gérer le stock d'ingrédients (entrées / sorties, seuils d'alerte).\n"
    "  2. Composer les recettes (ingrédients et quantités).\n"
    "  3. Décliner les recettes en plats (prix, régimes : sans gluten, halal, "
    "végétarien…).\n"
    "  4. Suivre les commandes à préparer."
)

_SECTION_SERVEUR = (
    "En tant que serveur, votre espace est la partie Service. Votre pipeline :\n"
    "  1. Gérer le plan des tables.\n"
    "  2. Prendre les commandes (par table / canal).\n"
    "  3. Suivre l'avancement des commandes.\n"
    "  4. Encaisser (espèces, ticket-restaurant, ou carte via Stripe) et générer "
    "la facture."
)

_SECTIONS = {
    'cuisinier': _SECTION_CUISINIER,
    'serveur': _SECTION_SERVEUR,
}


def sujet_et_corps(roles: list[str], prenom: str, lien: str, mot_de_passe: str) -> tuple[str, str]:
    """Renvoie (sujet, corps texte) pour l'invitation."""
    roles_ordonnes = [r for r in ROLES_RESTAURATION if r in roles]
    libelles = ', '.join(roles_ordonnes) or 'utilisateur'

    bonjour = f"Bonjour {prenom}," if prenom else "Bonjour,"
    blocs: list[str] = [
        bonjour,
        "",
        f"Un accès vient de vous être créé sur l'application Restauration "
        f"(rôle : {libelles}).",
        "",
    ]

    if 'manager' in roles_ordonnes:
        blocs += [_INTRO_MANAGER, ""]
    for role in roles_ordonnes:
        if role in _SECTIONS:
            blocs += [_SECTIONS[role], ""]

    blocs += [
        "── Votre connexion ──────────────────────────────",
        f"Adresse : {lien}",
        f"Identifiant : votre email",
        f"Mot de passe provisoire : {mot_de_passe}",
        "",
        "⚠ Pour des raisons de sécurité, ce mot de passe est provisoire : "
        "il vous sera demandé de le changer dès votre première connexion.",
        "",
        "Bonne découverte !",
    ]

    sujet = "Votre accès à l'application Restauration"
    return sujet, "\n".join(blocs)
