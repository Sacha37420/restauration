"""Client minimal de l'API fichiers de l'app storage.

Le backend agit via le **service account** du client confidentiel compagnon
``restauration-admin`` (flux ``client_credentials``) — le même client, et le
même token, que ceux déjà utilisés par ``api/keycloak_admin.py`` pour l'API
Admin Keycloak, appelés ici contre l'API ``storage``.

Pourquoi un compte de service plutôt que le forward du token de l'utilisateur
courant (variante ``carto-lab``) : **la lecture d'une photo de plat est
anonyme**. La carte publique (``views_public.public_plats``, page « commander »
sans authentification) affiche les photos des plats — il n'y a aucun token à
forwarder sur ce chemin. Le compte de service est donc indispensable de toute
façon, et l'écriture (upload par un manager) l'emprunte aussi pour rester
uniforme : l'autorisation fine est décidée par ``PlatViewSet.get_permissions``
(``IsManager``) *avant* d'appeler ce module, qui reste un simple transport.

Un unique partage (``settings.STORAGE_NAMESPACE``), pas un par sous-ressource :
tous les plats forment une seule carte. Il doit exister au préalable, côté
storage ::

    python manage.py create_group_share restauration \\
        --owner sacha --required-groups manager,cuisinier,serveur

et le compte de service y être autorisé via
``KEYCLOAK_SERVICE_WRITE_SHARES=restauration-admin:restauration``
(``storage/.env``).
"""
from __future__ import annotations

import time

import requests
from django.conf import settings

_TIMEOUT = 15


class StorageClientError(RuntimeError):
    """Erreur de communication ou de configuration avec l'API storage."""


def _split_issuer() -> tuple[str, str]:
    issuer = (settings.KEYCLOAK_ISSUER_URI or '').rstrip('/')
    if '/realms/' not in issuer:
        raise StorageClientError(
            f"KEYCLOAK_ISSUER_URI invalide : {issuer!r} (attendu …/realms/<realm>)."
        )
    base, realm = issuer.split('/realms/', 1)
    return base, realm.split('/', 1)[0]


# Cache de token au niveau process (chaque worker gunicorn a le sien).
_token_cache: dict[str, float | str] = {'value': '', 'exp': 0.0}


def _token() -> str:
    now = time.time()
    if _token_cache['value'] and float(_token_cache['exp']) > now + 5:
        return str(_token_cache['value'])

    client_id = getattr(settings, 'KEYCLOAK_ADMIN_CLIENT_ID', '') or ''
    secret = getattr(settings, 'KEYCLOAK_ADMIN_CLIENT_SECRET', '') or ''
    if not client_id or not secret:
        raise StorageClientError(
            "KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET manquants. "
            "Lancez setup2.sh restauration (provisionne le client restauration-admin)."
        )

    base, realm = _split_issuer()
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
        raise StorageClientError(f'Keycloak injoignable : {exc}') from exc
    if resp.status_code != 200:
        raise StorageClientError(
            f"Auth service account échouée (HTTP {resp.status_code}) : {resp.text[:200]}"
        )
    data = resp.json()
    _token_cache['value'] = data['access_token']
    _token_cache['exp'] = now + int(data.get('expires_in', 60))
    return str(_token_cache['value'])


def _headers() -> dict[str, str]:
    return {'Authorization': f'Bearer {_token()}'}


def _files_url(suffix: str = '') -> str:
    return (
        f'{settings.STORAGE_INTERNAL_URL}/api/files/'
        f'{settings.STORAGE_NAMESPACE}/{suffix}'
    )


def upload(relative_path: str, fileobj, filename: str, content_type: str = '') -> dict:
    """Dépose `fileobj` sous `relative_path`. Retourne le JSON de
    StoredFileSerializer (voir storage/backend/api/views.py)."""
    files = {'file': (filename, fileobj, content_type or 'application/octet-stream')}
    try:
        resp = requests.post(
            _files_url(), headers=_headers(),
            data={'relative_path': relative_path}, files=files, timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StorageClientError(f'storage injoignable : {exc}') from exc
    if resp.status_code != 201:
        raise StorageClientError(
            f'Upload storage échoué (HTTP {resp.status_code}) : {resp.text[:200]}'
        )
    return resp.json()


def download(relative_path: str) -> requests.Response:
    """Retourne la réponse streamée (`stream=True`) — à l'appelant de la
    consommer et de la fermer (cf. views_public.public_plat_photo)."""
    try:
        resp = requests.get(
            _files_url(f'content/{relative_path}'), headers=_headers(),
            stream=True, timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StorageClientError(f'storage injoignable : {exc}') from exc
    if resp.status_code != 200:
        raise StorageClientError(f'Téléchargement storage échoué (HTTP {resp.status_code}).')
    return resp


def delete(relative_path: str) -> None:
    try:
        resp = requests.delete(
            _files_url(f'content/{relative_path}'), headers=_headers(), timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise StorageClientError(f'storage injoignable : {exc}') from exc
    if resp.status_code not in (204, 404):
        raise StorageClientError(f'Suppression storage échouée (HTTP {resp.status_code}).')
