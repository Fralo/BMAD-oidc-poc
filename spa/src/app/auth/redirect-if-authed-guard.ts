import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AuthService } from './auth-service';
import { Me } from './auth.types';

export const redirectIfAuthedGuard: CanActivateFn = async () => {
  const http = inject(HttpClient);
  const router = inject(Router);
  const authService = inject(AuthService);

  try {
    const me = await firstValueFrom(http.get<Me>('/api/me'));
    authService.setMe(me);
    return router.parseUrl('/books');
  } catch {
    return true;
  }
};
