import threading
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    CategoriePlat, SousCategoriePlat,
    Fournisseur, Unite, Ingredient, ArticleFournisseur, PrixArticle,
    SelecteursCatalogue, SynchroCatalogue,
    Recette, LigneRecette, Plat, StockPlat,
    TableRestaurant, CompteClient, Employe, CanalCommande, StatutCommande,
    StatutPaiement, Commande, LigneCommande, Paiement, PlageTravail, MouvementStock,
    Facture,
)
from .serializers import (
    CategoriePlatSerializer, SousCategoriePlatSerializer,
    FournisseurSerializer, UniteSerializer,
    IngredientSerializer, IngredientDetailSerializer,
    ArticleFournisseurSerializer, ArticleFournisseurDetailSerializer,
    PrixArticleSerializer, SelecteursCatalogueSerializer, SynchroCatalogueSerializer,
    RecetteSerializer, RecetteDetailSerializer, LigneRecetteSerializer,
    PlatSerializer, StockPlatSerializer, TableRestaurantSerializer,
    CompteClientSerializer, EmployeSerializer,
    CanalCommandeSerializer, StatutCommandeSerializer, StatutPaiementSerializer,
    CommandeSerializer, CommandeDetailSerializer,
    LigneCommandeSerializer, LigneCommandeCreateSerializer,
    PaiementSerializer, PlageTravailSerializer, MouvementStockSerializer,
    FactureSerializer,
)
from .permissions import IsManager, IsManagerOrCuisinier, IsManagerOrServeur, IsAnyStaff
from . import constants
from . import nomenclature as nomenclature_module


class CategoriePlatViewSet(viewsets.ModelViewSet):
    queryset = CategoriePlat.objects.prefetch_related('sous_categories').all()
    serializer_class = CategoriePlatSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]


class SousCategoriePlatViewSet(viewsets.ModelViewSet):
    queryset = SousCategoriePlat.objects.select_related('categorie').all()
    serializer_class = SousCategoriePlatSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]


