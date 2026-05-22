import { isPlatformBrowser } from '@angular/common';
import { PLATFORM_ID, inject } from '@angular/core';
import { CanMatchFn, RedirectCommand, Router, UrlSegment } from '@angular/router';

import { AuthService } from './auth-service';

function buildReturnTo(router: Router, segments: UrlSegment[]): string {
  // Prefer the in-flight navigation's URL so query string + fragment survive
  // the auth round-trip. Falls back to the matched segments for cases where
  // no navigation is in progress (defensive — CanMatch always runs inside one).
  const nav = router.getCurrentNavigation();
  if (nav?.extractedUrl) {
    return router.serializeUrl(nav.extractedUrl);
  }
  const path = '/' + segments.map((s) => s.path).join('/');
  return path.startsWith('//') ? path.slice(1) : path;
}

function loginUrl(returnTo: string): string {
  return `/auth/login?return_to=${encodeURIComponent(returnTo)}`;
}

export const authGuard: CanMatchFn = async (_route, segments) => {
  const authService = inject(AuthService);
  const platformId = inject(PLATFORM_ID);
  const router = inject(Router);

  // Skip the /api/me round-trip on in-app navigation when the signal is hot.
  if (authService.me() !== null) {
    return true;
  }

  try {
    await authService.loadMe();
  } catch {
    // Non-401 errors (network, 5xx) treated as "no session" — fall through to redirect.
  }

  if (authService.me() !== null) {
    return true;
  }

  const target = loginUrl(buildReturnTo(router, segments));

  if (isPlatformBrowser(platformId)) {
    window.location.href = target;
    return false;
  }
  // SSR: returning a RedirectCommand makes the router successfully navigate
  // to the auth/login stub route declared in app.routes.ts. Angular SSR's
  // engine detects finalUrl !== urlToRender and emits an empty-body 302 via
  // createRedirectResponse.
  return new RedirectCommand(router.parseUrl(target));
};
