import json
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.db import connection, transaction
from django.db.utils import IntegrityError
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from .models import (
    Unite, Ingredient, MouvementStock, Plat, TableRestaurant,
    Commande, LigneCommande, Paiement, ConfigurationStripe,
    CanalCommande, StatutCommande, StatutPaiement, Facture,
    Fournisseur, ArticleFournisseur, PrixArticle, SynchroCatalogue,
    Recette, LigneRecette, StationMeteo,
)
from .authentication import KeycloakUser
from . import constants


class MouvementStockTest(APITestCase):
    """#4 — un mouvement de stock ajuste le stock de l'ingrédient."""

    def setUp(self):
        # 'kg' est déjà seedée par la migration 0003 → get_or_create pour éviter la collision.
        self.unite, _ = Unite.objects.get_or_create(nom='kg')
        self.ing = Ingredient.objects.create(nom='Farine', quantite_stock=Decimal('10'), unite=self.unite)

    def test_entree_incremente(self):
        MouvementStock.objects.create(ingredient=self.ing, type='entree', quantite=Decimal('5'))
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.quantite_stock, Decimal('15.000'))

    def test_sortie_decremente(self):
        MouvementStock.objects.create(ingredient=self.ing, type='sortie', quantite=Decimal('4'))
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.quantite_stock, Decimal('6.000'))

    def test_ajustement_fixe_la_valeur(self):
        MouvementStock.objects.create(ingredient=self.ing, type='ajustement', quantite=Decimal('99'))
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.quantite_stock, Decimal('99.000'))

    def test_modification_ne_rejoue_pas(self):
        mvt = MouvementStock.objects.create(ingredient=self.ing, type='entree', quantite=Decimal('5'))
        mvt.raison = 'correction'
        mvt.save()
        self.ing.refresh_from_db()
        self.assertEqual(self.ing.quantite_stock, Decimal('15.000'))


class StripeKeyEncryptionTest(APITestCase):
    """#6 — les clés Stripe sont chiffrées au repos."""

    def test_chiffrement_au_repos_et_dechiffrement(self):
        cfg = ConfigurationStripe.get()
        cfg.stripe_secret_key = 'sk_test_super_secret_value'
        cfg.save()

        # Valeur brute en base : ne doit pas contenir le secret en clair.
        with connection.cursor() as cursor:
            cursor.execute('SELECT stripe_secret_key FROM configuration_stripe WHERE id = 1')
            raw = cursor.fetchone()[0]
        self.assertNotIn('super_secret', raw)
        self.assertNotEqual(raw, 'sk_test_super_secret_value')

        # Relecture via l'ORM : déchiffrement transparent.
        self.assertEqual(ConfigurationStripe.get().stripe_secret_key, 'sk_test_super_secret_value')

    def test_serializer_masque_la_cle(self):
        from .serializers import ConfigurationStripeSerializer
        cfg = ConfigurationStripe.get()
        cfg.stripe_secret_key = 'sk_test_abcdef123456'
        cfg.save()
        data = ConfigurationStripeSerializer(cfg).data
        self.assertTrue(data['stripe_secret_key'].startswith('••••••••'))
        self.assertNotIn('abcdef', data['stripe_secret_key'][:8])


