from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import (
    ConfigurationAgentEvenements, ConfigurationMeteo, ConfigurationMistral, PromptMistral,
)
from .serializers import (
    ConfigurationAgentEvenementsSerializer, ConfigurationMeteoSerializer,
    ConfigurationMistralSerializer,
)
from .permissions import IsManager
from . import prompts

_MASKED_PREFIX = '••••••••'


def _int_or_none(value, current):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return current


class ConfigurationMistralView(APIView):
    """Clé, modèle et activation — partagés par les trois usages de Mistral."""
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        return Response(ConfigurationMistralSerializer(ConfigurationMistral.get()).data)

    def put(self, request):
        cfg = ConfigurationMistral.get()
        data = request.data

        cfg.actif = bool(data.get('actif', cfg.actif))
        cfg.modele = data.get('modele', cfg.modele) or 'mistral-large-latest'

        key = data.get('api_key', '')
        if key and not key.startswith(_MASKED_PREFIX):
            cfg.api_key = key

        cfg.save()
        return Response(ConfigurationMistralSerializer(cfg).data)


def _prompt_expose(usage, libelle):
    """Renvoie l'état d'un prompt : sa surcharge éventuelle, et toujours son défaut —
    pour que l'interface puisse afficher l'un et proposer de revenir à l'autre."""
    surcharge = PromptMistral.objects.filter(usage=usage).first()
    return {
        'usage': usage,
        'libelle': libelle,
        'contenu': PromptMistral.texte(usage),
        'par_defaut': prompts.DEFAUTS.get(usage, ''),
        'personnalise': bool(surcharge and surcharge.contenu.strip()),
        'updated_at': surcharge.updated_at if surcharge else None,
    }


class PromptsMistralView(APIView):
    """Les prompts des trois usages : liste, modification, réinitialisation."""
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        return Response([_prompt_expose(usage, libelle)
                         for usage, libelle in prompts.USAGES])

    def put(self, request):
        usage = request.data.get('usage')
        if usage not in prompts.DEFAUTS:
            return Response({'detail': f'Usage inconnu : {usage!r}.'},
                            status=status.HTTP_400_BAD_REQUEST)

        contenu = (request.data.get('contenu') or '').strip()
        if not contenu or contenu == prompts.DEFAUTS[usage].strip():
            # Identique au défaut : on ne stocke pas de surcharge. Le prompt suivra
            # ainsi les améliorations livrées avec les mises à jour de l'application.
            PromptMistral.objects.filter(usage=usage).delete()
        else:
            PromptMistral.objects.update_or_create(
                usage=usage, defaults={'contenu': contenu})

        libelle = dict(prompts.USAGES)[usage]
        return Response(_prompt_expose(usage, libelle))

    def delete(self, request):
        """Réinitialise un prompt : on supprime la surcharge, le défaut reprend la main."""
        usage = request.query_params.get('usage')
        if usage not in prompts.DEFAUTS:
            return Response({'detail': f'Usage inconnu : {usage!r}.'},
                            status=status.HTTP_400_BAD_REQUEST)
        PromptMistral.objects.filter(usage=usage).delete()
        return Response(_prompt_expose(usage, dict(prompts.USAGES)[usage]))


class ConfigurationAgentEvenementsView(APIView):
    """Paramètres propres à l'agent calendrier : ville et période ciblées."""
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        return Response(ConfigurationAgentEvenementsSerializer(
            ConfigurationAgentEvenements.get()).data)

    def put(self, request):
        cfg = ConfigurationAgentEvenements.get()
        data = request.data

        cfg.ville = data.get('ville', cfg.ville)
        if 'mois' in data:
            cfg.mois = _int_or_none(data.get('mois'), cfg.mois)
        if 'annee' in data:
            cfg.annee = _int_or_none(data.get('annee'), cfg.annee)

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
