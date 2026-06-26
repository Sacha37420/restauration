from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    CategoriePlat, SousCategoriePlat,
    Fournisseur, Unite, Ingredient, Recette, LigneRecette, Plat, StockPlat,
    TableRestaurant, CompteClient, Employe, CanalCommande, StatutCommande,
    StatutPaiement, Commande, LigneCommande, Paiement, PlageTravail, MouvementStock,
    Facture,
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
    FactureSerializer,
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

    def _get_or_create_facture(self, commande):
        """Récupère la facture de la commande ou la crée (numérotation FA-AAAA-NNNN)."""
        facture = Facture.objects.filter(commande=commande).first()
        if facture:
            return facture, False
        montant = sum(
            l.quantite * l.prix_unitaire_snapshot
            for l in commande.lignes_commande.all()
        )
        if not montant:
            return None, False
        annee = timezone.now().year
        prefixe = f'FA-{annee}-'
        with transaction.atomic():
            dernier = (
                Facture.objects.select_for_update()
                .filter(numero__startswith=prefixe)
                .order_by('-numero')
                .first()
            )
            seq = int(dernier.numero.rsplit('-', 1)[-1]) + 1 if dernier else 1
            facture = Facture.objects.create(
                commande=commande,
                numero=f'{prefixe}{seq:04d}',
                montant_ttc=montant,
                taux_tva=Decimal(str(settings.FACTURE_TVA_TAUX)),
            )
        return facture, True

    @action(detail=True, methods=['get', 'post'], url_path='facture')
    def facture(self, request, pk=None):
        """GET : métadonnées de la facture. POST : la crée si besoin et, si un
        champ `email` est fourni, génère le PDF et l'envoie en pièce jointe."""
        commande = self.get_object()
        if request.method == 'GET':
            facture = Facture.objects.filter(commande=commande).first()
            if not facture:
                return Response({'detail': 'Aucune facture pour cette commande.'},
                                status=status.HTTP_404_NOT_FOUND)
            return Response(FactureSerializer(facture).data)

        facture, _ = self._get_or_create_facture(commande)
        if facture is None:
            return Response({'detail': 'La commande ne contient aucun article.'},
                            status=status.HTTP_400_BAD_REQUEST)

        email = (request.data.get('email') or '').strip()
        if email:
            from .invoices import generer_pdf_facture, envoyer_facture_email
            pdf = generer_pdf_facture(facture)
            try:
                envoyer_facture_email(facture, pdf, email)
            except Exception as exc:  # SMTP indisponible / mal configuré
                return Response(
                    {'detail': f"Échec de l'envoi de l'email : {exc}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            facture.email_destinataire = email
            facture.envoyee_at = timezone.now()
            facture.save(update_fields=['email_destinataire', 'envoyee_at'])

        return Response(FactureSerializer(facture).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='facture/pdf')
    def facture_pdf(self, request, pk=None):
        commande = self.get_object()
        facture = get_object_or_404(Facture, commande=commande)
        from .invoices import generer_pdf_facture
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