class FournisseurViewSet(viewsets.ModelViewSet):
    queryset = Fournisseur.objects.all()
    serializer_class = FournisseurSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]

    @action(detail=True, methods=['post'], url_path='synchroniser')
    def synchroniser(self, request, pk=None):
        """Lance le robot de catalogue en tâche de fond.

        Un scan dure plusieurs minutes (navigation + appels Mistral + pagination) :
        on ne peut pas le faire dans le cycle de la requête. On répond immédiatement
        avec la SynchroCatalogue, que le client interroge pour suivre l'avancement.
        """
        fournisseur = self.get_object()
        if not fournisseur.url:
            return Response(
                {'detail': "Renseignez l'URL du site du fournisseur avant de lancer le robot."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        en_cours = SynchroCatalogue.objects.filter(
            fournisseur=fournisseur, statut='en_cours').first()
        if en_cours:
            return Response(
                {'detail': 'Une synchronisation est déjà en cours pour ce fournisseur.',
                 'synchro': SynchroCatalogueSerializer(en_cours).data},
                status=status.HTTP_409_CONFLICT,
            )

        synchro = SynchroCatalogue.objects.create(
            fournisseur=fournisseur, etape='Démarrage…')

        from .robot_fournisseur import synchroniser as lancer
        threading.Thread(target=lancer, args=(synchro.id,), daemon=True).start()

        return Response(SynchroCatalogueSerializer(synchro).data,
                        status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], url_path='oublier-session')
    def oublier_session(self, request, pk=None):
        """Efface l'état du navigateur mémorisé (magasin, cookies, session). La prochaine
        synchro repartira d'un navigateur vierge — utile si le magasin choisi n'est pas
        le bon, ou si la session a expiré et bloque le robot."""
        fournisseur = self.get_object()
        fournisseur.session_state = ''
        fournisseur.save(update_fields=['session_state'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='oublier-selecteurs')
    def oublier_selecteurs(self, request, pk=None):
        """Vide le cache de XPath : la prochaine synchro redécouvrira tout via Mistral.
        Utile quand le site a changé au point que le robot part dans le décor."""
        fournisseur = self.get_object()
        SelecteursCatalogue.objects.filter(fournisseur=fournisseur).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='selecteurs')
    def selecteurs(self, request, pk=None):
        fournisseur = self.get_object()
        selecteurs = SelecteursCatalogue.objects.filter(fournisseur=fournisseur).first()
        if not selecteurs:
            return Response({'detail': 'Aucun sélecteur en cache.'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(SelecteursCatalogueSerializer(selecteurs).data)


class SynchroCatalogueViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal des runs du robot — interrogé en boucle par le frontend pendant un scan."""
    queryset = SynchroCatalogue.objects.select_related('fournisseur').all()
    serializer_class = SynchroCatalogueSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        fournisseur = self.request.query_params.get('fournisseur')
        if fournisseur:
            qs = qs.filter(fournisseur_id=fournisseur)
        return qs


class UniteViewSet(viewsets.ModelViewSet):
    queryset = Unite.objects.all()
    serializer_class = UniteSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrCuisinier()]
        return [IsAuthenticated(), IsManager()]


def _prefetch_articles():
    """Les prix et fournisseurs sont lus en Python (paliers, meilleur prix) :
    sans ce prefetch, chaque ingrédient déclencherait une cascade de requêtes."""
    return Prefetch(
        'articles',
        queryset=ArticleFournisseur.objects.select_related(
            'fournisseur', 'unite').prefetch_related('prix'),
    )


class IngredientViewSet(viewsets.ModelViewSet):
    queryset = Ingredient.objects.select_related('unite').prefetch_related(
        _prefetch_articles()).all()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return IngredientDetailSerializer
        return IngredientSerializer

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsManagerOrCuisinier()]

    def get_queryset(self):
        qs = super().get_queryset()
        sous_seuil = self.request.query_params.get('sous_seuil')
        if sous_seuil and sous_seuil.lower() == 'true':
            qs = qs.filter(
                seuil_alerte__isnull=False,
                quantite_stock__lt=F('seuil_alerte'),
            )
        return qs


class ArticleFournisseurViewSet(viewsets.ModelViewSet):
    """Catalogue : les références achetables chez les fournisseurs."""
    queryset = ArticleFournisseur.objects.select_related(
        'fournisseur', 'unite', 'ingredient').prefetch_related('prix').all()

    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return ArticleFournisseurDetailSerializer
        return ArticleFournisseurSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrCuisinier()]
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        fournisseur = params.get('fournisseur')
        if fournisseur:
            qs = qs.filter(fournisseur_id=fournisseur)

        ingredient = params.get('ingredient')
        if ingredient:
            qs = qs.filter(ingredient_id=ingredient)

        # Articles rapportés par le robot mais pas encore rattachés à un ingrédient :
        # c'est la file d'attente de mapping.
        if (params.get('sans_ingredient') or '').lower() == 'true':
            qs = qs.filter(ingredient__isnull=True)

        recherche = params.get('q')
        if recherche:
            qs = qs.filter(
                Q(libelle__icontains=recherche)
                | Q(marque__icontains=recherche)
                | Q(reference__icontains=recherche)
                | Q(ean__icontains=recherche)
            )
        return qs

    @action(detail=True, methods=['post'], url_path='prix')
    def ajouter_prix(self, request, pk=None):
        """Ajoute un relevé de tarif (on historise, on n'écrase pas)."""
        article = self.get_object()
        data = {**request.data, 'article': article.pk}
        serializer = PrixArticleSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        article.refresh_from_db()
        return Response(
            ArticleFournisseurDetailSerializer(article).data,
            status=status.HTTP_201_CREATED,
        )


class PrixArticleViewSet(viewsets.ModelViewSet):
    queryset = PrixArticle.objects.select_related('article').all()
    serializer_class = PrixArticleSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrCuisinier()]
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        article = self.request.query_params.get('article')
        if article:
            qs = qs.filter(article_id=article)
        return qs


def _chiffrer_proposition(proposition):
    """Annote chaque ingrédient proposé : existe-t-il déjà ? a-t-il un prix fournisseur ?
    combien coûte la quantité demandée ? Puis totalise.

    Le coût n'est donné que si TOUS les ingrédients ont un prix connu : un coût partiel
    serait faussement rassurant, et c'est sur lui que le prix de vente serait fixé.
    """
    lignes = []
    total = Decimal('0')
    complet = True

    for ligne in (proposition.get('ingredients') or []):
        nom = nomenclature_module.normaliser_nom(ligne.get('nom'))
        try:
            quantite = Decimal(str(ligne.get('quantite') or 0))
        except (InvalidOperation, ValueError):
            quantite = Decimal('0')

        ingredient = nomenclature_module.trouver(nom)
        prix_unitaire = ingredient.meilleur_prix_unitaire if ingredient else None
        cout = prix_unitaire * quantite if prix_unitaire is not None else None
        if cout is None:
            complet = False
        else:
            total += cout

        if ingredient:
            unite, unite_corrigee = ingredient.unite.nom, False
        else:
            # Afficher l'unité que le LLM a proposée serait mentir : si elle n'est pas
            # dans la liste autorisée, ce n'est pas elle qui sera enregistrée.
            unite_obj, unite_corrigee = nomenclature_module.resoudre_unite(ligne.get('unite'))
            unite = unite_obj.nom

        lignes.append({
            'nom': nom,
            'quantite': quantite,
            'unite': unite,
            'unite_corrigee': unite_corrigee,
            'unite_proposee': (ligne.get('unite') or '') if unite_corrigee else '',
            'existant': ingredient is not None,
            'prix_unitaire': prix_unitaire,
            'cout': cout,
        })

    nb_portions = max(1, int(proposition.get('nb_portions') or 1))
    return {
        'nom': proposition.get('nom') or '',
        'temps_preparation': proposition.get('temps_preparation') or 0,
        'nb_portions': nb_portions,
        'instructions_html': proposition.get('instructions_html') or '',
        'ingredients': lignes,
        'cout_matiere': total if complet else None,
        'cout_par_portion': (total / nb_portions) if complet else None,
        'cout_incomplet': not complet,
    }


class RecetteViewSet(viewsets.ModelViewSet):
    queryset = Recette.objects.all()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return RecetteDetailSerializer
        return RecetteSerializer

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsManagerOrCuisinier()]

    @action(detail=True, methods=['get', 'post'], url_path='lignes')
    def lignes(self, request, pk=None):
        recette = self.get_object()
        if request.method == 'GET':
            lignes = LigneRecette.objects.filter(recette=recette).select_related('ingredient')
            return Response(LigneRecetteSerializer(lignes, many=True).data)

        serializer = LigneRecetteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(recette=recette)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'lignes/(?P<ligne_id>\d+)')
    def ligne_delete(self, request, pk=None, ligne_id=None):
        recette = self.get_object()
        ligne = get_object_or_404(LigneRecette, pk=ligne_id, recette=recette)
        ligne.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='generer')
    def generer(self, request):
        """Propose une recette SANS rien enregistrer : l'utilisateur valide avant
        sauvegarde (même patron que « proposer-mistral » pour les événements).

        La recette est composée à partir du référentiel d'ingrédients : on peut donc
        la chiffrer au prix fournisseur avant même de l'enregistrer.
        """
        from .nomenclature import nomenclature, unites_autorisees
        from .recette_mistral import generer as generer_recette
        from .robot_mistral import RobotErreur, RobotNonConfigure

        demande = (request.data.get('demande') or '').strip()
        if not demande:
            return Response({'detail': 'Décrivez la recette souhaitée.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            nb_portions = max(1, int(request.data.get('nb_portions') or 4))
        except (TypeError, ValueError):
            nb_portions = 4
        contraintes = request.data.get('contraintes') or []

        try:
            proposition = generer_recette(
                demande, nb_portions, contraintes, nomenclature(), unites_autorisees())
        except RobotNonConfigure as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RobotErreur as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(_chiffrer_proposition(proposition))

    @action(detail=False, methods=['post'], url_path='enregistrer-generee')
    def enregistrer_generee(self, request):
        """Crée la Recette, ses lignes, et le Plat associé. Le prix de vente vient de
        l'utilisateur : on ne le devine pas."""
        from .nomenclature import resoudre_ou_creer

        data = request.data
        nom = (data.get('nom') or '').strip()
        if not nom:
            return Response({'detail': 'Le nom de la recette est obligatoire.'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            recette = Recette.objects.create(
                nom=nom[:200],
                instructions_html=data.get('instructions_html') or '',
                temps_preparation=int(data.get('temps_preparation') or 0),
                nb_portions=max(1, int(data.get('nb_portions') or 1)),
            )

            for ligne in (data.get('ingredients') or []):
                ingredient, _ = resoudre_ou_creer(ligne.get('nom'), ligne.get('unite'))
                if ingredient is None:
                    continue
                try:
                    quantite = Decimal(str(ligne.get('quantite') or 0))
                except (InvalidOperation, ValueError):
                    continue
                if quantite <= 0:
                    continue

                # unique_together(recette, ingredient) : si le modèle a listé deux fois
                # le même ingrédient malgré la consigne, on additionne au lieu de planter.
                existante, creee = LigneRecette.objects.get_or_create(
                    recette=recette, ingredient=ingredient,
                    defaults={'quantite': quantite})
                if not creee:
                    existante.quantite += quantite
                    existante.save(update_fields=['quantite'])

            plat = None
            plat_data = data.get('plat') or {}
            if plat_data.get('creer'):
                try:
                    prix = Decimal(str(plat_data.get('prix_unitaire') or 0))
                except (InvalidOperation, ValueError):
                    prix = Decimal('0')
                plat = Plat.objects.create(
                    nom=(plat_data.get('nom') or recette.nom)[:200],
                    description=plat_data.get('description') or '',
                    prix_unitaire=prix,
                    recette=recette,
                    sous_categorie_id=plat_data.get('sous_categorie') or None,
                    sans_gluten=bool(plat_data.get('sans_gluten')),
                    vegetarien=bool(plat_data.get('vegetarien')),
                    halal=bool(plat_data.get('halal')),
                    # Un plat à 0 € ne doit jamais atterrir sur la carte publique.
                    actif=prix > 0,
                )

        return Response(
            {'recette': RecetteDetailSerializer(recette).data,
             'plat': PlatSerializer(plat).data if plat else None},
            status=status.HTTP_201_CREATED,
        )


class PlatViewSet(viewsets.ModelViewSet):
    queryset = Plat.objects.select_related('recette', 'sous_categorie__categorie').all()
    serializer_class = PlatSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrServeur()]
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ['actif', 'sans_gluten', 'halal', 'vegetarien']:
            val = self.request.query_params.get(field)
            if val is not None:
                qs = qs.filter(**{field: val.lower() == 'true'})
        return qs


class StockPlatViewSet(viewsets.ModelViewSet):
    queryset = StockPlat.objects.select_related('plat').all()
    serializer_class = StockPlatSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrCuisinier()]
        return [IsAuthenticated(), IsManager()]


class TableRestaurantViewSet(viewsets.ModelViewSet):
    queryset = TableRestaurant.objects.all()
    serializer_class = TableRestaurantSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]


class CompteClientViewSet(viewsets.ModelViewSet):
    queryset = CompteClient.objects.select_related('user').all()
    serializer_class = CompteClientSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]


