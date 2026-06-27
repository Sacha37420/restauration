from decimal import Decimal

from django.core import mail
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APITestCase
from rest_framework import status

from .models import (
    Unite, Ingredient, MouvementStock, Plat, TableRestaurant,
    Commande, LigneCommande, Paiement, ConfigurationStripe,
    CanalCommande, StatutCommande, StatutPaiement, Facture,
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

    def test_agent_enregistre_et_masque_la_cle(self):
        from .models import ConfigurationAgentEvenements
        self.client.force_authenticate(user=self._mgr())
        r = self.client.put('/api/agent-evenements/configuration/', {
            'actif': True, 'mistral_api_key': 'mistral-secret123', 'modele': 'mistral-large-latest',
            'ville': 'Paris', 'mois': 6, 'annee': 2026,
        }, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertTrue(r.data['mistral_api_key'].startswith('••••••••'))
        self.assertEqual(r.data['ville'], 'Paris')

        masque = self.client.get('/api/agent-evenements/configuration/').data
        self.client.put('/api/agent-evenements/configuration/', {**masque, 'ville': 'Lyon'}, format='json')
        cfg = ConfigurationAgentEvenements.get()
        self.assertEqual(cfg.mistral_api_key, 'mistral-secret123')
        self.assertEqual(cfg.ville, 'Lyon')

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
