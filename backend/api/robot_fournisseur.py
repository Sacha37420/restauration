"""Robot de catalogue : pilote un navigateur sur le portail d'un fournisseur,
guidé par Mistral, et en rapporte les produits et leurs prix.

Déroulé (cf. robot_mistral pour les questions posées au LLM) :
  1. connexion   — seulement si un identifiant ET un mot de passe sont renseignés ;
  2. navigation  — jusqu'à la liste des produits ;
  3. extraction  — les produits page par page, jusqu'à la dernière.

Deux principes gouvernent tout le fichier :

* **Les sélecteurs sont mis en cache.** Mistral n'est appelé que si l'on ne connaît
  pas encore les XPath du site, ou si ceux qu'on connaît ne résolvent plus. Une
  synchro de routine sur un site inchangé coûte donc *zéro* appel LLM.
* **Rien n'est écrit dans le référentiel.** Le robot crée des ArticleFournisseur et
  des PrixArticle avec source='robot', laisse `ingredient` à NULL et ne touche jamais
  au stock : le rattachement à un ingrédient reste une validation humaine.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation

from django.db import connection
from django.utils import timezone

from .models import (
    ArticleFournisseur, PrixArticle, SelecteursCatalogue, SynchroCatalogue, Unite,
)
from .nomenclature import nomenclature, resoudre_ou_creer, unite_par_defaut
from .robot_dom import elaguer
from .robot_mistral import (
    RobotErreur, RobotNonConfigure,
    analyser_obstacles, analyser_connexion, analyser_navigation, analyser_extraction,
    rapprocher_produits,
)

# Garde-fous : un site mal compris ne doit jamais faire tourner le robot indéfiniment.
MAX_ETAPES_NAVIGATION = 6
# Choisir un magasin demande plusieurs actions (ouvrir, saisir, commune, magasin),
# auxquelles peuvent s'ajouter cookies et modales.
MAX_OBSTACLES = 8
MAX_PAGES_PRODUITS = 50
TAILLE_LOT_RAPPROCHEMENT = 25   # articles par appel Mistral : 30 produits = 2 appels, pas 30
DELAI_ENTRE_PAGES = 1.0        # politesse : on n'inonde pas le serveur du fournisseur
TIMEOUT_MS = 20_000
CLIC_TIMEOUT_MS = 8_000    # un clic intercepté doit échouer vite, pour laisser sa chance au clic forcé

NAVIGATEUR_UA = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/125.0.0.0 Safari/537.36'
)

_RE_NOMBRE = re.compile(r'(\d+(?:[.,]\d+)?)')

# Un XPath terminé par /@href désigne un *nœud attribut*, pas un élément.
_RE_ATTRIBUT_FINAL = re.compile(r'/@[\w:.-]+\s*$')

_CLES_XPATH = (
    'xpath_identifiant', 'xpath_mot_de_passe', 'xpath_valider',
    'xpath_clic', 'xpath_produit', 'xpath_page_suivante',
)


def _normaliser_xpath(xpath):
    """Ramène un XPath sur l'élément porteur.

    Le LLM propose volontiers `//a[@class="suivant"]/@href` pour désigner un lien.
    Or Playwright ne sait ni cliquer un nœud attribut, ni en lire le texte : le
    sélecteur serait déclaré invalide et le lien réputé absent. On retire donc le
    `/@attribut` final — c'est le code qui lira l'attribut ensuite (cf. _texte).
    Le prompt l'interdit déjà, mais on ne se repose pas sur la docilité du modèle.
    """
    if not xpath:
        return ''
    return _RE_ATTRIBUT_FINAL.sub('', xpath.strip())


def _normaliser_analyse(resultat):
    """Nettoie tous les XPath d'une réponse Mistral, quel que soit le prompt."""
    for cle in _CLES_XPATH:
        if cle in resultat:
            resultat[cle] = _normaliser_xpath(resultat.get(cle))

    champs = resultat.get('champs')
    if isinstance(champs, dict):
        resultat['champs'] = {
            nom: _normaliser_xpath(xpath)
            for nom, xpath in champs.items()
            if _normaliser_xpath(xpath)
        }
    return resultat


# ── Passerelle ORM ──────────────────────────────────────────────────────────

