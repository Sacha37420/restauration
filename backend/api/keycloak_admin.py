"""Client minimal de l'API Admin Keycloak.

Le backend agit en administrateur Keycloak via le **service account** d'un client
confidentiel compagnon (``restauration-admin``, flux client_credentials). Il sert
à créer des utilisateurs (écrits dans le LDAP car la fédération est en
``editMode=WRITABLE``), poser un mot de passe temporaire et gérer l'appartenance
aux groupes applicatifs (écrite dans le LDAP via le group mapper ``WRITABLE``).

La portée fonctionnelle (rôles autorisés, qui peut appeler) est bornée **côté vues**
— ce module reste un simple transport.
"""
from __future__ import annotations

import time

import requests
from django.conf import settings

from .constants import ROLES_RESTAURATION

_TIMEOUT = 10


class KeycloakAdminError(RuntimeError):
    """Erreur de communication ou de configuration avec l'API Admin Keycloak."""


def _split_issuer() -> tuple[str, str]:
    """(base, realm) à partir de KEYCLOAK_ISSUER_URI (…/realms/<realm>)."""
    issuer = (settings.KEYCLOAK_ISSUER_URI or '').rstrip('/')
    if '/realms/' not in issuer:
        raise KeycloakAdminError(
            f"KEYCLOAK_ISSUER_URI invalide : {issuer!r} (attendu …/realms/<realm>)."
        )
    base, realm = issuer.split('/realms/', 1)
    return base, realm.split('/', 1)[0]


def _base_realm() -> tuple[str, str]:
    base, realm = _split_issuer()
    # Permet de router les appels admin vers une URL interne (ex. http://keycloak:8080)
    # si KEYCLOAK_ADMIN_BASE_URL est défini, sinon on réutilise l'URL publique de l'issuer.
    admin_base = (getattr(settings, 'KEYCLOAK_ADMIN_BASE_URL', '') or base).rstrip('/')
    return admin_base, realm


# Cache de token au niveau process (chaque worker gunicorn a le sien).
_token_cache: dict[str, float | str] = {'value': '', 'exp': 0.0}


