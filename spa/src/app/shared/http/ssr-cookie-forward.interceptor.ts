import { HttpInterceptorFn } from '@angular/common/http';
import { isPlatformServer } from '@angular/common';
import { PLATFORM_ID, REQUEST, inject } from '@angular/core';

import { SSR_API_TARGET } from './ssr-api-target.token';

/**
 * SSR-only: copy the inbound browser's `Cookie` header onto outbound
 * HttpClient requests so SSR-time calls to the BFF (e.g. `/api/me` at
 * bootstrap) carry the user's session. No-op in the browser, which sends
 * cookies natively via `withCredentials`.
 *
 * The `REQUEST` injection token (first-class in `@angular/core` since
 * Angular 19.2) provides a Fetch-API `Request` — cookies live on
 * `request.headers.get('cookie')`, NOT on `request.cookies`.
 *
 * Why the URL gate: this interceptor runs AFTER `ssrApiUrlInterceptor` (per
 * `app.config.ts` registration order), so by the time we see `req.url` for
 * a proxied call, it has been rewritten to `${SSR_API_TARGET}${path}`. We
 * only forward the cookie when the outbound URL targets the configured BFF
 * — otherwise an SSR call to a third-party origin (analytics, CDN) would
 * leak the user's `bff_session`.
 */
export const ssrCookieForwardInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isPlatformServer(inject(PLATFORM_ID))) {
    return next(req);
  }
  const target = inject(SSR_API_TARGET, { optional: true });
  if (!target || !req.url.startsWith(target)) {
    return next(req);
  }
  const request = inject(REQUEST, { optional: true });
  const cookie = request?.headers.get('cookie');
  if (!cookie) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { cookie } }));
};
