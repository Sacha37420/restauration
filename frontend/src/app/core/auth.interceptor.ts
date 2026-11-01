import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { from, switchMap, catchError } from 'rxjs';
import { KeycloakService } from './keycloak.service';
import { tokenBases } from './env';
import { carriesToken } from './token-scope';

/**
 * Joint le jeton de l'utilisateur aux appels vers l'API de l'app — et à elle
 * seule (`tokenBases()`). Une requête vers toute autre adresse part telle
 * quelle, sans jeton. Les routes publiques de l'API (`/api/public/`, page
 * `/commander`) partent aussi sans jeton, connecté ou non.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!carriesToken(req.url, tokenBases(), window.location.origin)) return next(req);
  if (req.url.includes('/api/public/')) {
    return next(req);
  }

  const kc = inject(KeycloakService);
  const token = kc.getToken();

  if (token && !kc.isTokenExpired(30)) {
    return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
  }

  return from(kc.updateToken(-1)).pipe(
    switchMap(() => {
      const fresh = kc.getToken();
      if (fresh) req = req.clone({ setHeaders: { Authorization: `Bearer ${fresh}` } });
      return next(req);
    }),
    catchError(() => next(req)),
  );
};
