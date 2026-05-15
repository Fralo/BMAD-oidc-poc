import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';

import { AuthService } from './auth/auth-service';
import { routes } from './app.routes';
import { csrfInterceptor } from './shared/http/csrf-interceptor';
import { withCredentialsInterceptor } from './shared/http/with-credentials-interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes),
    provideHttpClient(
      withFetch(),
      withInterceptors([withCredentialsInterceptor, csrfInterceptor]),
    ),
    provideAppInitializer(() => inject(AuthService).loadMe()),
  ],
};
