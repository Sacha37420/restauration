"""Vérifie la configuration SMTP en envoyant un email de test.

Usage : python manage.py test_email destinataire@exemple.fr
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un email de test pour vérifier la configuration SMTP (page Paramétrage)."

    def add_arguments(self, parser):
        parser.add_argument('destinataire', help="Adresse email de destination")

    def handle(self, *args, **options):
        from api.models import ConfigurationEmail
        from api.emails import envoyer_email

        dest = options['destinataire']
        cfg = ConfigurationEmail.get()

        self.stdout.write('Configuration email (base de données) :')
        self.stdout.write(f'  Active  : {cfg.actif}')
        self.stdout.write(f'  Hôte    : {cfg.email_host}:{cfg.email_port} (TLS={cfg.email_use_tls})')
        self.stdout.write(f'  Compte  : {cfg.email_host_user}')
        self.stdout.write(f'  From    : {cfg.default_from_email}')
        if not (cfg.actif and cfg.email_host):
            self.stdout.write(self.style.WARNING(
                "\n⚠️  Config base inactive : repli sur les réglages .env/settings.\n"
            ))

        try:
            envoyes = envoyer_email(
                subject='Test SMTP — Restauration',
                body="Si vous lisez ceci, l'envoi d'emails fonctionne. 🎉",
                to=[dest],
            )
        except Exception as exc:
            raise CommandError(
                f"Échec de l'envoi : {exc}\n"
                "Vérifiez le mot de passe d'application Google (sans espaces) "
                'et que la validation en 2 étapes est activée.'
            )

        if envoyes:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Email envoyé à {dest}.'))
        else:
            self.stdout.write(self.style.WARNING('\nAucun email envoyé (0 message accepté).'))
