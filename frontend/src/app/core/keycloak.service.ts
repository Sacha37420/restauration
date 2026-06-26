import { Injectable } from '@angular/core';
import Keycloak from 'keycloak-js';

interface EnvWindow {
  __env?: {
    keycloakUrl?: string;
    keycloakRealm?: string;
    keycloakClientId?: string;
    appUrl?: string;
    apiUrl?: string;
  };
}

@Injectable({ providedIn: 'root' })
export class KeycloakService {
  private kc!: Keycloak;

  async init(): Promise<boolean> {
    const env = (window as unknown as EnvWindow).__env ?? {};

    this.kc = new Keycloak({
      url:      env.keycloakUrl      ?? (window.location.protocol + '//' + window.location.hostname + ':8080'),
      realm:    env.keycloakRealm    ?? 'ssolab',
      clientId: env.keycloakClientId ?? 'restauration',
    });

    const isPublicRoute = window.location.pathname.includes('/commander');

    // Pour les routes publiques : check-sso via iframe silencieuse (pas de redirection
    // pleine page) pour ne pas perdre les query params de retour Stripe.
    const baseUri = document.baseURI.endsWith('/') ? document.baseURI : document.baseURI + '/';

    return this.kc.init({
      onLoad:                      isPublicRoute ? 'check-sso' : 'login-required',
      checkLoginIframe:            false,
      redirectUri:                 env.appUrl ?? window.location.origin,
      silentCheckSsoRedirectUri:   isPublicRoute ? `${baseUri}silent-check-sso.html` : undefined,
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
    this.kc.logout({ redirectUri: window.location.origin });
  }
}
