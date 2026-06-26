import sys

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'Restauration API'

    def ready(self):
        # En base de test, le schéma applicatif (créé en prod par l'infra,
        # infra/init/00_schemas.sql) n'existe pas : on le crée à la volée
        # pour que les migrations s'appliquent. Aucun effet hors `manage.py test`.
        if 'test' in sys.argv:
            from django.conf import settings
            from django.db.backends.signals import connection_created

            def _ensure_schema(sender, connection, **kwargs):
                schema = getattr(settings, 'DB_SCHEMA', None)
                if schema and connection.vendor == 'postgresql':
                    with connection.cursor() as cursor:
                        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

            connection_created.connect(_ensure_schema, weak=False)