class Base:
    """Exécute les accès base dans un thread dédié.

    L'API synchrone de Playwright fait tourner une boucle asyncio dans le thread
    courant. Django y détecte un « contexte async » et refuse alors tout accès ORM
    (SynchronousOnlyOperation) — y compris pour du code parfaitement synchrone comme
    le nôtre. Plutôt que de désactiver la garde globalement (DJANGO_ALLOW_ASYNC_UNSAFE,
    qui masquerait de vrais bugs ailleurs dans l'application), on déporte chaque
    opération dans un thread sans boucle d'événements : vraie connexion, vrai ORM
    synchrone, et le suivi en direct de la synchro reste possible.
    """

    def __init__(self):
        self._executeur = ThreadPoolExecutor(max_workers=1, thread_name_prefix='robot-db')

    def __call__(self, fonction, *args, **kwargs):
        return self._executeur.submit(fonction, *args, **kwargs).result()

    def fermer(self):
        # `connection` est un proxy thread-local : il doit être résolu DANS le thread
        # worker, sinon on tenterait de fermer la connexion d'un autre thread.
        self._executeur.submit(lambda: connection.close()).result()   # noqa: PLW0108
        self._executeur.shutdown(wait=True)


# ── Utilitaires page ────────────────────────────────────────────────────────

def _valide(page, xpath):
    """Un XPath n'est digne de confiance que s'il résout sur la page réelle.
    C'est le filet qui rattrape les hallucinations du LLM et les sites qui changent."""
    if not xpath:
        return False
    try:
        return page.locator(f'xpath={xpath}').count() > 0
    except Exception:
        return False


def _cliquer(page, xpath):
    """Clique, en deux tentatives.

    Un bandeau de cookies ou une modale recouvre la page et INTERCEPTE le clic : Playwright
    attend alors indéfiniment que la cible devienne « actionnable » et finit en timeout.
    D'où la seconde tentative en `force` — on clique aux coordonnées de l'élément sans
    exiger qu'il soit au premier plan.
    """
    if not _valide(page, xpath):
        return False

    cible = page.locator(f'xpath={xpath}').first
    for force in (False, True):
        try:
            if not force:
                cible.scroll_into_view_if_needed(timeout=CLIC_TIMEOUT_MS)
            cible.click(timeout=CLIC_TIMEOUT_MS, force=force)
            page.wait_for_load_state('domcontentloaded')
            time.sleep(DELAI_ENTRE_PAGES)
            return True
        except Exception:
            continue
    return False


def _texte(carte, xpath_relatif, champ):
    try:
        cible = carte.locator(f'xpath={xpath_relatif}')
        if cible.count() == 0:
            return ''
        if champ == 'url':
            return (cible.first.get_attribute('href') or '').strip()
        return (cible.first.inner_text() or '').strip()
    except Exception:
        return ''


def _parser_prix(texte):
    """« 12,50 € HT » → Decimal('12.50'). None si aucun nombre n'est lisible."""
    if not texte:
        return None
    nettoye = texte.replace(' ', '').replace('\xa0', '').replace(' ', '')
    trouve = _RE_NOMBRE.search(nettoye)
    if not trouve:
        return None
    try:
        return Decimal(trouve.group(1).replace(',', '.'))
    except InvalidOperation:
        return None


def _unite_par_defaut():
    """Le robot ne peut pas deviner l'unité de mesure : il rattache tout à « pièce »,
    à charge pour l'humain (ou pour l'étape de rattachement) de corriger."""
    return unite_par_defaut()


# ── Dialogue avec Mistral ───────────────────────────────────────────────────

def _etape(db, synchro, libelle):
    synchro.etape = libelle
    db(synchro.tracer, libelle)


def _appeler_mistral(db, synchro, fonction, page, contexte=''):
    html = elaguer(page.content())
    synchro.appels_mistral += 1
    # L'appel part par la passerelle : robot_mistral lit la clé en base (ConfigurationMistral).
    resultat = _normaliser_analyse(db(fonction, page.url, html, contexte))
    raison = (resultat.get('raison') or '')[:160]
    db(synchro.tracer, f'  ↳ Mistral : {resultat.get("etat", "ok")} — {raison}')
    return resultat


# ── Étape 0 : lever les obstacles ───────────────────────────────────────────

