from decimal import Decimal

from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone

from . import prompts
from .fields import EncryptedTextField


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200)
    email = models.CharField(max_length=254, blank=True, default='')
    telephone = models.CharField(max_length=20, blank=True, default='')
    commentaire = models.TextField(blank=True, default='')

    # Accès au portail du fournisseur, pour le robot de catalogue.
    # Identifiant/mot de passe vides = site consultable sans connexion.
    url = models.CharField(max_length=500, blank=True, default='')
    identifiant = models.CharField(max_length=255, blank=True, default='')
    mot_de_passe = EncryptedTextField(blank=True, default='')
    code_postal = models.CharField(
        max_length=10, blank=True, default='',
        help_text="Sert au robot quand le site exige de choisir un magasin ou un drive "
                  "pour afficher ses prix.",
    )
    # État du navigateur (cookies + localStorage), au format storage_state de Playwright.
    # C'est ce qui porte le magasin choisi, le consentement aux cookies et la session :
    # le rejouer évite de refranchir ces tunnels à chaque synchro. Chiffré, car il peut
    # contenir des jetons d'authentification.
    session_state = EncryptedTextField(blank=True, default='')
    rattachement_auto = models.BooleanField(
        default=True,
        help_text="À la fin d'une synchro, Mistral rattache les articles rapportés à un "
                  'ingrédient existant, ou en crée un. Décochez pour garder la main.',
    )

    class Meta:
        db_table = 'fournisseur'
        ordering = ['nom']

    @property
    def necessite_connexion(self):
        return bool(self.identifiant and self.mot_de_passe)

    def __str__(self):
        return self.nom


class Unite(models.Model):
    nom = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'unite'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Ingredient(models.Model):
    """Article de stock interne. Ne porte plus de fournisseur : les références
    achetables vivent dans ArticleFournisseur (un ingrédient peut être acheté
    chez plusieurs fournisseurs, sous plusieurs marques et conditionnements)."""
    nom = models.CharField(max_length=200, unique=True)
    quantite_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    seuil_alerte = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    unite = models.ForeignKey(
        Unite, on_delete=models.PROTECT, related_name='ingredients',
    )

    class Meta:
        db_table = 'ingredient'
        ordering = ['nom']

    @property
    def articles_disponibles(self):
        return [a for a in self.articles.all() if a.disponible]

    @property
    def article_prefere(self):
        """Article retenu par défaut pour le réappro : celui marqué « préféré »,
        sinon le moins cher ramené à l'unité de base."""
        articles = self.articles_disponibles
        if not articles:
            return None
        for a in articles:
            if a.prefere:
                return a
        chiffrables = [(a.prix_unitaire, a) for a in articles if a.prix_unitaire is not None]
        if not chiffrables:
            return articles[0]
        return min(chiffrables, key=lambda couple: couple[0])[1]

    @property
    def meilleur_prix_unitaire(self):
        prix = [a.prix_unitaire for a in self.articles_disponibles
                if a.prix_unitaire is not None]
        return min(prix) if prix else None

    def __str__(self):
        return self.nom


