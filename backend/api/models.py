from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone

from .fields import EncryptedTextField


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200)
    email = models.CharField(max_length=254, blank=True, default='')
    telephone = models.CharField(max_length=20, blank=True, default='')
    commentaire = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'fournisseur'
        ordering = ['nom']

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
    nom = models.CharField(max_length=200, unique=True)
    quantite_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    seuil_alerte = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    fournisseur = models.ForeignKey(
        Fournisseur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ingredients',
    )
    unite = models.ForeignKey(
        Unite, on_delete=models.PROTECT, related_name='ingredients',
    )

    class Meta:
        db_table = 'ingredient'
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Recette(models.Model):
    nom = models.CharField(max_length=200)
    instructions_html = models.TextField()
    temps_preparation = models.IntegerField()
    nb_portions = models.IntegerField()

    class Meta:
        db_table = 'recette'
        ordering = ['nom']

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


DEFAULT_PROMPT_AGENT = (
    "Tu es un analyste spécialisé dans l'impact des événements sur la fréquentation "
    "des villes. On te fournit une VILLE et une PÉRIODE (un mois précis, ou une année "
    "entière).\n\n"
    "Liste les événements connus et récurrents qui augmentent significativement la "
    "fréquentation de cette ville sur cette période : festivals, salons, foires, congrès, "
    "grands événements sportifs, concerts majeurs, marchés de Noël, jours fériés, "
    "vacances scolaires, etc.\n\n"
    "Pour chaque événement, estime le SURPLUS de fréquentation = le nombre de personnes "
    "supplémentaires présentes dans la ville par rapport à un jour normal (un entier).\n\n"
    "Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte autour :\n"
    '{"evenements": [{"titre": "...", "date_debut": "AAAA-MM-JJ", '
    '"date_fin": "AAAA-MM-JJ", "surplus_frequentation": 1234, '
    '"confiance": "faible|moyenne|elevee", "source": "..."}]}\n\n'
    "Règles : date_fin = date_debut pour un événement d'un seul jour ; "
    "surplus_frequentation est un entier (nombre de personnes) ; "
    "n'invente pas d'événement incertain — en cas de doute, baisse la confiance ou "
    "ne l'inclus pas ; n'écris rien en dehors du JSON."
)


class ConfigurationAgentEvenements(models.Model):
    """Config de l'agent Mistral qui complète le calendrier d'événements
    (ville + période ciblées) via l'API Mistral."""
    actif = models.BooleanField(default=False)
    mistral_api_key = EncryptedTextField(blank=True, default='')
    modele = models.CharField(max_length=50, default='mistral-large-latest')
    system_prompt = models.TextField(default=DEFAULT_PROMPT_AGENT)
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
