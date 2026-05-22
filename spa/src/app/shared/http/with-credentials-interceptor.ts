import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID, inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from '../../auth/auth-service';

const REDIRECT_EXEMPT_PATHS = new Set(['/api/me', '/auth/logout']);

function pathOf(url: string): string {
  try {
    return new URL(url, 'http://placeholder').pathname;
  } catch {
    return url;
  }
}

export const withCredentialsInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const platformId = inject(PLATFORM_ID);
  const authedReq = req.clone({ withCredentials: true });

  return next(authedReq).pipe(
    catchError((err: unknown) => {
      if (
        err instanceof HttpErrorResponse &&
        err.status === 401 &&
        !REDIRECT_EXEMPT_PATHS.has(pathOf(authedReq.url))
      ) {
        authService.clear();
        // Browser-only: full-page navigation so the BFF can issue the 302 to
        // Keycloak. SSR's 401 path is handled by the auth guard's RedirectCommand.
        if (isPlatformBrowser(platformId)) {
          const returnTo = encodeURIComponent(router.url);
          window.location.href = `/auth/login?return_to=${returnTo}`;
        }
      }
      return throwError(() => err);
    }),
  );
};