class CommandePubliqueSecurityTest(APITestCase):
    """#1 & #2 — endpoints publics : validation table, garde paiement, statut correct."""

    def setUp(self):
        # Le throttling stocke dans le cache (LocMemCache partagé entre tests) :
        # on repart d'un compteur propre à chaque test.
        cache.clear()
        self.table = TableRestaurant.objects.create(numero=3, token_qr='tok3', actif=True)
        self.plat = Plat.objects.create(nom='Pizza', prix_unitaire=Decimal('12.00'), actif=True)

    def _creer_commande_avec_ligne(self):
        # Création via l'API publique (chemin réel).
        r = self.client.post('/api/public/commandes/', {'numero_table': 3}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        cmd_id = r.data['id']
        self.client.post(f'/api/public/commandes/{cmd_id}/lignes/', {'plat': self.plat.id, 'quantite': 2}, format='json')
        return cmd_id

    def test_commande_sur_table_inconnue_refusee(self):
        r = self.client.post('/api/public/commandes/', {'numero_table': 999}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_commande_sur_table_inactive_refusee(self):
        self.table.actif = False
        self.table.save()
        r = self.client.post('/api/public/commandes/', {'numero_table': 3}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_commande_table_valide_ok(self):
        r = self.client.post('/api/public/commandes/', {'numero_table': 3}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_paiement_carte_refuse_hors_stripe(self):
        cmd_id = self._creer_commande_avec_ligne()
        r = self.client.post(f'/api/public/commandes/{cmd_id}/payer/', {'methode': 'carte'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Paiement.objects.filter(commande_id=cmd_id).exists())

    def test_paiement_sur_place_est_en_attente(self):
        cmd_id = self._creer_commande_avec_ligne()
        r = self.client.post(f'/api/public/commandes/{cmd_id}/payer/', {'methode': 'espèces'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        paiement = Paiement.objects.get(commande_id=cmd_id)
        # Le serveur ne confirme pas un encaissement physique : statut « en attente ».
        self.assertEqual(paiement.statut.nom, constants.STATUT_PAIEMENT_EN_ATTENTE)
        self.assertEqual(paiement.montant, Decimal('24.00'))
        Commande.objects.get(pk=cmd_id)
        self.assertEqual(Commande.objects.get(pk=cmd_id).statut.nom, constants.STATUT_CMD_EN_PREPARATION)

    def test_double_paiement_refuse(self):
        cmd_id = self._creer_commande_avec_ligne()
        self.client.post(f'/api/public/commandes/{cmd_id}/payer/', {'methode': 'espèces'}, format='json')
        r = self.client.post(f'/api/public/commandes/{cmd_id}/payer/', {'methode': 'espèces'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_modification_apres_paiement_refusee(self):
        cmd_id = self._creer_commande_avec_ligne()
        self.client.post(f'/api/public/commandes/{cmd_id}/payer/', {'methode': 'espèces'}, format='json')
        r = self.client.post(f'/api/public/commandes/{cmd_id}/lignes/', {'plat': self.plat.id, 'quantite': 1}, format='json')
        self.assertEqual(r.status_code, status.HTTP_409_CONFLICT)


class ApiProtegeeTest(APITestCase):
    """#2 — l'API métier reste protégée (401/403 sans token Keycloak)."""

    def test_acces_anonyme_refuse(self):
        r = self.client.get('/api/ingredients/')
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class ConfirmerPaiementStaffTest(APITestCase):
    """Encaissement sur place par un employé authentifié et rôlé, avec traçabilité."""

    def setUp(self):
        cache.clear()
        self.canal, _ = CanalCommande.objects.get_or_create(
            nom=constants.CANAL_SUR_PLACE, defaults={'description': 'x'})
        self.statut_cmd, _ = StatutCommande.objects.get_or_create(
            nom=constants.STATUT_CMD_EN_ATTENTE, defaults={'description': 'x'})
        self.plat = Plat.objects.create(nom='Burger', prix_unitaire=Decimal('10.00'), actif=True)
        self.commande = Commande.objects.create(
            numero_table=1, canal=self.canal, statut=self.statut_cmd)
        LigneCommande.objects.create(
            commande=self.commande, plat=self.plat, quantite=2,
            prix_unitaire_snapshot=Decimal('10.00'))

    def _staff(self, role, name='alice'):
        return KeycloakUser({'email': f'{name}@resto.fr', 'preferred_username': name, 'groups': [role]})

    def _url(self):
        return f'/api/commandes/{self.commande.id}/confirmer-paiement/'

    def test_serveur_encaisse_sans_paiement_existant(self):
        self.client.force_authenticate(user=self._staff('serveur'))
        r = self.client.post(self._url(), {'methode': 'espèces'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        p = Paiement.objects.get(commande=self.commande)
        self.assertEqual(p.statut.nom, constants.STATUT_PAIEMENT_PAYE)
        self.assertEqual(p.montant, Decimal('20.00'))
        self.assertEqual(p.confirme_par, 'alice')

    def test_manager_confirme_paiement_en_attente(self):
        statut_att, _ = StatutPaiement.objects.get_or_create(
            nom=constants.STATUT_PAIEMENT_EN_ATTENTE, defaults={'description': 'x'})
        Paiement.objects.create(
            commande=self.commande, statut=statut_att,
            montant=Decimal('20.00'), methode='espèces')
        self.client.force_authenticate(user=self._staff('manager', 'bob'))
        r = self.client.post(self._url(), {'methode': 'ticket_restaurant'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        p = Paiement.objects.get(commande=self.commande)
        self.assertEqual(p.statut.nom, constants.STATUT_PAIEMENT_PAYE)
        self.assertEqual(p.methode, 'ticket_restaurant')
        self.assertEqual(p.confirme_par, 'bob')

    def test_cuisinier_interdit(self):
        self.client.force_authenticate(user=self._staff('cuisinier'))
        r = self.client.post(self._url(), {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonyme_interdit(self):
        r = self.client.post(self._url(), {}, format='json')
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_double_confirmation_refusee(self):
        self.client.force_authenticate(user=self._staff('serveur'))
        self.client.post(self._url(), {'methode': 'espèces'}, format='json')
        r = self.client.post(self._url(), {'methode': 'espèces'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class FactureTest(APITestCase):
    """Génération locale de la facture (PDF) + envoi par email."""

    def setUp(self):
        cache.clear()
        self.canal, _ = CanalCommande.objects.get_or_create(
            nom=constants.CANAL_SUR_PLACE, defaults={'description': 'x'})
        self.statut_cmd, _ = StatutCommande.objects.get_or_create(
            nom=constants.STATUT_CMD_EN_ATTENTE, defaults={'description': 'x'})
        self.plat = Plat.objects.create(nom='Salade', prix_unitaire=Decimal('11.00'), actif=True)
        self.commande = Commande.objects.create(
            numero_table=4, canal=self.canal, statut=self.statut_cmd)
        LigneCommande.objects.create(
            commande=self.commande, plat=self.plat, quantite=3,
            prix_unitaire_snapshot=Decimal('11.00'))
        self.client.force_authenticate(
            user=KeycloakUser({'email': 'm@r.fr', 'preferred_username': 'm', 'groups': ['manager']}))

    def _url(self):
        return f'/api/commandes/{self.commande.id}/facture/'

    def test_generation_cree_facture_numerotee(self):
        r = self.client.post(self._url(), {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['numero'].startswith('FA-'))
        self.assertEqual(Decimal(r.data['montant_ttc']), Decimal('33.00'))

    def test_numerotation_sequentielle_et_idempotence(self):
        # Deux commandes → deux numéros distincts ; re-POST sur la même → même facture.
        r1 = self.client.post(self._url(), {}, format='json')
        again = self.client.post(self._url(), {}, format='json')
        self.assertEqual(r1.data['numero'], again.data['numero'])  # idempotent
        self.assertEqual(Facture.objects.filter(commande=self.commande).count(), 1)

        cmd2 = Commande.objects.create(numero_table=5, canal=self.canal, statut=self.statut_cmd)
        LigneCommande.objects.create(
            commande=cmd2, plat=self.plat, quantite=1, prix_unitaire_snapshot=Decimal('11.00'))
        r2 = self.client.post(f'/api/commandes/{cmd2.id}/facture/', {}, format='json')
        self.assertNotEqual(r1.data['numero'], r2.data['numero'])

    def test_envoi_email_avec_pdf(self):
        r = self.client.post(self._url(), {'email': 'client@email.fr'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['client@email.fr'])
        self.assertEqual(len(msg.attachments), 1)
        nom, contenu, mime = msg.attachments[0]
        self.assertTrue(nom.endswith('.pdf'))
        self.assertEqual(mime, 'application/pdf')
        self.assertTrue(contenu[:4] == b'%PDF')

    def test_telechargement_pdf(self):
        self.client.post(self._url(), {}, format='json')
        r = self.client.get(f'{self._url()}pdf/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content[:4] == b'%PDF')

    def test_facture_commande_vide_refusee(self):
        vide = Commande.objects.create(numero_table=6, canal=self.canal, statut=self.statut_cmd)
        r = self.client.post(f'/api/commandes/{vide.id}/facture/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class FactureAutoPubliqueTest(APITestCase):
    """Envoi automatique de la facture quand le client fournit un email sur /commander."""

    def setUp(self):
        cache.clear()
        self.table = TableRestaurant.objects.create(numero=7, token_qr='tok7', actif=True)
        self.plat = Plat.objects.create(nom='Tarte', prix_unitaire=Decimal('8.00'), actif=True)

    def _commande_avec_ligne(self):
        r = self.client.post('/api/public/commandes/', {'numero_table': 7}, format='json')
        cid = r.data['id']
        self.client.post(f'/api/public/commandes/{cid}/lignes/',
                         {'plat': self.plat.id, 'quantite': 2}, format='json')
        return cid

    def test_paiement_avec_email_envoie_facture(self):
        cid = self._commande_avec_ligne()
        r = self.client.post(f'/api/public/commandes/{cid}/payer/',
                             {'methode': 'espèces', 'email': 'client@x.fr'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Facture.objects.filter(commande_id=cid).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['client@x.fr'])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_paiement_sans_email_pas_de_facture(self):
        cid = self._commande_avec_ligne()
        r = self.client.post(f'/api/public/commandes/{cid}/payer/',
                             {'methode': 'espèces'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Facture.objects.filter(commande_id=cid).count(), 0)
        self.assertEqual(len(mail.outbox), 0)


class ConfigurationEmailTest(APITestCase):
    """Page Paramétrage — config SMTP en base (manager only, mot de passe masqué)."""

    def setUp(self):
        cache.clear()

    def _mgr(self):
        return KeycloakUser({'email': 'm@r.fr', 'preferred_username': 'm', 'groups': ['manager']})

    def _srv(self):
        return KeycloakUser({'email': 's@r.fr', 'preferred_username': 's', 'groups': ['serveur']})

    def test_manager_enregistre_et_masque_le_mot_de_passe(self):
        from .models import ConfigurationEmail
        self.client.force_authenticate(user=self._mgr())
        r = self.client.put('/api/email/configuration/', {
            'actif': True, 'email_host': 'smtp.gmail.com', 'email_port': 587,
            'email_use_tls': True, 'email_host_user': 'x@gmail.com',
            'email_host_password': 'secretpassword16', 'default_from_email': 'Resto <x@gmail.com>',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['email_host_password'].startswith('••••••••'))

        # Re-PUT en renvoyant la valeur masquée → le vrai mot de passe est conservé.
        masque = self.client.get('/api/email/configuration/').data
        self.client.put('/api/email/configuration/', {**masque, 'email_host': 'smtp.brevo.com'}, format='json')
        cfg = ConfigurationEmail.get()
        self.assertEqual(cfg.email_host_password, 'secretpassword16')
        self.assertEqual(cfg.email_host, 'smtp.brevo.com')

    def test_serveur_interdit(self):
        self.client.force_authenticate(user=self._srv())
        self.assertEqual(self.client.get('/api/email/configuration/').status_code,
                         status.HTTP_403_FORBIDDEN)

    def test_endpoint_test_envoie_un_email(self):
        self.client.force_authenticate(user=self._mgr())
        r = self.client.post('/api/email/test/', {'destinataire': 'dest@x.fr'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['dest@x.fr'])

    def test_endpoint_test_sans_destinataire(self):
        self.client.force_authenticate(user=self._mgr())
        self.assertEqual(self.client.post('/api/email/test/', {}, format='json').status_code,
                         status.HTTP_400_BAD_REQUEST)


class ConfigurationIntegrationsTest(APITestCase):
    """Page Paramétrage — config agent événements + Météo-France (manager only)."""

    def setUp(self):
        cache.clear()

    def _mgr(self):
        return KeycloakUser({'email': 'm@r.fr', 'preferred_username': 'm', 'groups': ['manager']})

    def _srv(self):
        return KeycloakUser({'email': 's@r.fr', 'preferred_username': 's', 'groups': ['serveur']})

    def test_mistral_enregistre_et_masque_la_cle(self):
        """La clé est désormais partagée par les trois usages de Mistral."""
        from .models import ConfigurationMistral
        self.client.force_authenticate(user=self._mgr())
        r = self.client.put('/api/mistral/configuration/', {
            'actif': True, 'api_key': 'mistral-secret123', 'modele': 'mistral-large-latest',
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['api_key'].startswith('••••••••'))

        # Renvoyer la valeur masquée ne doit pas écraser la vraie clé.
        masque = self.client.get('/api/mistral/configuration/').data
        self.client.put('/api/mistral/configuration/',
                        {**masque, 'modele': 'mistral-small-latest'}, format='json')
        cfg = ConfigurationMistral.get()
        self.assertEqual(cfg.api_key, 'mistral-secret123')
        self.assertEqual(cfg.modele, 'mistral-small-latest')

    def test_agent_evenements_ne_garde_que_ville_et_periode(self):
        from .models import ConfigurationAgentEvenements
        self.client.force_authenticate(user=self._mgr())
        r = self.client.put('/api/agent-evenements/configuration/', {
            'ville': 'Paris', 'mois': 6, 'annee': 2026,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['ville'], 'Paris')
        self.assertNotIn('mistral_api_key', r.data)     # la clé a déménagé
        self.assertEqual(ConfigurationAgentEvenements.get().mois, 6)

    def test_meteo_enregistre_et_masque_la_cle(self):
        from .models import ConfigurationMeteo
        self.client.force_authenticate(user=self._mgr())
        r = self.client.put('/api/meteo/configuration/', {
            'actif': True, 'api_key': 'meteo-token-abc', 'ville': 'Paris', 'annee': 2026,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['api_key'].startswith('••••••••'))

        masque = self.client.get('/api/meteo/configuration/').data
        self.client.put('/api/meteo/configuration/', {**masque, 'ville': 'Lyon'}, format='json')
        cfg = ConfigurationMeteo.get()
        self.assertEqual(cfg.api_key, 'meteo-token-abc')
        self.assertEqual(cfg.ville, 'Lyon')

    def test_serveur_interdit(self):
        self.client.force_authenticate(user=self._srv())
        self.assertEqual(self.client.get('/api/agent-evenements/configuration/').status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/meteo/configuration/').status_code,
                         status.HTTP_403_FORBIDDEN)


class MeteoAnalyseTest(APITestCase):
    """Indicateurs journaliers (agrégation horaire) + accès manager."""

    def setUp(self):
        from datetime import datetime, timezone as tz
        from .models import DonneeMeteoHoraire, IndicateurMeteoConfig
        cache.clear()
        self.DMH = DonneeMeteoHoraire
        self.IMC = IndicateurMeteoConfig
        # Relevés du 2026-06-01 (UTC) : 9h=100 (hors plage), 12h=10, 15h=20, 18h=30
        for h, t in [(9, 100.0), (12, 10.0), (15, 20.0), (18, 30.0)]:
            DonneeMeteoHoraire.objects.create(
                ville='Paris', horodatage=datetime(2026, 6, 1, h, tzinfo=tz.utc),
                temperature=t, nebulosite=4.0, precipitation=0.0, source='manuel')

    def _mgr(self):
        return KeycloakUser({'email': 'm@r.fr', 'preferred_username': 'm', 'groups': ['manager']})

    def test_indicateur_journalier_moyenne_sur_plage(self):
        self.IMC.objects.create(nom='Temp aprem', champ='temperature',
                                agregation='moyenne', heure_debut=12, heure_fin=18)
        self.client.force_authenticate(user=self._mgr())
        r = self.client.get('/api/analyse/meteo-horaire/indicateurs-journaliers/',
                            {'ville': 'Paris', 'annee': 2026, 'mois': 6})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        jour = r.data['jours'][0]
        self.assertEqual(jour['date'], '2026-06-01')
        # moyenne de 10,20,30 (le 100 de 9h est hors plage) = 20.0
        self.assertEqual(jour['valeurs']['Temp aprem'], 20.0)

    def test_indicateur_amplitude_journee_complete(self):
        self.IMC.objects.create(nom='Amplitude', champ='temperature',
                                agregation='amplitude', heure_debut=0, heure_fin=23)
        self.client.force_authenticate(user=self._mgr())
        r = self.client.get('/api/analyse/meteo-horaire/indicateurs-journaliers/',
                            {'ville': 'Paris', 'annee': 2026, 'mois': 6})
        self.assertEqual(r.data['jours'][0]['valeurs']['Amplitude'], 90.0)  # 100 - 10

    def test_meteo_reserve_aux_managers(self):
        self.client.force_authenticate(
            user=KeycloakUser({'email': 's@r.fr', 'preferred_username': 's', 'groups': ['serveur']}))
        self.assertEqual(self.client.get('/api/analyse/indicateurs-meteo/').status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get('/api/analyse/meteo-horaire/').status_code,
                         status.HTTP_403_FORBIDDEN)


class VentesAnalyseTest(APITestCase):
    """Agrégation des ventes depuis les commandes payées (HT/TTC, par catégorie)."""

    def setUp(self):
        from datetime import datetime, timezone as tz
        from .models import (CategoriePlat, SousCategoriePlat, Commande, LigneCommande,
                             Paiement, CanalCommande, StatutCommande, StatutPaiement, VenteAgregee)
        cache.clear()
        self.VenteAgregee = VenteAgregee
        cat = CategoriePlat.objects.create(nom='Boissons')
        sc = SousCategoriePlat.objects.create(categorie=cat, nom='Soft')
        self.cat = cat
        plat = Plat.objects.create(nom='Coca', prix_unitaire=Decimal('2.00'),
                                   taux_tva=Decimal('10'), sous_categorie=sc, actif=True)
        canal, _ = CanalCommande.objects.get_or_create(nom=constants.CANAL_SUR_PLACE, defaults={'description': 'x'})
        st_cmd, _ = StatutCommande.objects.get_or_create(nom=constants.STATUT_CMD_EN_PREPARATION, defaults={'description': 'x'})
        st_paye, _ = StatutPaiement.objects.get_or_create(nom='paye', defaults={'description': 'x'})

        quand = datetime(2026, 6, 15, 12, tzinfo=tz.utc)
        # commande PAYÉE : 10 cocas
        c1 = Commande.objects.create(numero_table=1, canal=canal, statut=st_cmd, created_at=quand)
        Paiement.objects.create(commande=c1, statut=st_paye, montant=Decimal('20.00'), methode='espèces')
        LigneCommande.objects.create(commande=c1, plat=plat, quantite=10, prix_unitaire_snapshot=Decimal('2.00'))
        # commande NON payée : ne doit pas compter
        c2 = Commande.objects.create(numero_table=2, canal=canal, statut=st_cmd, created_at=quand)
        LigneCommande.objects.create(commande=c2, plat=plat, quantite=5, prix_unitaire_snapshot=Decimal('2.00'))

    def test_recalcul_payees_uniquement_ht_ttc(self):
        from . import ventes
        n = ventes.recalculer_depuis_commandes(2026, 6)
        self.assertEqual(n, 2)  # 1 ligne catégorie + 1 ligne globale
        glob = self.VenteAgregee.objects.get(source='commandes', categorie__isnull=True)
        self.assertEqual(glob.montant_ttc, Decimal('20.00'))      # 10 × 2,00 (non payée exclue)
        self.assertEqual(glob.montant_ht, Decimal('18.18'))       # 20 / 1,10
        self.assertEqual(glob.quantite, 10)
        parcat = self.VenteAgregee.objects.get(source='commandes', categorie=self.cat)
        self.assertEqual(parcat.montant_ttc, Decimal('20.00'))

    def test_template_excel(self):
        from . import ventes
        contenu = ventes.construire_template()
        self.assertTrue(contenu[:2] == b'PK')  # xlsx = archive zip


class RegressionTest(APITestCase):
    """Régression ventes × (indicateurs météo + surplus de fréquentation)."""

    def setUp(self):
        from datetime import datetime, date, timezone as tz
        from .models import (DonneeMeteoHoraire, IndicateurMeteoConfig, Evenement, VenteAgregee)
        cache.clear()
        IndicateurMeteoConfig.objects.create(nom='Temp', champ='temperature',
                                             agregation='moyenne', heure_debut=0, heure_fin=23)
        temps = [10, 12, 14, 16, 18, 20]
        ttc = [105, 125, 146, 164, 185, 206]  # ~ 10*temp + 5 (léger bruit)
        for i, (t, v) in enumerate(zip(temps, ttc), start=1):
            jour = date(2026, 6, i)
            DonneeMeteoHoraire.objects.create(
                ville='Paris', horodatage=datetime(2026, 6, i, 12, tzinfo=tz.utc),
                temperature=float(t), source='manuel')
            VenteAgregee.objects.create(date=jour, categorie=None, montant_ht=v / 1.1,
                                        montant_ttc=v, quantite=t, source='commandes')
            if i % 2 == 0:  # surplus variable (jours pairs)
                Evenement.objects.create(ville='Paris', titre='E', date_debut=jour,
                                         date_fin=jour, surplus_frequentation=100)

    def test_regression_viable(self):
        from . import regression as reg
        r = reg.lancer('Paris', 2026, 6, 'montant_ttc', None, 'commandes')
        self.assertEqual(r['n'], 6)
        self.assertGreaterEqual(r['r2'], 0.99)
        self.assertTrue(r['viable'])
        # const + Temp + surplus_frequentation
        self.assertEqual(len(r['coefficients']), 3)

    def test_regression_donnees_insuffisantes(self):
        from . import regression as reg
        r = reg.lancer('Lyon', 2026, 6, 'montant_ttc', None, 'commandes')  # aucune donnée
        self.assertEqual(r['n'], 0)
        self.assertFalse(r['viable'])
        self.assertIn('insuffisantes', r['verdict'].lower())


# ── Gestion des utilisateurs par les managers ─────────────────────────────────
from unittest import mock  # noqa: E402
from .invitations import sujet_et_corps, generer_mot_de_passe  # noqa: E402


def _kc_user(role, name='m'):
    return KeycloakUser({'email': f'{name}@r.fr', 'preferred_username': name, 'groups': [role]})


class GestionUtilisateursPermsTest(APITestCase):
    """Seuls les managers accèdent à la gestion des utilisateurs."""

    def test_anonyme_refuse(self):
        self.assertIn(self.client.get('/api/utilisateurs/').status_code, (401, 403))

    def test_non_manager_refuse(self):
        self.client.force_authenticate(user=_kc_user('serveur', 's'))
        self.assertEqual(self.client.get('/api/utilisateurs/').status_code, 403)
        self.assertEqual(
            self.client.post('/api/utilisateurs/', {}, format='json').status_code, 403)

    def test_role_invalide_400(self):
        self.client.force_authenticate(user=_kc_user('manager'))
        r = self.client.post('/api/utilisateurs/',
                             {'email': 'a@b.fr', 'nom': 'Martin', 'roles': ['root']}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_nom_requis_400(self):
        self.client.force_authenticate(user=_kc_user('manager'))
        r = self.client.post('/api/utilisateurs/',
                             {'email': 'a@b.fr', 'roles': ['serveur']}, format='json')
        self.assertEqual(r.status_code, 400)


class CreationUtilisateurTest(APITestCase):
    """Création : crée le compte, pose un mot de passe temporaire, envoie l'invitation."""

    def setUp(self):
        self.client.force_authenticate(user=_kc_user('manager'))

    @mock.patch('api.views_users.kc.set_user_app_roles')
    @mock.patch('api.views_users.kc.set_temporary_password')
    @mock.patch('api.views_users.kc.create_user', return_value='u1')
    @mock.patch('api.views_users.kc.find_user',
                side_effect=[None, {'id': 'u1', 'email': 'a@b.fr', 'firstName': 'Alice'}])
    def test_creation_envoie_invitation(self, m_find, m_create, m_pwd, m_roles):
        r = self.client.post('/api/utilisateurs/',
                             {'email': 'A@B.fr', 'prenom': 'Alice', 'nom': 'Martin',
                              'roles': ['serveur']}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data['invitation_envoyee'])
        m_create.assert_called_once()
        m_roles.assert_called_once_with('u1', ['serveur'])
        self.assertTrue(m_pwd.called)
        # L'email contient le rôle, la consigne et le mot de passe posé.
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn('serveur', body)
        self.assertIn('première connexion', body)
        self.assertIn(m_pwd.call_args.args[1], body)
        # Le mot de passe n'est jamais renvoyé par l'API.
        self.assertNotIn('mot_de_passe', r.data)

    @mock.patch('api.views_users.kc.find_user', return_value={'id': 'x', 'email': 'a@b.fr'})
    def test_email_existant_409(self, m_find):
        r = self.client.post('/api/utilisateurs/',
                             {'email': 'a@b.fr', 'nom': 'Martin', 'roles': ['serveur']}, format='json')
        self.assertEqual(r.status_code, 409)


class InvitationContenuTest(APITestCase):
    """Le contenu de l'invitation dépend du rôle."""

    def test_manager_pitch_test_et_mdp(self):
        _, corps = sujet_et_corps(['manager'], 'Bob', 'http://app', 'PWD12345')
        self.assertIn('test', corps.lower())
        self.assertIn('manager', corps.lower())
        self.assertIn('PWD12345', corps)

    def test_cuisinier_pipeline(self):
        _, corps = sujet_et_corps(['cuisinier'], '', 'http://app', 'PWD')
        self.assertIn('recettes', corps.lower())
        self.assertIn('cuisinier', corps.lower())

    def test_serveur_pipeline(self):
        _, corps = sujet_et_corps(['serveur'], '', 'http://app', 'PWD')
        self.assertIn('tables', corps.lower())

    def test_mdp_genere_longueur(self):
        self.assertEqual(len(generer_mot_de_passe(14)), 14)


class CatalogueFournisseurTest(APITestCase):
    """Le prix dépend du fournisseur, du conditionnement et de la quantité —
    seul le prix ramené à l'unité de base est comparable."""

    def setUp(self):
        self.g, _ = Unite.objects.get_or_create(nom='g')
        self.tomate = Ingredient.objects.create(nom='Tomate', unite=self.g)
        self.metro = Fournisseur.objects.create(nom='Metro')
        self.transgourmet = Fournisseur.objects.create(nom='Transgourmet')

    def _article(self, fournisseur, contenu, **kwargs):
        return ArticleFournisseur.objects.create(
            fournisseur=fournisseur, ingredient=self.tomate, libelle='Tomate',
            unite=self.g, quantite_conditionnement=Decimal(contenu), **kwargs)

    def test_palier_degressif_selon_la_quantite(self):
        article = self._article(self.metro, '5000')
        PrixArticle.objects.create(article=article, quantite_min=1, prix_ht=Decimal('12.50'))
        PrixArticle.objects.create(article=article, quantite_min=10, prix_ht=Decimal('11.00'))

        self.assertEqual(article.prix_applicable(1).prix_ht, Decimal('12.5000'))
        self.assertEqual(article.prix_applicable(9).prix_ht, Decimal('12.5000'))
        self.assertEqual(article.prix_applicable(10).prix_ht, Decimal('11.0000'))
        self.assertEqual(article.prix_applicable(50).prix_ht, Decimal('11.0000'))

    def test_sans_tarif_le_prix_est_inconnu(self):
        article = self._article(self.metro, '5000')
        self.assertIsNone(article.prix_applicable(1))
        self.assertIsNone(article.prix_actuel)
        self.assertIsNone(article.prix_unitaire)

    def test_prix_unitaire_rend_les_conditionnements_comparables(self):
        carton = self._article(self.metro, '5000')          # 5 kg à 12,50 €
        PrixArticle.objects.create(article=carton, quantite_min=1, prix_ht=Decimal('12.50'))
        cagette = self._article(self.transgourmet, '3000')  # 3 kg à 6,90 €
        PrixArticle.objects.create(article=cagette, quantite_min=1, prix_ht=Decimal('6.90'))

        # Le carton est plus cher en valeur absolue, mais plus cher aussi au gramme.
        self.assertEqual(carton.prix_unitaire, Decimal('0.0025'))
        self.assertEqual(cagette.prix_unitaire, Decimal('0.0023'))
        self.assertEqual(self.tomate.meilleur_prix_unitaire, Decimal('0.0023'))

    def test_le_dernier_releve_gagne_sans_ecraser_l_historique(self):
        article = self._article(self.metro, '1000')
        ancien = PrixArticle.objects.create(
            article=article, quantite_min=1, prix_ht=Decimal('4.00'),
            releve_le=timezone.now() - timedelta(days=7))
        PrixArticle.objects.create(
            article=article, quantite_min=1, prix_ht=Decimal('4.60'),
            releve_le=timezone.now(), source='robot')

        article.refresh_from_db()
        self.assertEqual(article.prix_actuel, Decimal('4.6000'))
        self.assertEqual(article.prix.count(), 2)                    # historique conservé
        self.assertTrue(PrixArticle.objects.filter(pk=ancien.pk).exists())

    def test_un_seul_article_prefere_par_ingredient(self):
        premier = self._article(self.metro, '1000', prefere=True)
        second = self._article(self.transgourmet, '1000', prefere=True)

        premier.refresh_from_db()
        self.assertFalse(premier.prefere)
        self.assertTrue(second.prefere)
        self.assertEqual(self.tomate.article_prefere, second)

    def test_article_prefere_a_defaut_le_moins_cher(self):
        cher = self._article(self.metro, '1000')
        PrixArticle.objects.create(article=cher, quantite_min=1, prix_ht=Decimal('9.00'))
        pas_cher = self._article(self.transgourmet, '1000')
        PrixArticle.objects.create(article=pas_cher, quantite_min=1, prix_ht=Decimal('5.00'))

        self.assertEqual(self.tomate.article_prefere, pas_cher)

    def test_article_indisponible_exclu_des_agregats(self):
        dispo = self._article(self.metro, '1000')
        PrixArticle.objects.create(article=dispo, quantite_min=1, prix_ht=Decimal('9.00'))
        rupture = self._article(self.transgourmet, '1000', disponible=False)
        PrixArticle.objects.create(article=rupture, quantite_min=1, prix_ht=Decimal('2.00'))

        # Le moins cher est en rupture : il ne doit pas tirer le meilleur prix vers le bas.
        self.assertEqual(self.tomate.meilleur_prix_unitaire, Decimal('0.0090'))
        self.assertEqual(self.tomate.article_prefere, dispo)

    def test_reference_unique_par_fournisseur_mais_vide_autorisee(self):
        self._article(self.metro, '1000', reference='REF-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._article(self.metro, '1000', reference='REF-1')

        # Même référence chez un autre fournisseur : autorisé.
        self._article(self.transgourmet, '1000', reference='REF-1')
        # Références vides multiples (articles saisis à la main) : autorisées.
        self._article(self.metro, '1000')
        self._article(self.metro, '1000')


class RobotDomTest(APITestCase):
    """L'élagage doit réduire la page sans détruire ce qui sert à la cibler."""

    def test_supprime_le_bruit_et_garde_la_structure(self):
        from .robot_dom import elaguer
        html = '''
        <html><head><title>x</title></head><body>
          <script>var a = 1; // beaucoup de bruit</script>
          <style>.p { color: red }</style>
          <div class="produit" data-id="42">
            <h3 id="titre">Tomate grappe</h3>
            <span class="prix">12,50 €</span>
          </div>
        </body></html>
        '''
        sortie = elaguer(html)
        self.assertNotIn('<script', sortie)
        self.assertNotIn('<style', sortie)
        self.assertNotIn('var a = 1', sortie)
        # Ce qui permet de cibler l'élément doit survivre.
        self.assertIn('class="produit"', sortie)
        self.assertIn('data-id="42"', sortie)
        self.assertIn('id="titre"', sortie)
        self.assertIn('Tomate grappe', sortie)
        self.assertIn('12,50', sortie)

    def test_attribut_de_bruit_supprime(self):
        from .robot_dom import elaguer
        sortie = elaguer('<div onclick="track()" style="color:red" id="gardé">x</div>')
        self.assertNotIn('onclick', sortie)
        self.assertNotIn('style=', sortie)
        self.assertIn('id="gardé"', sortie)

    def test_page_vide_ou_invalide_ne_leve_pas(self):
        from .robot_dom import elaguer
        self.assertEqual(elaguer(''), '')
        self.assertIsInstance(elaguer('pas du html'), str)

    def test_sortie_bornee(self):
        from .robot_dom import elaguer, TAILLE_SORTIE_MAX
        enorme = '<body>' + ('<div class="x">produit</div>' * 20000) + '</body>'
        self.assertLessEqual(len(elaguer(enorme)), TAILLE_SORTIE_MAX + 20)


class RobotParsingPrixTest(APITestCase):
    """Le prix arrive comme du texte scrapé : formats français, espaces, devise."""

    def test_formats_courants(self):
        from .robot_fournisseur import _parser_prix
        self.assertEqual(_parser_prix('12,50 €'), Decimal('12.50'))
        self.assertEqual(_parser_prix('12.50'), Decimal('12.50'))
        self.assertEqual(_parser_prix('€ 8,90 HT'), Decimal('8.90'))
        self.assertEqual(_parser_prix('1 234,00 €'), Decimal('1234.00'))
        self.assertEqual(_parser_prix('7'), Decimal('7'))

    def test_texte_sans_prix(self):
        from .robot_fournisseur import _parser_prix
        self.assertIsNone(_parser_prix(''))
        self.assertIsNone(_parser_prix('Prix sur demande'))
        self.assertIsNone(_parser_prix(None))


class RobotEnregistrementTest(APITestCase):
    """Le robot alimente le catalogue sans jamais toucher au référentiel."""

    def setUp(self):
        self.fournisseur = Fournisseur.objects.create(nom='Metro', url='https://metro.example')
        self.unite, _ = Unite.objects.get_or_create(nom='pièce')
        self.synchro = SynchroCatalogue.objects.create(fournisseur=self.fournisseur)

    def _enregistrer(self, **donnees):
        from .robot_fournisseur import _enregistrer
        _enregistrer(self.fournisseur, donnees, self.unite, self.synchro)

    def test_cree_l_article_et_son_prix(self):
        self._enregistrer(libelle='Tomate grappe', prix_ht='12,50 €', reference='MET-1')

        article = ArticleFournisseur.objects.get(fournisseur=self.fournisseur, reference='MET-1')
        self.assertEqual(article.libelle, 'Tomate grappe')
        self.assertEqual(article.source, 'robot')
        self.assertIsNone(article.ingredient)          # le mapping reste humain
        self.assertEqual(article.prix_actuel, Decimal('12.5000'))
        self.assertEqual(self.synchro.articles_crees, 1)
        self.assertEqual(self.synchro.prix_releves, 1)

    def test_relance_ne_duplique_pas_et_ne_reecrit_pas_le_prix_inchange(self):
        self._enregistrer(libelle='Tomate', prix_ht='12,50', reference='MET-1')
        self._enregistrer(libelle='Tomate', prix_ht='12,50', reference='MET-1')

        self.assertEqual(ArticleFournisseur.objects.filter(fournisseur=self.fournisseur).count(), 1)
        article = ArticleFournisseur.objects.get(reference='MET-1')
        self.assertEqual(article.prix.count(), 1)      # prix inchangé → pas de relevé inutile
        self.assertEqual(self.synchro.articles_maj, 1)

    def test_prix_qui_bouge_ajoute_un_releve(self):
        self._enregistrer(libelle='Tomate', prix_ht='12,50', reference='MET-1')
        self._enregistrer(libelle='Tomate', prix_ht='13,90', reference='MET-1')

        article = ArticleFournisseur.objects.get(reference='MET-1')
        self.assertEqual(article.prix.count(), 2)      # historique conservé
        self.assertEqual(article.prix_actuel, Decimal('13.9000'))

    def test_ne_casse_pas_le_mapping_existant(self):
        """Le point le plus important : une resynchro ne doit jamais détacher un
        article déjà rattaché par un humain à un ingrédient."""
        self._enregistrer(libelle='Tomate', prix_ht='12,50', reference='MET-1')
        article = ArticleFournisseur.objects.get(reference='MET-1')

        ingredient = Ingredient.objects.create(nom='Tomate', unite=self.unite)
        article.ingredient = ingredient
        article.prefere = True
        article.save()

        self._enregistrer(libelle='Tomate grappe cat.1', prix_ht='13,00', reference='MET-1')

        article.refresh_from_db()
        self.assertEqual(article.ingredient, ingredient)   # mapping préservé
        self.assertTrue(article.prefere)
        self.assertEqual(article.libelle, 'Tomate grappe cat.1')   # libellé rafraîchi

    def test_produit_sans_libelle_ignore(self):
        self._enregistrer(libelle='', prix_ht='12,50')
        self.assertEqual(ArticleFournisseur.objects.count(), 0)

    def test_sans_reference_l_identite_repose_sur_libelle_marque_conditionnement(self):
        self._enregistrer(libelle='Tomate', marque='Bio', conditionnement='5 kg', prix_ht='9')
        self._enregistrer(libelle='Tomate', marque='Bio', conditionnement='5 kg', prix_ht='9')
        self._enregistrer(libelle='Tomate', marque='Bio', conditionnement='3 kg', prix_ht='6')

        self.assertEqual(ArticleFournisseur.objects.count(), 2)   # 5 kg et 3 kg = 2 articles


class RobotNormalisationXpathTest(APITestCase):
    """Mistral propose volontiers `.../@href` pour un lien : ce nœud attribut n'est ni
    cliquable ni lisible par Playwright. On le ramène sur l'élément porteur."""

    def test_attribut_final_retire(self):
        from .robot_fournisseur import _normaliser_xpath
        self.assertEqual(
            _normaliser_xpath("//a[contains(@class, 'suivant')]/@href"),
            "//a[contains(@class, 'suivant')]")
        self.assertEqual(_normaliser_xpath('.//img/@src'), './/img')
        self.assertEqual(_normaliser_xpath('.//input/@value'), './/input')

    def test_xpath_sur_element_inchange(self):
        from .robot_fournisseur import _normaliser_xpath
        for xpath in ("//article[contains(@class, 'produit')]",
                      ".//span[@class='prix']",
                      "//a[contains(text(), 'Page suivante')]"):
            self.assertEqual(_normaliser_xpath(xpath), xpath)

    def test_predicat_sur_attribut_preserve(self):
        """Ne pas confondre un prédicat @href=… avec une sélection d'attribut finale."""
        from .robot_fournisseur import _normaliser_xpath
        self.assertEqual(_normaliser_xpath("//a[@href='/page2']"), "//a[@href='/page2']")

    def test_analyse_complete_normalisee(self):
        from .robot_fournisseur import _normaliser_analyse
        analyse = _normaliser_analyse({
            'xpath_page_suivante': "//a[@class='suivant']/@href",
            'champs': {'libelle': './/h3', 'url': './/a/@href', 'vide': ''},
            'raison': 'inchangée',
        })
        self.assertEqual(analyse['xpath_page_suivante'], "//a[@class='suivant']")
        self.assertEqual(analyse['champs']['url'], './/a')
        self.assertEqual(analyse['champs']['libelle'], './/h3')
        self.assertNotIn('vide', analyse['champs'])     # champ sans XPath = écarté
        self.assertEqual(analyse['raison'], 'inchangée')


class RobotRattachementTest(APITestCase):
    """Mistral rapproche les produits scrapés des ingrédients. Le risque à contenir :
    polluer le référentiel de cuisine avec des non-aliments ou des doublons."""

    def setUp(self):
        self.fournisseur = Fournisseur.objects.create(nom='Metro', url='https://metro.example')
        self.g, _ = Unite.objects.get_or_create(nom='g')
        self.piece, _ = Unite.objects.get_or_create(nom='pièce')
        self.tomate = Ingredient.objects.create(nom='Tomate', unite=self.g)
        self.synchro = SynchroCatalogue.objects.create(fournisseur=self.fournisseur)

    def _article(self, libelle, **kwargs):
        return ArticleFournisseur.objects.create(
            fournisseur=self.fournisseur, libelle=libelle, unite=self.piece,
            quantite_conditionnement=1, source='robot', **kwargs)

    def _appliquer(self, articles, rattachements):
        from .robot_fournisseur import _appliquer_rattachements
        _appliquer_rattachements(articles, {'rattachements': rattachements}, self.synchro)

    def test_rattache_a_un_ingredient_existant_sans_le_dupliquer(self):
        a = self._article('Tomate grappe cat.1', conditionnement='Carton 5 kg')
        self._appliquer([a], [{'id': a.id, 'ingredient': 'Tomate', 'quantite': 5000}])

        a.refresh_from_db()
        self.assertEqual(a.ingredient, self.tomate)
        self.assertEqual(Ingredient.objects.filter(nom='Tomate').count(), 1)
        self.assertEqual(self.synchro.ingredients_crees, 0)
        self.assertEqual(self.synchro.articles_rattaches, 1)

    def test_conversion_dans_l_unite_de_l_ingredient(self):
        """Sans ça, comparer 12,50 €/carton et 6,90 €/cagette n'a aucun sens."""
        a = self._article('Tomate grappe', conditionnement='Carton 5 kg')
        self._appliquer([a], [{'id': a.id, 'ingredient': 'Tomate',
                               'quantite': 5000, 'preuve': 'Carton 5 kg'}])

        a.refresh_from_db()
        self.assertEqual(a.unite, self.g)                             # unité de l'ingrédient
        self.assertEqual(a.quantite_conditionnement, Decimal('5000.000'))

    def test_cree_l_ingredient_absent(self):
        a = self._article('Beurre doux Elle & Vire colis de 10')
        self._appliquer([a], [{'id': a.id, 'nouvel_ingredient': 'Beurre',
                               'unite': 'g', 'quantite': 2500}])

        a.refresh_from_db()
        self.assertEqual(a.ingredient.nom, 'Beurre')
        self.assertEqual(a.ingredient.unite, self.g)
        self.assertEqual(self.synchro.ingredients_crees, 1)

    def test_non_alimentaire_ignore(self):
        """Le garde-fou : un scan qui tombe sur des fleurs ne doit pas créer
        d'ingrédient « Rose »."""
        a = self._article('FLEURS Bouquet de 10 roses rouges')
        self._appliquer([a], [{'id': a.id, 'ignorer': True}])

        a.refresh_from_db()
        self.assertIsNone(a.ingredient)
        self.assertFalse(Ingredient.objects.filter(nom__icontains='rose').exists())
        self.assertEqual(self.synchro.articles_ignores, 1)
        self.assertEqual(self.synchro.ingredients_crees, 0)

    def test_ne_recree_pas_un_ingredient_a_la_casse_pres(self):
        a1 = self._article('tomate ronde')
        a2 = self._article('Tomate cerise')
        self._appliquer([a1, a2], [
            {'id': a1.id, 'nouvel_ingredient': 'tomate'},     # casse différente
            {'id': a2.id, 'nouvel_ingredient': 'TOMATE'},
        ])

        self.assertEqual(Ingredient.objects.filter(nom__iexact='tomate').count(), 1)
        self.assertEqual(self.synchro.ingredients_crees, 0)   # « Tomate » existait déjà

    def test_nom_avec_unite_entre_parentheses_nettoye(self):
        """La nomenclature envoyée à Mistral est « Tomate (g) » : il la recopie parfois telle quelle."""
        a = self._article('Courgette verte')
        self._appliquer([a], [{'id': a.id, 'nouvel_ingredient': 'Courgette (g)', 'unite': 'g'}])

        a.refresh_from_db()
        self.assertEqual(a.ingredient.nom, 'Courgette')

    def test_ne_detache_jamais_un_mapping_humain(self):
        a = self._article('Tomate grappe', ingredient=self.tomate)
        autre = Ingredient.objects.create(nom='Courgette', unite=self.g)
        self._appliquer([a], [{'id': a.id, 'ingredient': 'Courgette'}])

        a.refresh_from_db()
        self.assertEqual(a.ingredient, self.tomate)          # décision humaine préservée
        self.assertEqual(self.synchro.articles_rattaches, 0)

    def test_quantite_absente_laisse_le_conditionnement_intact(self):
        a = self._article('Tomate en vrac')
        self._appliquer([a], [{'id': a.id, 'ingredient': 'Tomate'}])   # pas de 'quantite'

        a.refresh_from_db()
        self.assertEqual(a.ingredient, self.tomate)
        self.assertEqual(a.quantite_conditionnement, Decimal('1.000'))  # inchangé, pas inventé
        self.assertEqual(a.unite, self.piece)

    def test_seuls_les_orphelins_sont_candidats(self):
        from .robot_fournisseur import _orphelins
        libre = self._article('Poireau')
        self._article('Tomate grappe', ingredient=self.tomate)

        self.assertEqual([a.id for a in _orphelins(self.fournisseur)], [libre.id])


class RobotRetryMistralTest(APITestCase):
    """Un scan enchaîne les appels : le 429 est une certitude, pas un aléa."""

    def test_erreur_transitoire_reconnue(self):
        from .robot_mistral import _est_transitoire
        self.assertTrue(_est_transitoire(Exception('Status 429. Rate limit exceeded')))
        self.assertTrue(_est_transitoire(Exception('Status 503')))
        self.assertTrue(_est_transitoire(Exception('Read timeout')))

    def test_erreur_definitive_non_reessayee(self):
        """Une clé invalide ne se répare pas en attendant : inutile de réessayer 4 fois."""
        from .robot_mistral import _est_transitoire
        self.assertFalse(_est_transitoire(Exception('Status 401. Unauthorized')))
        self.assertFalse(_est_transitoire(Exception('Invalid model')))


class RobotQuantiteProuveeTest(APITestCase):
    """Une quantité fausse est pire qu'une quantité absente : elle rend tous les prix
    au kilo aberrants. On n'accepte que ce que Mistral peut citer dans le texte."""

    def setUp(self):
        self.fournisseur = Fournisseur.objects.create(nom='Metro')
        self.g, _ = Unite.objects.get_or_create(nom='g')
        self.beurre = Ingredient.objects.create(nom='Beurre', unite=self.g)
        self.synchro = SynchroCatalogue.objects.create(fournisseur=self.fournisseur)

    def _article(self, libelle, conditionnement=''):
        return ArticleFournisseur.objects.create(
            fournisseur=self.fournisseur, libelle=libelle, conditionnement=conditionnement,
            unite=self.g, quantite_conditionnement=1, source='robot')

    def _appliquer(self, article, ligne):
        from .robot_fournisseur import _appliquer_rattachements
        _appliquer_rattachements([article], {'rattachements': [{**ligne, 'id': article.id}]},
                                 self.synchro)
        article.refresh_from_db()
        return article

    def test_quantite_citee_dans_le_texte_acceptee(self):
        a = self._article('Tomate grappe', 'Carton 5 kg')
        a = self._appliquer(a, {'nouvel_ingredient': 'Tomate', 'unite': 'g',
                                'quantite': 5000, 'preuve': 'Carton 5 kg'})
        self.assertEqual(a.quantite_conditionnement, Decimal('5000.000'))

    def test_quantite_inventee_rejetee(self):
        """« Colis de 10 » ne dit pas 10 de quoi : 250 g est une invention."""
        a = self._article('Beurre doux', 'Colis de 10')
        a = self._appliquer(a, {'ingredient': 'Beurre', 'quantite': 250,
                                'preuve': '10 plaquettes de 250 g'})   # absent du texte
        self.assertEqual(a.ingredient, self.beurre)                    # rattaché quand même
        self.assertEqual(a.quantite_conditionnement, Decimal('1.000'))  # mais quantité refusée

    def test_quantite_sans_preuve_rejetee(self):
        a = self._article('Beurre doux', 'Colis de 10')
        a = self._appliquer(a, {'ingredient': 'Beurre', 'quantite': 250})
        self.assertEqual(a.quantite_conditionnement, Decimal('1.000'))

    def test_quantite_negative_ou_nulle_rejetee(self):
        a = self._article('Beurre', 'Sac 2 kg')
        a = self._appliquer(a, {'ingredient': 'Beurre', 'quantite': 0, 'preuve': 'Sac 2 kg'})
        self.assertEqual(a.quantite_conditionnement, Decimal('1.000'))


class RecetteGenereeTest(APITestCase):
    """Enregistrement d'une recette générée : le LLM produit du texte libre, la base
    a des contraintes (unicité, FK, prix obligatoire). C'est là que ça casse."""

    def setUp(self):
        self.g, _ = Unite.objects.get_or_create(nom='g')
        self.piece, _ = Unite.objects.get_or_create(nom='pièce')
        self.tomate = Ingredient.objects.create(nom='Tomate', unite=self.g)
        self.client.force_authenticate(user=KeycloakUser(
            {'sub': 'u1', 'preferred_username': 'chef', 'groups': ['manager']}))

    def _enregistrer(self, payload):
        return self.client.post('/api/recettes/enregistrer-generee/', payload, format='json')

    def _base(self, **extra):
        return {'nom': 'Tarte', 'instructions_html': '<ol><li>Cuire</li></ol>',
                'temps_preparation': 30, 'nb_portions': 4,
                'ingredients': [{'nom': 'Tomate', 'quantite': 500, 'unite': 'g'}], **extra}

    def test_cree_recette_lignes_et_plat(self):
        r = self._enregistrer(self._base(plat={'creer': True, 'nom': 'Tarte tomate',
                                               'prix_unitaire': 12.5}))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

        recette = Recette.objects.get(nom='Tarte')
        self.assertEqual(recette.lignes_recette.count(), 1)
        self.assertEqual(recette.lignes_recette.first().ingredient, self.tomate)

        plat = Plat.objects.get(nom='Tarte tomate')
        self.assertEqual(plat.recette, recette)
        self.assertEqual(plat.prix_unitaire, Decimal('12.50'))
        self.assertTrue(plat.actif)

    def test_plat_sans_prix_reste_hors_carte(self):
        """Un plat à 0 € ne doit jamais atterrir sur la carte publique."""
        r = self._enregistrer(self._base(plat={'creer': True, 'prix_unitaire': 0}))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Plat.objects.get(nom='Tarte').actif)

    def test_ingredient_absent_est_cree(self):
        r = self._enregistrer(self._base(ingredients=[
            {'nom': 'Tomate', 'quantite': 500, 'unite': 'g'},
            {'nom': 'Basilic', 'quantite': 20, 'unite': 'g'},
        ]))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Ingredient.objects.get(nom='Basilic').unite, self.g)

    def test_doublon_dans_la_reponse_du_llm_est_fusionne(self):
        """unique_together(recette, ingredient) : deux lignes du même ingrédient
        feraient planter la création. On additionne au lieu de tomber en 500."""
        r = self._enregistrer(self._base(ingredients=[
            {'nom': 'Tomate', 'quantite': 500, 'unite': 'g'},
            {'nom': 'Tomate', 'quantite': 300, 'unite': 'g'},
        ]))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        lignes = Recette.objects.get(nom='Tarte').lignes_recette.all()
        self.assertEqual(lignes.count(), 1)
        self.assertEqual(lignes.first().quantite, Decimal('800.000'))

    def test_unite_hors_nomenclature_retombe_sur_le_defaut(self):
        """Mistral sort parfois de la liste (« pincée ») : on ne doit pas planter."""
        r = self._enregistrer(self._base(ingredients=[
            {'nom': 'Muscade', 'quantite': 1, 'unite': 'pincée'}]))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Ingredient.objects.get(nom='Muscade').unite, self.piece)

    def test_quantite_nulle_ignoree(self):
        r = self._enregistrer(self._base(ingredients=[
            {'nom': 'Tomate', 'quantite': 500, 'unite': 'g'},
            {'nom': 'Sel', 'quantite': 0, 'unite': 'g'},
        ]))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Recette.objects.get(nom='Tarte').lignes_recette.count(), 1)

    def test_sans_plat_seule_la_recette_est_creee(self):
        r = self._enregistrer(self._base(plat={'creer': False}))
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Plat.objects.count(), 0)

    def test_nom_vide_refuse(self):
        r = self._enregistrer(self._base(nom=''))
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class RecetteCoutMatiereTest(APITestCase):
    """Le coût matière sert à fixer un prix de vente : un coût partiel serait pire
    que pas de coût du tout."""

    def setUp(self):
        self.g, _ = Unite.objects.get_or_create(nom='g')
        self.fournisseur = Fournisseur.objects.create(nom='Metro')
        self.recette = Recette.objects.create(
            nom='Sauce', instructions_html='<p>x</p>', temps_preparation=10, nb_portions=4)

    def _ingredient_avec_prix(self, nom, prix_par_gramme):
        ingredient = Ingredient.objects.create(nom=nom, unite=self.g)
        article = ArticleFournisseur.objects.create(
            fournisseur=self.fournisseur, ingredient=ingredient, libelle=nom,
            unite=self.g, quantite_conditionnement=Decimal('1000'))
        PrixArticle.objects.create(
            article=article, quantite_min=1, prix_ht=Decimal(prix_par_gramme) * 1000)
        return ingredient

    def test_cout_calcule_au_meilleur_prix_fournisseur(self):
        tomate = self._ingredient_avec_prix('Tomate', '0.002')      # 2 €/kg
        LigneRecette.objects.create(recette=self.recette, ingredient=tomate,
                                    quantite=Decimal('500'))         # 500 g → 1 €
        self.assertEqual(self.recette.cout_matiere, Decimal('1.000'))
        self.assertEqual(self.recette.cout_par_portion, Decimal('0.250'))

    def test_ingredient_sans_prix_rend_le_cout_indisponible(self):
        tomate = self._ingredient_avec_prix('Tomate', '0.002')
        sans_prix = Ingredient.objects.create(nom='Basilic', unite=self.g)
        LigneRecette.objects.create(recette=self.recette, ingredient=tomate, quantite=Decimal('500'))
        LigneRecette.objects.create(recette=self.recette, ingredient=sans_prix, quantite=Decimal('10'))

        # Surtout pas 1 € : ce serait un coût faux sur lequel un prix de vente serait bâti.
        self.assertIsNone(self.recette.cout_matiere)
        self.assertIsNone(self.recette.cout_par_portion)

    def test_recette_vide_sans_cout(self):
        self.assertIsNone(self.recette.cout_matiere)


class NomenclatureRapprochementTest(APITestCase):
    """Le LLM ne recopie pas les noms au caractère près. Un rapprochement strictement
    textuel créerait « Crème fraîche » à côté de « Crème Fraiche » : deux ingrédients
    pour la même chose, donc deux stocks et deux prix qui divergent."""

    def setUp(self):
        self.g, _ = Unite.objects.get_or_create(nom='g')
        self.creme = Ingredient.objects.create(nom='Crème Fraiche', unite=self.g)
        self.oeuf = Ingredient.objects.create(nom='Oeuf', unite=self.g)

    def test_accents_ignores(self):
        from .nomenclature import trouver
        self.assertEqual(trouver('Crème fraîche'), self.creme)
        self.assertEqual(trouver('creme fraiche'), self.creme)
        self.assertEqual(trouver('CRÈME FRAÎCHE'), self.creme)

    def test_ligature_oe(self):
        from .nomenclature import trouver
        self.assertEqual(trouver('Œuf'), self.oeuf)
        self.assertEqual(trouver('œuf'), self.oeuf)

    def test_suffixe_unite_ignore(self):
        from .nomenclature import trouver
        self.assertEqual(trouver('Crème fraîche (mL)'), self.creme)

    def test_ingredient_reellement_absent(self):
        from .nomenclature import trouver
        self.assertIsNone(trouver('Chorizo'))
        self.assertIsNone(trouver(''))

    def test_resoudre_ou_creer_ne_duplique_pas_sur_un_accent(self):
        from .nomenclature import resoudre_ou_creer
        ingredient, cree = resoudre_ou_creer('Crème fraîche', 'g')
        self.assertFalse(cree)
        self.assertEqual(ingredient, self.creme)
        self.assertEqual(Ingredient.objects.filter(nom__icontains='fra').count(), 1)


class PromptsMistralTest(APITestCase):
    """Les 6 prompts des 3 usages : surchargeables, réinitialisables, et le défaut
    reprend la main dès que la surcharge disparaît."""

    def setUp(self):
        self.client.force_authenticate(user=KeycloakUser(
            {'sub': 'u', 'preferred_username': 'm', 'groups': ['manager']}))

    def test_les_six_usages_sont_exposes(self):
        from . import prompts
        r = self.client.get('/api/mistral/prompts/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        usages = [p['usage'] for p in r.data]
        self.assertEqual(sorted(usages), sorted(prompts.DEFAUTS.keys()))
        # Chacun expose son défaut, pour que l'UI puisse proposer d'y revenir.
        for p in r.data:
            self.assertTrue(p['par_defaut'])
            self.assertFalse(p['personnalise'])
            self.assertEqual(p['contenu'], p['par_defaut'])

    def test_surcharge_puis_prise_en_compte_immediate(self):
        from . import prompts
        from .models import PromptMistral
        r = self.client.put('/api/mistral/prompts/', {
            'usage': prompts.RECETTE, 'contenu': 'Tu es un chef végane.'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['personnalise'])
        # Le prompt est relu à chaque appel : pas de redémarrage nécessaire.
        self.assertEqual(PromptMistral.texte(prompts.RECETTE), 'Tu es un chef végane.')

    def test_reinitialisation_rend_la_main_au_defaut(self):
        from . import prompts
        from .models import PromptMistral
        self.client.put('/api/mistral/prompts/', {
            'usage': prompts.ROBOT_EXTRACTION, 'contenu': 'bidon'}, format='json')
        r = self.client.delete(f'/api/mistral/prompts/?usage={prompts.ROBOT_EXTRACTION}')

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertFalse(r.data['personnalise'])
        self.assertEqual(PromptMistral.texte(prompts.ROBOT_EXTRACTION),
                         prompts.DEFAUT_ROBOT_EXTRACTION)
        self.assertFalse(PromptMistral.objects.filter(usage=prompts.ROBOT_EXTRACTION).exists())

    def test_contenu_identique_au_defaut_nest_pas_stocke(self):
        """Sinon le prompt se figerait et ne bénéficierait plus des améliorations
        livrées avec les mises à jour de l'application."""
        from . import prompts
        from .models import PromptMistral
        self.client.put('/api/mistral/prompts/', {
            'usage': prompts.EVENEMENTS, 'contenu': prompts.DEFAUT_EVENEMENTS}, format='json')
        self.assertFalse(PromptMistral.objects.filter(usage=prompts.EVENEMENTS).exists())

    def test_contenu_vide_revient_au_defaut(self):
        from . import prompts
        from .models import PromptMistral
        self.client.put('/api/mistral/prompts/', {
            'usage': prompts.EVENEMENTS, 'contenu': 'perso'}, format='json')
        self.client.put('/api/mistral/prompts/', {
            'usage': prompts.EVENEMENTS, 'contenu': '   '}, format='json')
        self.assertEqual(PromptMistral.texte(prompts.EVENEMENTS), prompts.DEFAUT_EVENEMENTS)

    def test_usage_inconnu_refuse(self):
        r = self.client.put('/api/mistral/prompts/', {
            'usage': 'nimporte_quoi', 'contenu': 'x'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reserve_au_manager(self):
        self.client.force_authenticate(user=KeycloakUser(
            {'sub': 'c', 'preferred_username': 'c', 'groups': ['cuisinier']}))
        self.assertEqual(self.client.get('/api/mistral/prompts/').status_code,
                         status.HTTP_403_FORBIDDEN)


class SessionFournisseurTest(APITestCase):
    """L'état du navigateur (cookies + localStorage) porte le magasin choisi : c'est lui
    qui débloque les prix sur les sites qui les masquent. Il vaut un mot de passe."""

    def setUp(self):
        self.client.force_authenticate(user=KeycloakUser(
            {'sub': 'u', 'preferred_username': 'm', 'groups': ['manager']}))
        self.fournisseur = Fournisseur.objects.create(
            nom='Auchan', url='https://auchan.example')

    def _put(self, **champs):
        return self.client.put(f'/api/fournisseurs/{self.fournisseur.id}/',
                               {'nom': 'Auchan', 'url': 'https://auchan.example', **champs},
                               format='json')

    def test_session_enregistree_et_jamais_renvoyee(self):
        etat = json.dumps({'cookies': [{'name': 'store', 'value': 'sorigny'}], 'origins': []})
        r = self._put(session_state=etat)

        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertNotIn('session_state', r.data)        # jamais relu : usurpation possible
        self.assertTrue(r.data['session_memorisee'])
        self.fournisseur.refresh_from_db()
        self.assertEqual(self.fournisseur.session_state, etat)

    def test_chiffree_au_repos(self):
        etat = json.dumps({'cookies': [{'name': 'auth', 'value': 'jeton-tres-secret'}]})
        self._put(session_state=etat)
        with connection.cursor() as cursor:
            cursor.execute('SELECT session_state FROM fournisseur WHERE id = %s',
                           [self.fournisseur.id])
            brut = cursor.fetchone()[0]
        self.assertNotIn('jeton-tres-secret', brut)

    def test_session_vide_ne_l_efface_pas(self):
        """Le formulaire renvoie toujours un champ vide, puisque le serveur ne la
        réaffiche jamais : sans cette garde, chaque enregistrement l'effacerait."""
        etat = json.dumps({'cookies': [{'name': 'store', 'value': 'x'}]})
        self._put(session_state=etat)
        self._put(session_state='', code_postal='37500')

        self.fournisseur.refresh_from_db()
        self.assertEqual(self.fournisseur.session_state, etat)
        self.assertEqual(self.fournisseur.code_postal, '37500')

    def test_json_invalide_refuse_a_la_saisie(self):
        """Sinon chaque synchro échouerait plus tard, sur une erreur obscure."""
        r = self._put(session_state='{pas du json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_json_valide_mais_pas_un_etat_de_navigateur_refuse(self):
        r = self._put(session_state='{"foo": "bar"}')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oublier_session(self):
        self._put(session_state=json.dumps({'cookies': []}))
        r = self.client.post(f'/api/fournisseurs/{self.fournisseur.id}/oublier-session/')

        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.fournisseur.refresh_from_db()
        self.assertEqual(self.fournisseur.session_state, '')


class StationMeteoTest(APITestCase):
    """Le classement des stations ne doit plus être borné au département de la ville :
    la météo se moque des frontières administratives."""

    def setUp(self):
        # Chinon (37) ~ 47.174 / 0.250
        self.chinon = (47.174, 0.250)
        StationMeteo.objects.create(id_station='37242002', nom='SAVIGNY-VERON',
                                    departement='37', lat=47.183, lon=0.133, poste_ouvert=True)
        StationMeteo.objects.create(id_station='86137001', nom='LOUDUN',
                                    departement='86', lat=47.013, lon=0.083, poste_ouvert=True)
        StationMeteo.objects.create(id_station='37000999', nom='SAINT EPAIN',
                                    departement='37', lat=47.135, lon=0.585, poste_ouvert=True)
        StationMeteo.objects.create(id_station='37000111', nom='STATION FERMEE',
                                    departement='37', lat=47.174, lon=0.250, poste_ouvert=False)

    def test_tri_par_distance_toutes_stations_confondues(self):
        from .meteofrance import stations_par_distance
        classees = stations_par_distance(*self.chinon)
        noms = [s.nom for _, s in classees]

        # LOUDUN est dans le 86 : l'ancien code, borné au département 37, ne la voyait pas.
        self.assertIn('LOUDUN', noms)
        self.assertEqual(noms[0], 'SAVIGNY-VERON')          # la plus proche
        self.assertLess(noms.index('LOUDUN'), noms.index('SAINT EPAIN'))

    def test_stations_fermees_exclues(self):
        from .meteofrance import stations_par_distance
        noms = [s.nom for _, s in stations_par_distance(*self.chinon)]
        self.assertNotIn('STATION FERMEE', noms)            # pourtant à 0 km

    def test_distances_croissantes(self):
        from .meteofrance import stations_par_distance
        distances = [d for d, _ in stations_par_distance(*self.chinon)]
        self.assertEqual(distances, sorted(distances))

    def test_haversine_connu(self):
        """Paris ↔ Marseille ≈ 660 km à vol d'oiseau."""
        from .meteofrance import _haversine
        d = _haversine(48.8566, 2.3522, 43.2965, 5.3698)
        self.assertAlmostEqual(d, 660, delta=15)

    def test_fichier_sans_aucune_mesure_est_un_echec(self):
        """Une station peut renvoyer un fichier bien formé mais entièrement vide : sans
        cette garde, on enregistrerait des centaines de lignes toutes nulles."""
        from .meteofrance import _a_des_mesures
        vides = [{'temperature': None, 'nebulosite': None, 'precipitation': None}] * 24
        self.assertFalse(_a_des_mesures(vides))

        partiel = vides + [{'temperature': 16.7, 'nebulosite': None, 'precipitation': None}]
        self.assertTrue(_a_des_mesures(partiel))

    def test_periode_mois_et_annee(self):
        from .meteofrance import _periode
        import datetime as dt
        self.assertEqual(_periode(2, 2024), (dt.date(2024, 2, 1), dt.date(2024, 2, 29)))  # bissextile
        self.assertEqual(_periode(None, 2026), (dt.date(2026, 1, 1), dt.date(2026, 12, 31)))

    def test_catalogue_vide_refuse_la_recuperation(self):
        """Message actionnable, plutôt qu'un échec obscur au premier appel API."""
        from .meteofrance import recuperer, MeteoErreur
        from .models import ConfigurationMeteo
        StationMeteo.objects.all().delete()
        cfg = ConfigurationMeteo.get()
        cfg.actif, cfg.api_key = True, 'fausse-cle'
        cfg.save()

        with self.assertRaises(MeteoErreur) as ctx:
            recuperer('Chinon', 6, 2026)
        self.assertIn('catalogue', str(ctx.exception).lower())

    def test_corse_utilise_le_code_20(self):
        """2A/2B sont refusés par l'API DPClim (HTTP 400) : c'est « 20 » qu'il faut."""
        from .meteofrance import DEPARTEMENTS
        self.assertIn('20', DEPARTEMENTS)
        self.assertNotIn('2A', DEPARTEMENTS)
        self.assertNotIn('2B', DEPARTEMENTS)