def _saisir(page, xpath, valeur):
    """Remplit un champ puis valide. Beaucoup de sélecteurs de magasin proposent une
    autocomplétion : on la laisse s'afficher et on prend la première suggestion, ce qui
    est plus fiable que de cliquer un <li> dont le texte est éclaté."""
    if not _valide(page, xpath) or not valeur:
        return False
    try:
        champ = page.locator(f'xpath={xpath}').first
        champ.click()
        champ.fill('')
        champ.type(valeur, delay=100)
        page.wait_for_timeout(3000)          # laisser venir l'autocomplétion
        page.keyboard.press('ArrowDown')
        page.keyboard.press('Enter')
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(3000)
        return True
    except Exception:
        return False


def _preparer(db, page, synchro, fournisseur, moment):
    """Lève ce qui empêche de LIRE la page : bandeau cookies, pop-in, porte d'âge, et
    surtout le choix d'un magasin — sans lequel certains sites n'affichent aucun prix.

    Sans cette étape, le robot « voit » une page que l'utilisateur ne voit jamais : c'est
    ainsi qu'un scan d'Auchan rapportait 30 produits sans aucun tarif, en silence.

    Le tunnel de choix d'un magasin demande plusieurs actions successives (ouvrir, saisir
    le code postal, choisir la commune, choisir le magasin) : on boucle, en redonnant la
    page à Mistral après chaque action.
    """
    historique = []
    for _ in range(MAX_OBSTACLES):
        analyse = _appeler_mistral(
            db, synchro, analyser_obstacles, page,
            contexte=_contexte_obstacles(fournisseur, historique))
        obstacle = analyse.get('obstacle')
        if obstacle in (None, '', 'aucun'):
            return

        action = analyse.get('action') or 'cliquer'
        if action == 'saisir':
            valeur = fournisseur.code_postal if analyse.get('valeur') == 'code_postal' \
                else (analyse.get('valeur') or '')
            xpath = analyse.get('xpath_saisie', '')
            ok = _saisir(page, xpath, valeur)
            detail = f'saisie « {valeur} »'
        else:
            xpath = analyse.get('xpath_clic', '')
            ok = _cliquer(page, xpath)
            detail = 'clic'

        if not ok:
            db(synchro.tracer,
               f'  ⚠ Obstacle « {obstacle} » repéré mais {detail} impossible : on continue sans le lever.')
            return

        # Chaque appel à Mistral est sans mémoire : sans cet historique, il repropose
        # indéfiniment la première étape du tunnel sans jamais voir qu'elle est franchie.
        trace = f'{action} sur {xpath}'
        if trace in historique:
            db(synchro.tracer,
               f'  ⚠ Le tunnel « {obstacle} » n’avance plus (même action répétée) : on abandonne.')
            return
        historique.append(trace)
        db(synchro.tracer, f'  ↳ Obstacle « {obstacle} » — {detail} ({moment}).')

    db(synchro.tracer,
       f'  ⚠ Obstacles toujours présents après {MAX_OBSTACLES} actions : on continue quand même.')


def _contexte_obstacles(fournisseur, historique):
    lignes = []
    if fournisseur.code_postal:
        lignes.append(f'Code postal du restaurant : {fournisseur.code_postal}')
    else:
        lignes.append("Aucun code postal renseigné : si le site exige de choisir un "
                      "magasin, on ne pourra pas aller au bout.")

    if historique:
        lignes.append(
            'Actions DÉJÀ effectuées sur cette page, dans l’ordre (ne les refais pas — '
            'passe à l’étape SUIVANTE du tunnel) :')
        lignes.extend(f'  {i}. {a}' for i, a in enumerate(historique, 1))
    return '\n'.join(lignes)


# ── Étape 1 : connexion ─────────────────────────────────────────────────────

def _remplir_connexion(page, fournisseur, selecteurs):
    """Renseigne le formulaire et valide. Retourne True si la connexion a pris."""
    for xpath in (selecteurs.xpath_identifiant, selecteurs.xpath_mot_de_passe,
                  selecteurs.xpath_valider):
        if not _valide(page, xpath):
            return False
    try:
        page.locator(f'xpath={selecteurs.xpath_identifiant}').first.fill(fournisseur.identifiant)
        page.locator(f'xpath={selecteurs.xpath_mot_de_passe}').first.fill(fournisseur.mot_de_passe)
        page.locator(f'xpath={selecteurs.xpath_valider}').first.click()
        page.wait_for_load_state('domcontentloaded')
        time.sleep(DELAI_ENTRE_PAGES)
    except Exception:
        return False

    # Si le champ mot de passe est toujours là, c'est que la connexion a échoué
    # (mauvais identifiants, captcha, 2FA…).
    return not _valide(page, selecteurs.xpath_mot_de_passe)


