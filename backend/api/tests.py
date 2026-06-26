from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from rest_framework.test import APITestCase
from rest_framework import status

from .models import (
    Unite, Ingredient, MouvementStock, Plat, TableRestaurant,
    Commande, Paiement, ConfigurationStripe,
)
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
