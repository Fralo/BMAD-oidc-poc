import { HttpInterceptorFn } from '@angular/common/http';
import { isPlatformServer } from '@angular/common';
import { PLATFORM_ID, inject } from '@angular/core';

import { SSR_API_TARGET } from './ssr-api-target.token';
import { SSR_PROXIED_PREFIXES } from './ssr-proxied-prefixes';

/**
 * SSR-only: rewrite same-origin URLs (`/api/me`) onto the absolute BFF
 * target so the SSR runtime's `fetch` can resolve them. No-op in the
 * browser (the SPA edge proxies same-origin paths to the BFF).
 */
export const ssrApiUrlInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isPlatformServer(inject(PLATFORM_ID))) {
    return next(req);
  }
  const target = inject(SSR_API_TARGET, { optional: true });
  if (!target) {
    return next(req);
  }
  if (!SSR_PROXIED_PREFIXES.some((prefix) => req.url.startsWith(prefix))) {
    return next(req);
  }
  return next(req.clone({ url: `${target}${req.url}` }));
};
