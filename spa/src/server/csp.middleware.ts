import type { NextFunction, Request, Response } from 'express';

// Byte-for-byte identical to the value previously emitted by the BFF's
// SecurityHeadersMiddleware (deleted in Story 6.4 per architecture A8
// amendment). The CSP value did NOT change; only the attaching service did.
// Any drift here vs. the historical BFF literal is caught by the spec at
// `./csp.middleware.spec.ts`.
export const CSP_VALUE =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
  "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; " +
  "base-uri 'self'; form-action 'self'";

// CSP attachment for the SPA SSR edge. Registered between the `/auth /api /v1`
// proxy mount and the Angular SSR handler in `spa/src/server.ts`, so:
//   - BFF-proxied JSON responses (`/auth /api /v1`) do NOT carry CSP (the
//     proxy mount short-circuits before this middleware runs).
//   - SSR-rendered HTML responses from the Angular handler DO carry CSP
//     (this middleware runs before the handler sets headers + streams).
export function cspMiddleware(_req: Request, res: Response, next: NextFunction): void {
  res.setHeader('Content-Security-Policy', CSP_VALUE);
  next();
}
