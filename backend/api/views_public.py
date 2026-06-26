import stripe
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Plat, Commande, LigneCommande, CanalCommande, StatutCommande, StatutPaiement, Paiement, ConfigurationStripe
from .serializers import PlatSerializer, CommandeDetailSerializer, LigneCommandeCreateSerializer, PaiementSerializer


@api_view(['GET'])
@permission_classes([AllowAny])
def public_plats(request):
    plats = Plat.objects.filter(actif=True).order_by('nom')
    return Response(PlatSerializer(plats, many=True).data)


@api_view(['POST'])
@permission_classes([AllowAny])
def public_create_commande(request):
    numero_table = request.data.get('numero_table')
    if not numero_table:
        return Response({'detail': 'numero_table requis.'}, status=status.HTTP_400_BAD_REQUEST)

    canal, _ = CanalCommande.objects.get_or_create(
        nom='sur_place',
        defaults={'description': 'Commande passée en salle'},
    )
    statut_cmd, _ = StatutCommande.objects.get_or_create(
        nom='en_attente',
        defaults={'description': 'Commande en attente de traitement'},
    )
    commande = Commande.objects.create(
        numero_table=int(numero_table),
        canal=canal,
        statut=statut_cmd,
    )
    return Response(CommandeDetailSerializer(commande).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_commande_detail(request, commande_id):
    commande = get_object_or_404(
        Commande.objects.select_related('canal', 'statut').prefetch_related(
            'lignes_commande__plat', 'paiement__statut'
        ),
        pk=commande_id,
    )
    return Response(CommandeDetailSerializer(commande).data)


@api_view(['POST'])
@permission_classes([AllowAny])
def public_add_ligne(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    serializer = LigneCommandeCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    plat = serializer.validated_data['plat']
    serializer.save(commande=commande, prix_unitaire_snapshot=plat.prix_unitaire)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def public_delete_ligne(request, commande_id, ligne_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    ligne = get_object_or_404(LigneCommande, pk=ligne_id, commande=commande)
    ligne.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([AllowAny])
def public_payer(request, commande_id):
    commande = get_object_or_404(
        Commande.objects.prefetch_related('lignes_commande'),
        pk=commande_id,
    )
    if Paiement.objects.filter(commande=commande).exists():
        return Response({'detail': 'Cette commande a déjà été payée.'}, status=status.HTTP_400_BAD_REQUEST)

    methode = request.data.get('methode', 'carte')
    montant = sum(
        l.quantite * l.prix_unitaire_snapshot
        for l in commande.lignes_commande.all()
    )

    statut_paye, _ = StatutPaiement.objects.get_or_create(
        nom='paye',
        defaults={'description': 'Paiement validé'},
    )
    paiement = Paiement.objects.create(
        commande=commande,
        statut=statut_paye,
        montant=montant,
        methode=methode,
    )

    statut_prep, _ = StatutCommande.objects.get_or_create(
        nom='en_preparation',
        defaults={'description': 'Commande prise en charge en cuisine'},
    )
    commande.statut = statut_prep
    commande.save(update_fields=['statut'])

    return Response(PaiementSerializer(paiement).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
def public_stripe_checkout(request, commande_id):
    commande = get_object_or_404(
        Commande.objects.prefetch_related('lignes_commande__plat'),
        pk=commande_id,
    )

    if Paiement.objects.filter(commande=commande, methode='stripe').exists():
        return Response({'detail': 'Un paiement Stripe est déjà en cours pour cette commande.'}, status=status.HTTP_400_BAD_REQUEST)

    config = ConfigurationStripe.get()
    if not config.stripe_secret_key:
        return Response(
            {'detail': 'Le paiement en ligne n\'est pas disponible pour le moment.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    stripe.api_key = config.stripe_secret_key

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:4200')
    script_name = getattr(settings, 'FORCE_SCRIPT_NAME', '') or ''

    line_items = [
        {
            'price_data': {
                'currency': 'eur',
                'product_data': {'name': ligne.plat.nom},
                'unit_amount': int(ligne.prix_unitaire_snapshot * 100),
            },
            'quantity': ligne.quantite,
        }
        for ligne in commande.lignes_commande.all()
    ]

    if not line_items:
        return Response({'detail': 'La commande ne contient aucun article.'}, status=status.HTTP_400_BAD_REQUEST)

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        metadata={'commande_id': str(commande.pk)},
        success_url=f'{frontend_url}{script_name}/commander?paiement=succes&commande={commande.pk}',
        cancel_url=f'{frontend_url}{script_name}/commander?paiement=annule&commande={commande.pk}&table={commande.numero_table}',
    )

    return Response({'checkout_url': session.url})
