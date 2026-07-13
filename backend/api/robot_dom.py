"""Réduction d'une page HTML à ce qu'un LLM doit voir pour la comprendre.

Une page de catalogue fournisseur pèse couramment 300 Ko à 1 Mo : l'envoyer telle
quelle à Mistral est impossible (contexte) et ruineux (tokens). On en retire tout
ce qui ne porte pas de sens structurel — scripts, styles, SVG, commentaires — et on
tronque les attributs et textes trop longs.

Conséquence importante pour les XPath : l'élagage **décale les index positionnels**.
Un `div[3]/input[2]` déduit du HTML élagué serait faux sur la vraie page. C'est
pourquoi on impose à Mistral des XPath fondés sur les attributs (cf. robot_mistral),
et qu'on les valide ensuite sur la page réelle avant de s'en servir.
"""
import re

from lxml import etree, html as lxml_html

# Balises sans valeur structurelle pour l'analyse : on les supprime avec leur contenu.
BALISES_INUTILES = [
    'script', 'style', 'noscript', 'svg', 'canvas', 'iframe', 'template',
    'link', 'meta', 'br', 'hr', 'source', 'picture', 'video', 'audio',
]

# Seuls ces attributs aident à cibler un élément ; le reste (style inline, classes
# utilitaires interminables, data-* de tracking) est du bruit.
ATTRS_UTILES = {
    'id', 'name', 'type', 'class', 'href', 'value', 'placeholder', 'role',
    'title', 'alt', 'aria-label', 'data-testid', 'data-test', 'data-id',
    'itemprop', 'label', 'for',
}

LONGUEUR_ATTR_MAX = 120
LONGUEUR_TEXTE_MAX = 200
TAILLE_SORTIE_MAX = 60_000

# Répartition quand la page dépasse la taille max : la tête porte les motifs produits,
# la queue porte la pagination. Sacrifier l'une ou l'autre casse le robot.
TAILLE_TETE = 44_000
TAILLE_QUEUE = 16_000


def _supprimer(el):
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _nettoyer(arbre):
    # list() obligatoire : on retire des nœuds pendant le parcours.
    for balise in BALISES_INUTILES:
        for el in list(arbre.iter(balise)):
            _supprimer(el)

    for el in list(arbre.iter()):
        if not isinstance(el.tag, str):       # commentaires, instructions de traitement
            _supprimer(el)
            continue

        for nom, valeur in list(el.attrib.items()):
            if nom not in ATTRS_UTILES:
                del el.attrib[nom]
            elif len(valeur) > LONGUEUR_ATTR_MAX:
                el.attrib[nom] = valeur[:LONGUEUR_ATTR_MAX] + '…'

        if el.text and len(el.text) > LONGUEUR_TEXTE_MAX:
            el.text = el.text[:LONGUEUR_TEXTE_MAX] + '…'
        if el.tail and len(el.tail) > LONGUEUR_TEXTE_MAX:
            el.tail = el.tail[:LONGUEUR_TEXTE_MAX] + '…'


def elaguer(contenu_html: str) -> str:
    """HTML brut → HTML compact, exploitable par le LLM."""
    if not contenu_html:
        return ''
    try:
        arbre = lxml_html.fromstring(contenu_html)
    except (etree.ParserError, ValueError):
        return contenu_html[:TAILLE_SORTIE_MAX]

    for tete in arbre.iter('head'):
        parent = tete.getparent()
        if parent is not None:
            parent.remove(tete)

    _nettoyer(arbre)

    sortie = lxml_html.tostring(arbre, encoding='unicode', pretty_print=False)
    sortie = re.sub(r'\s+', ' ', sortie)          # les blancs multiples coûtent des tokens
    sortie = re.sub(r'>\s+<', '><', sortie)

    if len(sortie) > TAILLE_SORTIE_MAX:
        # Garder uniquement le début serait une erreur : les motifs produits sont bien
        # en tête, mais la PAGINATION est en pied de page. La tronquer revient à faire
        # croire au LLM qu'il n'y a pas de page suivante — et à n'aspirer qu'une page
        # sur N. On conserve donc les deux extrémités.
        sortie = (sortie[:TAILLE_TETE]
                  + '…[milieu tronqué]…'
                  + sortie[-TAILLE_QUEUE:])
    return sortie
