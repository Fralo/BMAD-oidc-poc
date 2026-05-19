import {
  AngularNodeAppEngine,
  createNodeRequestHandler,
  isMainModule,
  writeResponseToNodeResponse,
} from '@angular/ssr/node';
import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { join } from 'node:path';

import { SSR_PROXIED_PREFIXES } from './app/shared/http/ssr-proxied-prefixes';
import { cspMiddleware } from './server/csp.middleware';

const browserDistFolder = join(import.meta.dirname, '../browser');

// Strip trailing slashes so `${target}${req.url}` never produces `//`.
// `||` (not `??`) so empty-string env values also fall back to the default.
const bffInternalUrl = (process.env['BFF_INTERNAL_URL'] || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

// `pathFilter` accepts micromatch-style globs. Trailing `/**` ensures we
// match only path segments that begin with `/auth/`, `/api/`, or `/v1/` —
// not prefix-collision URLs like `/apiOther` or `/v1foo`. Sourced from
// `SSR_PROXIED_PREFIXES` to stay in lockstep with the SPA-side interceptor.
const proxyPathFilter = SSR_PROXIED_PREFIXES.map((prefix) => `${prefix}**`);

const app = express();
const angularApp = new AngularNodeAppEngine();

// 1. Lightweight health endpoint for compose's healthcheck (Story 6.2 will
//    poll this). Kept first so it short-circuits before the proxy or Angular.
app.get('/_health', (_req, res) => {
  res.json({ ok: true });
});

// 2. Reverse-proxy the BFF API surface. Mounted at the root with
//    `pathFilter` (NOT `app.use(path, middleware)`) because Express strips
//    the mount path before invoking the middleware — that would forward
//    `/api/me` as `/me` to the BFF. `pathFilter` matches the trailing-`/**`
//    globs above so prefix-collision paths (e.g. `/apiOther`) are not
//    silently proxied. `http-proxy-middleware` forwards every incoming
//    header by default (including `Cookie` and `X-CSRF-Token`), so browser
//    auth state flows through unchanged. `changeOrigin: true` rewrites the
//    `Host` header to the target's; `xfwd` adds `X-Forwarded-*` so the BFF
//    sees the original client identity. Paths are 1:1 between the SPA edge
//    and the BFF — no `pathRewrite`. Middleware order is non-negotiable:
//    this MUST be registered before the Angular catch-all below, otherwise
//    Angular would render `/api/me` as HTML.
//
//    `proxyTimeout` caps how long we wait for the BFF to respond before
//    returning 504; without it a hung BFF would stall SSR renders
//    indefinitely. `on.error` surfaces upstream failures as 502 instead of
//    leaking proxy internals through Express's default error handler.
app.use(
  createProxyMiddleware({
    pathFilter: proxyPathFilter,
    target: bffInternalUrl,
    changeOrigin: true,
    xfwd: true,
    proxyTimeout: 30_000,
    timeout: 30_000,
    on: {
      error: (err, _req, res) => {
        console.error(`[spa-edge] proxy error to ${bffInternalUrl}: ${err.message}`);
        if ('writeHead' in res && !res.headersSent) {
          res.writeHead(502, { 'content-type': 'application/json' });
          res.end(JSON.stringify({ errorCode: 'bff_unreachable', message: 'BFF unreachable' }));
        }
      },
    },
  }),
);

// 3. CSP attached to SSR HTML responses only — moved from BFF middleware per
//    architecture A8 amendment (Sprint Change Proposal 2026-05-19, Story 6.4).
//    Order matters: AFTER the proxy mount (so BFF-proxied JSON responses on
//    /auth /api /v1 do NOT carry CSP) and BEFORE the Angular SSR catch-all
//    (so the SSR response stream picks up `Content-Security-Policy` before
//    headers are sent). Static-asset responses (step 4) also pick up CSP
//    here; that's harmless and matches the pre-Epic-6 BFF posture (Story
//    1.14's static-mount likewise attached CSP on JS/CSS responses).
app.use(cspMiddleware);

// 4. Serve hashed browser bundles + assets from `dist/spa/browser`.
app.use(
  express.static(browserDistFolder, {
    maxAge: '1y',
    index: false,
    redirect: false,
  }),
);

// 5. Angular SSR catch-all — LAST. Anything that wasn't a probe, proxied
//    path, or static asset goes through `AngularNodeAppEngine`.
app.use((req, res, next) => {
  angularApp
    .handle(req)
    .then((response) => (response ? writeResponseToNodeResponse(response, res) : next()))
    .catch(next);
});

/**
 * Start the server if this module is the main entry point, or it is ran via PM2.
 * The server listens on the port defined by the `PORT` environment variable, or defaults to 4000.
 */
if (isMainModule(import.meta.url) || process.env['pm_id']) {
  const port = Number(process.env['PORT']) || 4000;
  const server = app.listen(port, () => {
    console.log(`Node Express server listening on http://localhost:${port}`);
    console.log(`Proxying /auth /api /v1 → ${bffInternalUrl}`);
  });
  server.on('error', (err) => {
    console.error(`[spa-edge] failed to bind on port ${port}: ${err.message}`);
    throw err;
  });
}

/**
 * Request handler used by the Angular CLI (for dev-server and during build) or Firebase Cloud Functions.
 */
export const reqHandler = createNodeRequestHandler(app);