def _connecter(db, page, synchro, fournisseur, selecteurs):
    if selecteurs.connexion_prete:
        _etape(db, synchro, 'Connexion (sélecteurs en cache)')
        try:
            page.goto(selecteurs.url_connexion, wait_until='domcontentloaded')
        except Exception:
            pass
        if _remplir_connexion(page, fournisseur, selecteurs):
            db(synchro.tracer, '  ↳ Connecté sans appel Mistral (sélecteurs en cache).')
            return
        db(synchro.tracer, '  ↳ Les sélecteurs en cache ne fonctionnent plus → redécouverte.')

    _etape(db, synchro, 'Recherche de la page de connexion (Mistral)')
    vues = set()
    for _ in range(MAX_ETAPES_NAVIGATION):
        vues.add(page.url)
        analyse = _appeler_mistral(db, synchro, analyser_connexion, page)
        etat = analyse.get('etat')

        if etat == 'deja_connecte':
            db(synchro.tracer, '  ↳ Session déjà authentifiée.')
            return

        if etat == 'page_connexion':
            selecteurs.url_connexion = page.url
            selecteurs.xpath_identifiant = analyse.get('xpath_identifiant', '')
            selecteurs.xpath_mot_de_passe = analyse.get('xpath_mot_de_passe', '')
            selecteurs.xpath_valider = analyse.get('xpath_valider', '')
            if not _remplir_connexion(page, fournisseur, selecteurs):
                raise RobotErreur(
                    'Formulaire de connexion trouvé, mais la connexion a échoué. '
                    'Vérifiez identifiant/mot de passe (ou un captcha bloque le robot).'
                )
            selecteurs.decouvert_le = timezone.now()
            db(selecteurs.save)
            db(synchro.tracer, '  ↳ Connecté. Sélecteurs mis en cache.')
            return

        if etat == 'lien_connexion':
            xpath = analyse.get('xpath_clic', '')
            if not _cliquer(page, xpath):
                raise RobotErreur(
                    f"Impossible de cliquer sur le lien de connexion proposé : {xpath!r}")
            if page.url in vues:
                raise RobotErreur('La navigation vers la connexion tourne en rond.')
            continue

        raise RobotErreur(
            f"Mistral n'a pas trouvé comment se connecter : {analyse.get('raison', '')}")

    raise RobotErreur(
        f'Page de connexion non atteinte après {MAX_ETAPES_NAVIGATION} étapes.')


# ── Étape 2 : navigation jusqu'au catalogue ─────────────────────────────────

def _atteindre_produits(db, page, synchro, selecteurs):
    if selecteurs.url_produits:
        _etape(db, synchro, 'Ouverture du catalogue (URL en cache)')
        try:
            page.goto(selecteurs.url_produits, wait_until='domcontentloaded')
            if _valide(page, selecteurs.xpath_produit):
                db(synchro.tracer, '  ↳ Catalogue atteint sans appel Mistral.')
                return
        except Exception:
            pass
        db(synchro.tracer, "  ↳ L'URL en cache ne donne plus la liste → redécouverte.")

    _etape(db, synchro, 'Recherche de la liste des produits (Mistral)')
    vues = set()
    for _ in range(MAX_ETAPES_NAVIGATION):
        vues.add(page.url)
        analyse = _appeler_mistral(db, synchro, analyser_navigation, page)
        etat = analyse.get('etat')

        if etat == 'liste_produits':
            selecteurs.url_produits = page.url
            db(selecteurs.save)
            db(synchro.tracer, f'  ↳ Liste des produits atteinte : {page.url}')
            return

        if etat == 'lien':
            xpath = analyse.get('xpath_clic', '')
            if not _cliquer(page, xpath):
                raise RobotErreur(
                    f'Impossible de cliquer sur le lien catalogue proposé : {xpath!r}')
            if page.url in vues:
                raise RobotErreur('La navigation vers le catalogue tourne en rond.')
            continue

        raise RobotErreur(
            f"Mistral n'a pas trouvé la liste des produits : {analyse.get('raison', '')}")

    raise RobotErreur(
        f'Liste des produits non atteinte après {MAX_ETAPES_NAVIGATION} étapes.')


# ── Étape 3 : extraction ────────────────────────────────────────────────────

