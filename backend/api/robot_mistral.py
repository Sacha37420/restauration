"""Appels Mistral du robot de catalogue, et client partagé par tous les usages.

Les prompts ne sont plus écrits ici : ils vivent dans prompts.py (valeurs par défaut)
et peuvent être surchargés depuis la page Paramétrage (modèle PromptMistral). On les
relit à CHAQUE appel : une modification du prompt prend effet immédiatement, sans
redémarrage.
"""
import json
import time

from . import prompts
from .models import ConfigurationMistral, PromptMistral

# Délais entre deux tentatives, en secondes. Le rate limit Mistral se dégage vite ;
# inutile d'attendre longtemps, mais il faut attendre.
ATTENTES_RETRY = [3, 10, 30]


class RobotNonConfigure(Exception):
    pass


class RobotErreur(Exception):
    pass


def _client():
    cfg = ConfigurationMistral.get()
    if not (cfg.actif and cfg.api_key):
        raise RobotNonConfigure(
            "La clé Mistral n'est pas configurée ou Mistral est désactivé "
            '(page Paramétrage → Mistral).'
        )
    from mistralai import Mistral      # import tardif : dépendance optionnelle
    return Mistral(api_key=cfg.api_key), cfg.modele


def _est_transitoire(exc):
    """429 (rate limit) et 5xx : ça vaut la peine de réessayer. Une clé invalide, non."""
    texte = str(exc)
    return any(code in texte
               for code in ('429', '500', '502', '503', '504', 'timeout', 'Timeout'))


def completer(prompt_systeme, message):
    """Appelle Mistral et renvoie le JSON de la réponse.

    Un scan de catalogue enchaîne les appels : le rate limit (429) est une certitude,
    pas un aléa. On réessaie avec un délai croissant plutôt que de laisser une synchro
    de plusieurs minutes échouer sur une limite passagère.
    """
    client, modele = _client()
    derniere_erreur = None

    for attente in ATTENTES_RETRY + [None]:
        try:
            reponse = client.chat.complete(
                model=modele,
                messages=[
                    {'role': 'system', 'content': prompt_systeme},
                    {'role': 'user', 'content': message},
                ],
                response_format={'type': 'json_object'},
                temperature=0,      # on veut un comportement reproductible, pas créatif
            )
            return json.loads(reponse.choices[0].message.content)
        except json.JSONDecodeError as exc:
            raise RobotErreur(f'Réponse Mistral illisible : {exc}') from exc
        except Exception as exc:                       # noqa: BLE001
            derniere_erreur = exc
            if attente is None or not _est_transitoire(exc):
                break
            time.sleep(attente)

    raise RobotErreur(
        f'Appel Mistral en échec après {len(ATTENTES_RETRY) + 1} tentatives : '
        f'{derniere_erreur}'
    )


def _demander(usage, url, html_elague, indice=''):
    message = f'URL : {url}\n'
    if indice:
        message += f'Remarque : {indice}\n'
    message += f'\nHTML de la page (élagué) :\n{html_elague}'
    return completer(PromptMistral.texte(usage), message)


def analyser_obstacles(url, html_elague, indice=''):
    """Étape 0 — qu'est-ce qui empêche de lire la page (cookies, magasin, âge, modale) ?"""
    return _demander(prompts.ROBOT_OBSTACLES, url, html_elague, indice)


def analyser_connexion(url, html_elague, indice=''):
    """Étape 1 — où et comment se connecter ?"""
    return _demander(prompts.ROBOT_CONNEXION, url, html_elague, indice)


def analyser_navigation(url, html_elague, indice=''):
    """Étape 2 — comment atteindre la liste des produits ?"""
    return _demander(prompts.ROBOT_NAVIGATION, url, html_elague, indice)


def analyser_extraction(url, html_elague, indice=''):
    """Étape 3 — comment extraire les produits et passer à la page suivante ?"""
    return _demander(prompts.ROBOT_EXTRACTION, url, html_elague, indice)


def rapprocher_produits(produits, ingredients, unites):
    """Étape 4 — à quel ingrédient rattacher chaque produit rapporté ?

    `produits` : [{'id', 'libelle', 'marque', 'conditionnement'}]
    `ingredients` : ['Tomate (g)', 'Oeuf (pièce)', …] — la nomenclature à imiter
    `unites` : ['g', 'kg', 'L', 'pièce', …]
    """
    message = (
        f'Ingrédients existants : {json.dumps(ingredients, ensure_ascii=False)}\n'
        f'Unités autorisées : {json.dumps(unites, ensure_ascii=False)}\n\n'
        f'Produits à rattacher :\n{json.dumps(produits, ensure_ascii=False, indent=1)}'
    )
    return completer(PromptMistral.texte(prompts.ROBOT_RAPPROCHEMENT), message)
