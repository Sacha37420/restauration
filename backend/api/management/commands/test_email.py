"""Vérifie la configuration SMTP en envoyant un email de test.

Usage : python manage.py test_email destinataire@exemple.fr
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un email de test pour vérifier la configuration SMTP."

    def add_arguments(self, parser):
        parser.add_argument('destinataire', help="Adresse email de destination")

    def handle(self, *args, **options):
        dest = options['destinataire']

        self.stdout.write('Configuration email active :')
        self.stdout.write(f'  Backend : {settings.EMAIL_BACKEND}')
        self.stdout.write(f'  Hôte    : {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (TLS={settings.EMAIL_USE_TLS})')
        self.stdout.write(f'  Compte  : {settings.EMAIL_HOST_USER}')
        self.stdout.write(f'  From    : {settings.DEFAULT_FROM_EMAIL}')

        if 'console' in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING(
                "\n⚠️  Backend 'console' : l'email s'affichera ci-dessous mais ne sera PAS "
                "réellement envoyé. Mettez EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend "
                "pour un envoi réel.\n"
            ))

        try:
            envoyes = send_mail(
                subject='Test SMTP — Restauration',
                message="Si vous lisez ceci, l'envoi d'emails fonctionne. 🎉",
                from_email=None,  # utilise DEFAULT_FROM_EMAIL
                recipient_list=[dest],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(
                f'Échec de l\'envoi : {exc}\n'
                "Vérifiez EMAIL_HOST_PASSWORD (mot de passe d'application Google, sans espaces) "
                'et que la validation en 2 étapes est activée.'
            )

        if envoyes:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Email envoyé à {dest}.'))
        else:
            self.stdout.write(self.style.WARNING('\nAucun email envoyé (0 message accepté).'))