def _enregistrer(fournisseur, donnees, unite, synchro):
    """Crée ou met à jour l'article, et ajoute un relevé de prix si le prix a bougé.
    Ne touche jamais au champ `ingredient` : le mapping appartient à l'humain."""
    libelle = (donnees.get('libelle') or '').strip()[:255]
    if not libelle:
        return

    reference = (donnees.get('reference') or '').strip()[:100]
    marque = (donnees.get('marque') or '').strip()[:120]
    conditionnement = (donnees.get('conditionnement') or '').strip()[:100]
    ean = (donnees.get('ean') or '').strip()[:14]
    url = (donnees.get('url') or '').strip()[:500]

    commun = {
        'libelle': libelle,
        'marque': marque,
        'conditionnement': conditionnement,
        'ean': ean,
        'url': url,
        'unite': unite,
        'disponible': True,
        'source': 'robot',
        'synchronise_le': timezone.now(),
    }

    if reference:
        # La référence fournisseur est l'identité la plus fiable (cf. contrainte d'unicité).
        article, cree = ArticleFournisseur.objects.get_or_create(
            fournisseur=fournisseur, reference=reference, defaults=commun)
    else:
        article, cree = ArticleFournisseur.objects.get_or_create(
            fournisseur=fournisseur, libelle=libelle, marque=marque,
            conditionnement=conditionnement, defaults=commun)

    if not cree:
        for champ, valeur in commun.items():
            setattr(article, champ, valeur)
        article.save()
        synchro.articles_maj += 1
    else:
        synchro.articles_crees += 1

    prix = _parser_prix(donnees.get('prix_ht') or '')
    if prix is None:
        return
    dernier = article.prix_applicable(1)
    if dernier is None or dernier.prix_ht != prix:
        PrixArticle.objects.create(
            article=article, quantite_min=1, prix_ht=prix, source='robot')
        synchro.prix_releves += 1


def _extraire_page(db, page, synchro, fournisseur, selecteurs, unite):
    cartes = page.locator(f'xpath={selecteurs.xpath_produit}')
    nombre = cartes.count()
    for i in range(nombre):
        carte = cartes.nth(i)
        donnees = {
            champ: _texte(carte, xpath_relatif, champ)
            for champ, xpath_relatif in (selecteurs.champs or {}).items()
        }
        db(_enregistrer, fournisseur, donnees, unite, synchro)
    return nombre


def _extraire(db, page, synchro, fournisseur, selecteurs):
    unite = db(_unite_par_defaut)
    pages = 0

    while pages < MAX_PAGES_PRODUITS:
        # On ne rappelle Mistral que si l'on ne sait pas extraire, ou si le sélecteur
        # connu ne résout plus (le site a changé) : le robot se répare tout seul.
        if not (selecteurs.extraction_prete and _valide(page, selecteurs.xpath_produit)):
            _etape(db, synchro, 'Analyse de la liste des produits (Mistral)')
            analyse = _appeler_mistral(db, synchro, analyser_extraction, page)
            selecteurs.xpath_produit = analyse.get('xpath_produit', '')
            selecteurs.champs = analyse.get('champs') or {}
            selecteurs.xpath_page_suivante = analyse.get('xpath_page_suivante', '')
            selecteurs.url_produits = selecteurs.url_produits or page.url
            selecteurs.decouvert_le = timezone.now()
            db(selecteurs.save)

            if not _valide(page, selecteurs.xpath_produit):
                raise RobotErreur(
                    'Le XPath produit proposé par Mistral ne sélectionne rien sur la page.')
            if not (selecteurs.champs or {}).get('libelle'):
                raise RobotErreur("Mistral n'a pas identifié le libellé des produits.")

            # Un catalogue sans prix ne sert à rien : il faut le DIRE, pas rapporter
            # 30 articles muets et laisser l'utilisateur chercher pourquoi.
            if analyse.get('prix_indisponible') or not (selecteurs.champs or {}).get('prix_ht'):
                raison = (analyse.get('raison') or '')[:200]
                db(synchro.tracer,
                   '  ⚠ AUCUN PRIX sur cette page — les articles seront rapportés sans tarif. '
                   f'{raison}')

        pages += 1
        synchro.pages_scannees += 1
        trouves = _extraire_page(db, page, synchro, fournisseur, selecteurs, unite)
        _etape(db, synchro, f'Page {pages} — {trouves} produits extraits')

        suivante = selecteurs.xpath_page_suivante
        if not _valide(page, suivante):
            db(synchro.tracer, '  ↳ Pas de page suivante : dernière page atteinte.')
            break
        if not _cliquer(page, suivante):
            db(synchro.tracer, '  ↳ Le lien « page suivante » ne répond plus : on arrête là.')
            break
    else:
        db(synchro.tracer,
           f'  ↳ Arrêt de sécurité : {MAX_PAGES_PRODUITS} pages atteintes.')


