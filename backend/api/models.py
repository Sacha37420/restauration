from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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

    class Meta:
        db_table = 'plat'
        ordering = ['nom']

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

    def __str__(self):
        return f'{self.type} {self.quantite} {self.ingredient} le {self.date:%Y-%m-%d}'