class ArticleFournisseur(models.Model):
    """Référence achetable chez un fournisseur (un « SKU »).

    Plusieurs articles — fournisseurs, marques ou conditionnements différents —
    peuvent pointer vers le même Ingredient : c'est ce qui rend les prix
    comparables. Le tarif lui-même vit dans PrixArticle, car il dépend aussi de
    la quantité commandée (paliers dégressifs) et change dans le temps.
    """
    SOURCES = [
        ('manuel', 'Manuel'),
        ('csv', 'Import CSV'),
        ('robot', 'Robot fournisseur'),
    ]

    fournisseur = models.ForeignKey(
        Fournisseur, on_delete=models.CASCADE, related_name='articles',
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles',
    )
    libelle = models.CharField(max_length=255)
    reference = models.CharField(max_length=100, blank=True, default='')
    ean = models.CharField(max_length=14, blank=True, default='')
    marque = models.CharField(max_length=120, blank=True, default='')
    conditionnement = models.CharField(max_length=100, blank=True, default='')
    quantite_conditionnement = models.DecimalField(
        max_digits=12, decimal_places=3, default=1,
        help_text="Contenu d'un conditionnement, exprimé dans `unite` (ex : 5 pour un carton de 5 kg).",
    )
    unite = models.ForeignKey(Unite, on_delete=models.PROTECT, related_name='articles')
    disponible = models.BooleanField(default=True)
    prefere = models.BooleanField(default=False)
    url = models.CharField(max_length=500, blank=True, default='')
    source = models.CharField(max_length=20, choices=SOURCES, default='manuel')
    synchronise_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'article_fournisseur'
        ordering = ['fournisseur__nom', 'libelle']
        constraints = [
            models.UniqueConstraint(
                fields=['fournisseur', 'reference'],
                condition=~models.Q(reference=''),
                name='uniq_reference_par_fournisseur',
            ),
        ]

    def prix_applicable(self, quantite=1):
        """Dernier relevé du meilleur palier atteint par `quantite` conditionnements.
        None si l'article n'a aucun tarif connu."""
        derniers = {}
        for p in self.prix.all():
            if p.quantite_min > quantite:
                continue
            courant = derniers.get(p.quantite_min)
            if courant is None or p.releve_le > courant.releve_le:
                derniers[p.quantite_min] = p
        if not derniers:
            return None
        return derniers[max(derniers)]

    @property
    def prix_actuel(self):
        """Prix HT d'un conditionnement, à l'unité (palier 1)."""
        p = self.prix_applicable(1)
        return p.prix_ht if p else None

    @property
    def prix_unitaire(self):
        """Prix HT ramené à l'unité de base (au kg, au litre…) — la seule grandeur
        comparable entre deux conditionnements ou deux fournisseurs."""
        prix = self.prix_actuel
        if prix is None or not self.quantite_conditionnement:
            return None
        return prix / self.quantite_conditionnement

    def save(self, *args, **kwargs):
        # Un seul article préféré par ingrédient.
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.prefere and self.ingredient_id:
                ArticleFournisseur.objects.filter(
                    ingredient_id=self.ingredient_id,
                ).exclude(pk=self.pk).update(prefere=False)

    def __str__(self):
        return f'{self.libelle} — {self.fournisseur.nom}'


class SelecteursCatalogue(models.Model):
    """XPath du portail d'un fournisseur, découverts par Mistral puis mis en cache.

    Sans ce cache, chaque synchro rappellerait le LLM sur chaque page : lent, coûteux
    et non déterministe. Les runs suivants rejouent ces sélecteurs sans aucun appel
    Mistral. On ne redécouvre que lorsqu'un sélecteur cesse de résoudre — c'est ce qui
    permet au robot de se réparer seul quand le site change.
    """
    fournisseur = models.OneToOneField(
        Fournisseur, on_delete=models.CASCADE, related_name='selecteurs',
    )
    # Étape 1 — connexion
    url_connexion = models.CharField(max_length=500, blank=True, default='')
    xpath_identifiant = models.CharField(max_length=500, blank=True, default='')
    xpath_mot_de_passe = models.CharField(max_length=500, blank=True, default='')
    xpath_valider = models.CharField(max_length=500, blank=True, default='')
    # Étape 2 — navigation jusqu'à la liste des produits
    url_produits = models.CharField(max_length=500, blank=True, default='')
    # Étape 3 — extraction
    xpath_produit = models.CharField(max_length=500, blank=True, default='')
    champs = models.JSONField(
        default=dict, blank=True,
        help_text="XPath relatifs à un produit : {'libelle': './/h3', 'prix_ht': ...}",
    )
    xpath_page_suivante = models.CharField(max_length=500, blank=True, default='')
    decouvert_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'selecteurs_catalogue'

    @property
    def extraction_prete(self):
        """Vrai si on peut rejouer l'extraction sans redemander à Mistral."""
        return bool(self.url_produits and self.xpath_produit and self.champs)

    @property
    def connexion_prete(self):
        return bool(
            self.url_connexion and self.xpath_identifiant
            and self.xpath_mot_de_passe and self.xpath_valider
        )

    def __str__(self):
        return f'Sélecteurs — {self.fournisseur.nom}'


