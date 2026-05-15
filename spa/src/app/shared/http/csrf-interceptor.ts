import { HttpInterceptorFn } from '@angular/common/http';

const STATE_CHANGING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const CSRF_COOKIE_NAME = 'csrf_token';
const CSRF_HEADER_NAME = 'X-CSRF-Token';

function readCsrfTokenCookie(): string | null {
  const cookies = document.cookie ? document.cookie.split('; ') : [];
  for (const c of cookies) {
    const eq = c.indexOf('=');
    const name = eq === -1 ? c : c.slice(0, eq);
    if (name === CSRF_COOKIE_NAME) {
      const raw = eq === -1 ? '' : c.slice(eq + 1);
      if (!raw) return null;
      try {
        return decodeURIComponent(raw);
      } catch {
        return raw;
      }
    }
  }
  return null;
}

export const csrfInterceptor: HttpInterceptorFn = (req, next) => {
  if (!STATE_CHANGING_METHODS.has(req.method.toUpperCase())) {
    return next(req);
  }
  const token = readCsrfTokenCookie();
  if (!token) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { [CSRF_HEADER_NAME]: token } }));
};
