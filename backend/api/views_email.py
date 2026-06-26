from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import ConfigurationEmail
from .serializers import ConfigurationEmailSerializer
from .permissions import IsManager

_MASKED_PREFIX = '••••••••'


class ConfigurationEmailView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        return Response(ConfigurationEmailSerializer(ConfigurationEmail.get()).data)

    def put(self, request):
        cfg = ConfigurationEmail.get()
        data = request.data

        cfg.actif = bool(data.get('actif', cfg.actif))
        cfg.email_host = data.get('email_host', cfg.email_host)
        cfg.email_use_tls = bool(data.get('email_use_tls', cfg.email_use_tls))
        cfg.email_host_user = data.get('email_host_user', cfg.email_host_user)
        cfg.default_from_email = data.get('default_from_email', cfg.default_from_email)
        try:
            cfg.email_port = int(data.get('email_port', cfg.email_port) or 587)
        except (ValueError, TypeError):
            return Response({'detail': 'Port invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        # Ne pas écraser le mot de passe si la valeur masquée est renvoyée telle quelle.
        pwd = data.get('email_host_password', '')
        if pwd and not pwd.startswith(_MASKED_PREFIX):
            cfg.email_host_password = pwd

        cfg.save()
        return Response(ConfigurationEmailSerializer(cfg).data)


class TestEmailView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request):
        destinataire = (request.data.get('destinataire') or '').strip()
        if not destinataire:
            return Response({'detail': 'Adresse destinataire requise.'},
                            status=status.HTTP_400_BAD_REQUEST)
        from .emails import envoyer_email
        try:
            envoyer_email(
                subject='Test SMTP — Restauration',
                body="Si vous lisez ceci, l'envoi d'emails fonctionne. 🎉",
                to=[destinataire],
            )
        except Exception as exc:
            return Response({'detail': f"Échec de l'envoi : {exc}"},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response({'detail': f'Email de test envoyé à {destinataire}.'})
