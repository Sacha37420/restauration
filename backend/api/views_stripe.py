import stripe
import logging
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

logger = logging.getLogger(__name__)

from .models import ConfigurationStripe, Commande, Paiement, StatutPaiement, StatutCommande
from .serializers import ConfigurationStripeSerializer
from .permissions import IsManager
from . import constants

_MASKED_PREFIX = '••••••••'


class ConfigurationStripeView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        config = ConfigurationStripe.get()
        return Response(ConfigurationStripeSerializer(config).data)

    def put(self, request):
        config = ConfigurationStripe.get()
        data = request.data

        new_key = data.get('stripe_secret_key', '')
        new_secret = data.get('stripe_webhook_secret', '')

        # Ne pas écraser si la valeur masquée est renvoyée sans modification
        if new_key and not new_key.startswith(_MASKED_PREFIX):
            config.stripe_secret_key = new_key
        if new_secret and not new_secret.startswith(_MASKED_PREFIX):
            config.stripe_webhook_secret = new_secret

        config.save()
        return Response(ConfigurationStripeSerializer(config).data)


class CreerSessionCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        commande_id = request.data.get('commande_id')
        if not commande_id:
            return Response({'detail': 'commande_id requis.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            commande = Commande.objects.prefetch_related(
                'lignes_commande__plat'
            ).get(pk=commande_id)
        except Commande.DoesNotExist:
            return Response({'detail': 'Commande introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        config = ConfigurationStripe.get()
        if not config.stripe_secret_key:
            return Response(
                {'detail': 'Stripe n\'est pas configuré. Contactez un manager.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        stripe.api_key = config.stripe_secret_key

        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:4200').rstrip('/')

        line_items = []
        for ligne in commande.lignes_commande.all():
            line_items.append({
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': ligne.plat.nom},
                    'unit_amount': int(ligne.prix_unitaire_snapshot * 100),
                },
                'quantity': ligne.quantite,
            })

        if not line_items:
            return Response(
                {'detail': 'La commande ne contient aucun article.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            metadata={'commande_id': str(commande.pk)},
            success_url=f'{frontend_url}/commandes?paiement=succes&commande={commande.pk}',
            cancel_url=f'{frontend_url}/commandes?paiement=annule&commande={commande.pk}',
        )

        return Response({'checkout_url': session.url})


@method_decorator(csrf_exempt, name='dispatch')
class WebhookStripeView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        config = ConfigurationStripe.get()
        if not config.stripe_webhook_secret:
            return Response({'detail': 'Webhook non configuré.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        stripe.api_key = config.stripe_secret_key
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

        try:
            payload = request.body
            event = stripe.Webhook.construct_event(payload, sig_header, config.stripe_webhook_secret)
        except ValueError as e:
            logger.error('Webhook payload invalide: %s', e)
            return Response({'detail': 'Payload invalide.'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            logger.error('Webhook signature invalide: %s', e)
            return Response({'detail': 'Signature invalide.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Erreur inattendue lors de construct_event: %s', e)
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if event.type == 'checkout.session.completed':
                session = event.data.object
                meta = getattr(session, 'metadata', None)
                commande_id = getattr(meta, 'commande_id', None) if meta else None
                if commande_id:
                    self._enregistrer_paiement(commande_id, session)
        except Exception as e:
            logger.exception('Erreur lors du traitement de l\'événement Stripe: %s', e)
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'ok'})

    def _enregistrer_paiement(self, commande_id, session):
        try:
            commande = Commande.objects.get(pk=commande_id)
        except Commande.DoesNotExist:
            return

        statut_paye, _ = StatutPaiement.objects.get_or_create(
            nom=constants.STATUT_PAIEMENT_PAYE,
            defaults={'description': constants.DESC_PAIEMENT_PAYE},
        )
        montant = (session.amount_total or 0) / 100

        Paiement.objects.update_or_create(
            commande=commande,
            defaults={
                'statut': statut_paye,
                'montant': montant,
                'methode': 'stripe',
                'transaction_id': session.payment_intent or '',
            },
        )

        statut_prep, _ = StatutCommande.objects.get_or_create(
            nom=constants.STATUT_CMD_EN_PREPARATION,
            defaults={'description': constants.DESC_CMD_EN_PREPARATION},
        )
        commande.statut = statut_prep
        commande.save(update_fields=['statut'])