class SynchroCatalogue(models.Model):
    """Journal d'un run du robot. Une synchro dure plusieurs minutes : elle tourne
    en tâche de fond et le frontend suit son avancement en interrogeant ce modèle."""
    STATUTS = [
        ('en_cours', 'En cours'),
        ('succes', 'Succès'),
        ('echec', 'Échec'),
    ]

    fournisseur = models.ForeignKey(
        Fournisseur, on_delete=models.CASCADE, related_name='synchros',
    )
    statut = models.CharField(max_length=20, choices=STATUTS, default='en_cours')
    etape = models.CharField(max_length=200, blank=True, default='')
    message = models.TextField(blank=True, default='')
    pages_scannees = models.IntegerField(default=0)
    appels_mistral = models.IntegerField(default=0)
    articles_crees = models.IntegerField(default=0)
    articles_maj = models.IntegerField(default=0)
    prix_releves = models.IntegerField(default=0)
    # Rattachement automatique aux ingrédients (dernière étape de la synchro).
    articles_rattaches = models.IntegerField(default=0)
    ingredients_crees = models.IntegerField(default=0)
    articles_ignores = models.IntegerField(default=0)
    journal = models.JSONField(default=list, blank=True)
    demarre_le = models.DateTimeField(default=timezone.now)
    termine_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'synchro_catalogue'
        ordering = ['-demarre_le']

    COMPTEURS = [
        'pages_scannees', 'appels_mistral', 'articles_crees', 'articles_maj',
        'prix_releves', 'articles_rattaches', 'ingredients_crees', 'articles_ignores',
    ]

    def tracer(self, ligne):
        """Ajoute une ligne au journal et la persiste immédiatement : c'est le seul
        moyen pour l'utilisateur de suivre un run qui tourne en tâche de fond."""
        self.journal = (self.journal or []) + [ligne]
        self.save(update_fields=['journal', 'etape'] + self.COMPTEURS)

    def __str__(self):
        return f'{self.fournisseur.nom} — {self.statut} ({self.demarre_le:%Y-%m-%d %H:%M})'


class PrixArticle(models.Model):
    """Tarif d'un article, à un palier de quantité donné, historisé.

    On n'écrase jamais un tarif : chaque synchro ajoute un relevé. Le prix courant
    d'un palier est le relevé le plus récent (cf. ArticleFournisseur.prix_applicable),
    ce qui permet de suivre l'évolution des prix fournisseur dans le temps.
    """
    article = models.ForeignKey(
        ArticleFournisseur, on_delete=models.CASCADE, related_name='prix',
    )
    quantite_min = models.DecimalField(
        max_digits=12, decimal_places=3, default=1,
        help_text='Palier dégressif : tarif valable à partir de N conditionnements.',
    )
    prix_ht = models.DecimalField(max_digits=10, decimal_places=4)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=5.5)
    releve_le = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=20, choices=ArticleFournisseur.SOURCES, default='manuel')

    class Meta:
        db_table = 'prix_article'
        ordering = ['quantite_min', '-releve_le']
        constraints = [
            models.UniqueConstraint(
                fields=['article', 'quantite_min', 'releve_le'],
                name='uniq_releve_par_palier',
            ),
        ]

    def __str__(self):
        return f'{self.article.libelle} — {self.prix_ht} € HT (dès {self.quantite_min})'


