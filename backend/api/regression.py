"""Régression linéaire (OLS) entre les ventes et les indicateurs climatiques +
le surplus de fréquentation, jour par jour, pour une ville/période.

Cible : montant_ht, montant_ttc ou quantite — globale ou par catégorie.
"""
import datetime as dt
import math
from collections import defaultdict

from .models import DonneeMeteoHoraire, IndicateurMeteoConfig, Evenement, VenteAgregee
from .ventes import _periode

CIBLES = {'montant_ht', 'montant_ttc', 'quantite'}


def _agreger(agregation, valeurs):
    valeurs = [v for v in valeurs if v is not None]
    if not valeurs:
        return None
    if agregation == 'moyenne':
        return sum(valeurs) / len(valeurs)
    if agregation == 'min':
        return min(valeurs)
    if agregation == 'max':
        return max(valeurs)
    if agregation == 'somme':
        return sum(valeurs)
    if agregation == 'amplitude':
        return max(valeurs) - min(valeurs)
    return None


def _arrondi(x):
    return round(float(x), 4) if x is not None and math.isfinite(x) else None


def _indicateurs_par_jour(ville, debut, fin):
    qs = DonneeMeteoHoraire.objects.filter(
        ville__iexact=ville, horodatage__date__gte=debut, horodatage__date__lte=fin)
    configs = list(IndicateurMeteoConfig.objects.filter(actif=True))
    par_jour = defaultdict(list)
    for d in qs:
        par_jour[d.horodatage.date()].append(d)
    valeurs = {}
    for jour, releves in par_jour.items():
        vals = {}
        for c in configs:
            xs = [getattr(r, c.champ) for r in releves if c.heure_debut <= r.horodatage.hour <= c.heure_fin]
            vals[c.nom] = _agreger(c.agregation, xs)
        valeurs[jour] = vals
    return [c.nom for c in configs], valeurs


def _surplus_par_jour(ville, debut, fin):
    surplus = defaultdict(int)
    for e in Evenement.objects.filter(ville__iexact=ville, date_debut__lte=fin, date_fin__gte=debut):
        jour = max(e.date_debut, debut)
        derniere = min(e.date_fin, fin)
        while jour <= derniere:
            surplus[jour] += e.surplus_frequentation or 0
            jour += dt.timedelta(days=1)
    return surplus


def _ventes_par_jour(debut, fin, categorie_id, cible, source):
    qs = VenteAgregee.objects.filter(date__gte=debut, date__lte=fin)
    qs = qs.filter(categorie_id=categorie_id) if categorie_id else qs.filter(categorie__isnull=True)
    if source:
        qs = qs.filter(source=source)
    out = defaultdict(float)
    for v in qs:
        out[v.date] += float(getattr(v, cible))
    return out


def lancer(ville, annee, mois, cible, categorie_id=None, source=None):
    if cible not in CIBLES:
        raise ValueError(f'Cible invalide : {cible}')
    debut, fin = _periode(annee, mois)
    noms_ind, ind_jour = _indicateurs_par_jour(ville, debut, fin)
    surplus = _surplus_par_jour(ville, debut, fin)
    ventes = _ventes_par_jour(debut, fin, categorie_id, cible, source)

    features = noms_ind + ['surplus_frequentation']
    X, y = [], []
    for jour, cible_val in sorted(ventes.items()):
        vals = ind_jour.get(jour, {})
        ligne = []
        complet = True
        for nom in noms_ind:
            x = vals.get(nom)
            if x is None:
                complet = False
                break
            ligne.append(x)
        if not complet:
            continue
        ligne.append(surplus.get(jour, 0))
        X.append(ligne)
        y.append(cible_val)

    n, k = len(y), len(features)
    base = {'cible': cible, 'n': n, 'features': features,
            'r2': None, 'r2_adj': None, 'f_pvalue': None, 'coefficients': []}

    if k == 0:
        return {**base, 'viable': False,
                'verdict': "Aucune variable explicative : définis des indicateurs météo (page Météo) "
                           "et/ou renseigne des événements."}
    if n < k + 2:
        return {**base, 'viable': False,
                'verdict': f'Données insuffisantes : {n} jour(s) exploitable(s) pour {k} variable(s) '
                           f'(il en faut au moins {k + 2}). Récupère plus de données météo/ventes.'}

    import numpy as np
    import statsmodels.api as sm

    Xa = sm.add_constant(np.array(X, dtype=float))
    res = sm.OLS(np.array(y, dtype=float), Xa).fit()

    noms = ['(constante)'] + features
    coefficients = []
    for i, nom in enumerate(noms):
        p = float(res.pvalues[i])
        coefficients.append({
            'nom': nom,
            'coef': _arrondi(res.params[i]),
            'p_value': _arrondi(p),
            'significatif': bool(math.isfinite(p) and p < 0.05),
        })

    r2 = float(res.rsquared)
    fp = float(res.f_pvalue)
    significatif = math.isfinite(fp) and fp < 0.05
    explicatif = math.isfinite(r2) and r2 >= 0.5
    viable = bool(significatif and explicatif)
    if not significatif:
        verdict = 'Non viable — aucune relation statistiquement significative (p ≥ 0,05).'
    elif not explicatif:
        verdict = 'Significative mais faible pouvoir explicatif (R² < 0,5) : à interpréter avec prudence.'
    else:
        verdict = 'Viable — relation statistiquement significative et explicative.'

    return {**base, 'r2': _arrondi(r2), 'r2_adj': _arrondi(res.rsquared_adj),
            'f_pvalue': _arrondi(fp), 'viable': viable, 'verdict': verdict,
            'coefficients': coefficients}
