import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from '../../auth/auth-service';

const ME_PATH = '/api/me';

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
  const authedReq = req.clone({ withCredentials: true });

  return next(authedReq).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && pathOf(authedReq.url) !== ME_PATH) {
        authService.clear();
        const returnTo = encodeURIComponent(router.url);
        router.navigateByUrl(`/login?return_to=${returnTo}`);
      }
      return throwError(() => err);
    }),
  );
};
