"""Appel à l'API Mistral pour proposer les événements impactant la
fréquentation d'une ville sur un mois/une année. Renvoie une liste de dicts
(non enregistrés — l'utilisateur valide avant sauvegarde).

Passe désormais par le client partagé (clé, modèle et retry communs à tous les usages
de Mistral) et par le prompt modifiable en Paramétrage.
"""
from . import prompts
from .models import PromptMistral
from .robot_mistral import RobotErreur, RobotNonConfigure, completer


class AgentNonConfigure(Exception):
    pass


def proposer_evenements(ville: str, mois, annee: int) -> list[dict]:
    periode = f'mois {mois} année {annee}' if mois else f'année {annee}'
    message = f'Ville: {ville}\nPériode: {periode}'

    try:
        data = completer(PromptMistral.texte(prompts.EVENEMENTS), message)
    except RobotNonConfigure as exc:
        raise AgentNonConfigure(str(exc)) from exc
    except RobotErreur as exc:
        raise AgentNonConfigure(str(exc)) from exc

    evenements = []
    for e in data.get('evenements', []):
        evenements.append({
            'ville': ville,
            'titre': e.get('titre', ''),
            'date_debut': e.get('date_debut'),
            'date_fin': e.get('date_fin') or e.get('date_debut'),
            'surplus_frequentation': int(e.get('surplus_frequentation') or 0),
            'confiance': e.get('confiance', ''),
            'source': 'mistral',
        })
    return evenements
