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
