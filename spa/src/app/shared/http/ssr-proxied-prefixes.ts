/**
 * Single source of truth for the URL prefixes the SPA reverse-proxies to the
 * BFF. Used by:
 * - `src/server.ts` — Express `http-proxy-middleware` `pathFilter`
 * - `src/app/shared/http/ssr-api-url.interceptor.ts` — SSR-time URL rewriter
 *
 * Trailing slashes are intentional: they prevent prefix-collision matches
 * like `/apiOther`, `/v1foo`, `/authenticate` from being silently treated
 * as proxied API paths.
 */
export const SSR_PROXIED_PREFIXES = ['/auth/', '/api/', '/v1/'] as const;