class EmployeViewSet(viewsets.ModelViewSet):
    queryset = Employe.objects.select_related('user').all()
    serializer_class = EmployeSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]


class CanalCommandeViewSet(viewsets.ModelViewSet):
    queryset = CanalCommande.objects.all()
    serializer_class = CanalCommandeSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]


class StatutCommandeViewSet(viewsets.ModelViewSet):
    queryset = StatutCommande.objects.all()
    serializer_class = StatutCommandeSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]


class StatutPaiementViewSet(viewsets.ModelViewSet):
    queryset = StatutPaiement.objects.all()
    serializer_class = StatutPaiementSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]


class CommandeViewSet(viewsets.ModelViewSet):
    queryset = Commande.objects.select_related(
        'canal', 'statut', 'table_restaurant', 'compte_client',
        'paiement', 'paiement__statut',
    ).prefetch_related('lignes_commande__plat').all()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CommandeDetailSerializer
        return CommandeSerializer

    def get_permissions(self):
        # L'encaissement sur place est réservé aux rôles en contact avec le client.
        if self.action == 'confirmer_paiement':
            return [IsAuthenticated(), IsManagerOrServeur()]
        return [IsAuthenticated(), IsAnyStaff()]

    def get_queryset(self):
        qs = super().get_queryset()
        statut_id = self.request.query_params.get('statut')
        canal_id = self.request.query_params.get('canal')
        date_debut = self.request.query_params.get('date_debut')
        date_fin = self.request.query_params.get('date_fin')
        if statut_id:
            qs = qs.filter(statut_id=statut_id)
        if canal_id:
            qs = qs.filter(canal_id=canal_id)
        if date_debut:
            qs = qs.filter(created_at__date__gte=date_debut)
        if date_fin:
            qs = qs.filter(created_at__date__lte=date_fin)
        numero_table = self.request.query_params.get('numero_table')
        if numero_table:
            qs = qs.filter(numero_table=numero_table)
        limit = self.request.query_params.get('limit')
        if limit:
            try:
                qs = qs[:int(limit)]
            except (ValueError, TypeError):
                pass
        return qs

    def perform_create(self, serializer):
        statut = serializer.validated_data.get('statut')
        if not statut:
            statut, _ = StatutCommande.objects.get_or_create(
                nom=constants.STATUT_CMD_EN_ATTENTE,
                defaults={'description': constants.DESC_CMD_EN_ATTENTE},
            )
        canal = serializer.validated_data.get('canal')
        if not canal:
            canal, _ = CanalCommande.objects.get_or_create(
                nom=constants.CANAL_SUR_PLACE,
                defaults={'description': constants.DESC_CANAL_SUR_PLACE},
            )
        serializer.save(statut=statut, canal=canal)

    @action(detail=True, methods=['get', 'post'], url_path='lignes')
    def lignes(self, request, pk=None):
        commande = self.get_object()
        if request.method == 'GET':
            lignes = commande.lignes_commande.all()
            return Response(LigneCommandeCreateSerializer(lignes, many=True).data)

        serializer = LigneCommandeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plat = serializer.validated_data['plat']
        prix = plat.prix_unitaire
        serializer.save(commande=commande, prix_unitaire_snapshot=prix)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'lignes/(?P<ligne_id>\d+)')
    def ligne_delete(self, request, pk=None, ligne_id=None):
        commande = self.get_object()
        ligne = get_object_or_404(LigneCommande, pk=ligne_id, commande=commande)
        ligne.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='confirmer-paiement')
    def confirmer_paiement(self, request, pk=None):
        """Marque une commande réglée sur place (liquide, ticket resto…).

        Réservé au personnel en contact client ; trace l'employé qui encaisse.
        Aucun appel à Stripe : règlement enregistré localement. Si un paiement
        « en attente » existe déjà (flux libre-service), il est confirmé ;
        sinon un paiement est créé pour le total de la commande.
        """
        commande = self.get_object()
        methode = request.data.get('methode') or 'espèces'
        confirme_par = (
            getattr(request.user, 'username', '')
            or getattr(request.user, 'email', '')
        )
        statut_paye, _ = StatutPaiement.objects.get_or_create(
            nom=constants.STATUT_PAIEMENT_PAYE,
            defaults={'description': constants.DESC_PAIEMENT_PAYE},
        )

        paiement = Paiement.objects.filter(commande=commande).select_related('statut').first()
        if paiement:
            if paiement.statut.nom == constants.STATUT_PAIEMENT_PAYE:
                return Response({'detail': 'Cette commande est déjà réglée.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if paiement.methode == 'stripe':
                return Response({'detail': 'Paiement Stripe : le règlement se fait en ligne.'},
                                status=status.HTTP_400_BAD_REQUEST)
            paiement.statut = statut_paye
            paiement.methode = methode
            paiement.confirme_par = confirme_par
            paiement.save(update_fields=['statut', 'methode', 'confirme_par'])
        else:
            montant = sum(
                l.quantite * l.prix_unitaire_snapshot
                for l in commande.lignes_commande.all()
            )
            if not montant:
                return Response({'detail': 'La commande ne contient aucun article.'},
                                status=status.HTTP_400_BAD_REQUEST)
            paiement = Paiement.objects.create(
                commande=commande,
                statut=statut_paye,
                montant=montant,
                methode=methode,
                confirme_par=confirme_par,
            )

        return Response(PaiementSerializer(paiement).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'post'], url_path='facture')
    def facture(self, request, pk=None):
        """GET : métadonnées de la facture. POST : la crée si besoin et, si un
        champ `email` est fourni, génère le PDF et l'envoie en pièce jointe."""
        from . import invoices
        commande = self.get_object()
        if request.method == 'GET':
            facture = Facture.objects.filter(commande=commande).first()
            if not facture:
                return Response({'detail': 'Aucune facture pour cette commande.'},
                                status=status.HTTP_404_NOT_FOUND)
            return Response(FactureSerializer(facture).data)

        facture, _ = invoices.get_or_create_facture(commande)
        if facture is None:
            return Response({'detail': 'La commande ne contient aucun article.'},
                            status=status.HTTP_400_BAD_REQUEST)

        email = (request.data.get('email') or '').strip()
        if email:
            try:
                invoices.envoyer_facture(facture, email)
            except Exception as exc:  # SMTP indisponible / mal configuré
                return Response(
                    {'detail': f"Échec de l'envoi de l'email : {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        return Response(FactureSerializer(facture).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='facture/pdf')
    def facture_pdf(self, request, pk=None):
        from .invoices import generer_pdf_facture
        commande = self.get_object()
        facture = get_object_or_404(Facture, commande=commande)
        pdf = generer_pdf_facture(facture)
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{facture.numero}.pdf"'
        return response


class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiement.objects.select_related('commande', 'statut').all()
    serializer_class = PaiementSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsAnyStaff()]


class PlageTravailViewSet(viewsets.ModelViewSet):
    queryset = PlageTravail.objects.select_related('employe__user').all()
    serializer_class = PlageTravailSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsAnyStaff()]
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        employe_id = self.request.query_params.get('employe')
        if employe_id:
            qs = qs.filter(employe_id=employe_id)
        return qs


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = MouvementStock.objects.select_related('ingredient', 'employe__user').all()
    serializer_class = MouvementStockSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrCuisinier()]
        return [IsAuthenticated(), IsManagerOrCuisinier()]

    def get_queryset(self):
        qs = super().get_queryset()
        ingredient_id = self.request.query_params.get('ingredient')
        if ingredient_id:
            qs = qs.filter(ingredient_id=ingredient_id)
        return qs
