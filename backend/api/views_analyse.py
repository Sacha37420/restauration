import calendar
from collections import defaultdict
from datetime import date

from django.db import transaction
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Evenement, DonneeMeteoHoraire, IndicateurMeteoConfig, VenteAgregee
from .serializers import (
    EvenementSerializer, DonneeMeteoHoraireSerializer, IndicateurMeteoConfigSerializer,
    VenteAgregeeSerializer,
)
from .permissions import IsManager


def _periode(annee, mois):
    annee = int(annee)
    if mois:
        mois = int(mois)
        return date(annee, mois, 1), date(annee, mois, calendar.monthrange(annee, mois)[1])
    return date(annee, 1, 1), date(annee, 12, 31)


def _agreger(agregation, valeurs):
    valeurs = [v for v in valeurs if v is not None]
    if not valeurs:
        return None
    if agregation == 'moyenne':
        r = sum(valeurs) / len(valeurs)
    elif agregation == 'min':
        r = min(valeurs)
    elif agregation == 'max':
        r = max(valeurs)
    elif agregation == 'somme':
        r = sum(valeurs)
    elif agregation == 'amplitude':
        r = max(valeurs) - min(valeurs)
    else:
        return None
    return round(r, 2)


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


class IndicateurMeteoConfigViewSet(viewsets.ModelViewSet):
    queryset = IndicateurMeteoConfig.objects.all()
    serializer_class = IndicateurMeteoConfigSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]


class DonneeMeteoHoraireViewSet(viewsets.ModelViewSet):
    queryset = DonneeMeteoHoraire.objects.all()
    serializer_class = DonneeMeteoHoraireSerializer

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        ville = p.get('ville')
        if ville:
            qs = qs.filter(ville__iexact=ville)
        jour = p.get('date')
        if jour:
            qs = qs.filter(horodatage__date=jour)
        elif p.get('annee'):
            try:
                debut, fin = _periode(p.get('annee'), p.get('mois'))
                qs = qs.filter(horodatage__date__gte=debut, horodatage__date__lte=fin)
            except (ValueError, TypeError):
                pass
        return qs

    @action(detail=False, methods=['post'], url_path='recuperer')
    def recuperer(self, request):
        """Récupère les relevés horaires via Météo-France et les enregistre
        (remplace la période pour la ville)."""
        from . import meteofrance
        ville = (request.data.get('ville') or '').strip()
        annee = request.data.get('annee')
        mois = request.data.get('mois') or None
        if not ville or not annee:
            return Response({'detail': 'ville et annee sont requis.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rows, debut, fin = meteofrance.recuperer(ville, mois, int(annee))
        except meteofrance.MeteoNonConfigure as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({'detail': f'Échec Météo-France : {exc}'}, status=status.HTTP_502_BAD_GATEWAY)

        with transaction.atomic():
            DonneeMeteoHoraire.objects.filter(
                ville__iexact=ville, horodatage__date__gte=debut, horodatage__date__lte=fin,
            ).delete()
            DonneeMeteoHoraire.objects.bulk_create(
                [DonneeMeteoHoraire(**r) for r in rows], ignore_conflicts=True,
            )
        return Response({'detail': f'{len(rows)} relevés enregistrés.', 'count': len(rows)})

    @action(detail=False, methods=['get'], url_path='indicateurs-journaliers')
    def indicateurs_journaliers(self, request):
        """Calcule les indicateurs configurés pour chaque jour de la période."""
        p = self.request.query_params
        ville = p.get('ville')
        if not ville or not p.get('annee'):
            return Response({'detail': 'ville et annee sont requis.'}, status=status.HTTP_400_BAD_REQUEST)
        debut, fin = _periode(p.get('annee'), p.get('mois'))
        qs = DonneeMeteoHoraire.objects.filter(
            ville__iexact=ville, horodatage__date__gte=debut, horodatage__date__lte=fin,
        )
        configs = list(IndicateurMeteoConfig.objects.filter(actif=True))

        par_jour = defaultdict(list)
        for d in qs:
            par_jour[d.horodatage.date().isoformat()].append(d)

        jours = []
        for jour in sorted(par_jour):
            releves = par_jour[jour]
            valeurs = {}
            for c in configs:
                vals = [
                    getattr(r, c.champ) for r in releves
                    if c.heure_debut <= r.horodatage.hour <= c.heure_fin
                ]
                valeurs[c.nom] = _agreger(c.agregation, vals)
            jours.append({'date': jour, 'valeurs': valeurs})

        return Response({
            'indicateurs': [
                {'nom': c.nom, 'champ': c.champ, 'agregation': c.agregation,
                 'heure_debut': c.heure_debut, 'heure_fin': c.heure_fin}
                for c in configs
            ],
            'jours': jours,
        })


class VenteAgregeeViewSet(viewsets.ModelViewSet):
    queryset = VenteAgregee.objects.select_related('categorie').all()
    serializer_class = VenteAgregeeSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        return [IsAuthenticated(), IsManager()]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get('annee'):
            try:
                debut, fin = _periode(p.get('annee'), p.get('mois'))
                qs = qs.filter(date__gte=debut, date__lte=fin)
            except (ValueError, TypeError):
                pass
        if p.get('source'):
            qs = qs.filter(source=p.get('source'))
        return qs

    @action(detail=False, methods=['post'], url_path='recalculer-commandes')
    def recalculer_commandes(self, request):
        from . import ventes
        annee = request.data.get('annee')
        mois = request.data.get('mois') or None
        if not annee:
            return Response({'detail': 'annee requise.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            n = ventes.recalculer_depuis_commandes(int(annee), mois)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': f'{n} lignes recalculées depuis les commandes payées.', 'count': n})

    @action(detail=False, methods=['post'], url_path='importer-excel')
    def importer_excel(self, request):
        from . import ventes
        fichier = request.FILES.get('fichier')
        if not fichier:
            return Response({'detail': 'Fichier « fichier » requis.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            n = ventes.importer_excel(fichier)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({'detail': f'Import impossible : {exc}'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': f'{n} lignes importées.', 'count': n})

    @action(detail=False, methods=['get'], url_path='template-excel')
    def template_excel(self, request):
        from . import ventes
        contenu = ventes.construire_template()
        resp = HttpResponse(
            contenu,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        resp['Content-Disposition'] = 'attachment; filename="modele_ventes.xlsx"'
        return resp
