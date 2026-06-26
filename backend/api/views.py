from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    CategoriePlat, SousCategoriePlat,
    Fournisseur, Unite, Ingredient, Recette, LigneRecette, Plat, StockPlat,
    TableRestaurant, CompteClient, Employe, CanalCommande, StatutCommande,
    StatutPaiement, Commande, LigneCommande, Paiement, PlageTravail, MouvementStock,
)
from .serializers import (
    CategoriePlatSerializer, SousCategoriePlatSerializer,
    FournisseurSerializer, UniteSerializer,
    IngredientSerializer, IngredientDetailSerializer,
    RecetteSerializer, RecetteDetailSerializer, LigneRecetteSerializer,
    PlatSerializer, StockPlatSerializer, TableRestaurantSerializer,
    CompteClientSerializer, EmployeSerializer,
    CanalCommandeSerializer, StatutCommandeSerializer, StatutPaiementSerializer,
    CommandeSerializer, CommandeDetailSerializer,
    LigneCommandeSerializer, LigneCommandeCreateSerializer,
    PaiementSerializer, PlageTravailSerializer, MouvementStockSerializer,
)
from .permissions import IsManager, IsManagerOrCuisinier, IsManagerOrServeur, IsAnyStaff
from . import constants


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


class UniteViewSet(viewsets.ModelViewSet):
    queryset = Unite.objects.all()
    serializer_class = UniteSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), IsManagerOrCuisinier()]
        return [IsAuthenticated(), IsManager()]


class IngredientViewSet(viewsets.ModelViewSet):
    queryset = Ingredient.objects.select_related('fournisseur', 'unite').all()

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
