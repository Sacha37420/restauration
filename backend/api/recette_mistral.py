"""Génération d'une recette ORIGINALE par Mistral, contrainte au référentiel du restaurant.

Aucune recette n'est copiée d'une source externe : le texte est produit par le modèle.
C'est ce qui écarte toute question de droit d'auteur — les instructions d'une recette
publiée (Marmiton & co) sont une œuvre protégée, qu'on ne peut pas recopier pour un
usage commercial.

Contrepartie : le modèle ne propose que des ingrédients que le restaurant peut
réellement acheter, ce qui permet d'en chiffrer le coût matière au prix fournisseur.

Le prompt est modifiable depuis la page Paramétrage (cf. prompts.py pour le défaut).
"""
import json

from . import prompts
from .models import PromptMistral
from .robot_mistral import completer


def generer(demande, nb_portions, contraintes, ingredients, unites):
    """Renvoie une proposition de recette (non enregistrée).

    `ingredients` : ['Tomate (g)', 'Oeuf (pièce)', …] — le référentiel à privilégier
    `contraintes` : ['végétarien', 'sans gluten', …]
    """
    message = (
        f'Ingrédients disponibles : {json.dumps(ingredients, ensure_ascii=False)}\n'
        f'Unités autorisées : {json.dumps(unites, ensure_ascii=False)}\n\n'
        f'Recette demandée : {demande}\n'
        f'Nombre de portions : {nb_portions}\n'
    )
    if contraintes:
        message += f'Contraintes impératives : {", ".join(contraintes)}\n'

    return completer(PromptMistral.texte(prompts.RECETTE), message)