# ── Étape 4 : rattachement aux ingrédients ──────────────────────────────────

def _orphelins(fournisseur):
    """Seuls les articles non rattachés sont candidats : on ne défait jamais un
    rattachement décidé par un humain."""
    return list(ArticleFournisseur.objects.filter(
        fournisseur=fournisseur, ingredient__isnull=True))


def _resoudre_ingredient(reponse, synchro):
    nom = (reponse.get('ingredient') or '').strip() or (reponse.get('nouvel_ingredient') or '')
    ingredient, cree = resoudre_ou_creer(nom, reponse.get('unite') or '')
    if cree:
        synchro.ingredients_crees += 1
    return ingredient


def _quantite_prouvee(article, ligne, synchro):
    """N'accepte une quantité que si Mistral cite un fragment du texte du produit qui
    la justifie, et que ce fragment s'y trouve réellement.

    Sans ce garde-fou, « Colis de 10 » (10 de quoi ?) devient « 250 g », le prix au kilo
    du beurre passe à 168 € et toute la comparaison entre fournisseurs devient absurde.
    Une quantité fausse est bien pire qu'une quantité absente : on préfère laisser le
    conditionnement à 1 et laisser l'humain trancher.
    """
    quantite = ligne.get('quantite')
    if quantite in (None, '', 0):
        return None

    preuve = (ligne.get('preuve') or '').strip().lower()
    texte = f'{article.libelle} {article.conditionnement}'.lower()
    if not preuve or preuve not in texte:
        synchro.tracer(
            f'  ⚠ Quantité ignorée pour « {article.libelle[:40]} » : '
            f'Mistral annonce {quantite} sans preuve dans le texte ({preuve!r}).')
        return None

    try:
        valeur = Decimal(str(quantite))
    except (InvalidOperation, ValueError):
        return None
    return valeur if valeur > 0 else None


def _appliquer_rattachements(lot, reponse, synchro):
    par_id = {article.id: article for article in lot}

    for ligne in (reponse.get('rattachements') or []):
        article = par_id.get(ligne.get('id'))
        if article is None or article.ingredient_id:
            continue

        if ligne.get('ignorer'):
            synchro.articles_ignores += 1
            continue

        ingredient = _resoudre_ingredient(ligne, synchro)
        if ingredient is None:
            continue

        article.ingredient = ingredient

        # Le prix n'est comparable entre fournisseurs que si le contenu du
        # conditionnement est exprimé dans l'unité de base de l'ingrédient.
        quantite = _quantite_prouvee(article, ligne, synchro)
        if quantite is not None:
            article.quantite_conditionnement = quantite
            article.unite = ingredient.unite

        article.save()
        synchro.articles_rattaches += 1


def _rattacher(db, synchro, fournisseur):
    articles = db(_orphelins, fournisseur)
    if not articles:
        db(synchro.tracer, 'Rattachement : aucun article en attente.')
        return

    _etape(db, synchro, f'Rattachement de {len(articles)} articles aux ingrédients (Mistral)')
    unites = db(lambda: list(Unite.objects.values_list('nom', flat=True)))

    for debut in range(0, len(articles), TAILLE_LOT_RAPPROCHEMENT):
        lot = articles[debut:debut + TAILLE_LOT_RAPPROCHEMENT]
        # Nomenclature relue à chaque lot : les ingrédients créés au lot précédent
        # doivent être proposés au suivant, sinon on créerait « Tomate » deux fois.
        ingredients = db(nomenclature)
        produits = [{
            'id': a.id,
            'libelle': a.libelle,
            'marque': a.marque,
            'conditionnement': a.conditionnement,
        } for a in lot]

        synchro.appels_mistral += 1
        reponse = db(rapprocher_produits, produits, ingredients, unites)
        db(_appliquer_rattachements, lot, reponse, synchro)
        db(synchro.tracer,
           f'  ↳ Lot {debut // TAILLE_LOT_RAPPROCHEMENT + 1} : '
           f'{synchro.articles_rattaches} rattachés, '
           f'{synchro.ingredients_crees} ingrédients créés, '
           f'{synchro.articles_ignores} ignorés (non alimentaires).')


