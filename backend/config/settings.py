import os
from decouple import config

SECRET_KEY = config('SECRET_KEY', default='django-insecure-restauration-change-in-production')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*').split(',')

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
FORCE_SCRIPT_NAME = config('SCRIPT_NAME', default='')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'rest_framework',
    'corsheaders',
    'drf_spectacular_sidecar',
    'drf_spectacular',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

_DB_SCHEMA = config('DB_SCHEMA', default='restauration')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST':     config('DB_HOST',     default='postgres'),
        'PORT':     config('DB_PORT',     default=5432, cast=int),
        'NAME':     config('DB_NAME',     default='devdb'),
        'USER':     config('DB_USER',     default='devuser'),
        'PASSWORD': config('DB_PASSWORD', default='devpassword'),
        'OPTIONS': {
            'options': f'-c search_path={_DB_SCHEMA},public',
        },
    }
}

DB_SCHEMA = _DB_SCHEMA
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.authentication.KeycloakJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'public': '60/min',
        'public-write': '15/min',
    },
}

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:4200')

# URL PUBLIQUE mise dans les emails d'invitation : l'invité est externe, il lui
# faut une adresse atteignable depuis l'extérieur. Ordre de priorité :
#   1. INVITATION_URL (surcharge explicite) ;
#   2. si DOMAIN (DDNS) est configuré → https://<DOMAIN>/<chemin de l'app>
#      (le chemin Caddy est dérivé de SCRIPT_NAME en retirant le suffixe '-api') ;
#   3. sinon, IP WAN directe → <SERVER_URL_WAN>:<PORT_FRONTEND> (sans DDNS) ;
#   4. repli : FRONTEND_URL (dev local).
_DOMAIN = config('DOMAIN', default='').strip()
_SERVER_URL_WAN = config('SERVER_URL_WAN', default='').rstrip('/')
_PORT_FRONTEND = config('PORT_FRONTEND', default='')
_APP_PATH = FORCE_SCRIPT_NAME[:-4] if FORCE_SCRIPT_NAME.endswith('-api') else ''

if config('INVITATION_URL', default=''):
    INVITATION_URL = config('INVITATION_URL')
elif _DOMAIN and _DOMAIN != 'CHANGE_ME':
    INVITATION_URL = f'https://{_DOMAIN}{_APP_PATH}'
elif _SERVER_URL_WAN and _PORT_FRONTEND:
    INVITATION_URL = f'{_SERVER_URL_WAN}:{_PORT_FRONTEND}'
else:
    INVITATION_URL = FRONTEND_URL

# Le lien doit impérativement se terminer par '/' : servie sous un sous-chemin
# (ex. https://<domaine>/restauration), l'URL sans slash final ne résout pas le
# routage de l'app. On garantit un slash unique quelle que soit la source ci-dessus.
INVITATION_URL = INVITATION_URL.rstrip('/') + '/'

# --- Email (envoi des factures) ---
# En DEBUG, sortie console par défaut : fonctionne sans serveur SMTP réel.
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend' if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@restauration.local')

# --- Identité du restaurant (en-tête de facture) + TVA ---
RESTO_NOM = config('RESTO_NOM', default='Mon Restaurant')
RESTO_ADRESSE = config('RESTO_ADRESSE', default='')
RESTO_SIRET = config('RESTO_SIRET', default='')
RESTO_TVA_INTRA = config('RESTO_TVA_INTRA', default='')
# Taux de TVA appliqué sur les factures (%). 10 % = restauration sur place (France).
FACTURE_TVA_TAUX = config('FACTURE_TVA_TAUX', default='10.0')

KEYCLOAK_ISSUER_URI = config(
    'KEYCLOAK_ISSUER_URI',
    default='http://keycloak:8080/realms/ssolab',
)
KEYCLOAK_CLIENT_ID = config('KEYCLOAK_CLIENT_ID', default='restauration')
KEYCLOAK_PUBLIC_URL = config('KEYCLOAK_PUBLIC_URL', default=None)
KEYCLOAK_REALM = config('KEYCLOAK_REALM', default=None)

