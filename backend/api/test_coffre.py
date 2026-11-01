"""Coffre des secrets (chantier « failles », I3) — `api/fields.py` et migration 0025.

Couvre : chiffrement sous VAULT_ENCRYPTION_KEY (et non sous SECRET_KEY),
lecture de l'ancien chiffrement, valeur historique en clair, valeur corrompue
traitée comme absente (journalisée sans sa valeur), rechiffrement par la
migration (rejouable, sans toucher l'indéchiffrable), indépendance vis-à-vis
d'une rotation de SECRET_KEY, et absence de la clé dans les réponses.
"""
from django.apps import apps as global_apps
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from . import fields
from .authentication import KeycloakUser
from .models import ConfigurationMistral, ConfigurationStripe, Fournisseur

MIGRATION_CHAMPS = __import__(
    'api.migrations.0025_rechiffrer_coffre', fromlist=['CHAMPS']).CHAMPS


def _raw(model, field, pk):
    table = connection.ops.quote_name(model._meta.db_table)
    col = connection.ops.quote_name(model._meta.get_field(field).column)
    with connection.cursor() as cur:
        cur.execute(f'SELECT {col} FROM {table} WHERE id = %s', [pk])
        return cur.fetchone()[0]


def _set_raw(model, field, pk, value):
    table = connection.ops.quote_name(model._meta.db_table)
    col = connection.ops.quote_name(model._meta.get_field(field).column)
    with connection.cursor() as cur:
        cur.execute(f'UPDATE {table} SET {col} = %s WHERE id = %s', [value, pk])


def _legacy(plaintext):
    return fields._legacy_fernet().encrypt(plaintext.encode()).decode()


class _SchemaEditor:
    """Ce que `rewrite_encrypted_columns` lit d'un schema_editor : sa connexion."""
    connection = connection


class ChampChiffreTest(TestCase):

    def setUp(self):
        self.cfg = ConfigurationMistral.get()

    def test_chiffre_sous_la_cle_du_coffre_et_pas_sous_secret_key(self):
        self.cfg.api_key = 'sk-mistral-0123456789'
        self.cfg.save()
        raw = _raw(ConfigurationMistral, 'api_key', self.cfg.pk)
        self.assertTrue(raw.startswith('gAAAAA'))
        self.assertNotIn('sk-mistral', raw)
        self.assertEqual(fields.vault_fernet().decrypt(raw.encode()).decode(), 'sk-mistral-0123456789')
        with self.assertRaises(Exception):
            fields._legacy_fernet().decrypt(raw.encode())

    def test_lit_l_ancien_chiffrement(self):
        _set_raw(ConfigurationMistral, 'api_key', self.cfg.pk, _legacy('ancienne-cle'))
        self.assertEqual(ConfigurationMistral.objects.get(pk=self.cfg.pk).api_key, 'ancienne-cle')

    def test_valeur_historique_en_clair_rendue_telle_quelle(self):
        _set_raw(ConfigurationMistral, 'api_key', self.cfg.pk, 'cle-en-clair')
        self.assertEqual(ConfigurationMistral.objects.get(pk=self.cfg.pk).api_key, 'cle-en-clair')

    def test_valeur_corrompue_absente_et_journalisee_sans_sa_valeur(self):
        corrompu = 'gAAAAABcorrompu-' + 'x' * 60
        _set_raw(ConfigurationMistral, 'api_key', self.cfg.pk, corrompu)
        with self.assertLogs('api.fields', level='WARNING') as logs:
            valeur = ConfigurationMistral.objects.get(pk=self.cfg.pk).api_key
        self.assertEqual(valeur, '')
        journal = '\n'.join(logs.output)
        self.assertIn('ConfigurationMistral.api_key', journal)
        self.assertNotIn(corrompu, journal)
        self.assertNotIn('corrompu', journal)

    def test_jeton_d_une_autre_cle_absent(self):
        from cryptography.fernet import Fernet
        etranger = Fernet(Fernet.generate_key()).encrypt(b'secret-d-ailleurs').decode()
        _set_raw(ConfigurationMistral, 'api_key', self.cfg.pk, etranger)
        with self.assertLogs('api.fields', level='WARNING'):
            self.assertEqual(ConfigurationMistral.objects.get(pk=self.cfg.pk).api_key, '')

    def test_rotation_de_secret_key_ne_detruit_plus_rien(self):
        self.cfg.api_key = 'survit-a-la-rotation'
        self.cfg.save()
        with override_settings(SECRET_KEY='une-toute-autre-secret-key'):
            self.assertEqual(ConfigurationMistral.objects.get(pk=self.cfg.pk).api_key, 'survit-a-la-rotation')

    def test_sans_cle_du_coffre_refus_explicite(self):
        with override_settings(VAULT_ENCRYPTION_KEY=''):
            self.cfg.api_key = 'x'
            with self.assertRaises(RuntimeError):
                self.cfg.save()