def _token() -> str:
    now = time.time()
    if _token_cache['value'] and float(_token_cache['exp']) > now + 5:
        return str(_token_cache['value'])

    client_id = getattr(settings, 'KEYCLOAK_ADMIN_CLIENT_ID', '') or ''
    secret = getattr(settings, 'KEYCLOAK_ADMIN_CLIENT_SECRET', '') or ''
    if not client_id or not secret:
        raise KeycloakAdminError(
            "KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET manquants. "
            "Lancez setup2.sh restauration (provisionne le client restauration-admin)."
        )

    base, realm = _base_realm()
    try:
        resp = requests.post(
            f'{base}/realms/{realm}/protocol/openid-connect/token',
            data={
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': secret,
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise KeycloakAdminError(f"Keycloak injoignable : {exc}") from exc
    if resp.status_code != 200:
        raise KeycloakAdminError(
            f"Auth service account échouée (HTTP {resp.status_code}) : {resp.text[:200]}"
        )
    data = resp.json()
    _token_cache['value'] = data['access_token']
    _token_cache['exp'] = now + int(data.get('expires_in', 60))
    return str(_token_cache['value'])


def _req(method: str, path: str, **kwargs) -> requests.Response:
    base, realm = _base_realm()
    url = f'{base}/admin/realms/{realm}{path}'
    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f'Bearer {_token()}'
    try:
        resp = requests.request(method, url, headers=headers, timeout=_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise KeycloakAdminError(f"Appel Keycloak échoué ({method} {path}) : {exc}") from exc
    if resp.status_code >= 400:
        raise KeycloakAdminError(
            f"Keycloak {method} {path} → HTTP {resp.status_code} : {resp.text[:300]}"
        )
    return resp


# ── Groupes applicatifs ───────────────────────────────────────────────────────

def app_groups() -> dict[str, str]:
    """Mappe {nom_de_groupe: id} restreint aux rôles applicatifs."""
    groups = _req('GET', '/groups?briefRepresentation=true&max=200').json()
    return {g['name']: g['id'] for g in groups if g['name'] in ROLES_RESTAURATION}


# ── Utilisateurs ──────────────────────────────────────────────────────────────

def find_user(email: str) -> dict | None:
    users = _req('GET', '/users', params={'email': email, 'exact': 'true'}).json()
    return users[0] if users else None


def get_user(user_id: str) -> dict:
    return _req('GET', f'/users/{user_id}').json()


def create_user(*, email: str, username: str, first_name: str, last_name: str) -> str:
    """Crée l'utilisateur (atterrit dans le LDAP) et renvoie son id Keycloak.

    emailVerified=True pour permettre la connexion sans vérification d'email
    (pas de SMTP realm requis) ; le mot de passe est posé ensuite, temporaire.
    """
    payload = {
        'username': username,
        'email': email,
        'firstName': first_name,
        'lastName': last_name,
        'enabled': True,
        'emailVerified': True,
    }
    resp = _req('POST', '/users', json=payload)
    location = resp.headers.get('Location', '')
    if location:
        return location.rstrip('/').rsplit('/', 1)[-1]
    found = find_user(email)
    if not found:
        raise KeycloakAdminError("Utilisateur créé mais introuvable au relookup.")
    return found['id']


def set_temporary_password(user_id: str, password: str) -> None:
    """Pose un mot de passe temporaire → Keycloak impose le changement au 1er login."""
    _req(
        'PUT', f'/users/{user_id}/reset-password',
        json={'type': 'password', 'value': password, 'temporary': True},
    )


def set_enabled(user_id: str, enabled: bool) -> None:
    _req('PUT', f'/users/{user_id}', json={'enabled': enabled})


def add_user_to_group(user_id: str, group_id: str) -> None:
    _req('PUT', f'/users/{user_id}/groups/{group_id}')


def remove_user_from_group(user_id: str, group_id: str) -> None:
    _req('DELETE', f'/users/{user_id}/groups/{group_id}')


def user_app_roles(user_id: str) -> list[str]:
    """Rôles applicatifs (groupes) de l'utilisateur, dans l'ordre canonique."""
    groups = _req('GET', f'/users/{user_id}/groups').json()
    names = {g['name'] for g in groups}
    return [r for r in ROLES_RESTAURATION if r in names]


def list_app_users() -> list[dict]:
    """Liste dédupliquée des utilisateurs ayant au moins un rôle applicatif."""
    gmap = app_groups()
    by_id: dict[str, dict] = {}
    for role, gid in gmap.items():
        members = _req('GET', f'/groups/{gid}/members', params={'max': 500}).json()
        for m in members:
            entry = by_id.setdefault(m['id'], {
                'id': m['id'],
                'username': m.get('username', ''),
                'email': m.get('email', ''),
                'prenom': m.get('firstName', ''),
                'nom': m.get('lastName', ''),
                'enabled': m.get('enabled', True),
                'roles': [],
            })
            entry['roles'].append(role)
    # Réordonne les rôles dans l'ordre canonique.
    for entry in by_id.values():
        entry['roles'] = [r for r in ROLES_RESTAURATION if r in entry['roles']]
    return sorted(by_id.values(), key=lambda e: (e['nom'].lower(), e['prenom'].lower()))


def set_user_app_roles(user_id: str, roles: list[str]) -> None:
    """Aligne l'appartenance aux groupes applicatifs sur ``roles``.

    Note : retirer un utilisateur du dernier membre d'un groupe LDAP (groupOfNames)
    est rejeté par le LDAP → l'erreur remonte en KeycloakAdminError.
    """
    gmap = app_groups()
    current = set(user_app_roles(user_id))
    wanted = set(roles)
    for role in wanted - current:
        add_user_to_group(user_id, gmap[role])
    for role in current - wanted:
        remove_user_from_group(user_id, gmap[role])
