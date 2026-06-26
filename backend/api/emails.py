"""Envoi d'emails en s'appuyant sur la configuration SMTP stockée en base
(ConfigurationEmail), avec repli sur les réglages Django (.env) si inactive.
"""
from django.conf import settings
from django.core.mail import EmailMessage, get_connection


def _connexion_et_expediteur():
    """Retourne (connection, from_email).

    Si la config base est active et renseignée → connexion SMTP explicite.
    Sinon connection=None → backend par défaut défini dans settings/.env
    (et locmem pendant les tests).
    """
    from .models import ConfigurationEmail
    cfg = ConfigurationEmail.get()
    if cfg.actif and cfg.email_host:
        conn = get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=cfg.email_host,
            port=cfg.email_port,
            username=cfg.email_host_user,
            password=cfg.email_host_password,
            use_tls=cfg.email_use_tls,
            fail_silently=False,
        )
        return conn, (cfg.default_from_email or settings.DEFAULT_FROM_EMAIL)
    return None, settings.DEFAULT_FROM_EMAIL


def envoyer_email(subject, body, to, attachments=None):
    """Envoie un email (avec PJ optionnelles : liste de (nom, contenu, mimetype))."""
    connection, from_email = _connexion_et_expediteur()
    message = EmailMessage(
        subject=subject, body=body, from_email=from_email,
        to=to, connection=connection,
    )
    for nom, contenu, mimetype in (attachments or []):
        message.attach(nom, contenu, mimetype)
    return message.send()
