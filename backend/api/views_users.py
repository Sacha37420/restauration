"""Gestion des utilisateurs de l'app par les managers.

Toutes les routes sont réservées aux managers (IsManager). Le backend agit en
admin Keycloak via le service account (cf. keycloak_admin) : création d'un compte
(écrit dans le LDAP), mot de passe provisoire, gestion des rôles applicatifs
{manager, cuisinier, serveur}, et envoi d'une invitation par email.
"""
from __future__ import annotations

import re

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import keycloak_admin as kc
from .constants import ROLES_RESTAURATION
from .emails import envoyer_email
from .invitations import generer_mot_de_passe, sujet_et_corps
from .keycloak_admin import KeycloakAdminError
from .permissions import IsManager


def _valider_roles(roles) -> tuple[list[str] | None, str | None]:
    if not isinstance(roles, list) or not roles:
        return None, "Au moins un rôle est requis."
    inconnus = [r for r in roles if r not in ROLES_RESTAURATION]
    if inconnus:
        return None, f"Rôle(s) invalide(s) : {', '.join(map(str, inconnus))}."
    # Dédup en conservant l'ordre canonique.
    return [r for r in ROLES_RESTAURATION if r in roles], None


def _username_depuis_email(email: str) -> str:
    base = re.sub(r'[^a-z0-9._-]', '', email.split('@', 1)[0].lower())
    return base or 'user'


def _envoyer_invitation(email: str, prenom: str, roles: list[str]) -> tuple[bool, str | None]:
    """Régénère un mot de passe provisoire, le pose, et envoie l'invitation.

    Renvoie (succès_email, message_erreur). Le compte doit déjà exister.
    """
    user = kc.find_user(email)
    if not user:
        return False, "Utilisateur introuvable dans Keycloak."
    mot_de_passe = generer_mot_de_passe()
    kc.set_temporary_password(user['id'], mot_de_passe)
    sujet, corps = sujet_et_corps(roles, prenom, settings.FRONTEND_URL, mot_de_passe)
    try:
        envoyer_email(subject=sujet, body=corps, to=[email])
    except Exception as exc:  # SMTP indisponible / mal configuré
        return False, f"Compte prêt mais l'email n'a pas pu être envoyé : {exc}"
    return True, None


class UtilisateursView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        try:
            return Response(kc.list_app_users())
        except KeycloakAdminError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    def post(self, request):
        data = request.data
        email = (data.get('email') or '').strip().lower()
        prenom = (data.get('prenom') or '').strip()
        nom = (data.get('nom') or '').strip()
        roles, err = _valider_roles(data.get('roles'))
        if not email or '@' not in email:
            return Response({'detail': 'Email valide requis.'}, status=status.HTTP_400_BAD_REQUEST)
        if not nom:
            return Response({'detail': 'Nom requis.'}, status=status.HTTP_400_BAD_REQUEST)
        if err:
            return Response({'detail': err}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if kc.find_user(email):
                return Response({'detail': 'Un utilisateur avec cet email existe déjà.'},
                                status=status.HTTP_409_CONFLICT)
            user_id = kc.create_user(
                email=email, username=_username_depuis_email(email),
                first_name=prenom, last_name=nom,
            )
            kc.set_user_app_roles(user_id, roles)
        except KeycloakAdminError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        email_ok, msg = _envoyer_invitation(email, prenom, roles)
        corps = {
            'id': user_id, 'email': email, 'prenom': prenom, 'nom': nom,
            'roles': roles, 'enabled': True, 'invitation_envoyee': email_ok,
        }
        if not email_ok:
            corps['detail'] = msg
        return Response(corps, status=status.HTTP_201_CREATED)


class UtilisateurRolesView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def put(self, request, user_id: str):
        roles, err = _valider_roles(request.data.get('roles'))
        if err:
            return Response({'detail': err}, status=status.HTTP_400_BAD_REQUEST)
        try:
            kc.set_user_app_roles(user_id, roles)
            return Response({'id': user_id, 'roles': kc.user_app_roles(user_id)})
        except KeycloakAdminError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class UtilisateurInvitationView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request, user_id: str):
        try:
            user = kc.get_user(user_id)
            roles = kc.user_app_roles(user_id)
        except KeycloakAdminError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        email = user.get('email', '')
        if not email:
            return Response({'detail': "Cet utilisateur n'a pas d'email."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            email_ok, msg = _envoyer_invitation(email, user.get('firstName', ''), roles)
        except KeycloakAdminError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        if not email_ok:
            return Response({'detail': msg}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({'detail': f'Invitation renvoyée à {email}.'})


class UtilisateurEtatView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def post(self, request, user_id: str):
        enabled = request.data.get('enabled')
        if not isinstance(enabled, bool):
            return Response({'detail': "Champ 'enabled' (booléen) requis."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            kc.set_enabled(user_id, enabled)
            return Response({'id': user_id, 'enabled': enabled})
        except KeycloakAdminError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