# --- Service account Keycloak (gestion des utilisateurs par les managers) ---
# Client confidentiel compagnon provisionné par create-app-client.sh
# (cf. restauration/.keycloak-service-account-roles). Le backend l'utilise en
# client_credentials pour créer des utilisateurs et gérer les groupes.
KEYCLOAK_ADMIN_CLIENT_ID = config('KEYCLOAK_ADMIN_CLIENT_ID', default='restauration-admin')
KEYCLOAK_ADMIN_CLIENT_SECRET = config('KEYCLOAK_ADMIN_CLIENT_SECRET', default='')
# Optionnel : router les appels admin vers une URL interne (ex. http://keycloak:8080).
# Vide → réutilise la base de KEYCLOAK_ISSUER_URI.
KEYCLOAK_ADMIN_BASE_URL = config('KEYCLOAK_ADMIN_BASE_URL', default='')

if KEYCLOAK_PUBLIC_URL and KEYCLOAK_REALM:
    _KEYCLOAK_ISSUER_FOR_UI = f"{KEYCLOAK_PUBLIC_URL.rstrip('/')}/realms/{KEYCLOAK_REALM}"
else:
    _KEYCLOAK_ISSUER_FOR_UI = KEYCLOAK_ISSUER_URI

SPECTACULAR_SETTINGS = {
    'TITLE': 'Restauration API',
    'DESCRIPTION': 'API de gestion de restaurant — stocks, commandes, planning, paiements.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SECURITY': [{'BearerAuth': []}],
    'COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'oauth2',
                'flows': {
                    'authorizationCode': {
                        'authorizationUrl': f'{_KEYCLOAK_ISSUER_FOR_UI}/protocol/openid-connect/auth',
                        'tokenUrl': f'{_KEYCLOAK_ISSUER_FOR_UI}/protocol/openid-connect/token',
                        'scopes': {
                            'openid': 'OpenID Connect scope',
                            'profile': 'Profile scope',
                            'email': 'Email scope',
                        },
                    }
                }
            }
        }
    },
    'SWAGGER_UI_DIST': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest',
    'SWAGGER_UI_FAVICON_HREF': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest/favicon-32x32.png',
    'SWAGGER_UI_OAUTH2_CONFIG': {
        'clientId': KEYCLOAK_CLIENT_ID,
        'usePkceWithAuthorizationCodeGrant': True,
        'scope': 'openid profile email',
        'authorizationUrl': f'{_KEYCLOAK_ISSUER_FOR_UI}/protocol/openid-connect/auth',
        'tokenUrl': f'{_KEYCLOAK_ISSUER_FOR_UI}/protocol/openid-connect/token',
        'oauth2RedirectUrl': f'{FORCE_SCRIPT_NAME}/api/docs/oauth2-redirect.html',
    },
    'POSTPROCESSING_HOOKS': [
        'config.spectacular_hooks.add_bearer_security',
    ],
}

CORS_ALLOW_ALL_ORIGINS = DEBUG

if not DEBUG:
    _cors_explicit = config('CORS_ALLOWED_ORIGINS', default='')
    _cors_list = [s for s in _cors_explicit.split(',') if s]
    if not _cors_list:
        _fport = config('PORT_FRONTEND', default='')
        _wan = config('SERVER_URL_WAN', default='')
        _lan = config('SERVER_URL_LAN', default='')
        _local = config('FRONTEND_URL', default='')
        for _o in [_local,
                   f"{_wan}:{_fport}" if _wan and _fport else '',
                   f"{_lan}:{_fport}" if _lan and _fport else '']:
            if _o and _o not in _cors_list:
                _cors_list.append(_o)
    CORS_ALLOWED_ORIGINS = _cors_list
else:
    CORS_ALLOWED_ORIGINS = []

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
