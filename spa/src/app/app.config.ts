import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { isPlatformServer } from '@angular/common';
import {
  ApplicationConfig,
  PLATFORM_ID,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { provideClientHydration } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

import { AuthService } from './auth/auth-service';
import { routes } from './app.routes';
import { csrfInterceptor } from './shared/http/csrf-interceptor';
import { ssrApiUrlInterceptor } from './shared/http/ssr-api-url.interceptor';
import { ssrCookieForwardInterceptor } from './shared/http/ssr-cookie-forward.interceptor';
import { withCredentialsInterceptor } from './shared/http/with-credentials-interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZonelessChangeDetection(),
    provideRouter(routes),
    // `withFetch()` is required for hydration's HttpClient transfer cache to
    // engage. The two `ssr*` interceptors short-circuit on the browser
    // platform; they're listed after the browser-time interceptors so they
    // don't mutate URLs/headers the browser interceptors then re-read.
    provideHttpClient(
      withFetch(),
      withInterceptors([
        withCredentialsInterceptor,
        csrfInterceptor,
        ssrApiUrlInterceptor,
        ssrCookieForwardInterceptor,
      ]),
    ),
    provideAppInitializer(() => {
      const platformId = inject(PLATFORM_ID);
      const bootstrap = inject(AuthService).loadMe();
      // Build-time route extraction and SSR renders against an unreachable
      // BFF must not crash the app — fall back to anonymous and let the
      // browser's hydration retry decide the user's auth state. The
      // `console.warn` keeps swallowed failures operator-visible in SSR
      // logs so a 5xx / programmer-bug masquerading as "anonymous" doesn't
      // disappear silently.
      return isPlatformServer(platformId)
        ? bootstrap.catch((err: unknown) => {
            console.warn('[ssr] AuthService.loadMe() failed during SSR bootstrap:', err);
            return undefined;
          })
        : bootstrap;
    }),
    // No `withEventReplay()` — its inline `<script id="ng-event-dispatch-contract">`
    // violates `script-src 'self'` in `csp.middleware.ts`. Without nonces/hashes
    // wired through Angular's `CSP_NONCE` provider, the event-replay shim is
    // blocked anyway; dropping it removes the console noise. Cost: events
    // dispatched during the ~ms hydration window are lost — negligible UX impact.
    provideClientHydration(),
  ],
};
