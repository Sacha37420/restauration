"""Résolution d'un nom d'ingrédient proposé par un LLM vers le référentiel.

Partagé par le robot de catalogue (rattachement des articles fournisseur) et par le
générateur de recettes : dans les deux cas, Mistral propose un nom qu'il faut retrouver
dans le référentiel — ou créer — sans jamais le dupliquer.
"""
import re
import unicodedata

from .models import Ingredient, Unite

UNITE_PAR_DEFAUT = 'pièce'

# La nomenclature envoyée au LLM porte l'unité entre parenthèses (« Tomate (g) ») :
# il la recopie parfois telle quelle dans sa réponse.
_RE_SUFFIXE_UNITE = re.compile(r'\s*\([^)]*\)\s*$')


def unite_par_defaut():
    unite, _ = Unite.objects.get_or_create(
        nom=UNITE_PAR_DEFAUT, defaults={'description': 'Pièce'})
    return unite


def normaliser_nom(nom):
    return _RE_SUFFIXE_UNITE.sub('', (nom or '').strip()).strip()[:200]


def cle_comparaison(nom):
    """Clé de rapprochement : minuscules, sans accent, sans ligature.

    Le LLM ne recopie pas toujours le nom au caractère près : « Crème fraîche » contre
    « Crème Fraiche », « Œuf » contre « Oeuf ». Un rapprochement strictement textuel
    créerait alors un doublon dans le référentiel à chaque variation d'accent — et deux
    ingrédients pour la même chose, ce sont deux stocks et deux prix qui divergent.
    """
    texte = normaliser_nom(nom).lower().replace('œ', 'oe').replace('æ', 'ae')
    decompose = unicodedata.normalize('NFKD', texte)
    return ''.join(c for c in decompose if not unicodedata.combining(c)).strip()


def trouver(nom):
    """L'ingrédient correspondant à `nom`, ou None. Insensible à la casse et aux accents."""
    nom = normaliser_nom(nom)
    if not nom:
        return None

    exact = Ingredient.objects.filter(nom__iexact=nom).first()
    if exact:
        return exact

    # Le référentiel d'un restaurant tient en quelques centaines de lignes : un balayage
    # en Python coûte moins cher qu'une colonne normalisée à maintenir en base.
    cle = cle_comparaison(nom)
    for ingredient in Ingredient.objects.all():
        if cle_comparaison(ingredient.nom) == cle:
            return ingredient
    return None


def nomenclature():
    """Les ingrédients existants avec leur unité — le modèle que le LLM doit imiter."""
    return [f'{i.nom} ({i.unite.nom})'
            for i in Ingredient.objects.select_related('unite').all()]


def unites_autorisees():
    return list(Unite.objects.values_list('nom', flat=True))


def resoudre_unite(unite_nom):
    """L'unité réellement retenue pour `unite_nom`, et si elle a dû être corrigée.

    Le LLM sort parfois de la liste imposée (« pincée », « cuillère »…). On retombe sur
    l'unité par défaut — mais l'appelant doit pouvoir le DIRE à l'utilisateur, sinon
    l'aperçu afficherait une unité qui ne sera pas celle enregistrée.
    """
    unite = Unite.objects.filter(nom__iexact=(unite_nom or '').strip()).first()
    if unite:
        return unite, False
    return unite_par_defaut(), bool((unite_nom or '').strip())


def resoudre_ou_creer(nom, unite_nom=''):
    """Retourne (ingredient, cree)."""
    nom = normaliser_nom(nom)
    if not nom:
        return None, False

    existant = trouver(nom)
    if existant:
        return existant, False

    unite, _ = resoudre_unite(unite_nom)
    return Ingredient.objects.create(nom=nom, unite=unite), True
