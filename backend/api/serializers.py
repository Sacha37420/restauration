from rest_framework import serializers
from .models import (
    ConfigurationStripe,
    CategoriePlat, SousCategoriePlat,
    Fournisseur, Unite, Ingredient, Recette, LigneRecette, Plat, StockPlat,
    TableRestaurant, CompteClient, Employe, CanalCommande, StatutCommande,
    StatutPaiement, Commande, LigneCommande, Paiement, PlageTravail, MouvementStock,
    Facture, ConfigurationEmail, ConfigurationAgentEvenements, ConfigurationMeteo,
)


class CategoriePlatSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoriePlat
        fields = ['id', 'nom', 'ordre']


class SousCategoriePlatInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SousCategoriePlat
        fields = ['id', 'nom', 'ordre']


class CategoriePlatSerializer(serializers.ModelSerializer):
    sous_categories = SousCategoriePlatInlineSerializer(many=True, read_only=True)

    class Meta:
        model = CategoriePlat
        fields = ['id', 'nom', 'ordre', 'sous_categories']


class SousCategoriePlatSerializer(serializers.ModelSerializer):
    categorie_detail = CategoriePlatSimpleSerializer(source='categorie', read_only=True)

    class Meta:
        model = SousCategoriePlat
        fields = ['id', 'categorie', 'nom', 'ordre', 'categorie_detail']


class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fournisseur
        fields = ['id', 'nom', 'email', 'telephone', 'commentaire']


class UniteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unite
        fields = ['id', 'nom', 'description']


class IngredientSerializer(serializers.ModelSerializer):
    sous_seuil = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Ingredient
        fields = ['id', 'nom', 'quantite_stock', 'seuil_alerte',
                  'fournisseur', 'unite', 'sous_seuil']

    def get_sous_seuil(self, obj):
        if obj.seuil_alerte is None:
            return False
        return obj.quantite_stock < obj.seuil_alerte


class IngredientDetailSerializer(IngredientSerializer):
    fournisseur_detail = FournisseurSerializer(source='fournisseur', read_only=True)
    unite_detail = UniteSerializer(source='unite', read_only=True)

    class Meta(IngredientSerializer.Meta):
        fields = IngredientSerializer.Meta.fields + ['fournisseur_detail', 'unite_detail']


class LigneRecetteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneRecette
        fields = ['id', 'ingredient', 'quantite']


class RecetteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recette
        fields = ['id', 'nom', 'instructions_html', 'temps_preparation', 'nb_portions']


class RecetteDetailSerializer(RecetteSerializer):
    lignes_recette = LigneRecetteSerializer(many=True, read_only=True)

    class Meta(RecetteSerializer.Meta):
        fields = RecetteSerializer.Meta.fields + ['lignes_recette']


class PlatSerializer(serializers.ModelSerializer):
    sous_categorie_detail = SousCategoriePlatSerializer(source='sous_categorie', read_only=True)

    class Meta:
        model = Plat
        fields = [
            'id', 'nom', 'description', 'photo', 'prix_unitaire',
            'sans_gluten', 'halal', 'vegetarien', 'actif', 'recette',
            'sous_categorie', 'sous_categorie_detail',
        ]


class StockPlatSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockPlat
        fields = ['id', 'plat', 'quantite_disponible', 'date_production']


class TableRestaurantSerializer(serializers.ModelSerializer):
    class Meta:
        model = TableRestaurant
        fields = ['id', 'numero', 'token_qr', 'actif', 'pos_x', 'pos_y']


class CompteClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteClient
        fields = ['id', 'user', 'telephone']


class EmployeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employe
        fields = ['id', 'user', 'role']


class CanalCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CanalCommande
        fields = ['id', 'nom', 'description']


class StatutCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutCommande
        fields = ['id', 'nom', 'description']


class StatutPaiementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatutPaiement
        fields = ['id', 'nom', 'description']


class LigneCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneCommande
        fields = ['id', 'commande', 'plat', 'quantite', 'prix_unitaire_snapshot']


class LigneCommandeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneCommande
        fields = ['id', 'plat', 'quantite', 'prix_unitaire_snapshot']
        read_only_fields = ['prix_unitaire_snapshot']


class CommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commande
        fields = [
            'id', 'canal', 'statut', 'table_restaurant', 'compte_client',
            'numero_table', 'created_at',
        ]
        read_only_fields = ['created_at']


class PaiementInlineSerializer(serializers.ModelSerializer):
    statut_detail = StatutPaiementSerializer(source='statut', read_only=True)

    class Meta:
        model = Paiement
        fields = ['id', 'statut', 'statut_detail', 'montant', 'methode', 'transaction_id', 'confirme_par', 'created_at']
        read_only_fields = ['created_at', 'confirme_par']


class CommandeDetailSerializer(CommandeSerializer):
    canal_detail = CanalCommandeSerializer(source='canal', read_only=True)
    statut_detail = StatutCommandeSerializer(source='statut', read_only=True)
    lignes_commande = LigneCommandeCreateSerializer(many=True, read_only=True)
    paiement = PaiementInlineSerializer(read_only=True)

    class Meta(CommandeSerializer.Meta):
        fields = CommandeSerializer.Meta.fields + [
            'canal_detail', 'statut_detail', 'lignes_commande', 'paiement',
        ]


class PaiementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paiement
        fields = [
            'id', 'commande', 'statut', 'montant', 'methode',
            'transaction_id', 'confirme_par', 'created_at',
        ]
        read_only_fields = ['created_at', 'confirme_par']


class PlageTravailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlageTravail
        fields = ['id', 'employe', 'debut', 'fin', 'note']


class MouvementStockSerializer(serializers.ModelSerializer):
    class Meta:
        model = MouvementStock
        fields = ['id', 'ingredient', 'employe', 'type', 'quantite', 'date', 'raison']
        read_only_fields = ['date']


class FactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Facture
        fields = [
            'id', 'commande', 'numero', 'montant_ttc', 'taux_tva',
            'email_destinataire', 'envoyee_at', 'created_at',
        ]
        read_only_fields = fields


class ConfigurationEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationEmail
        fields = [
            'actif', 'email_host', 'email_port', 'email_use_tls',
            'email_host_user', 'email_host_password', 'default_from_email', 'updated_at',
        ]
        read_only_fields = ['updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        pwd = data.get('email_host_password', '')
        if pwd:
            data['email_host_password'] = '••••••••' + pwd[-4:]
        return data


class ConfigurationAgentEvenementsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationAgentEvenements
        fields = ['actif', 'anthropic_api_key', 'modele', 'ville', 'mois', 'annee', 'updated_at']
        read_only_fields = ['updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        key = data.get('anthropic_api_key', '')
        if key:
            data['anthropic_api_key'] = '••••••••' + key[-4:]
        return data


class ConfigurationMeteoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationMeteo
        fields = ['actif', 'api_key', 'ville', 'mois', 'annee', 'updated_at']
        read_only_fields = ['updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        key = data.get('api_key', '')
        if key:
            data['api_key'] = '••••••••' + key[-4:]
        return data


class ConfigurationStripeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfigurationStripe
        fields = ['stripe_secret_key', 'stripe_webhook_secret', 'updated_at']
        read_only_fields = ['updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Masquer la clé secrète dans les réponses GET (affiche seulement les 8 derniers chars)
        key = data.get('stripe_secret_key', '')
        if key:
            data['stripe_secret_key'] = '••••••••' + key[-8:]
        secret = data.get('stripe_webhook_secret', '')
        if secret:
            data['stripe_webhook_secret'] = '••••••••' + secret[-8:]
        return data
