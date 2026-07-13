import json

from rest_framework import serializers
from .models import (
    ConfigurationStripe,
    CategoriePlat, SousCategoriePlat,
    Fournisseur, Unite, Ingredient, ArticleFournisseur, PrixArticle,
    SelecteursCatalogue, SynchroCatalogue,
    Recette, LigneRecette, Plat, StockPlat,
    TableRestaurant, CompteClient, Employe, CanalCommande, StatutCommande,
    StatutPaiement, Commande, LigneCommande, Paiement, PlageTravail, MouvementStock,
    Facture, ConfigurationEmail, ConfigurationAgentEvenements, ConfigurationMeteo,
    ConfigurationMistral, PromptMistral,
    Evenement, DonneeMeteoHoraire, IndicateurMeteoConfig, VenteAgregee,
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
    """Le mot de passe n'est jamais renvoyé, même masqué : les derniers caractères
    d'un mot de passe sont déjà une fuite. Le client sait seulement s'il est défini.
    Un mot de passe vide à l'écriture = « ne change rien » (le formulaire renvoie
    toujours un champ vide). Pour désactiver la connexion, videz l'identifiant."""
    mot_de_passe = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={'input_type': 'password'})
    # Jamais relu : contient des cookies de session, donc de quoi usurper le compte.
    session_state = serializers.CharField(
        write_only=True, required=False, allow_blank=True)
    mot_de_passe_defini = serializers.SerializerMethodField(read_only=True)
    robot_pret = serializers.SerializerMethodField(read_only=True)
    session_memorisee = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Fournisseur
        fields = ['id', 'nom', 'email', 'telephone', 'commentaire',
                  'url', 'identifiant', 'mot_de_passe', 'mot_de_passe_defini',
                  'code_postal', 'session_state', 'session_memorisee',
                  'robot_pret', 'rattachement_auto']

    def validate_session_state(self, valeur):
        """Un état de navigateur illisible ferait échouer chaque synchro, avec une erreur
        obscure : on refuse tout de suite, à la saisie."""
        valeur = (valeur or '').strip()
        if not valeur:
            return valeur
        try:
            etat = json.loads(valeur)
        except json.JSONDecodeError as exc:
            raise serializers.ValidationError(f'JSON invalide : {exc}') from exc
        if not isinstance(etat, dict) or 'cookies' not in etat:
            raise serializers.ValidationError(
                "Ce n'est pas un état de navigateur : on attend un objet JSON contenant "
                'au moins une clé « cookies » (format storage_state de Playwright).')
        return valeur

    def get_mot_de_passe_defini(self, obj):
        return bool(obj.mot_de_passe)

    def get_session_memorisee(self, obj):
        """L'état du navigateur n'est jamais renvoyé : il contient des cookies de session,
        donc potentiellement de quoi usurper le compte. On dit seulement s'il existe."""
        return bool(obj.session_state)

    def get_robot_pret(self, obj):
        """Le robot n'a besoin que d'une URL : un site consultable sans compte
        se scanne très bien sans identifiants."""
        return bool(obj.url)

    def _sans_secrets_vides(self, validated_data):
        """Un secret vide veut dire « ne change rien » : le formulaire renvoie toujours un
        champ vide, puisque le serveur ne réaffiche jamais ces valeurs. Sans ça, chaque
        enregistrement effacerait le mot de passe et la session mémorisée."""
        for champ in ('mot_de_passe', 'session_state'):
            if not validated_data.get(champ):
                validated_data.pop(champ, None)
        return validated_data

    def create(self, validated_data):
        return super().create(self._sans_secrets_vides(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._sans_secrets_vides(validated_data))


class UniteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unite
        fields = ['id', 'nom', 'description']


class PrixArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrixArticle
        fields = ['id', 'article', 'quantite_min', 'prix_ht', 'taux_tva',
                  'releve_le', 'source']


class ArticleFournisseurSerializer(serializers.ModelSerializer):
    prix_actuel = serializers.DecimalField(
        max_digits=10, decimal_places=4, read_only=True)
    prix_unitaire = serializers.DecimalField(
        max_digits=16, decimal_places=4, read_only=True)

    class Meta:
        model = ArticleFournisseur
        fields = ['id', 'fournisseur', 'ingredient', 'libelle', 'reference', 'ean',
                  'marque', 'conditionnement', 'quantite_conditionnement', 'unite',
                  'disponible', 'prefere', 'url', 'source', 'synchronise_le',
                  'prix_actuel', 'prix_unitaire']


class ArticleFournisseurDetailSerializer(ArticleFournisseurSerializer):
    fournisseur_detail = FournisseurSerializer(source='fournisseur', read_only=True)
    unite_detail = UniteSerializer(source='unite', read_only=True)
    prix = PrixArticleSerializer(many=True, read_only=True)

    class Meta(ArticleFournisseurSerializer.Meta):
        fields = ArticleFournisseurSerializer.Meta.fields + [
            'fournisseur_detail', 'unite_detail', 'prix']


class SelecteursCatalogueSerializer(serializers.ModelSerializer):
    """Exposé en lecture seule : ces XPath sont découverts par le robot, pas saisis.
    Les afficher permet de comprendre ce que le robot a compris du site."""
    extraction_prete = serializers.BooleanField(read_only=True)
    connexion_prete = serializers.BooleanField(read_only=True)

    class Meta:
        model = SelecteursCatalogue
        fields = ['fournisseur', 'url_connexion', 'xpath_identifiant',
                  'xpath_mot_de_passe', 'xpath_valider', 'url_produits',
                  'xpath_produit', 'champs', 'xpath_page_suivante',
                  'decouvert_le', 'extraction_prete', 'connexion_prete']
        read_only_fields = fields


class SynchroCatalogueSerializer(serializers.ModelSerializer):
    fournisseur_nom = serializers.CharField(source='fournisseur.nom', read_only=True)

    class Meta:
        model = SynchroCatalogue
        fields = ['id', 'fournisseur', 'fournisseur_nom', 'statut', 'etape', 'message',
                  'pages_scannees', 'appels_mistral', 'articles_crees', 'articles_maj',
                  'prix_releves', 'articles_rattaches', 'ingredients_crees',
                  'articles_ignores', 'journal', 'demarre_le', 'termine_le']
        read_only_fields = fields


class IngredientSerializer(serializers.ModelSerializer):
    sous_seuil = serializers.SerializerMethodField(read_only=True)
    nb_articles = serializers.SerializerMethodField(read_only=True)
    fournisseurs = serializers.SerializerMethodField(read_only=True)
    meilleur_prix_unitaire = serializers.DecimalField(
        max_digits=16, decimal_places=4, read_only=True)
    unite_detail = UniteSerializer(source='unite', read_only=True)

    class Meta:
        model = Ingredient
        fields = ['id', 'nom', 'quantite_stock', 'seuil_alerte', 'unite', 'sous_seuil',
                  'nb_articles', 'fournisseurs', 'meilleur_prix_unitaire', 'unite_detail']

    def get_sous_seuil(self, obj):
        if obj.seuil_alerte is None:
            return False
        return obj.quantite_stock < obj.seuil_alerte

    def get_nb_articles(self, obj):
        return len(obj.articles_disponibles)

    def get_fournisseurs(self, obj):
        noms = []
        for article in obj.articles_disponibles:
            if article.fournisseur.nom not in noms:
                noms.append(article.fournisseur.nom)
        return noms


class IngredientDetailSerializer(IngredientSerializer):
    articles = ArticleFournisseurDetailSerializer(many=True, read_only=True)

    class Meta(IngredientSerializer.Meta):
        fields = IngredientSerializer.Meta.fields + ['articles']


class LigneRecetteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneRecette
        fields = ['id', 'ingredient', 'quantite']


class RecetteSerializer(serializers.ModelSerializer):
    # Chiffré au meilleur prix fournisseur connu. null si un ingrédient n'a pas de prix :
    # un coût partiel serait faussement rassurant pour fixer un prix de vente.
    cout_matiere = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True)
    cout_par_portion = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Recette
        fields = ['id', 'nom', 'instructions_html', 'temps_preparation', 'nb_portions',
                  'cout_matiere', 'cout_par_portion']


