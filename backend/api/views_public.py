import stripe
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import (
    Plat, Commande, LigneCommande, CanalCommande, StatutCommande,
    StatutPaiement, Paiement, ConfigurationStripe, TableRestaurant,
)
from .serializers import PlatSerializer, CommandeDetailSerializer, LigneCommandeCreateSerializer, PaiementSerializer
from . import constants


class PublicReadThrottle(AnonRateThrottle):
    scope = 'public'


class PublicWriteThrottle(AnonRateThrottle):
    scope = 'public-write'


def _commande_modifiable(commande):
    """Une commande publique n'est modifiable que tant qu'aucun paiement
    n'est enregistré (sinon n'importe qui pourrait altérer une commande payée)."""
    return not Paiement.objects.filter(commande=commande).exists()


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([PublicReadThrottle])
def public_plats(request):
    plats = Plat.objects.filter(actif=True).select_related('sous_categorie__categorie')
    return Response(PlatSerializer(plats, many=True).data)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PublicWriteThrottle])
def public_create_commande(request):
    numero_table = request.data.get('numero_table')
    if not numero_table:
        return Response({'detail': 'numero_table requis.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        numero_table = int(numero_table)
    except (ValueError, TypeError):
        return Response({'detail': 'numero_table invalide.'}, status=status.HTTP_400_BAD_REQUEST)

    # La table doit exister et être active (évite la création de commandes
    # sur des numéros arbitraires).
    if not TableRestaurant.objects.filter(numero=numero_table, actif=True).exists():
        return Response({'detail': 'Table inconnue ou inactive.'}, status=status.HTTP_404_NOT_FOUND)

    canal, _ = CanalCommande.objects.get_or_create(
        nom=constants.CANAL_SUR_PLACE,
        defaults={'description': constants.DESC_CANAL_SUR_PLACE},
    )
    statut_cmd, _ = StatutCommande.objects.get_or_create(
        nom=constants.STATUT_CMD_EN_ATTENTE,
        defaults={'description': constants.DESC_CMD_EN_ATTENTE},
    )
    commande = Commande.objects.create(
        numero_table=numero_table,
        canal=canal,
        statut=statut_cmd,
        email_client=(request.data.get('email') or '').strip(),
    )
    return Response(CommandeDetailSerializer(commande).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([PublicReadThrottle])
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
@throttle_classes([PublicWriteThrottle])
def public_add_ligne(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    if not _commande_modifiable(commande):
        return Response(
            {'detail': 'Cette commande est déjà payée et ne peut plus être modifiée.'},
            status=status.HTTP_409_CONFLICT,
        )
    serializer = LigneCommandeCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    plat = serializer.validated_data['plat']
    serializer.save(commande=commande, prix_unitaire_snapshot=plat.prix_unitaire)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([AllowAny])
@throttle_classes([PublicWriteThrottle])
def public_delete_ligne(request, commande_id, ligne_id):
    commande = get_object_or_404(Commande, pk=commande_id)
    if not _commande_modifiable(commande):
        return Response(
            {'detail': 'Cette commande est déjà payée et ne peut plus être modifiée.'},
            status=status.HTTP_409_CONFLICT,
        )
    ligne = get_object_or_404(LigneCommande, pk=ligne_id, commande=commande)
    ligne.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PublicWriteThrottle])
def public_payer(request, commande_id):
    commande = get_object_or_404(
        Commande.objects.prefetch_related('lignes_commande'),
        pk=commande_id,
    )
    if Paiement.objects.filter(commande=commande).exists():
        return Response({'detail': 'Cette commande a déjà été payée.'}, status=status.HTTP_400_BAD_REQUEST)

    methode = request.data.get('methode', 'espèces')
    # Le paiement par carte passe obligatoirement par Stripe : on n'accepte ici
    # que les méthodes encaissées sur place. Le serveur ne peut pas confirmer
    # un encaissement physique, donc le paiement est enregistré « en attente ».
    if methode not in constants.METHODES_SUR_PLACE:
        return Response(
            {'detail': 'Méthode de paiement non autorisée pour ce canal. Utilisez le paiement en ligne.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    montant = sum(
        l.quantite * l.prix_unitaire_snapshot
        for l in commande.lignes_commande.all()
    )
    if not montant:
        return Response(
            {'detail': 'La commande ne contient aucun article.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    statut_attente, _ = StatutPaiement.objects.get_or_create(
        nom=constants.STATUT_PAIEMENT_EN_ATTENTE,
        defaults={'description': constants.DESC_PAIEMENT_EN_ATTENTE},
    )
    paiement = Paiement.objects.create(
        commande=commande,
        statut=statut_attente,
        montant=montant,
        methode=methode,
    )

    statut_prep, _ = StatutCommande.objects.get_or_create(
        nom=constants.STATUT_CMD_EN_PREPARATION,
        defaults={'description': constants.DESC_CMD_EN_PREPARATION},
    )
    commande.statut = statut_prep
    commande.save(update_fields=['statut'])

    # Envoi automatique de la facture si un email a été fourni (best effort).
    email = (request.data.get('email') or commande.email_client or '').strip()
    if email:
        if email != commande.email_client:
            commande.email_client = email
            commande.save(update_fields=['email_client'])
        from .invoices import envoyer_facture_auto
        envoyer_facture_auto(commande, email)

    return Response(PaiementSerializer(paiement).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PublicWriteThrottle])
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

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:4200').rstrip('/')

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

    email = (request.data.get('email') or '').strip()
    if email and email != commande.email_client:
        commande.email_client = email
        commande.save(update_fields=['email_client'])

    session_kwargs = dict(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        metadata={'commande_id': str(commande.pk)},
        success_url=f'{frontend_url}/commander?paiement=succes&commande={commande.pk}',
        cancel_url=f'{frontend_url}/commander?paiement=annule&commande={commande.pk}&table={commande.numero_table}',
    )
    if email:
        session_kwargs['customer_email'] = email
    session = stripe.checkout.Session.create(**session_kwargs)

    return Response({'checkout_url': session.url})