# ── Orchestration ───────────────────────────────────────────────────────────

def _charger_session(fournisseur, synchro):
    """L'état du navigateur mémorisé pour ce fournisseur (magasin choisi, cookies
    acceptés, session ouverte), ou None."""
    if not fournisseur.session_state:
        return None
    try:
        return json.loads(fournisseur.session_state)
    except (json.JSONDecodeError, TypeError):
        synchro.tracer('  ⚠ Session mémorisée illisible : on repart d’un navigateur vierge.')
        return None


def _memoriser_session(fournisseur, etat):
    """Rejouer cet état au prochain run évite de refranchir bandeau cookies, choix de
    magasin et connexion. On le rafraîchit à chaque succès pour qu'il n'expire pas.

    `etat` est lu par l'appelant, DANS le thread du navigateur : les objets Playwright
    sont liés à leur thread, les toucher depuis la passerelle ORM les casse.
    """
    fournisseur.session_state = etat
    fournisseur.save(update_fields=['session_state'])


def _executer(db, page, synchro, fournisseur, selecteurs):
    _etape(db, synchro, f'Ouverture de {fournisseur.url}')
    page.goto(fournisseur.url, wait_until='domcontentloaded')

    _etape(db, synchro, 'Levée des obstacles (cookies, magasin, modales)')
    _preparer(db, page, synchro, fournisseur, "à l'arrivée")

    if fournisseur.necessite_connexion:
        _connecter(db, page, synchro, fournisseur, selecteurs)
    else:
        db(synchro.tracer, 'Aucun identifiant renseigné → connexion non nécessaire.')

    _atteindre_produits(db, page, synchro, selecteurs)

    # Une modale ou un choix de magasin peut n'apparaître qu'ici, sur la page catalogue —
    # et c'est justement là qu'il masque les prix.
    _preparer(db, page, synchro, fournisseur, 'sur le catalogue')

    _extraire(db, page, synchro, fournisseur, selecteurs)

    if fournisseur.rattachement_auto:
        _rattacher(db, synchro, fournisseur)
    else:
        db(synchro.tracer,
           'Rattachement automatique désactivé → les articles restent en attente de mapping.')


def synchroniser(synchro_id):
    """Point d'entrée du thread de fond. Ne lève rien : tout est consigné dans la
    SynchroCatalogue, que le frontend interroge pour suivre l'avancement."""
    from playwright.sync_api import sync_playwright   # import tardif : dépendance lourde

    synchro = SynchroCatalogue.objects.select_related('fournisseur').get(pk=synchro_id)
    fournisseur = synchro.fournisseur
    selecteurs, _ = SelecteursCatalogue.objects.get_or_create(fournisseur=fournisseur)

    db = Base()
    try:
        if not fournisseur.url:
            raise RobotErreur("Aucune URL n'est renseignée pour ce fournisseur.")

        session = db(_charger_session, fournisseur, synchro)
        if session:
            db(synchro.tracer,
               '  ↳ Session mémorisée rechargée (magasin, cookies, connexion).')

        with sync_playwright() as pw:
            navigateur = pw.chromium.launch(headless=True)
            contexte = navigateur.new_context(
                user_agent=NAVIGATEUR_UA, locale='fr-FR', storage_state=session)
            page = contexte.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            try:
                _executer(db, page, synchro, fournisseur, selecteurs)
                # Uniquement après un run réussi : on ne mémorise pas un état bancal.
                # storage_state() se lit ici, dans le thread du navigateur.
                db(_memoriser_session, fournisseur, json.dumps(contexte.storage_state()))
            finally:
                navigateur.close()

        synchro.statut = 'succes'
        synchro.etape = 'Terminé'
    except (RobotErreur, RobotNonConfigure) as exc:
        synchro.statut = 'echec'
        synchro.message = str(exc)
        synchro.etape = 'Échec'
    except Exception as exc:                      # noqa: BLE001 — un thread ne doit jamais mourir muet
        synchro.statut = 'echec'
        synchro.message = f'{type(exc).__name__} : {exc}'
        synchro.etape = 'Échec'
    finally:
        db.fermer()
        # Hors du bloc Playwright : la boucle asyncio a disparu, l'ORM redevient accessible.
        synchro.termine_le = timezone.now()
        synchro.save()
        connection.close()                        # thread → on rend la connexion au pool
