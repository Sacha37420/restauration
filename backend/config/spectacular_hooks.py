from django.conf import settings


def add_bearer_security(result, generator, request, public):
    comps = result.setdefault("components", {})
    sec = comps.setdefault("securitySchemes", {})
    if "BearerAuth" in sec:
        return result

    public_url = getattr(settings, "KEYCLOAK_PUBLIC_URL", None)
    realm = getattr(settings, "KEYCLOAK_REALM", None)
    if public_url and realm:
        issuer = f"{public_url.rstrip('/')}/realms/{realm}"
    else:
        issuer = getattr(settings, "KEYCLOAK_ISSUER_URI", "http://keycloak:8080/realms/ssolab")
    sec["BearerAuth"] = {
        "type": "oauth2",
        "flows": {
            "authorizationCode": {
                "authorizationUrl": f"{issuer}/protocol/openid-connect/auth",
                "tokenUrl": f"{issuer}/protocol/openid-connect/token",
                "scopes": {
                    "openid": "OpenID Connect scope",
                    "profile": "Profile scope",
                    "email": "Email scope",
                },
            }
        },
    }
    return result
