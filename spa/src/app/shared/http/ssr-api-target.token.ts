import { InjectionToken } from '@angular/core';

/**
 * Server-side base URL the SSR Express runtime forwards proxied paths to.
 * Provided in `app.config.server.ts` from `process.env['BFF_INTERNAL_URL']`.
 * Absent (or `null`) on the browser platform — the interceptor short-circuits.
 */
export const SSR_API_TARGET = new InjectionToken<string>('SSR_API_TARGET');
