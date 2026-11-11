import { Injectable } from '@angular/core';
import Keycloak from 'keycloak-js';
import { loginRedirectUri } from './redirect-uri';
import { labEnv } from './env';

@Injectable({ providedIn: 'root' })
export class KeycloakService {
  private kc!: Keycloak;

  async init(): Promise<boolean> {
    const env = labEnv();

    this.kc = new Keycloak({
      url:      env.keycloakUrl      ?? (window.location.protocol + '//' + window.location.hostname + ':8080'),
      realm:    env.keycloakRealm    ?? 'ssolab',
      clientId: env.keycloakClientId ?? 'restauration',
    });

    const isPublicRoute = window.location.pathname.includes('/commander');

    // Pour les routes publiques : check-sso via iframe silencieuse (pas de redirection
    // pleine page) pour ne pas perdre les query params de retour Stripe.
    const baseUri = document.baseURI.endsWith('/') ? document.baseURI : document.baseURI + '/';

    // Pages privées : retour sur la page demandée (core/redirect-uri.ts).
    // Page publique (`/commander`, check-sso) : comportement inchangé, `appUrl` —
    // check-sso passe par l'iframe silencieuse et ne redirige jamais la page,
    // et cette page n'appelle jamais login() : redirectUri n'y sert pas.
    const redirectUri = isPublicRoute
      ? (env.appUrl ?? window.location.origin)
      : loginRedirectUri(window.location.href, env.appUrl, window.location.origin);

    return this.kc.init({
      onLoad:                      isPublicRoute ? 'check-sso' : 'login-required',
      checkLoginIframe:            false,
      redirectUri,
      silentCheckSsoRedirectUri:   isPublicRoute ? `${baseUri}silent-check-sso.html` : undefined,
      pkceMethod:                  'S256',
    });
  }

  get username(): string {
    return (this.kc?.tokenParsed as Record<string, unknown>)?.['preferred_username'] as string ?? '';
  }

  get email(): string {
    return (this.kc?.tokenParsed as Record<string, unknown>)?.['email'] as string ?? '';
  }

  get groups(): string[] {
    return (this.kc?.tokenParsed as Record<string, unknown>)?.['groups'] as string[] ?? [];
  }

  hasRole(role: string): boolean {
    return this.groups.includes(role);
  }

  isManager(): boolean  { return this.hasRole('manager'); }
  isCuisinier(): boolean { return this.hasRole('cuisinier'); }
  isServeur(): boolean  { return this.hasRole('serveur'); }

  getToken(): string | undefined {
    return this.kc?.token;
  }

  isTokenExpired(minValidity = 0): boolean {
    return this.kc?.isTokenExpired(minValidity) ?? true;
  }

  async updateToken(minValidity: number): Promise<boolean> {
    try {
      return await this.kc.updateToken(minValidity);
    } catch {
      return false;
    }
  }

  logout(): void {
    // Retour sous le préfixe de l'app (<base href>, ex. /<app>/) : la racine du domaine
    // n'est pas une URI de retour du client depuis --prune-uris (LOGOUT_ERROR
    // invalid_redirect_uri, constaté sur peripheriques le 2026-11-08).
    this.kc.logout({ redirectUri: document.baseURI });
  }
}
