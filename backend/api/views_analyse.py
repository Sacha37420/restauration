import calendar
from datetime import date

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Evenement
from .serializers import EvenementSerializer
from .permissions import IsManager


class EvenementViewSet(viewsets.ModelViewSet):
    queryset = Evenement.objects.all()
    serializer_class = EvenementSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        ville = self.request.query_params.get('ville')
        annee = self.request.query_params.get('annee')
        mois = self.request.query_params.get('mois')
        if ville:
            qs = qs.filter(ville__iexact=ville)
        if annee:
            try:
                annee = int(annee)
                if mois:
                    mois = int(mois)
                    debut = date(annee, mois, 1)
                    fin = date(annee, mois, calendar.monthrange(annee, mois)[1])
                else:
                    debut = date(annee, 1, 1)
                    fin = date(annee, 12, 31)
                # événements qui chevauchent la période
                qs = qs.filter(date_debut__lte=fin, date_fin__gte=debut)
            except (ValueError, TypeError):
                pass
        return qs

    @action(detail=False, methods=['post'], url_path='proposer-mistral')
    def proposer_mistral(self, request):
        """Propose des événements via Mistral SANS les enregistrer (aperçu à valider)."""
        from .mistral_agent import proposer_evenements, AgentNonConfigure
        ville = (request.data.get('ville') or '').strip()
        annee = request.data.get('annee')
        mois = request.data.get('mois') or None
        if not ville or not annee:
            return Response({'detail': 'ville et annee sont requis.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            propositions = proposer_evenements(ville, mois, int(annee))
        except AgentNonConfigure as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({'detail': f'Échec de l\'appel Mistral : {exc}'},
                            status=status.HTTP_502_BAD_GATEWAY)
        return Response({'evenements': propositions})

    @action(detail=False, methods=['post'], url_path='enregistrer-lot')
    def enregistrer_lot(self, request):
        """Enregistre la liste d'événements validée/éditée par l'utilisateur."""
        items = request.data.get('evenements', [])
        serializer = EvenementSerializer(data=items, many=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
