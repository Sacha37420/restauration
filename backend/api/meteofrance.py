"""Client de l'API Météo-France « Données climatologiques » (DPClim) — relevés horaires
(température, nébulosité, précipitation) pour une ville, sur un mois ou une année.

Choix de la station, en six temps :
  1. le catalogue de TOUTES les stations horaires est mis en cache localement
     (l'API ne sait lister que département par département) ;
  2. la ville est géocodée en coordonnées via l'API Adresse ;
  3. la distance ville → station est calculée pour chaque station (Haversine) ;
  4. les stations sont triées par distance croissante ;
  5. on tente la plus proche ; si elle n'a pas de données sur la période, on passe à la
     suivante, et ainsi de suite ;
  6. la station finalement retenue est renvoyée et enregistrée avec les relevés.

Le point 5 est le nerf de l'affaire : rien, dans le catalogue, ne dit quelle période une
station couvre réellement. Une station « ouverte » et toute proche peut très bien n'avoir
aucune mesure sur le mois demandé. Il faut donc essayer pour savoir — et garder trace de
qui a répondu, sinon on ne sait pas d'où vient la donnée qu'on analyse.
"""
import calendar
import csv
import datetime as dt
import io
import math
import time

import requests

from .models import ConfigurationMeteo, StationMeteo

BASE = 'https://public-api.meteofrance.fr/public/DPClim/v1'
GEO = 'https://api-adresse.data.gouv.fr/search/'

# La Corse se demande sous le code « 20 » (2A/2B sont refusés par l'API).
# Mayotte (976) n'est pas exposée par DPClim.
DEPARTEMENTS = (
    [f'{n:02d}' for n in range(1, 20)]           # 01 → 19
    + ['20']                                      # Corse (2A + 2B)
    + [f'{n:02d}' for n in range(21, 96)]         # 21 → 95
    + ['971', '972', '973', '974', '975', '984', '986', '987', '988']
)

# Au-delà, la station est si lointaine que sa météo ne dit plus rien de la ville demandée.
MAX_STATIONS_ESSAYEES = 8

DELAI_ENTRE_APPELS = 0.4     # l'API est limitée en débit ; on ne la bombarde pas


class MeteoNonConfigure(Exception):
    pass


class MeteoErreur(Exception):
    pass


def _headers(key):
    return {'apikey': key, 'Accept': 'application/json'}


def _cle():
    cfg = ConfigurationMeteo.get()
    if not (cfg.actif and cfg.api_key):
        raise MeteoNonConfigure(
            "L'API Météo-France n'est pas configurée ou est désactivée (page Paramétrage).")
    return cfg.api_key


def _haversine(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau, en km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ── 1. Catalogue des stations ───────────────────────────────────────────────

def synchroniser_stations(progression=None):
    """Rapatrie le catalogue complet des stations horaires et le met en cache.

    ~100 appels (un par département) : opération lente, faite une fois. Un département qui
    échoue n'interrompt pas les autres — mieux vaut un catalogue incomplet que pas de
    catalogue du tout.
    """
    key = _cle()
    total, echecs = 0, []

    for departement in DEPARTEMENTS:
        try:
            r = requests.get(f'{BASE}/liste-stations/horaire',
                             params={'id-departement': departement},
                             headers=_headers(key), timeout=30)
            if r.status_code != 200:
                echecs.append(f'{departement} ({r.status_code})')
                continue
            stations = r.json()
        except (requests.RequestException, ValueError) as exc:
            echecs.append(f'{departement} ({type(exc).__name__})')
            continue

        for s in stations:
            if s.get('lat') is None or s.get('lon') is None:
                continue
            StationMeteo.objects.update_or_create(
                id_station=str(s['id']),
                defaults={
                    'nom': (s.get('nom') or '')[:120],
                    'departement': departement,
                    'lat': s['lat'],
                    'lon': s['lon'],
                    'altitude': s.get('alt'),
                    'poste_ouvert': bool(s.get('posteOuvert', True)),
                    'type_poste': s.get('typePoste'),
                },
            )
            total += 1

        if progression:
            progression(departement, total)
        time.sleep(DELAI_ENTRE_APPELS)

    return total, echecs


# ── 2. Ville → coordonnées ──────────────────────────────────────────────────

def geocoder(ville):
    """Coordonnées de la commune, via l'API Adresse (Base Adresse Nationale)."""
    r = requests.get(GEO, params={'q': ville, 'type': 'municipality', 'limit': 1}, timeout=20)
    r.raise_for_status()
    feats = r.json().get('features', [])
    if not feats:
        raise MeteoErreur(f'Ville introuvable : {ville}')
    lon, lat = feats[0]['geometry']['coordinates']   # GeoJSON : [lon, lat]
    return lat, lon


# ── 3 & 4. Distances et tri ─────────────────────────────────────────────────

def stations_par_distance(lat, lon, ouvertes_seulement=True):
    """Toutes les stations du cache, triées par distance croissante à la ville.

    Le tri n'est plus borné au département de la ville : une station du département voisin,
    plus proche, passe désormais devant — ce que l'ancienne implémentation ne permettait
    pas, alors que la météo se moque des frontières administratives.
    """
    qs = StationMeteo.objects.all()
    if ouvertes_seulement:
        qs = qs.filter(poste_ouvert=True)

    classees = [(_haversine(lat, lon, s.lat, s.lon), s) for s in qs]
    classees.sort(key=lambda couple: couple[0])
    return classees


# ── 5. Commande des données, station par station ────────────────────────────

def _commander(id_station, debut_iso, fin_iso, key):
    r = requests.get(f'{BASE}/commande-station/horaire',
                     params={'id-station': id_station,
                             'date-deb-periode': debut_iso, 'date-fin-periode': fin_iso},
                     headers=_headers(key), timeout=30)
    if r.status_code not in (200, 202):
        raise MeteoErreur(f'commande refusée ({r.status_code})')
    return r.json()['elaboreProduitAvecDemandeResponse']['return']


def _telecharger(id_cmde, key, max_essais=8, delai=5):
    for _ in range(max_essais):
        r = requests.get(f'{BASE}/commande/fichier',
                         params={'id-cmde': id_cmde}, headers=_headers(key), timeout=60)
        if r.status_code in (200, 201):
            return r.text
        if r.status_code in (204, 202):   # fichier encore en production
            time.sleep(delai)
            continue
        raise MeteoErreur(f'téléchargement ({r.status_code})')
    raise MeteoErreur("fichier non prêt après l'attente (production asynchrone)")


def _parser(csv_text, ville, station, distance):
    rows = []
    for row in csv.DictReader(io.StringIO(csv_text), delimiter=';'):
        brut = (row.get('DATE') or row.get('date') or '').strip()
        if not brut:
            continue
        try:
            ts = dt.datetime.strptime(brut, '%Y%m%d%H').replace(tzinfo=dt.timezone.utc)
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
            'station': station,
            'distance_km': round(distance, 1),
        })
    return rows


