"""Appel à l'API Mistral pour proposer les événements impactant la
fréquentation d'une ville sur un mois/une année. Renvoie une liste de dicts
(non enregistrés — l'utilisateur valide avant sauvegarde)."""
import json

from .models import ConfigurationAgentEvenements


class AgentNonConfigure(Exception):
    pass


def proposer_evenements(ville: str, mois, annee: int) -> list[dict]:
    cfg = ConfigurationAgentEvenements.get()
    if not (cfg.actif and cfg.mistral_api_key):
        raise AgentNonConfigure(
            "L'agent Mistral n'est pas configuré ou est désactivé (page Paramétrage)."
        )

    from mistralai import Mistral  # import tardif : dépendance optionnelle

    periode = f'mois {mois} année {annee}' if mois else f'année {annee}'
    user_msg = f'Ville: {ville}\nPériode: {periode}'

    client = Mistral(api_key=cfg.mistral_api_key)
    resp = client.chat.complete(
        model=cfg.modele,
        messages=[
            {'role': 'system', 'content': cfg.system_prompt},
            {'role': 'user', 'content': user_msg},
        ],
        response_format={'type': 'json_object'},
        temperature=0.2,
    )
    contenu = resp.choices[0].message.content
    data = json.loads(contenu)

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
