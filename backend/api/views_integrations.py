from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import ConfigurationAgentEvenements, ConfigurationMeteo
from .serializers import (
    ConfigurationAgentEvenementsSerializer, ConfigurationMeteoSerializer,
)
from .permissions import IsManager

_MASKED_PREFIX = '••••••••'


def _int_or_none(value, current):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return current


class ConfigurationAgentEvenementsView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        return Response(ConfigurationAgentEvenementsSerializer(
            ConfigurationAgentEvenements.get()).data)

    def put(self, request):
        cfg = ConfigurationAgentEvenements.get()
        data = request.data

        cfg.actif = bool(data.get('actif', cfg.actif))
        cfg.modele = data.get('modele', cfg.modele) or 'mistral-large-latest'
        if 'system_prompt' in data:
            cfg.system_prompt = data.get('system_prompt') or cfg.system_prompt
        cfg.ville = data.get('ville', cfg.ville)
        if 'mois' in data:
            cfg.mois = _int_or_none(data.get('mois'), cfg.mois)
        if 'annee' in data:
            cfg.annee = _int_or_none(data.get('annee'), cfg.annee)

        key = data.get('mistral_api_key', '')
        if key and not key.startswith(_MASKED_PREFIX):
            cfg.mistral_api_key = key

        cfg.save()
        return Response(ConfigurationAgentEvenementsSerializer(cfg).data)


class ConfigurationMeteoView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        return Response(ConfigurationMeteoSerializer(ConfigurationMeteo.get()).data)

    def put(self, request):
        cfg = ConfigurationMeteo.get()
        data = request.data

        cfg.actif = bool(data.get('actif', cfg.actif))
        cfg.ville = data.get('ville', cfg.ville)
        if 'mois' in data:
            cfg.mois = _int_or_none(data.get('mois'), cfg.mois)
        if 'annee' in data:
            cfg.annee = _int_or_none(data.get('annee'), cfg.annee)

        key = data.get('api_key', '')
        if key and not key.startswith(_MASKED_PREFIX):
            cfg.api_key = key

        cfg.save()
        return Response(ConfigurationMeteoSerializer(cfg).data)
