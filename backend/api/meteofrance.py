"""Client de l'API Météo-France « Données climatologiques » (DPClim) — relevés
horaires (température, nébulosité, précipitation) pour la station la plus proche
d'une ville, sur un mois ou une année.

Flux asynchrone : géocodage ville → station la plus proche → commande du fichier
→ polling jusqu'à disponibilité → parsing CSV.
"""
import calendar
import csv
import datetime as dt
import io
import math
import time

import requests

from .models import ConfigurationMeteo

BASE = 'https://public-api.meteofrance.fr/public/DPClim/v1'
GEO = 'https://api-adresse.data.gouv.fr/search/'


class MeteoNonConfigure(Exception):
    pass


class MeteoErreur(Exception):
    pass


def _headers(key):
    return {'apikey': key, 'Accept': 'application/json'}


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _geocode(ville):
    r = requests.get(GEO, params={'q': ville, 'type': 'municipality', 'limit': 1}, timeout=20)
    r.raise_for_status()
    feats = r.json().get('features', [])
    if not feats:
        raise MeteoErreur(f'Ville introuvable : {ville}')
    f = feats[0]
    lon, lat = f['geometry']['coordinates']
    citycode = f['properties'].get('citycode', '')
    dept = citycode[:3] if citycode[:2] in ('97', '98') else citycode[:2]
    return lat, lon, dept


def _station_la_plus_proche(dept, lat, lon, key):
    r = requests.get(f'{BASE}/liste-stations/horaire',
                     params={'id-departement': dept}, headers=_headers(key), timeout=30)
    if r.status_code != 200:
        raise MeteoErreur(f'liste-stations ({r.status_code}) : {r.text[:200]}')
    stations = r.json()
    meilleure, meilleure_d = None, float('inf')
    for s in stations:
        slat, slon = s.get('lat'), s.get('lon')
        if slat is None or slon is None:
            continue
        d = _haversine(lat, lon, slat, slon)
        if d < meilleure_d:
            meilleure_d, meilleure = d, s
    if not meilleure:
        raise MeteoErreur(f'Aucune station horaire trouvée pour le département {dept}.')
    return meilleure['id']


def _commander(station, debut_iso, fin_iso, key):
    r = requests.get(f'{BASE}/commande-station/horaire',
                     params={'id-station': station, 'date-deb-periode': debut_iso, 'date-fin-periode': fin_iso},
                     headers=_headers(key), timeout=30)
    if r.status_code not in (200, 202):
        raise MeteoErreur(f'Commande refusée ({r.status_code}) : {r.text[:200]}')
    return r.json()['elaboreProduitAvecDemandeResponse']['return']


def _telecharger(id_cmde, key, max_essais=8, delai=5):
    for _ in range(max_essais):
        r = requests.get(f'{BASE}/commande/fichier',
                         params={'id-cmde': id_cmde}, headers=_headers(key), timeout=60)
        if r.status_code in (200, 201):
            return r.text
        if r.status_code in (204, 202):   # en cours de production
            time.sleep(delai)
            continue
        raise MeteoErreur(f'Téléchargement ({r.status_code}) : {r.text[:200]}')
    raise MeteoErreur(
        "Le fichier Météo-France n'était pas prêt après l'attente. "
        'Réessayez dans une minute (la production est asynchrone).'
    )


def _parser(csv_text, ville):
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=';')
    for row in reader:
        d = (row.get('DATE') or row.get('date') or '').strip()
        if not d:
            continue
        try:
            ts = dt.datetime.strptime(d, '%Y%m%d%H').replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue

        def num(*cles):
            for k in cles:
                v = (row.get(k) or '').replace(',', '.').strip()
                if v:
                    try:
                        return float(v)
                    except ValueError:
                        pass
            return None

        rows.append({
            'ville': ville,
            'horodatage': ts,
            'temperature': num('T'),
            'nebulosite': num('N', 'NBAS'),
            'precipitation': num('RR1'),
            'source': 'meteofrance',
        })
    return rows


def recuperer(ville, mois, annee):
    """Retourne (rows, date_debut, date_fin). rows = liste de dicts prêts pour
    DonneeMeteoHoraire. Lève MeteoNonConfigure / MeteoErreur en cas de problème."""
    cfg = ConfigurationMeteo.get()
    if not (cfg.actif and cfg.api_key):
        raise MeteoNonConfigure("L'API Météo-France n'est pas configurée ou est désactivée (page Paramétrage).")

    lat, lon, dept = _geocode(ville)
    station = _station_la_plus_proche(dept, lat, lon, cfg.api_key)

    if mois:
        debut = dt.date(annee, int(mois), 1)
        fin = dt.date(annee, int(mois), calendar.monthrange(annee, int(mois))[1])
    else:
        debut = dt.date(annee, 1, 1)
        fin = dt.date(annee, 12, 31)

    debut_iso = debut.strftime('%Y-%m-%dT00:00:00Z')
    fin_iso = fin.strftime('%Y-%m-%dT23:00:00Z')

    id_cmde = _commander(station, debut_iso, fin_iso, cfg.api_key)
    texte = _telecharger(id_cmde, cfg.api_key)
    return _parser(texte, ville), debut, fin
