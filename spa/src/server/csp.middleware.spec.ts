import type { NextFunction, Request, Response } from 'express';

import { CSP_VALUE, cspMiddleware } from './csp.middleware';

function makeRes(): Pick<Response, 'setHeader' | 'getHeader'> & {
  headers: Record<string, string>;
} {
  const headers: Record<string, string> = {};
  return {
    headers,
    setHeader(name: string, value: string | number | readonly string[]): Response {
      headers[name] = String(value);
      return this as unknown as Response;
    },
    getHeader(name: string): string | undefined {
      return headers[name];
    },
  };
}

describe('cspMiddleware', () => {
  it('attaches the exact CSP byte string on the response', () => {
    const res = makeRes();
    let nextCalled = false;
    const next: NextFunction = () => {
      nextCalled = true;
    };

    cspMiddleware({} as Request, res as unknown as Response, next);

    expect(res.getHeader('Content-Security-Policy')).toBe(CSP_VALUE);
    expect(nextCalled).toBe(true);
  });

  it('CSP_VALUE is the byte string mandated by architecture A8', () => {
    // Pin-test: if anyone edits CSP_VALUE without also updating the security
    // review's directive table (docs/security-review.md §6), this test fires.
    expect(CSP_VALUE).toBe(
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; " +
        "base-uri 'self'; form-action 'self'",
    );
  });
});