class RecetteDetailSerializer(RecetteSerializer):
    lignes_recette = LigneRecetteSerializer(many=True, read_only=True)

    class Meta(RecetteSerializer.Meta):
        fields = RecetteSerializer.Meta.fields + ['lignes_recette']


class PlatSerializer(serializers.ModelSerializer):
    sous_categorie_detail = SousCategoriePlatSerializer(source='sous_categorie', read_only=True)

    class Meta:
        model = Plat
        fields = [
            'id', 'nom', 'description', 'photo', 'prix_unitaire', 'taux_tva',
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


class EvenementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evenement
        fields = ['id', 'ville', 'titre', 'date_debut', 'date_fin',
                  'surplus_frequentation', 'confiance', 'source', 'created_at']
        read_only_fields = ['created_at']


class DonneeMeteoHoraireSerializer(serializers.ModelSerializer):
    class Meta:
        model = DonneeMeteoHoraire
        fields = ['id', 'ville', 'horodatage', 'temperature', 'nebulosite', 'precipitation', 'source']


class IndicateurMeteoConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicateurMeteoConfig
        fields = ['id', 'nom', 'champ', 'agregation', 'heure_debut', 'heure_fin', 'actif']


class VenteAgregeeSerializer(serializers.ModelSerializer):
    categorie_nom = serializers.SerializerMethodField()

    class Meta:
        model = VenteAgregee
        fields = ['id', 'date', 'categorie', 'categorie_nom',
                  'montant_ht', 'montant_ttc', 'quantite', 'source']

    def get_categorie_nom(self, obj):
        return obj.categorie.nom if obj.categorie else 'Global'


class ConfigurationMistralSerializer(serializers.ModelSerializer):
    """Accès à l'API, partagé par les trois usages (robot, recettes, événements)."""
    class Meta:
        model = ConfigurationMistral
        fields = ['actif', 'api_key', 'modele', 'updated_at']
        read_only_fields = ['updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        key = data.get('api_key', '')
        if key:
            data['api_key'] = '••••••••' + key[-4:]
        return data


class PromptMistralSerializer(serializers.Serializer):
    """Un prompt par usage. `contenu` vide = le défaut du code s'applique."""
    usage = serializers.CharField(read_only=True)
    libelle = serializers.CharField(read_only=True)
    contenu = serializers.CharField(allow_blank=True)
    par_defaut = serializers.CharField(read_only=True)
    personnalise = serializers.BooleanField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)


class ConfigurationAgentEvenementsSerializer(serializers.ModelSerializer):
    """Paramètres propres à l'agent calendrier (ville, période). La clé et le modèle
    sont dans ConfigurationMistral, le prompt dans PromptMistral."""
    class Meta:
        model = ConfigurationAgentEvenements
        fields = ['ville', 'mois', 'annee', 'updated_at']
        read_only_fields = ['updated_at']


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