def _a_des_mesures(rows):
    """Un fichier peut être bien formé mais vide de toute mesure : la station existe, elle
    n'a simplement rien relevé sur la période. C'est un échec, pas un succès — sans cette
    vérification, on enregistrerait des centaines de lignes toutes nulles."""
    return any(r['temperature'] is not None
               or r['nebulosite'] is not None
               or r['precipitation'] is not None
               for r in rows)


def _periode(mois, annee):
    if mois:
        debut = dt.date(annee, int(mois), 1)
        fin = dt.date(annee, int(mois), calendar.monthrange(annee, int(mois))[1])
    else:
        debut = dt.date(annee, 1, 1)
        fin = dt.date(annee, 12, 31)
    return debut, fin


def recuperer(ville, mois, annee, max_stations=MAX_STATIONS_ESSAYEES):
    """Retourne (rows, debut, fin, station_retenue, distance_km, tentatives).

    On essaie les stations de la plus proche à la plus lointaine jusqu'à en trouver une qui
    ait effectivement des mesures sur la période. `tentatives` retrace tous les essais :
    c'est ce qui permet d'expliquer pourquoi la station retenue n'est pas la plus proche.
    """
    key = _cle()

    if not StationMeteo.objects.exists():
        raise MeteoErreur(
            'Le catalogue des stations est vide : lancez « Mettre à jour les stations » '
            'avant de récupérer des relevés.')

    lat, lon = geocoder(ville)
    classees = stations_par_distance(lat, lon)
    if not classees:
        raise MeteoErreur('Aucune station ouverte dans le catalogue.')

    debut, fin = _periode(mois, annee)
    debut_iso = debut.strftime('%Y-%m-%dT00:00:00Z')
    fin_iso = fin.strftime('%Y-%m-%dT23:00:00Z')

    tentatives = []
    for distance, station in classees[:max_stations]:
        essai = {'station': station.nom, 'id_station': station.id_station,
                 'distance_km': round(distance, 1)}
        try:
            id_cmde = _commander(station.id_station, debut_iso, fin_iso, key)
            texte = _telecharger(id_cmde, key)
            rows = _parser(texte, ville, station, distance)
        except MeteoErreur as exc:
            essai['echec'] = str(exc)
            tentatives.append(essai)
            continue

        if not _a_des_mesures(rows):
            essai['echec'] = 'aucune mesure sur la période'
            tentatives.append(essai)
            continue

        essai['retenue'] = True
        essai['releves'] = len(rows)
        tentatives.append(essai)
        return rows, debut, fin, station, round(distance, 1), tentatives

    detail = ' ; '.join(f"{t['station']} ({t['distance_km']} km) : {t.get('echec')}"
                        for t in tentatives)
    raise MeteoErreur(
        f'Aucune des {len(tentatives)} stations les plus proches de {ville} '
        f"n'a de données sur la période. Détail — {detail}")