class MigrationRechiffrementTest(TestCase):

    def _run(self, transform=fields.reencrypt_raw):
        return fields.rewrite_encrypted_columns(global_apps, _SchemaEditor(), MIGRATION_CHAMPS, transform)

    def test_rechiffre_l_ancien_et_le_clair_laisse_l_indechiffrable(self):
        cfg = ConfigurationMistral.get()
        stripe = ConfigurationStripe.get()
        f1 = Fournisseur.objects.create(nom='F1')
        f2 = Fournisseur.objects.create(nom='F2')
        corrompu = 'gAAAAABcorrompu-' + 'y' * 60
        _set_raw(ConfigurationMistral, 'api_key', cfg.pk, _legacy('mistral-ancien'))
        _set_raw(ConfigurationStripe, 'stripe_secret_key', stripe.pk, 'sk_live_en_clair')
        _set_raw(Fournisseur, 'mot_de_passe', f1.pk, _legacy('mdp-f1'))
        _set_raw(Fournisseur, 'mot_de_passe', f2.pk, corrompu)

        self.assertEqual(self._run()['rewritten'], 3)

        for model, champ, pk, attendu in [
            (ConfigurationMistral, 'api_key', cfg.pk, 'mistral-ancien'),
            (ConfigurationStripe, 'stripe_secret_key', stripe.pk, 'sk_live_en_clair'),
            (Fournisseur, 'mot_de_passe', f1.pk, 'mdp-f1'),
        ]:
            raw = _raw(model, champ, pk)
            self.assertEqual(fields.vault_fernet().decrypt(raw.encode()).decode(), attendu)
            self.assertEqual(getattr(model.objects.get(pk=pk), champ), attendu)
        # L'indéchiffrable n'est pas effacé en base, et se lit comme absent.
        self.assertEqual(_raw(Fournisseur, 'mot_de_passe', f2.pk), corrompu)
        with self.assertLogs('api.fields', level='WARNING'):
            self.assertEqual(Fournisseur.objects.get(pk=f2.pk).mot_de_passe, '')

        # Rejouable : plus rien à réécrire.
        self.assertEqual(self._run()['rewritten'], 0)

    def test_retour_arriere_remet_sous_l_ancienne_cle(self):
        cfg = ConfigurationMistral.get()
        cfg.api_key = 'aller-retour'
        cfg.save()
        self.assertEqual(self._run(fields.legacy_encrypt_raw)['rewritten'], 1)
        raw = _raw(ConfigurationMistral, 'api_key', cfg.pk)
        self.assertEqual(fields._legacy_fernet().decrypt(raw.encode()).decode(), 'aller-retour')


class CleAbsenteDesReponsesTest(APITestCase):

    def test_la_cle_mistral_n_est_jamais_rendue_en_entier(self):
        self.client.force_authenticate(
            user=KeycloakUser({'email': 'm@r.fr', 'preferred_username': 'm', 'groups': ['manager']}))
        r = self.client.put('/api/mistral/configuration/',
                            {'actif': True, 'api_key': 'sk-tres-secret-ABCD'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('sk-tres-secret', r.content.decode())
        r = self.client.get('/api/mistral/configuration/')
        self.assertNotIn('sk-tres-secret', r.content.decode())

    def test_valeur_corrompue_ne_fuit_pas_par_le_masque(self):
        """Avant : le texte chiffré était rendu comme une clé, et son suffixe affiché."""
        cfg = ConfigurationMistral.get()
        corrompu = 'gAAAAABcorrompu-' + 'z' * 56 + 'QUEUE'
        _set_raw(ConfigurationMistral, 'api_key', cfg.pk, corrompu)
        self.client.force_authenticate(
            user=KeycloakUser({'email': 'm@r.fr', 'preferred_username': 'm', 'groups': ['manager']}))
        with self.assertLogs('api.fields', level='WARNING'):
            r = self.client.get('/api/mistral/configuration/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['api_key'], '')
        self.assertNotIn('QUEUE', r.content.decode())