class Recette(models.Model):
    nom = models.CharField(max_length=200)
    instructions_html = models.TextField()
    temps_preparation = models.IntegerField()
    nb_portions = models.IntegerField()

    class Meta:
        db_table = 'recette'
        ordering = ['nom']

    @property
    def cout_matiere(self):
        """Coût matière de la recette entière, au meilleur prix fournisseur connu.

        None si aucun ingrédient n'a de prix : mieux vaut ne rien afficher qu'un coût
        faussement rassurant, calculé sur la moitié des ingrédients seulement.
        """
        total = Decimal('0')
        for ligne in self.lignes_recette.all():
            prix = ligne.ingredient.meilleur_prix_unitaire
            if prix is None:
                return None
            total += prix * ligne.quantite
        return total if self.lignes_recette.all() else None

    @property
    def cout_par_portion(self):
        cout = self.cout_matiere
        if cout is None or not self.nb_portions:
            return None
        return cout / self.nb_portions

    def __str__(self):
        return self.nom


class LigneRecette(models.Model):
    recette = models.ForeignKey(
        Recette, on_delete=models.CASCADE, related_name='lignes_recette',
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, related_name='lignes_recette',
    )
    quantite = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        db_table = 'ligne_recette'
        unique_together = [('recette', 'ingredient')]

    def __str__(self):
        return f'{self.recette} — {self.ingredient} x{self.quantite}'


class CategoriePlat(models.Model):
    nom = models.CharField(max_length=100)
    ordre = models.IntegerField(default=0)

    class Meta:
        db_table = 'categorie_plat'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom


class SousCategoriePlat(models.Model):
    categorie = models.ForeignKey(
        CategoriePlat, on_delete=models.CASCADE, related_name='sous_categories',
    )
    nom = models.CharField(max_length=100)
    ordre = models.IntegerField(default=0)

    class Meta:
        db_table = 'sous_categorie_plat'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return f'{self.categorie} › {self.nom}'


class Plat(models.Model):
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    photo = models.ImageField(upload_to='plats/', null=True, blank=True)
    prix_unitaire = models.DecimalField(max_digits=8, decimal_places=2)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=10)  # % (prix TTC)
    sans_gluten = models.BooleanField(default=False)
    halal = models.BooleanField(default=False)
    vegetarien = models.BooleanField(default=False)
    actif = models.BooleanField(default=True)
    recette = models.ForeignKey(
        Recette, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plats',
    )
    sous_categorie = models.ForeignKey(
        SousCategoriePlat, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plats',
    )

    class Meta:
        db_table = 'plat'
        ordering = ['sous_categorie__categorie__ordre', 'sous_categorie__ordre', 'nom']

    def __str__(self):
        return self.nom


class StockPlat(models.Model):
    plat = models.ForeignKey(
        Plat, on_delete=models.CASCADE, related_name='stocks_plat',
    )
    quantite_disponible = models.IntegerField(default=0)
    date_production = models.DateTimeField()

    class Meta:
        db_table = 'stock_plat'
        ordering = ['-date_production']

    def __str__(self):
        return f'{self.plat} — {self.quantite_disponible} le {self.date_production:%Y-%m-%d}'


class TableRestaurant(models.Model):
    numero = models.IntegerField(unique=True)
    token_qr = models.CharField(max_length=64, unique=True)
    actif = models.BooleanField(default=True)
    pos_x = models.FloatField(null=True, blank=True)
    pos_y = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'table_restaurant'
        ordering = ['numero']

    def __str__(self):
        return f'Table {self.numero}'


class CompteClient(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='compte_client',
    )
    telephone = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        db_table = 'compte_client'

    def __str__(self):
        return str(self.user)


class Employe(models.Model):
    ROLES = [
        ('manager', 'Manager'),
        ('cuisinier', 'Cuisinier'),
        ('serveur', 'Serveur'),
    ]
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='employe',
    )
    role = models.CharField(max_length=20, choices=ROLES)

    class Meta:
        db_table = 'employe'

    def __str__(self):
        return f'{self.user} ({self.role})'


