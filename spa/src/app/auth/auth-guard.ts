import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AuthService } from './auth-service';
import { Me } from './auth.types';

export const authGuard: CanActivateFn = async (_route, state) => {
  const http = inject(HttpClient);
  const router = inject(Router);
  const authService = inject(AuthService);

  try {
    const me = await firstValueFrom(http.get<Me>('/api/me'));
    authService.setMe(me);
    return true;
  } catch (err) {
    if (err instanceof HttpErrorResponse && err.status === 401) {
      return router.parseUrl(`/login?return_to=${encodeURIComponent(state.url)}`);
    }
    return router.parseUrl('/login');
  }
};