class CanalCommande(models.Model):
    nom = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'canal_commande'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class StatutCommande(models.Model):
    nom = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'statut_commande'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class StatutPaiement(models.Model):
    nom = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'statut_paiement'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Commande(models.Model):
    table_restaurant = models.ForeignKey(
        TableRestaurant, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commandes',
    )
    compte_client = models.ForeignKey(
        CompteClient, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='commandes',
    )
    canal = models.ForeignKey(
        CanalCommande, on_delete=models.PROTECT, related_name='commandes',
    )
    statut = models.ForeignKey(
        StatutCommande, on_delete=models.PROTECT, related_name='commandes',
    )
    numero_table = models.IntegerField(null=True, blank=True)
    # Email facultatif fourni par le client (page /commander) pour recevoir la facture.
    email_client = models.CharField(max_length=254, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'commande'
        ordering = ['-created_at']

    def __str__(self):
        return f'Commande #{self.pk} — {self.statut}'


class LigneCommande(models.Model):
    commande = models.ForeignKey(
        Commande, on_delete=models.CASCADE, related_name='lignes_commande',
    )
    plat = models.ForeignKey(
        Plat, on_delete=models.PROTECT, related_name='lignes_commande',
    )
    quantite = models.IntegerField(default=1)
    prix_unitaire_snapshot = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        db_table = 'ligne_commande'

    def __str__(self):
        return f'{self.commande} — {self.plat} x{self.quantite}'


class Paiement(models.Model):
    commande = models.OneToOneField(
        Commande, on_delete=models.CASCADE, related_name='paiement',
    )
    statut = models.ForeignKey(
        StatutPaiement, on_delete=models.PROTECT, related_name='paiements',
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    methode = models.CharField(max_length=20)
    transaction_id = models.CharField(max_length=255, blank=True, default='')
    # Employé (username Keycloak) ayant confirmé un encaissement sur place.
    confirme_par = models.CharField(max_length=254, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'paiement'
        ordering = ['-created_at']

    def __str__(self):
        return f'Paiement #{self.pk} — {self.montant}€ ({self.statut})'


class PlageTravail(models.Model):
    employe = models.ForeignKey(
        Employe, on_delete=models.CASCADE, related_name='plages_travail',
    )
    debut = models.DateTimeField()
    fin = models.DateTimeField()
    note = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'plage_travail'
        ordering = ['debut']

    def __str__(self):
        return f'{self.employe} — {self.debut:%Y-%m-%d %H:%M}'


class ConfigurationStripe(models.Model):
    stripe_secret_key = EncryptedTextField(blank=True, default='')
    stripe_webhook_secret = EncryptedTextField(blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuration_stripe'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuration Stripe'


class Facture(models.Model):
    commande = models.OneToOneField(
        Commande, on_delete=models.PROTECT, related_name='facture',
    )
    numero = models.CharField(max_length=30, unique=True)
    montant_ttc = models.DecimalField(max_digits=10, decimal_places=2)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2)
    email_destinataire = models.CharField(max_length=254, blank=True, default='')
    envoyee_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'facture'
        ordering = ['-created_at']

    def __str__(self):
        return self.numero


class ConfigurationEmail(models.Model):
    actif = models.BooleanField(default=False)
    email_host = models.CharField(max_length=255, blank=True, default='')
    email_port = models.IntegerField(default=587)
    email_use_tls = models.BooleanField(default=True)
    email_host_user = models.CharField(max_length=255, blank=True, default='')
    email_host_password = EncryptedTextField(blank=True, default='')
    default_from_email = models.CharField(max_length=255, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuration_email'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuration Email'


# La migration 0014 importe ce nom : on le conserve pour ne pas casser l'historique
# des migrations (le prompt lui-même vit désormais dans prompts.py).
DEFAULT_PROMPT_AGENT = prompts.DEFAUT_EVENEMENTS


class ConfigurationMistral(models.Model):
    """Accès à l'API Mistral, PARTAGÉ par tous ses usages.

    La clé et le modèle vivaient auparavant dans ConfigurationAgentEvenements, du temps
    où Mistral ne servait qu'au calendrier. Ils sont désormais utilisés par trois usages
    (robot fournisseur, génération de recettes, événements) : les laisser dans la config
    d'un seul d'entre eux n'avait plus de sens.
    """
    actif = models.BooleanField(default=False)
    api_key = EncryptedTextField(blank=True, default='')
    modele = models.CharField(max_length=50, default='mistral-large-latest')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuration_mistral'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuration Mistral'


class PromptMistral(models.Model):
    """Surcharge du prompt d'un usage. Absent = on utilise le défaut du code (prompts.py).

    « Réinitialiser » supprime simplement la ligne : le prompt par défaut reprend la main,
    et bénéficie des améliorations livrées avec les mises à jour.
    """
    usage = models.CharField(max_length=40, choices=prompts.USAGES, unique=True)
    contenu = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'prompt_mistral'
        ordering = ['usage']

    @classmethod
    def texte(cls, usage):
        """Le prompt effectif : la surcharge si elle existe, le défaut sinon."""
        surcharge = cls.objects.filter(usage=usage).first()
        if surcharge and surcharge.contenu.strip():
            return surcharge.contenu
        return prompts.DEFAUTS.get(usage, '')

    @property
    def par_defaut(self):
        return prompts.DEFAUTS.get(self.usage, '')

    def __str__(self):
        return f'Prompt — {self.get_usage_display()}'


class ConfigurationAgentEvenements(models.Model):
    """Paramètres PROPRES à l'agent calendrier : la ville et la période ciblées.
    La clé API, le modèle et l'activation vivent dans ConfigurationMistral ; le prompt
    dans PromptMistral."""
    ville = models.CharField(max_length=120, blank=True, default='')
    mois = models.IntegerField(null=True, blank=True)   # 1-12, optionnel
    annee = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuration_agent_evenements'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuration Agent Événements'


class ConfigurationMeteo(models.Model):
    """Config de l'API Météo-France (températures horaires) pour une ville
    et une période données."""
    actif = models.BooleanField(default=False)
    api_key = EncryptedTextField(blank=True, default='')
    ville = models.CharField(max_length=120, blank=True, default='')
    mois = models.IntegerField(null=True, blank=True)
    annee = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configuration_meteo'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Configuration Météo'


class StationMeteo(models.Model):
    """Cache local des stations horaires de Météo-France.

    L'API DPClim ne sait lister les stations que département par département (~100 appels
    pour couvrir la France). On les rapatrie une fois et on les garde : le classement des
    stations par distance devient alors un calcul purement local — et surtout il n'est plus
    borné au département de la ville, ce qui permet enfin de retenir une station voisine
    située de l'autre côté d'une frontière départementale.
    """
    id_station = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=120)
    departement = models.CharField(max_length=5)
    lat = models.FloatField()
    lon = models.FloatField()
    altitude = models.IntegerField(null=True, blank=True)
    poste_ouvert = models.BooleanField(default=True)
    type_poste = models.IntegerField(null=True, blank=True)
    maj_le = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'station_meteo'
        ordering = ['departement', 'nom']

    def __str__(self):
        return f'{self.nom} ({self.id_station})'


class Evenement(models.Model):
    """Événement impactant la fréquentation d'une ville (module Analyse économique)."""
    CONFIANCES = [('faible', 'Faible'), ('moyenne', 'Moyenne'), ('elevee', 'Élevée')]
    ville = models.CharField(max_length=120)
    titre = models.CharField(max_length=255)
    date_debut = models.DateField()
    date_fin = models.DateField()
    surplus_frequentation = models.IntegerField(default=0)
    confiance = models.CharField(max_length=10, choices=CONFIANCES, blank=True, default='')
    source = models.CharField(max_length=20, default='manuel')  # manuel | mistral
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'evenement'
        ordering = ['date_debut', 'titre']

    def __str__(self):
        return f'{self.titre} ({self.ville}, {self.date_debut})'


class DonneeMeteoHoraire(models.Model):
    """Relevé météo horaire (module Analyse économique)."""
    ville = models.CharField(max_length=120)
    horodatage = models.DateTimeField()
    temperature = models.FloatField(null=True, blank=True)     # °C
    nebulosite = models.FloatField(null=True, blank=True)      # octas 0-8
    precipitation = models.FloatField(null=True, blank=True)   # mm sur l'heure
    source = models.CharField(max_length=20, default='meteofrance')  # meteofrance | manuel
    # D'où vient la donnée : la station la plus proche n'ayant pas toujours de relevés sur
    # la période, celle qui a finalement répondu peut être plus lointaine. Il faut le savoir.
    station = models.ForeignKey(
        StationMeteo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='releves',
    )
    distance_km = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'donnee_meteo_horaire'
        ordering = ['horodatage']
        unique_together = [('ville', 'horodatage')]

    def __str__(self):
        return f'{self.ville} {self.horodatage:%Y-%m-%d %H:%M}'


class IndicateurMeteoConfig(models.Model):
    """Définition d'un indicateur journalier = agrégation d'une grandeur météo
    sur une plage horaire de la journée."""
    CHAMPS = [
        ('temperature', 'Température'),
        ('nebulosite', 'Nébulosité'),
        ('precipitation', 'Précipitation'),
    ]
    AGREGATIONS = [
        ('moyenne', 'Moyenne'),
        ('min', 'Minimum'),
        ('max', 'Maximum'),
        ('somme', 'Somme'),
        ('amplitude', 'Amplitude (max - min)'),
    ]
    nom = models.CharField(max_length=100)
    champ = models.CharField(max_length=20, choices=CHAMPS)
    agregation = models.CharField(max_length=20, choices=AGREGATIONS)
    heure_debut = models.IntegerField(default=0)   # 0-23 inclus
    heure_fin = models.IntegerField(default=23)    # 0-23 inclus
    actif = models.BooleanField(default=True)

    class Meta:
        db_table = 'indicateur_meteo_config'
        ordering = ['nom']

    def __str__(self):
        return f'{self.nom} ({self.agregation} {self.champ} {self.heure_debut}-{self.heure_fin}h)'


class VenteAgregee(models.Model):
    """Ventes agrégées par jour (et par catégorie), en HT et TTC.
    categorie NULL = total global de la journée."""
    date = models.DateField()
    categorie = models.ForeignKey(
        CategoriePlat, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ventes_agregees',
    )
    montant_ht = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quantite = models.IntegerField(default=0)
    source = models.CharField(max_length=20, default='commandes')  # commandes | excel | manuel

    class Meta:
        db_table = 'vente_agregee'
        ordering = ['date', 'categorie__nom']

    def __str__(self):
        cat = self.categorie.nom if self.categorie else 'Global'
        return f'{self.date} — {cat} : {self.montant_ttc} € TTC'


class MouvementStock(models.Model):
    TYPES = [
        ('entree', 'Entrée'),
        ('sortie', 'Sortie'),
        ('ajustement', 'Ajustement'),
    ]
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name='mouvements_stock',
    )
    employe = models.ForeignKey(
        Employe, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mouvements_stock',
    )
    type = models.CharField(max_length=20, choices=TYPES)
    quantite = models.DecimalField(max_digits=12, decimal_places=3)
    date = models.DateTimeField(default=timezone.now)
    raison = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'mouvement_stock'
        ordering = ['-date']

    def save(self, *args, **kwargs):
        # Répercute le mouvement sur le stock de l'ingrédient, une seule fois,
        # à la création (les mouvements sont un registre : on ne rejoue pas un
        # ajustement sur modification).
        is_new = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                stock = Ingredient.objects.filter(pk=self.ingredient_id)
                if self.type == 'entree':
                    stock.update(quantite_stock=models.F('quantite_stock') + self.quantite)
                elif self.type == 'sortie':
                    stock.update(quantite_stock=models.F('quantite_stock') - self.quantite)
                elif self.type == 'ajustement':
                    stock.update(quantite_stock=self.quantite)

    def __str__(self):
        return f'{self.type} {self.quantite} {self.ingredient} le {self.date:%Y-%m-%d}'
