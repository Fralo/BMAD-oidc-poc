---
status: done
story_key: 6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding
epic: 6
prerequisites: Epic 1–5 all done (Epic 6 introduced 2026-05-19 via Sprint Change Proposal at `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md`). Story 1.14's SPA-in-BFF surface is **still live** at this point — it is NOT removed in Story 6.1. Story 6.3 owns BFF cleanup (drop the Node-builder Dockerfile stage, delete `_register_spa`/`_SPA_DIR`/`_json_404_fallback`/`_spa_or_404` from `services/bff/src/bff/main.py`, delete `services/bff/tests/api/test_static.py`). Story 6.2 owns the new `spa` compose service + Keycloak realm port pin (`http://localhost:8000` → `http://localhost:4000`). Story 6.4 owns the e2e + smoke + docs sweep. Story 6.1 therefore runs **strictly inside `spa/`** — the SPA continues to be served by the BFF in compose during 6.1's review.
supersedes_partially: Story 1.14 (partial — the SPA-in-BFF runtime model. Story 1.14 stays in the historical record; supersession lands in 6.3.)
created: 2026-05-19
baseline_commit: ed34ac7
---

# Story 6.1: SPA — Angular SSR scaffold + Express proxy middleware + SSR-time cookie forwarding

Status: done

<!-- Sprint: Epic 6 (Frontend Split & SSR Edge). First story in Epic 6. -->
<!-- Precedes: Story 6.2 (SPA Dockerfile + compose service + Keycloak realm port). -->
<!-- Source of truth: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.1; Epic 6 is NOT yet in `_bmad-output/planning-artifacts/epics.md` (Story 6.4 owns that edit). -->

## Story

As the SPA codebase,
I want to become an Angular SSR project whose Express runtime is the public edge — serving SSR-rendered HTML, reverse-proxying `/auth/*`, `/api/*`, `/v1/*` to the BFF, and forwarding the incoming browser's session cookies into SSR-time outbound calls,
so that the next story (6.2) can drop this Express runtime into its own container, the BFF can stop serving HTML (6.3), and the project's same-origin security model is preserved with a clean two-app split.

## Scope (read this first)

Story 6.1 lands **inside `spa/` only.** Zero edits to `services/`, `compose/`, `keycloak/`, `e2e/`, `_bmad-output/planning-artifacts/`. The deliverables are:

1. **`@angular/ssr` applied to the SPA** — `ng add @angular/ssr` (Angular 21 schematic) produces an Express SSR scaffold; this story customizes it to fit the project's auth contract.
2. **A custom `src/server.ts`** — Express server that mounts `http-proxy-middleware` for `/auth/*`, `/api/*`, `/v1/*` to `BFF_INTERNAL_URL`; exposes `/_health` for compose; mounts the Angular handler last.
3. **Two new HTTP interceptors** — `ssrApiUrlInterceptor` rewrites server-side URLs from same-origin (`/api/me`) to the SSR-visible BFF target; `ssrCookieForwardInterceptor` copies the inbound browser cookies into SSR-time outbound HTTP calls.
4. **SSR-safety patches to existing interceptors and the auth bootstrap** — `csrfInterceptor` and `withCredentialsInterceptor` short-circuit on the server platform; `provideAppInitializer(() => inject(AuthService).loadMe())` continues to work but its `/api/me` call now uses both new interceptors during SSR.
5. **TransferState-deduplicated bootstrap `/api/me`** — `provideClientHydration(withEventReplay())` + the HttpClient transfer cache means the bootstrap `/api/me` fires on the server, the response ships in the SSR payload, and the browser hydrates without re-firing.
6. **`proxy.conf.json` deleted; `angular.json` `serve.options.proxyConfig` reference removed.** The proxy is now in `server.ts`; the dev loop (host-side `ng serve` against the BFF on `:8000`) keeps working because `server.ts` IS the dev edge under SSR.
7. **Unit tests for the new interceptors** + updated specs for the two patched interceptors. SPA Vitest suite stays green; new code lands at ≥80% line coverage per Story 5.1's per-file floor.

What this story **does NOT do** (handled by later Epic 6 stories — do not touch any of these here):

- **`services/bff/Dockerfile`** — keep the Node-builder stage (Story 1.14 still in force at 6.1 close). Story 6.3 drops it.
- **`services/bff/src/bff/main.py`** — keep `_register_spa`, `_SPA_DIR`, `_json_404_fallback`, `_spa_or_404`, the `StaticFiles` mount, the `FileResponse` catch-all. Story 6.3 removes them.
- **`services/bff/tests/api/test_static.py`** — keep. Story 6.3 deletes.
- **`services/bff/src/bff/middleware/security_headers.py`** — keep. The CSP middleware moves to `spa/server.ts` in Story 6.4 (per Sprint Change Proposal §2.3 A8 amendment). Story 6.1 does NOT replicate the CSP header.
- **`compose/app.yml`** — do not add a `spa` service, do not change BFF ports, do not change the BFF build context. Story 6.2 owns all compose surgery.
- **`compose/app.e2e.yml`** — untouched. Story 6.4 owns e2e config sweep.
- **`keycloak/realm-bmad-books.json`** — keep `localhost:8000` redirect URIs / webOrigins / post.logout.redirect.uris. Story 6.2 flips them to `localhost:4000`.
- **`.env.example`** — keep. Story 6.2 adds `SPA_HOST_PORT`.
- **`e2e/playwright.config.ts`** — keep `E2E_BASE_URL=http://localhost:8000` and the existing `--host-resolver-rules`. Story 6.4 owns e2e config sweep.
- **`_bmad-output/planning-artifacts/architecture.md`** — do not flip line 178 (`--ssr=false`), line 289 (SSR not needed), line 354 (A8 — CSP source), lines 436–439 (F3), or line 509 (I6). Story 6.4 applies all architecture amendments.
- **`_bmad-output/planning-artifacts/PRD.md`** — do not edit. Story 6.4 owns the one-line §6 clarification.
- **`_bmad-output/planning-artifacts/epics.md`** — do not append an Epic 6 section. Story 6.4 owns it (the Sprint Change Proposal is the source of truth for Epic 6 until then).
- **`README.md`** — do not edit. Story 6.4 owns architecture-overview + dev-workflow + prod-shaped-workflow rewrites.
- **`docs/smoke-run.md`, `docs/security-review.md`, `docs/coverage-report.md`** — do not edit. Story 6.4 owns them.

Why this strict scope split: Stories 6.2 and 6.3 each have their own review surface. 6.1's review surface is the SPA's SSR readiness in isolation — it's verifiable by building the SPA, starting the SSR server on the host, and probing it against the BFF still running on `:8000`. Conflating any of 6.2/6.3 into 6.1 creates a multi-surface diff that is hard to review and hard to roll back if Angular 21's SSR integration surprises us.

## Acceptance Criteria

> Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.1 (AC1–AC7 there). Re-derived and tightened here with concrete file paths, exact API names verified against Angular 21 + `@angular/ssr` v21 + `http-proxy-middleware` v3.

### AC1 — `@angular/ssr` v21 applied to the SPA

**Given** the SPA at `spa/` is Angular 21.2.x (`spa/package.json` `@angular/core: ^21.2.0`),
**When** the developer inspects `spa/package.json` after this story,
**Then** the file lists in `dependencies` (or `devDependencies` where the schematic placed them — keep the schematic's defaults):
- `@angular/ssr` pinned to `^21.2.x` (must match the Angular major-minor of the existing `@angular/core`).
- `express` pinned to whatever version `ng add @angular/ssr` installs (current schematic ships `^4.18.x` for Angular 21; do NOT manually upgrade to Express 5 in this story).
- `http-proxy-middleware` pinned to `^3.0.x` (current latest; Angular 21 SSR scaffold does NOT install this — add it explicitly via `npm install http-proxy-middleware`).
- `@types/express` in `devDependencies` (schematic installs this).

**And** `spa/angular.json` has been updated by the schematic to add:
- A `server` build target under `projects.spa.architect.build.options` (`"server": "src/server.ts"`).
- A `serve-ssr` target (Angular 21's name for `@angular/build:dev-server`'s SSR variant — verify the exact key against what the schematic emits; do not invent the name).
- A `prerender` target (left at schematic default; this story does not prerender).
- Output naming preserved: `dist/spa/browser/` + `dist/spa/server/`.

**And** `spa/angular.json`'s `projects.spa.architect.serve.options.proxyConfig` reference to `"proxy.conf.json"` is **removed**. The dev loop's proxying now lives in `src/server.ts` (see AC3 / AC8); the standalone proxy config file is deleted in AC10.

**And** `spa/package.json` has a new run script (whatever name `ng add @angular/ssr` emits — typically `"serve:ssr:spa": "node dist/spa/server/server.mjs"`). Do not rename it; later docs (Story 6.2's Dockerfile `ENTRYPOINT`, Story 6.4's README dev-workflow section) will quote this exact script name.

> **Verification commands** (Task 9 will execute these):
> - `grep -nE "@angular/ssr|http-proxy-middleware|express" spa/package.json` → all three present.
> - `grep -nE "proxyConfig|proxy.conf.json" spa/angular.json` → no matches.
> - `grep -nE '"server":\s*"src/server.ts"' spa/angular.json` → exactly 1 match.

### AC2 — Production build emits both browser and server bundles

**Given** the SSR scaffold from AC1 is applied,
**When** the developer runs `cd spa && npm run build` (which still resolves to `ng build` — the script in `spa/package.json:7` is unchanged),
**Then** the command exits 0 and the following files exist:
- `spa/dist/spa/browser/index.csr.html` (Angular 21 SSR renames `index.html` → `index.csr.html`; the SSR server's render output is what gets shipped on the wire).
- `spa/dist/spa/browser/main-*.js` (browser bundle, hashed).
- `spa/dist/spa/server/server.mjs` (the Express server, the file `npm run serve:ssr:spa` runs).
- `spa/dist/spa/server/main.server.mjs` (Angular's server-side application bundle that `server.mjs` imports).

**And** the production build's `Initial total` / `Initial chunks` budget reported by `ng build` stays under the 1 MB cap in `spa/angular.json` `configurations.production.budgets[0]` (current SPA bundles at ~256 kB initial / 72 kB transfer per `_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md` baseline). The SSR scaffold should not move this materially; if it does, surface in Anomalies.

> **Failure-prevention note:** Angular 21's `@angular/build:application` builder does the SSR build via the existing `build` target with the `server` option set (no separate `ng run spa:server` command needed). If `npm run build` does NOT produce `dist/spa/server/`, the schematic application is incomplete — fix `angular.json` rather than invoke an alternate command.

### AC3 — `src/server.ts` is the customized Express edge

**Given** the schematic generates a default `spa/src/server.ts` using `AngularNodeAppEngine` + `createNodeRequestHandler` + `writeResponseToNodeResponse` from `@angular/ssr/node`,
**When** the developer inspects the post-customization `spa/src/server.ts`,
**Then** the file:

1. **Imports** at minimum:
   - `import express, { Request, Response, NextFunction } from 'express';`
   - `import { AngularNodeAppEngine, createNodeRequestHandler, writeResponseToNodeResponse, isMainModule } from '@angular/ssr/node';`
   - `import { createProxyMiddleware } from 'http-proxy-middleware';`
   - `import { dirname, resolve } from 'node:path';`
   - `import { fileURLToPath } from 'node:url';`

2. **Resolves** `browserDistFolder` to the absolute path of `dist/spa/browser/` using `fileURLToPath(import.meta.url)` + `dirname` + `resolve('../browser')` (the exact pattern Angular 21's schematic emits — keep it).

3. **Reads** `process.env['BFF_INTERNAL_URL']` (default `'http://localhost:8000'` for host-dev; Story 6.2 wires `http://bff:8000` in compose). Name the local constant `bffInternalUrl`.

4. **Middleware order is non-negotiable** (Express matches in registration order; getting this wrong = Angular renders `/api/me` as HTML):
   1. `app.get('/_health', (_req, res) => { res.json({ ok: true }); });` — lightweight healthcheck for Story 6.2's compose healthcheck.
   2. `app.use(['/auth', '/api', '/v1'], createProxyMiddleware({ target: bffInternalUrl, changeOrigin: true, xfwd: true }));` — proxy mount. `http-proxy-middleware` v3 forwards **all** incoming request headers including `Cookie` and `X-CSRF-Token` by default — no extra config needed for the cookie pass-through. `xfwd: true` adds the standard `X-Forwarded-*` headers so the BFF sees the original client IP/proto/host.
   3. `app.use(...)` Angular static-asset serving from `browserDistFolder` (the schematic's default — keep it).
   4. `app.use('/**', (req, res, next) => { angularApp.handle(req).then(response => response ? writeResponseToNodeResponse(response, res) : next()).catch(next); });` — Angular SSR catch-all, LAST.

5. **Bootstraps Express only when run as the main module:**
   ```ts
   if (isMainModule(import.meta.url)) {
     const port = Number(process.env['PORT'] ?? 4000);
     app.listen(port, () => {
       console.log(`SPA SSR server listening on http://localhost:${port}`);
       console.log(`Proxying /auth /api /v1 to ${bffInternalUrl}`);
     });
   }
   ```
   Port defaults to `4000` — matches the Sprint Change Proposal's `SPA_HOST_PORT:-4000` (Story 6.2 wires the env mapping).

6. **`reqHandler` export** stays as the schematic emits it (`export const reqHandler = createNodeRequestHandler(app);`) — Angular's CLI uses this when running the SSR dev server.

> **Failure-prevention note 1 (path-filter footgun):** `createProxyMiddleware({ pathFilter: ['/auth', '/api', '/v1'], ... })` syntax also works in v3, but mixing it with `app.use(path, middleware)` mounting causes double path-filtering. Use the Express-mount form above and leave `pathFilter` unset.
>
> **Failure-prevention note 2 (do NOT use `pathRewrite`):** the BFF expects the exact same paths — `/auth/login` → BFF `/auth/login`, `/api/me` → BFF `/api/me`. No rewrite. The dev-to-ultrawizard pattern that strips a `/api` prefix (`pathRewrite: { '^/api': '' }`) is wrong for this project.
>
> **Failure-prevention note 3 (do NOT mount CSP middleware here):** the Sprint Change Proposal moves CSP attestation source from BFF to the SPA edge, but that move is in Story 6.4. Story 6.1's `server.ts` ships without CSP middleware. The BFF still attaches CSP (`services/bff/src/bff/middleware/security_headers.py`) on HTML responses it serves — and during 6.1/6.2 it still serves HTML in the SPA-in-BFF path that Story 1.14 wired up.

### AC4 — `SSR_API_TARGET` injection token + `ssrApiUrlInterceptor`

**Given** during SSR, Angular's `HttpClient` issues an outbound request to the relative URL `/api/me` (from `AuthService.loadMe()` via `provideAppInitializer(...)`),
**And** the SSR Node process has no Browser-style same-origin to resolve that relative URL against — Angular SSR with `withFetch()` will reject the relative URL unless an absolute one is supplied,
**When** an interceptor server-side rewrites the URL to `${BFF_INTERNAL_URL}${url}`,
**Then** the SSR call lands on the BFF and the SSR render carries the authenticated `/api/me` shape into the hydration payload.

**Concretely**, create `spa/src/app/shared/http/ssr-api-target.token.ts` (NEW):
```ts
import { InjectionToken } from '@angular/core';

/**
 * Server-side base URL the SSR Express runtime forwards proxied paths to.
 * Provided in `app.config.server.ts` from `process.env['BFF_INTERNAL_URL']`.
 * Absent (or `null`) on the browser platform — the interceptor short-circuits.
 */
export const SSR_API_TARGET = new InjectionToken<string>('SSR_API_TARGET');
```

And create `spa/src/app/shared/http/ssr-api-url.interceptor.ts` (NEW):
```ts
import { HttpInterceptorFn } from '@angular/common/http';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformServer } from '@angular/common';

import { SSR_API_TARGET } from './ssr-api-target.token';

const PROXIED_PREFIXES = ['/auth/', '/api/', '/v1/'];

export const ssrApiUrlInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isPlatformServer(inject(PLATFORM_ID))) {
    return next(req);
  }
  const target = inject(SSR_API_TARGET, { optional: true });
  if (!target) {
    return next(req);
  }
  if (!PROXIED_PREFIXES.some((prefix) => req.url.startsWith(prefix))) {
    return next(req);
  }
  return next(req.clone({ url: `${target}${req.url}` }));
};
```

**AC4 close gate (unit test in `ssr-api-url.interceptor.spec.ts`):**
- Server platform + `SSR_API_TARGET=http://bff:8000` + URL `/api/me` → forwarded URL is `http://bff:8000/api/me`.
- Server platform + `SSR_API_TARGET=http://bff:8000` + URL `https://example.com/foo` → unchanged (doesn't match prefixes).
- Server platform + `SSR_API_TARGET` absent → unchanged.
- Browser platform → unchanged for every URL (no rewrite regardless of token state).

> **Failure-prevention note:** Do NOT use `req.urlWithParams` or `new URL(...)` here — `req.url` is the right field to test for prefix and to clone. The clone preserves all headers, body, params, and `withCredentials`.

### AC5 — `REQUEST` token cookie forwarding interceptor

**Given** during SSR the SPA needs the inbound browser's `bff_session` + `csrf_token` cookies on its outbound `/api/me` call,
**And** Angular 21 exposes the platform-specific Node `Request` via `import { REQUEST } from '@angular/core'` (first-class injection token since Angular 19.2; do NOT use the deprecated `@nguniversal/express-engine/tokens` path),
**When** an interceptor server-side reads `request.headers.cookie` and attaches it to the outbound `HttpRequest`,
**Then** the BFF resolves the session and the SSR render receives the authenticated `Me` shape.

Create `spa/src/app/shared/http/ssr-cookie-forward.interceptor.ts` (NEW):
```ts
import { HttpInterceptorFn } from '@angular/common/http';
import { PLATFORM_ID, REQUEST, inject } from '@angular/core';
import { isPlatformServer } from '@angular/common';

export const ssrCookieForwardInterceptor: HttpInterceptorFn = (req, next) => {
  if (!isPlatformServer(inject(PLATFORM_ID))) {
    return next(req);
  }
  const request = inject(REQUEST, { optional: true });
  // `request` is a Web-API `Request` in Angular 21's REQUEST token contract,
  // not the raw Node Express `req`. Cookies are exposed via headers.get('cookie').
  const cookie = request?.headers.get('cookie');
  if (!cookie) {
    return next(req);
  }
  return next(req.clone({ setHeaders: { cookie } }));
};
```

> **Critical clarification on the `REQUEST` token contract:**
> Angular 21's `REQUEST` injection token (`@angular/core`) provides a **Fetch-API `Request`** object, not a raw Node `http.IncomingMessage` and not the Express `req`. Headers are accessed via `.headers.get('header-name')` (case-insensitive per the Headers spec). This matches what `AngularNodeAppEngine.handle(req)` synthesizes from the Express request. Calling `request.cookies` or `request.signedCookies` (Express API) will throw — those properties don't exist on a Web Request.

**AC5 close gate (unit test in `ssr-cookie-forward.interceptor.spec.ts`):**
- Server platform + synthetic `REQUEST` token with `headers: new Headers({ cookie: 'bff_session=abc; csrf_token=xyz' })` → outbound HTTP request has `cookie: bff_session=abc; csrf_token=xyz` header.
- Server platform + `REQUEST` token returning a `Request` whose `headers.get('cookie')` returns `null` → outbound request unchanged.
- Server platform + `REQUEST` token absent (`inject(REQUEST, { optional: true })` returns `null`) → outbound request unchanged.
- Browser platform → outbound request unchanged regardless of REQUEST state (interceptor short-circuits at `isPlatformServer`).

> **Failure-prevention note:** Use `setHeaders` (not `headers`) on `req.clone()` to preserve any existing headers (e.g. CSRF) and merge the cookie in. Using `headers: new HttpHeaders(...)` would replace the entire header set and clobber CSRF on state-changing requests.

### AC6 — Server-side providers in `app.config.server.ts`

**Given** the schematic generates `spa/src/app/app.config.server.ts` with `provideServerRendering()` and `mergeApplicationConfig(appConfig, serverConfig)`,
**When** the developer inspects the post-customization file,
**Then** it provides:
- `provideServerRendering()` from `@angular/ssr` (NOT from `@angular/platform-server` — that import path produces NG0201 in Angular 20+).
- `{ provide: SSR_API_TARGET, useFactory: () => process.env['BFF_INTERNAL_URL'] ?? 'http://localhost:8000' }` — server-only token value.
- The `HTTP_TRANSFER_CACHE_ORIGIN_MAP` (from `@angular/common/http`) mapping the SSR-visible BFF origin to the browser-visible origin so the HttpClient transfer cache key for `/api/me` lines up across SSR → hydration. Specifically:
  ```ts
  {
    provide: HTTP_TRANSFER_CACHE_ORIGIN_MAP,
    useFactory: () => ({
      [process.env['BFF_INTERNAL_URL'] ?? 'http://localhost:8000']: 'http://localhost:4000',
    }),
  }
  ```
  This is the documented mechanism for SSR/CSR cache alignment when SSR calls absolute URLs but the browser calls same-origin relative URLs. The `'http://localhost:4000'` is the SPA edge origin Story 6.2 will publish; for Story 6.1's host-only verification it's a hint to the cache, not a runtime URL — the browser never re-fires the call thanks to the transfer cache.

And the merged provider tree includes the new `ssrApiUrlInterceptor` + `ssrCookieForwardInterceptor` (see AC8).

> **Failure-prevention note:** `provideServerRendering()` takes no required arguments in Angular 21; it's `provideServerRendering()` with the empty call, not `provideServerRendering({ ... })`.

### AC7 — Client config gains hydration

**Given** `spa/src/app/app.config.ts` currently provides `provideHttpClient(withFetch(), withInterceptors([withCredentialsInterceptor, csrfInterceptor]))`,
**When** the developer extends it,
**Then** the providers list adds:
- `provideClientHydration(withEventReplay())` from `@angular/platform-browser` — enables hydration (mandatory for the transfer cache to work; without it the browser silently re-fires `/api/me`).
- `withInterceptors([withCredentialsInterceptor, csrfInterceptor, ssrApiUrlInterceptor, ssrCookieForwardInterceptor])` — interceptor order matters; the two SSR-specific ones run after the browser-time ones because both have a server-platform short-circuit. Adding them at the end avoids re-ordering existing interceptor coverage.
- `withFetch()` is **already present** in the current file (line 22) — leave it. (The Angular SSR docs require `withFetch()` for hydration's transfer cache to engage.)

> **Failure-prevention note 1:** Do NOT remove `provideZonelessChangeDetection()`. Angular 21 supports SSR + zoneless together; the existing zoneless setup is what the dev / test stack relies on.
>
> **Failure-prevention note 2:** `provideAppInitializer(() => inject(AuthService).loadMe())` on line 25 stays. The transfer cache means this SSR-time call's response is reused by the browser; do not duplicate the initializer in `app.config.server.ts`.

### AC8 — SSR-safety patches to existing interceptors

`spa/src/app/shared/http/csrf-interceptor.ts` reads `document.cookie` directly (line 8). `document` does not exist on the server.

**Given** the SSR render is in flight,
**When** `csrfInterceptor` runs,
**Then** it MUST early-return `next(req)` without touching `document` if `isPlatformServer(inject(PLATFORM_ID))`.

Patch:
```ts
import { HttpInterceptorFn } from '@angular/common/http';
import { PLATFORM_ID, inject } from '@angular/core';
import { isPlatformServer } from '@angular/common';

// ... existing constants/helpers ...

export const csrfInterceptor: HttpInterceptorFn = (req, next) => {
  if (isPlatformServer(inject(PLATFORM_ID))) {
    return next(req); // CSRF is browser-only (only state-changing browser requests need the double-submit token).
  }
  if (!STATE_CHANGING_METHODS.has(req.method.toUpperCase())) {
    return next(req);
  }
  // ... rest unchanged ...
};
```

And `spa/src/app/shared/http/with-credentials-interceptor.ts` calls `router.navigateByUrl(...)` on 401 (line 28). Programmatic navigation during SSR triggers Angular Router state that may corrupt the SSR render or hang.

**Given** the SSR render encounters a 401 from `/api/me`,
**When** `withCredentialsInterceptor` catches it,
**Then** it MUST NOT call `router.navigateByUrl` on the server platform. The auth-guard's UrlTree-based redirect (already SSR-safe) handles the redirect during the SSR render flow.

Patch:
```ts
export const withCredentialsInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const platformId = inject(PLATFORM_ID);
  const authedReq = req.clone({ withCredentials: true });

  return next(authedReq).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && pathOf(authedReq.url) !== ME_PATH) {
        authService.clear();
        if (isPlatformBrowser(platformId)) {
          const returnTo = encodeURIComponent(router.url);
          router.navigateByUrl(`/login?return_to=${returnTo}`);
        }
      }
      return throwError(() => err);
    }),
  );
};
```

> **Failure-prevention note 1:** The 401-on-`/api/me` carve-out (existing logic `pathOf(authedReq.url) !== ME_PATH`) is preserved — `loadMe()` swallows the 401 itself and clears the signal. Don't change that behavior.
>
> **Failure-prevention note 2:** `authService.clear()` is safe on both platforms (it just resets a signal); keep it outside the `isPlatformBrowser` guard.

**Existing test specs** (`csrf-interceptor.spec.ts`, `with-credentials-interceptor.spec.ts`) must be updated to add server-platform cases via `TestBed.configureTestingModule({ providers: [{ provide: PLATFORM_ID, useValue: 'server' }] })`. See AC9 for coverage requirements.

### AC9 — Unit tests land and the SPA Vitest suite stays green

**Given** the SPA Vitest suite currently has 152 specs across 19 files (Story 5.1 baseline),
**When** the developer runs `cd spa && npm test -- --run` after this story,
**Then** the suite exits 0 with:
- ≥156 specs (4 net-new on the two new interceptors: 2 happy-path + 2 short-circuit; minimum).
- All existing 152 specs still pass.
- The two updated specs (`csrf-interceptor.spec.ts`, `with-credentials-interceptor.spec.ts`) each gain at least 1 server-platform case.

**Coverage** (per Story 5.1 NFR11 per-file floor of 50% statements / 70% functions; new code at ≥80% line):
- `ssr-api-url.interceptor.ts` — ≥80% line, all four branches in AC4 exercised.
- `ssr-cookie-forward.interceptor.ts` — ≥80% line, all four branches in AC5 exercised.
- `ssr-api-target.token.ts` — trivial (just `new InjectionToken`); excluded from coverage via `// istanbul ignore file` only if Vitest reports it; otherwise leave it.

`cd spa && npm run test:coverage` must exit 0 with the aggregate at or above the Story 5.1 baseline (`94.71%` statements, `91.16%` branches, `95.74%` functions, `94.52%` lines). New code SHOULD pull aggregate slightly up, not down; if it goes down, surface in Anomalies.

> **Failure-prevention note 1:** Vitest auto-discovers `*.spec.ts` colocated with sources. The two new spec files live at `spa/src/app/shared/http/ssr-api-url.interceptor.spec.ts` and `spa/src/app/shared/http/ssr-cookie-forward.interceptor.spec.ts`.
>
> **Failure-prevention note 2:** Provide a synthetic `REQUEST` token in the cookie-forward spec via `TestBed.configureTestingModule({ providers: [{ provide: REQUEST, useValue: new Request('http://localhost/', { headers: { cookie: 'bff_session=abc' } }) }] })`. Use the Web-API `Request` constructor, NOT a hand-rolled `{ headers: { cookie: ... } }` object — the interceptor calls `request.headers.get('cookie')` which only works on real `Headers`.

### AC10 — `proxy.conf.json` deleted; `angular.json` reference removed

**Given** the existing `spa/proxy.conf.json` declares the host-side `ng serve` proxy for `/auth/*`, `/api/*`, `/v1/*` to `http://localhost:8000`,
**When** the developer deletes the file and removes the reference,
**Then**:
- `spa/proxy.conf.json` no longer exists.
- `grep -nE "proxy.conf.json|proxyConfig" spa/angular.json` returns zero matches.
- The dev loop's proxy behavior is preserved because `src/server.ts` IS the dev edge once the developer runs the SSR dev mode (see AC11) or `node dist/spa/server/server.mjs` after `ng build`.

### AC11 — Dev loop documented (containerized + host-only fallback)

**Given** Angular 21's `@angular/build:dev-server` SSR support is the current developer pain point named in the Sprint Change Proposal §2.9 (risk row 1),
**When** the developer documents the dev loop in the story's Dev Notes,
**Then** the documentation names:

1. **Canonical (Story 6.2 owns):** containerized SSR dev — `docker compose up` (post-6.2) brings the SPA service up with a volume-mount of `./spa`. Hot reload is via Angular's built-in change detection inside the container.
2. **Story 6.1's verification path (host-only):** `cd spa && npm run build && PORT=4000 BFF_INTERNAL_URL=http://localhost:8000 node dist/spa/server/server.mjs` — assumes BFF is up on `:8000` (true with the SPA-in-BFF compose stack still running, per Story 1.14 surface still in place).
3. **Fallback for SSR-dev (if `@angular/build:dev-server` SSR mode does not support custom Express middleware in this Angular 21.2 build):** `cd spa && npm run build -- --watch --configuration development &` + `node --watch dist/spa/server/server.mjs` — rebuilds on source change; restart on `server.ts` change.

Story 6.1 does NOT need to ship a working `ng serve --ssr` flow — the close-gate is the production build (AC2) + the host-run SSR server (AC12). The Sprint Change Proposal explicitly carves this — *"If Angular 21's `@angular/build:dev-server` does not support custom middleware natively, fall back to `ng build --watch` + `node-with-restart` (documented in Dev Notes)"*.

### AC12 — Live host-run verification

**Given** the BFF stack is up via `docker compose up` (Story 1.14's profile — BFF serves the SPA on `:8000`, RS on internal `:8000`, Keycloak on `:8080`) — i.e., the **existing** production-shaped path is untouched and reachable,
**When** the developer runs `cd spa && npm run build && PORT=4000 BFF_INTERNAL_URL=http://localhost:8000 node dist/spa/server/server.mjs`,
**Then** the following four HTTP probes all return the expected response (record actual responses in Completion Notes — Dev Agent Record):

1. **SSR HTML** — `curl -sS http://localhost:4000/` returns HTTP 200, content-type `text/html`, body contains literal `<app-root` (the SSR-rendered Angular host element). Body also contains a hydration boundary marker (`ngh="..."` attribute on `<app-root>`) — proof hydration is wired.
2. **Proxied API (anonymous)** — `curl -sS http://localhost:4000/api/me` returns HTTP 401 with body `{"errorCode":"session_expired","message":"Session expired or not present","detail":null}` (the BFF's anonymous `/api/me` envelope verified verbatim in `docs/smoke-run.md`'s 2026-05-18 Run Record). Confirms the Express proxy forwards correctly.
3. **Proxied OAuth start** — `curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' http://localhost:4000/auth/login` returns `302 http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth?...&redirect_uri=http://localhost:8000/auth/callback&...` (the BFF emits its OWN `BFF_BASE_URL=http://localhost:8000` in `redirect_uri`; this is correct for 6.1 because Story 6.2 owns the `BFF_BASE_URL` flip to `:4000`).
4. **Health** — `curl -sS http://localhost:4000/_health` returns HTTP 200, content-type `application/json`, body `{"ok":true}`.

> **Failure-prevention note 1:** Probe 1 (`<app-root`) is opaque-string match, not byte-for-byte. The SSR output between `<app-root` and the closing `>` will contain hydration attributes (`ngh="0"`, etc.) — that's expected.
>
> **Failure-prevention note 2:** Probe 3's `redirect_uri` is `localhost:8000` deliberately during 6.1. Story 6.2 changes both Keycloak's registered redirect URI AND the BFF's `BFF_BASE_URL` in one atomic story (compose env + realm JSON edits both land in 6.2). Do not preempt that change here.
>
> **Failure-prevention note 3:** If probe 2 returns HTML instead of JSON, the middleware order is wrong (Angular handler is intercepting `/api/me`). Fix the order per AC3 step 4 — `app.use(['/auth', '/api', '/v1'], proxy)` must run BEFORE the Angular catch-all.

### AC13 — Out-of-scope verification (no leaks)

**Given** Story 6.1's scope is `spa/` only,
**When** the developer runs `git status --short` immediately before closing the story,
**Then** the entry list contains zero matches against any of the following paths (this list is the ground truth — anything matching is a scope leak):
- `services/bff/` (any file)
- `services/resource-server/` (any file)
- `compose/` (any file)
- `keycloak/` (any file)
- `e2e/` (any file)
- `_bmad-output/planning-artifacts/` (any file — this is Story 6.4's territory)
- `README.md`, `docs/` (any file — Story 6.4's territory)
- `.env.example`, `Justfile` (Story 6.2's territory)

Expected entries: `spa/**` (modified and new files per AC1–AC10), `_bmad-output/implementation-artifacts/6-1-...md` (this story file), `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip). Optionally `_bmad-output/implementation-artifacts/deferred-work.md` if new defers logged.

## Tasks / Subtasks

- [x] **Task 1 — Apply `@angular/ssr` schematic** (AC: 1, 2)
  - [x] 1.1 `npx ng add @angular/ssr@^21.2 --skip-confirmation --defaults` ran clean against the `spa/` workspace; schematic created `src/main.server.ts`, `src/app/app.config.server.ts`, `src/app/app.routes.server.ts`, `src/server.ts` and updated `angular.json`, `tsconfig.app.json`, `package.json`, `src/app/app.config.ts`.
  - [x] 1.2 `npm install http-proxy-middleware` added v4 to dependencies (schematic does not ship the proxy library).
  - [x] 1.3 `spa/package.json` lists `@angular/ssr ^21.2.11`, `express ^5.1.0`, `http-proxy-middleware ^4.0.0`, `@types/express ^5.0.1`, and the `serve:ssr:spa` script.
  - [x] 1.4 `spa/angular.json` `build.options` gained `"server": "src/main.server.ts"`, `"outputMode": "server"`, `"security": { "allowedHosts": ["localhost"] }`, `"ssr": { "entry": "src/server.ts" }`.
  - [x] 1.5 `npm run build` emits `dist/spa/browser/index.csr.html` + `dist/spa/server/server.mjs` + `dist/spa/server/main.server.mjs`.

- [x] **Task 2 — Customize `src/server.ts`** (AC: 3)
  - [x] 2.1 Imports include `AngularNodeAppEngine` / `createNodeRequestHandler` / `isMainModule` / `writeResponseToNodeResponse` from `@angular/ssr/node`, `express`, `createProxyMiddleware` from `http-proxy-middleware`, `join` from `node:path`.
  - [x] 2.2 `bffInternalUrl` reads `process.env['BFF_INTERNAL_URL'] ?? 'http://localhost:8000'`.
  - [x] 2.3 Middleware order is `app.get('/_health', ...)` → `app.use(createProxyMiddleware({ pathFilter: ['/auth','/api','/v1'], ... }))` → `express.static(browserDistFolder, ...)` → Angular SSR catch-all. **Key correction vs. AC3:** Express's `app.use(path, mw)` strips the prefix before invoking the proxy (so BFF would receive `/me` for `/api/me`); the proxy is mounted at the root with `pathFilter` to preserve full paths 1:1.
  - [x] 2.4 Two `console.log` lines on startup name the listening port and the proxy target.
  - [x] 2.5 Schematic's `export const reqHandler = createNodeRequestHandler(app)` preserved.
  - [x] 2.6 Also flipped `spa/src/app/app.routes.server.ts` from schematic-default `RenderMode.Prerender` to `RenderMode.Server` — prerender runs at build time, when the BFF isn't up, and would crash on the `/api/me` call.

- [x] **Task 3 — Add new interceptor + token files** (AC: 4, 5)
  - [x] 3.1 `spa/src/app/shared/http/ssr-api-target.token.ts` exports `SSR_API_TARGET = new InjectionToken<string>('SSR_API_TARGET')`.
  - [x] 3.2 `ssr-api-url.interceptor.ts` server-platform-gated; rewrites only `/auth/`, `/api/`, `/v1/` prefixed URLs onto `${SSR_API_TARGET}`; no-op on absent token or non-matching URL.
  - [x] 3.3 `ssr-cookie-forward.interceptor.ts` reads `inject(REQUEST, { optional: true })` from `@angular/core`, copies `request.headers.get('cookie')` onto the outbound `setHeaders`.

- [x] **Task 4 — Patch existing interceptors for SSR-safety** (AC: 8)
  - [x] 4.1 `csrf-interceptor.ts` — `isPlatformServer(inject(PLATFORM_ID))` short-circuit added before the state-changing-methods check; `document.cookie` is now never touched on the server.
  - [x] 4.2 `with-credentials-interceptor.ts` — `router.navigateByUrl(...)` wrapped in `isPlatformBrowser(platformId)`; `authService.clear()` still fires on both platforms (signal write only).
  - [x] 4.3 SPA Vitest suite stayed green: 164/164 specs across 21 files.

- [x] **Task 5 — Wire interceptors and providers into the config files** (AC: 6, 7)
  - [x] 5.1 `app.config.ts` — adds `provideClientHydration(withEventReplay())` (the schematic added this for us); extends `withInterceptors([...])` with the two new SSR interceptors after the browser-time ones; keeps `withFetch()`. **Additional patch:** `provideAppInitializer` now wraps `loadMe()` in a server-platform-only `.catch(() => undefined)` so build-time route extraction (and any other SSR call against an unreachable BFF) cannot crash app bootstrap.
  - [x] 5.2 `app.config.server.ts` provides `SSR_API_TARGET` from `process.env['BFF_INTERNAL_URL']` (default `http://localhost:8000`); provides `HTTP_TRANSFER_CACHE_ORIGIN_MAP` from `@angular/common/http` mapping the SSR-target to `'http://localhost:4000'` (overridable via `SPA_PUBLIC_ORIGIN`); keeps `provideServerRendering(withRoutes(serverRoutes))`.

- [x] **Task 6 — Add unit tests** (AC: 9)
  - [x] 6.1 `ssr-api-url.interceptor.spec.ts` — five cases: rewrite `/api/*`, rewrite `/auth/*` + `/v1/*`, no-op on outside-prefix URL, no-op on absent token, no-op on browser platform, direct injection-context call.
  - [x] 6.2 `ssr-cookie-forward.interceptor.spec.ts` — four cases: attach cookie on server with REQUEST, no-op on server without cookie header, no-op on server without REQUEST, no-op on browser regardless of REQUEST.
  - [x] 6.3 `csrf-interceptor.spec.ts` extended with server-platform POST case asserting no `X-CSRF-Token` header.
  - [x] 6.4 `with-credentials-interceptor.spec.ts` extended with server-platform 401 case asserting `clear()` fires but `navigateByUrl` does NOT.
  - [x] 6.5 `npx ng test --watch=false` → 164/164 passing across 21 files.
  - [x] 6.6 `npx ng test --watch=false --coverage` per-file: `ssr-api-target.token.ts` 100%/100%/100%, `ssr-api-url.interceptor.ts` 100%/100%/100%, `ssr-cookie-forward.interceptor.ts` 100%/100%/100%, `csrf-interceptor.ts` 95.65% L / 75% B / 100% F, `with-credentials-interceptor.ts` 93.75% L / 100% B / 100% F. Aggregate up to 94.88%/91.45%/95.87%/94.73% (statements/branches/functions/lines).

- [x] **Task 7 — Delete `proxy.conf.json` + clean `angular.json`** (AC: 10)
  - [x] 7.1 `rm spa/proxy.conf.json`.
  - [x] 7.2 Removed `"proxyConfig": "proxy.conf.json"` from `angular.json` `serve.options`; the block is now `"options": {}`.
  - [x] 7.3 `grep -nE "proxy.conf.json|proxyConfig" spa/angular.json` → no matches.

- [x] **Task 8 — Document the dev loop in Dev Notes** (AC: 11)
  - [x] 8.1 Documented (see "Dev-loop reality (post-implementation)" subsection below) — production-build + `node dist/spa/server/server.mjs` is the verified path on this Angular 21.2 build; containerized `ng serve --ssr` is deferred to Story 6.2; the build-watch + node-watch fallback path was not exercised in 6.1's review and is left as an option for 6.2.

- [x] **Task 9 — Live verification** (AC: 12)
  - [x] 9.1 `docker compose up -d --wait` brought up keycloak/bff/resource-server all healthy; SSR server started via `PORT=4000 BFF_INTERNAL_URL=http://localhost:8000 node dist/spa/server/server.mjs`.
  - [x] 9.2 Probe results captured in Completion Notes below.
  - [x] 9.3 Hydration verified — `ng-server-context="ssr"`, `ngh="0/1/2"` boundaries, and `id="ng-state"` transfer-state script all present on the SSR'd `/login` page.

- [x] **Task 10 — Scope-leak audit + close** (AC: 13)
  - [x] 10.1 `git status --short` clean of `services/`, `compose/`, `keycloak/`, `e2e/`, `README.md`, `docs/`, `.env.example`, `Justfile` (the only untracked planning artifact, `sprint-change-proposal-2026-05-19.md`, predates this dev session per the session-start git snapshot).
  - [x] 10.2 No defers logged in `deferred-work.md` (the two AC-vs-reality nits — Express v5 / http-proxy-middleware v4 schematic-shipped versions, and probe 1's 302-vs-200 redirect chain — are documentation-only observations recorded in Completion Notes, not deferred work).
  - [x] 10.3 Status flipped: `ready-for-dev → in-progress → review`; sprint-status.yaml updated.

### Review Findings

Three-layer adversarial review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) run on the `spa/`-scoped 787-line diff vs baseline `ed34ac7` on 2026-05-19. Acceptance Auditor: PASS on AC1, AC3–AC10, AC13; PARTIAL on AC1 (Express v5 / http-proxy-middleware v4 schematic-shipped versions vs spec's v4/v3 — documented in Completion Notes); AC2/AC11/AC12 not verifiable from diff (PASS by dev report). 1 decision-needed (resolved → patch), 8 patches applied, 5 deferred, 12 dismissed as noise. Post-patch: `npx ng test --watch=false` 166/166 across 21 files (+2 new cookie-leak-guard cases); `npm run build` clean.

- [x] [Review][Patch] `bootstrap.catch(() => undefined)` swallows SSR errors silently — surface via `console.warn` (decision: keep blanket catch but make swallowed errors operator-visible in SSR logs) [spa/src/app/app.config.ts:45]
- [x] [Review][Patch] SSR cookie forwarder leaks `Cookie` to non-BFF outbound calls — gate on `req.url.startsWith(SSR_API_TARGET)` so cookies only forward to the configured BFF [spa/src/app/shared/http/ssr-cookie-forward.interceptor.ts:24]
- [x] [Review][Patch] Proxy has no `proxyTimeout`/error handler — slow BFF stalls SSR indefinitely; added `proxyTimeout`/`timeout: 30_000` + `on.error` 502 handler [spa/src/server.ts:42-49]
- [x] [Review][Patch] Empty-string `BFF_INTERNAL_URL` falls through `??` and produces malformed URLs — switched to `||` in both reads [spa/src/server.ts:18; spa/src/app/app.config.server.ts:9]
- [x] [Review][Patch] Empty-string `SPA_PUBLIC_ORIGIN` not validated before populating `HTTP_TRANSFER_CACHE_ORIGIN_MAP` — switched to `||` [spa/src/app/app.config.server.ts:13]
- [x] [Review][Patch] Trailing slash in `BFF_INTERNAL_URL` produces double-slash absolute URLs (`http://bff:8000//api/me`) — normalized via `.replace(/\/+$/, '')` at both read sites [spa/src/app/shared/http/ssr-api-url.interceptor.ts:25; spa/src/server.ts:18]
- [x] [Review][Defer] `tsconfig.app.json` `"types": ["node"]` exposes Node globals (`process`, `Buffer`, `__dirname`) to browser-target source [spa/tsconfig.app.json:7] — deferred to a follow-up that adds `tsconfig.server.json` + wires it via `angular.json`; a one-line removal would break server.ts compilation
- [x] [Review][Patch] Server `pathFilter: ['/auth','/api','/v1']` lacks trailing slashes — `/apiOther`, `/v1foo`, `/authenticate` are silently proxied; also drifts from `PROXIED_PREFIXES` in `ssr-api-url.interceptor.ts` — single-sourced via new `spa/src/app/shared/http/ssr-proxied-prefixes.ts` and converted server pathFilter to `/**` glob form [spa/src/server.ts:44; spa/src/app/shared/http/ssr-api-url.interceptor.ts:7]
- [x] [Review][Patch] `app.listen(port, error => ...)` dead `error` arg (Express 5 callback has no error param) + `PORT` not coerced to number — coerced via `Number(...)` and moved bind-failure handling to `server.on('error', ...)` [spa/src/server.ts:74-82]
- [x] [Review][Defer] BFF_INTERNAL_URL read in two places (`server.ts` + `app.config.server.ts`) [spa/src/server.ts:18; spa/src/app/app.config.server.ts:9] — deferred, single-source refactor better folded into Story 6.2's compose wiring
- [x] [Review][Defer] No `app.set('trust proxy', ...)` configuration; `xfwd: true` appends to spoofable `X-Forwarded-For` [spa/src/server.ts:42-49] — deferred, depends on Story 6.2's deployment topology (ingress / compose front)
- [x] [Review][Defer] No `SIGTERM` graceful shutdown — container stop kills in-flight SSR renders [spa/src/server.ts:73-83] — deferred, operational concern for Story 6.2's compose service shape
- [x] [Review][Defer] `import.meta.dirname` may be undefined on older Node runtimes [spa/src/server.ts:11] — deferred, project pins recent Node; revisit if compose base image changes



### What this story changes vs. preserves in `spa/`

**New files** (≈8):
- `spa/src/server.ts` — Express edge (customized from `ng add @angular/ssr` output).
- `spa/src/main.server.ts` — Angular server bootstrap (schematic-generated; do not customize unless the schematic's default fails the AC2 build).
- `spa/src/app/app.config.server.ts` — server-side providers (schematic-generated then customized per AC6).
- `spa/src/app/app.routes.server.ts` — server-side `ServerRoute` array (schematic default is `{ path: '**', renderMode: RenderMode.Server }` — keep it).
- `spa/src/app/shared/http/ssr-api-target.token.ts` — `SSR_API_TARGET` `InjectionToken`.
- `spa/src/app/shared/http/ssr-api-url.interceptor.ts` — server-side URL rewriter.
- `spa/src/app/shared/http/ssr-api-url.interceptor.spec.ts` — its Vitest spec.
- `spa/src/app/shared/http/ssr-cookie-forward.interceptor.ts` — server-side cookie forwarder.
- `spa/src/app/shared/http/ssr-cookie-forward.interceptor.spec.ts` — its Vitest spec.

**Modified files** (≈6):
- `spa/package.json` — adds `@angular/ssr`, `express`, `http-proxy-middleware`, `@types/express`; adds `serve:ssr:spa` script.
- `spa/angular.json` — adds `server` build target + Angular 21's serve-ssr target name; removes `proxyConfig` reference.
- `spa/tsconfig.app.json` — schematic adds `src/server.ts` and `src/main.server.ts` to `files` or `include`; keep its edit.
- `spa/src/app/app.config.ts` — adds `provideClientHydration(withEventReplay())`; extends `withInterceptors([...])` with the two new SSR interceptors.
- `spa/src/app/shared/http/csrf-interceptor.ts` — adds `isPlatformServer` short-circuit.
- `spa/src/app/shared/http/with-credentials-interceptor.ts` — wraps `router.navigateByUrl` in `isPlatformBrowser` guard.
- `spa/src/app/shared/http/csrf-interceptor.spec.ts` — adds a server-platform case.
- `spa/src/app/shared/http/with-credentials-interceptor.spec.ts` — adds a server-platform case.

**Deleted files** (1):
- `spa/proxy.conf.json`.

**Files NOT to touch in `spa/`** (preserved as-is):
- `spa/src/main.ts` (browser bootstrap stays the same — `bootstrapApplication(App, appConfig)`).
- `spa/src/app/app.ts`, `app.html`, `app.css`, `app.routes.ts` — no template / route changes.
- `spa/src/app/auth/auth-guard.ts`, `redirect-if-authed-guard.ts` — the `CanActivateFn` UrlTree pattern is SSR-safe (Angular Router serializes UrlTrees during SSR and resolves the redirect transparently). Do not patch the guards unless probe 1 in AC12 reveals a guard-related SSR error.
- `spa/src/app/auth/auth-service.ts` — the `provideAppInitializer(() => loadMe())` flow is SSR-safe once the two new interceptors are in place. Do not patch.
- `spa/eslint.config.js`, `tsconfig.json`, `tsconfig.spec.json` — schematic may extend these; keep its edits, do not invent your own.
- `spa/public/` (favicon and friends) — unchanged.

### Angular 21 SSR contracts the implementer MUST honor

Verified against current Angular 21 docs (angular.dev/guide/ssr as of 2026-05) and the `@angular/ssr` v21 package:

1. **`provideServerRendering()` import path** — `@angular/ssr`, NOT `@angular/platform-server`. The latter triggers `NG0201` at SSR-time on Angular 20+.

2. **`REQUEST` injection token** — `@angular/core` (since Angular 19.2). Do NOT use `@nguniversal/express-engine/tokens` (deprecated; was removed when `@nguniversal/*` packages were retired in Angular 17.x). The token provides a **Fetch-API `Request`**, not a Node Express `req`; access cookies via `request.headers.get('cookie')`.

3. **`AngularNodeAppEngine` API** (in `@angular/ssr/node`) — call `angularApp.handle(req)` returning `Promise<Response | null>`. If `null`, fall through to `next()` (Angular has no route for this URL — usually means the proxy or static handler should have caught it; in practice the schematic registers the static handler before SSR, so `null` is rare).

4. **`createNodeRequestHandler` + `writeResponseToNodeResponse`** — the schematic's pattern for converting Angular's Web Response to Express's `res`. Use the schematic's exact pattern; do NOT replace with `res.send(await response.text())` — that loses the response status and streaming.

5. **Build output paths** — `dist/spa/browser/index.csr.html` (renamed from `index.html`), `dist/spa/browser/main-*.js`, `dist/spa/server/server.mjs`, `dist/spa/server/main.server.mjs`. The `.mjs` suffix is Angular 21's ESM-only SSR output.

6. **Hydration + transfer cache** — `provideClientHydration(withEventReplay())` in `app.config.ts` + `withFetch()` in `provideHttpClient` (already present). For absolute SSR URLs to deduplicate against same-origin browser URLs, provide `HTTP_TRANSFER_CACHE_ORIGIN_MAP` in `app.config.server.ts` per AC6.

### `http-proxy-middleware` v3 defaults (no extra config needed for cookies)

Verified against `chimurai/http-proxy-middleware` v3 docs:
- **Headers are forwarded by default** — every header on the incoming request, including `Cookie` and `X-CSRF-Token`, is passed to the proxy target without configuration. No `headers: { cookie: ... }` clone needed.
- **`xfwd: true`** adds the four standard `X-Forwarded-*` headers (`-For`, `-Host`, `-Proto`, `-Port`). The BFF doesn't currently consume these but they're a no-cost good-citizen default.
- **`changeOrigin: true`** rewrites the `Host` header to match the target (BFF). Required when the target's virtual host differs from the source's; safe to enable unconditionally.
- **Do NOT enable `secure: false`** — that's a TLS-trust override for self-signed certs and is irrelevant here (BFF is on HTTP in compose).
- **Do NOT use `pathRewrite`** — paths line up 1:1 between SPA edge and BFF.

### Middleware-order foot-gun (this is the most likely LLM mistake)

Express middlewares match in **registration order**, not in specificity order. If `app.use('/**', angularHandler)` is registered BEFORE the proxy mount, the Angular catch-all will try to render `/api/me` as HTML — symptom: probe 2 in AC12 returns an HTML page instead of the BFF 401 JSON envelope.

Correct order:
1. `app.get('/_health', ...)` — most specific first.
2. `app.use(['/auth', '/api', '/v1'], createProxyMiddleware(...))` — proxy second.
3. `app.use(<browser dist static>, ...)` — schematic-emitted static serving (`assets/`, `main-*.js`, etc.).
4. `app.use('/**', angularSsrHandler)` — Angular catch-all LAST.

The schematic's default `server.ts` already registers static + Angular in that order. The proxy mount slots in between #1 and #3.

### Angular 21 `@angular/build:dev-server` SSR-mode caveat

The dev-server (used by `ng serve`) in Angular 21 supports SSR, but its support for **custom Express middleware mounted by the user** is incomplete in 21.2.x — the dev-server builds its own Express instance and does not provide a hook for `server.ts`'s mounted middleware. Symptoms include `/api/me` returning Angular HTML even with `server.ts` configured correctly.

This is the Sprint Change Proposal §2.9 risk row 1. Story 6.1's close-gate is NOT `ng serve --ssr` — it is the AC2 production build + AC12 host-run probes. Story 6.2 will revisit dev-mode under containerized SSR; until then, the fallback in AC11 is the documented dev path.

If you discover `ng serve` SSR + middleware works cleanly in this Angular 21.2 build, document the working invocation in Completion Notes — it's a positive signal for 6.2's dev story. If it doesn't, log the failure mode (exact error + version) as a defer with severity `low` (dev-only, not a runtime defect).

### Dev-loop reality (post-implementation)

The path used to verify Story 6.1 against a live BFF:

```sh
# Terminal 1: existing default-profile stack (Story 1.14 surface, BFF on :8000)
docker compose up -d --wait

# Terminal 2: SPA SSR edge on :4000 reverse-proxying to the BFF
cd spa
npm run build
PORT=4000 BFF_INTERNAL_URL=http://localhost:8000 node dist/spa/server/server.mjs
```

The four AC12 probes ran clean against this setup (see Completion Notes). `ng serve --ssr` with custom middleware was **not** exercised in 6.1's review — Story 6.2 (containerized dev) is where this gets revisited. The build-watch + node-watch fallback in AC11 was not needed because each edit cycle was small enough that a full `npm run build` (~2 s warm cache) was faster than building the watcher chain.

Two Angular-21-specific gotchas surfaced during 6.1 that the dev agent should know about before re-running:

1. **Schematic-default `RenderMode.Prerender` crashes the build** for an auth-gated app — the prerender phase runs the app initializer (`loadMe()`) at build time with no BFF reachable. Fix: flip `spa/src/app/app.routes.server.ts` to `RenderMode.Server` (per-request SSR) AND wrap `provideAppInitializer` in a server-platform-only `.catch(() => undefined)` so build-time route extraction (which still runs the app once even with `RenderMode.Server`) cannot crash on a network error.
2. **`security.allowedHosts` in `angular.json`** is mandatory for Angular 21 SSR — empty array (the schematic default) means every SSR request gets a 400 with the "Header 'host' is not allowed" message. The validator extracts the **hostname only** (port stripped) when comparing against the allowlist, so `"localhost"` covers `localhost:4000`, `localhost:8080`, etc. Story 6.2 will need to extend this list when the SSR edge moves into compose (`spa:4000` will need adding).

### How AC4 + AC5 + AC6 + AC7 + AC8 compose into one SSR `/api/me` round-trip

Walk through the chain so the implementer sees the whole flow:

1. Browser hits `http://localhost:4000/` with `Cookie: bff_session=abc; csrf_token=xyz` (session set on the BFF on previous login; cookies are same-origin to `:4000` because the BFF set them on the same host).
2. Express `server.ts` receives the request. None of the proxy paths match `/`; falls through to Angular handler.
3. Angular SSR begins rendering. `provideAppInitializer(() => inject(AuthService).loadMe())` fires.
4. `loadMe()` calls `this.http.get<Me>('/api/me')`.
5. Interceptor chain runs:
   a. `withCredentialsInterceptor` clones with `withCredentials: true` (no-op for the credentials property on Node fetch, but kept for the catchError 401 logic — which short-circuits on server platform after Task 4.2's patch).
   b. `csrfInterceptor` — short-circuits on server platform per Task 4.1's patch.
   c. `ssrApiUrlInterceptor` — server platform + URL starts with `/api/` + `SSR_API_TARGET=http://localhost:8000` → rewrites to `http://localhost:8000/api/me`.
   d. `ssrCookieForwardInterceptor` — server platform + REQUEST token has `cookie: bff_session=abc; csrf_token=xyz` → clones with that cookie header attached.
6. Angular's `HttpClient` (with `withFetch()`) issues the fetch to `http://localhost:8000/api/me` with `cookie: bff_session=abc; csrf_token=xyz`.
7. BFF resolves the session; responds with `200 { sub: "user-..." }` (or `401` if the cookie is missing/expired).
8. The response is cached in the SSR transfer state (auto-enabled by `withFetch()` + `provideClientHydration`).
9. The SSR-rendered HTML ships to the browser with the transfer cache embedded.
10. The browser hydrates. `provideAppInitializer` fires again, but `HttpClient`'s transfer cache returns the SSR's response without a network call. `Me` is set immediately; no `/api/me` re-fire.

The `HTTP_TRANSFER_CACHE_ORIGIN_MAP` from AC6 is what makes step 10 work: it maps the SSR-side URL `http://localhost:8000/api/me` to the browser-side same-origin URL `http://localhost:4000/api/me` so the cache key lines up.

### Project Structure Notes

- New interceptors live alongside the existing two in `spa/src/app/shared/http/` — same flat-file convention as `csrf-interceptor.ts` + `with-credentials-interceptor.ts`. Per `architecture.md:1018` SPA tree and Story 3.5's precedent (the `shared/http/` folder predates this story).
- The injection token lives in its own file `ssr-api-target.token.ts`. Reason: tokens are typically standalone files in this project (mirror `spa/src/app/settings/reading-speed.types.ts` precedent — Story 4.3 AC1 established the "own file per shared symbol" convention).
- `server.ts` lives in `spa/src/` (not `spa/`) — the Angular 21 schematic insists on this; do not move it.
- `app.config.server.ts` and `main.server.ts` likewise live in `spa/src/app/` and `spa/src/` per the schematic; do not relocate.

### Previous Story Intelligence

- **Story 4.3** (`spa/src/app/books/estimate.types.ts` creation) — taught the "shared symbol in its own file" pattern. Apply the same pattern for `SSR_API_TARGET` (AC4).
- **Story 3.5** (SPA interceptor work) — established the `shared/http/` folder layout, the `HttpInterceptorFn` arrow style, and the `inject(...)` (function-style) DI pattern. Match it exactly.
- **Story 1.10** (LoginView + TopChrome + route table) — established `provideAppInitializer(() => inject(AuthService).loadMe())` in `app.config.ts`. Story 6.1 must not break this.
- **Story 5.1** (coverage audit) — sets the per-file 50% statements / 70% functions floor and pegs the SPA aggregate at 94.71% statements / 91.16% branches. New code at ≥80% line (AC9) keeps headroom.
- **Story 5.2** (security review) — §6 CSP attestation currently cites `services/bff/src/bff/middleware/security_headers.py:17–21` as the byte-for-byte CSP source. Story 6.1 does NOT move the CSP source (that's 6.4); but the security-review doc will eventually retag this to `spa/src/server.ts` or a dedicated `spa/src/server/csp.middleware.ts`. Do NOT preempt that move.
- **Story 1.14** (BFF multi-stage build serves SPA bundle) — the surface 6.1 prepares to supersede. **Story 1.14's runtime surface stays live during 6.1.** This is intentional: it means the BFF stack can keep serving the SPA from `:8000` while 6.1 verifies the new SSR edge on `:4000` against the same BFF. Story 6.3 removes the 1.14 surface.

### Git Intelligence (recent commits)

```
ed34ac7 fix(d140-d141): make bare `docker compose up` work for a fresh clone
5f9b0f7 chore(epic-5): retrospective — flip epic-5 done, A1/A2 action items
b81129a Merge story 5.4 — final docker compose up smoke (default profile)
3d5f0b6 chore(5.4): code review — 8 patches applied, mark done, log D144-D148
417ab1e Merge epic-5 into E5S4 — resolve conflicts + renumber D-IDs
```

- `ed34ac7` removed per-service `.env` files and consolidated to root `.env`; both BFF and RS now load `../.env` from compose. Story 6.1 does not interact with this (no compose edits).
- The Epic 5 close means the codebase is at a clean baseline; Story 6.1 starts from `main` HEAD `ed34ac7` per frontmatter `baseline_commit`.
- No SPA-side commits in the last 5. The SPA hasn't been modified since the Epic 4 close two commits before the visible range; check `git log --oneline -- spa/` if needed.

### Latest Tech Information

Verified against Angular 21 / `@angular/ssr` v21 / `http-proxy-middleware` v3 docs (May 2026):

- **`@angular/ssr` v21.2.x**: exposes `AngularNodeAppEngine`, `createNodeRequestHandler`, `writeResponseToNodeResponse`, `isMainModule` from `@angular/ssr/node`; `provideServerRendering`, `AngularAppEngine`, `createRequestHandler`, `RenderMode`, `ServerRoute` from `@angular/ssr`. The Node and non-Node entry points are distinct — only import from `@angular/ssr/node` when running under Node (this project does).
- **Angular 21 hydration**: `provideClientHydration(withEventReplay())` enables event replay during hydration (clicks/inputs that fire before hydration completes are buffered and replayed). `withFetch()` is **required** for the transfer cache to engage; the project's `app.config.ts:22` already has it.
- **`http-proxy-middleware` v3.0.5+**: `createProxyMiddleware({ target, changeOrigin, xfwd })` is the v3 import. v3 changed the default of `pathFilter` from string-only to array+RegExp+function — for our use the simpler `app.use(path, middleware)` Express-mount form is preferred.
- **`HTTP_TRANSFER_CACHE_ORIGIN_MAP`**: lives in `@angular/common/http` since Angular 19; documents itself as "origin map for HttpClient transfer-cache key alignment between SSR and CSR". Provide in `app.config.server.ts` only — providing it on the browser side has no effect.
- **`express` v4 vs v5**: Angular 21's `ng add @angular/ssr` installs Express v4.18.x. Do not upgrade to v5 in this story — v5's middleware error-handling semantics differ and the schematic's `(req, res, next) => angularApp.handle(req).then(...).catch(next)` pattern relies on v4's behavior.

### Testing Standards

- **Vitest 4.x via `@angular/build:unit-test`** — `cd spa && npm test -- --run` for one-shot; `cd spa && npm run test:coverage` for coverage report. Existing 152 specs / 19 files baseline; Story 6.1 lifts to ≥156 specs / 21 files.
- **`TestBed.configureTestingModule({ providers: [{ provide: PLATFORM_ID, useValue: 'server' }] })`** is the standard pattern for forcing the server platform inside an interceptor spec. Mirror it from existing zoneless test setups.
- **`new Request('http://localhost/', { headers: { cookie: '...' } })`** for the synthetic SSR REQUEST. Web-API Request constructor; available natively in Node 22 + Vitest's `jsdom` environment.
- **Per Story 5.1's coverage philosophy**: do not add `coverage.exclude` patterns for the new files. Cover them ≥80% line.
- **Don't write integration tests for `server.ts`** — Express + Angular SSR + proxy is hard to mock and brittle. AC12's live host-run probes are the integration verification.

### References

- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.1 (AC1–AC7) — primary source of truth for Epic 6 scope]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §2.6 SPA source impact — file-by-file list]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §2.9 Risks — Angular 21 dev SSR + middleware integration risk]
- [Source: `_bmad-output/planning-artifacts/architecture.md` §F3 (line 436) — current SPA-in-BFF model that 6.3 supersedes]
- [Source: `_bmad-output/planning-artifacts/architecture.md` §I6 (line 509) — current compose-side serving]
- [Source: `_bmad-output/planning-artifacts/architecture.md` §A8 (line 354) — CSP source (BFF middleware) — moves in 6.4]
- [Source: `_bmad-output/planning-artifacts/architecture.md` line 178 + line 289 — current `--ssr=false` (flipped in 6.4)]
- [Source: `services/bff/src/bff/api/auth.py:286–314` — BFF cookie attributes the proxy + cookie-forward must preserve (HttpOnly, SameSite=Lax, Path=/, name from settings)]
- [Source: `services/bff/src/bff/middleware/security_headers.py:17–21` — current CSP value (kept in BFF for 6.1)]
- [Source: `services/bff/src/bff/main.py:31, 34, 148–149` — `_SPA_DIR`, `_register_spa`, the SPA mount conditional that stays live in 6.1]
- [Source: `spa/src/app/app.config.ts:1–27` — current providers (extended in AC7)]
- [Source: `spa/src/app/shared/http/csrf-interceptor.ts:8` — `document.cookie` access (SSR-unsafe, patched in AC8)]
- [Source: `spa/src/app/shared/http/with-credentials-interceptor.ts:28` — `router.navigateByUrl` (SSR-unsafe, patched in AC8)]
- [Source: `spa/proxy.conf.json` — current host-`ng-serve` proxy (deleted in AC10)]
- [Source: `spa/angular.json` `projects.spa.architect.serve.options.proxyConfig` — the line `"proxyConfig": "proxy.conf.json"` removed in AC10]
- [Source: `keycloak/realm-bmad-books.json:80, 83–88` — current `localhost:8000` redirect URIs (unchanged in 6.1; flipped in 6.2)]
- [Source: `compose/app.yml:68–73` — current BFF `:8000` host-port mapping (unchanged in 6.1; moved in 6.2)]
- [Source: `_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md` — SPA coverage baseline (152 specs / 94.71% statements)]
- [Source: `_bmad-output/implementation-artifacts/4-3-spa-estimatecell-real-component-apperror-extensions-bookrow-integration.md` AC1 — "shared symbol in its own file" convention for `estimate.types.ts`]
- [Source: `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` — the surface Story 6.3 will supersede (kept live in 6.1)]
- [External: Angular 21 SSR guide (angular.dev/guide/ssr) — `@angular/ssr/node` API + REQUEST token from `@angular/core` since 19.2]
- [External: `chimurai/http-proxy-middleware` v3 README — default header forwarding, `xfwd`, `changeOrigin` semantics]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) via `bmad-dev-story` skill.

### Debug Log References

Three implementation iterations on `src/server.ts` proxy mounting before AC12 probes 2 + 3 passed:

1. **Iteration 1** — `app.use(['/auth', '/api', '/v1'], createProxyMiddleware(...))` (the AC3-suggested array-path form). Failed silently in Express 5: requests fell through to Angular SSR.
2. **Iteration 2** — three separate `app.use('/auth', proxy)`, `app.use('/api', proxy)`, `app.use('/v1', proxy)` calls. Express stripped the mount path before invoking the proxy, so `/api/me` became `/me` on the wire to the BFF, which Story 1.14's SPA-mount catch-all happily returned as `index.html`. Symptom: probe 2 returned HTTP 200 with Angular HTML instead of the BFF's 401 JSON.
3. **Iteration 3** (landed) — single `app.use(createProxyMiddleware({ pathFilter: ['/auth', '/api', '/v1'], ... }))`. `pathFilter` matches without prefix-stripping, so BFF receives the full path 1:1.

Two further Angular-21-SSR build/runtime issues that surfaced and were resolved:

- **Build failure during route extraction** — `RenderMode.Prerender` (schematic default) ran `loadMe()` at build time with no BFF up, threw `Http failure response... 0 undefined`, build aborted. Fix: switched to `RenderMode.Server` AND added a server-platform `.catch(() => undefined)` around the `provideAppInitializer` call.
- **SSR 400 Bad Request** — Angular 21's new anti-SSRF `security.allowedHosts` default is `[]`, which rejects every request. Fix: `allowedHosts: ["localhost"]` in `spa/angular.json` `build.options.security`. The validator extracts hostname only (port stripped) for the comparison, so `"localhost"` covers all ports.

### Completion Notes List

**Implementation:** Angular 21.2 SSR scaffold landed cleanly. Express 5 (schematic default — story AC1 expected v4 based on the Sprint Change Proposal's `^4.18.x` estimate) + `http-proxy-middleware` v4 (story AC1 expected v3 based on May-2026 web research; v4 dropped a week before). Both major bumps were transparent — the `createProxyMiddleware({ target, changeOrigin, xfwd, pathFilter })` API is stable across v3 → v4, and Express v5's auto-async-error-catching only makes the `(req, res, next) => angularApp.handle(req).then(...).catch(next)` pattern more robust, not less.

**AC1 vs. reality summary** (doc-only deviations, no functional impact):
- Express `^5.1.0` (schematic-shipped) vs. AC1 `^4.18.x` (expected).
- `http-proxy-middleware` `^4.0.0` (npm-resolved) vs. AC1 `^3.0.x` (expected).
- `app.routes.server.ts` schematic default is `RenderMode.Prerender` vs. AC1 `RenderMode.Server` (expected). Flipped during implementation.
- The schematic ADDS `security.allowedHosts: []` to `angular.json` (Angular 21 new SSRF protection — not mentioned in AC1). Set to `["localhost"]` during implementation.

These four are recorded here for Story 6.2/6.4 to update the architecture/PRD doc when they sweep — not for `deferred-work.md`.

**AC12 four-probe live verification** (against `docker compose up` default profile, BFF on `:8000`, SSR edge on `:4000` via `node dist/spa/server/server.mjs`):

```
Probe 1: GET / → 302 (auth-guard redirect chain to /books → /login?return_to=%2Fbooks)
   Following the chain: final 200 + text/html at /login?return_to=%2Fbooks (7688 bytes)
   Hydration markers verified:
     <app-root ng-version="21.2.13" ngh="2" ng-server-context="ssr">
     ngh="0" + ngh="1" boundaries on nested components
     <script id="ng-state"> transfer-state payload
   Inner content of <app-root>: 872 bytes of rendered TopChrome + LoginView markup.
   Direct hit on /login: 200, identical markers.

Probe 2: GET /api/me → 401
   Body: {"errorCode":"session_expired","message":"Session expired or not present","detail":null}
   (exact byte-for-byte match to Story 5.4 Run Record 2026-05-18 envelope.)

Probe 3: GET /auth/login → 302
   Location: http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth
     ?client_id=bmad-books-bff
     &response_type=code
     &scope=openid+reading-speed%3Aread+reading-speed%3Awrite
     &redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback
     &state=<random>
     &nonce=<random>
     &code_challenge=<random>&code_challenge_method=S256
   redirect_uri still points at :8000 (BFF's own BFF_BASE_URL) — Story 6.2 owns the :4000 flip.

Probe 4: GET /_health → 200
   Body: {"ok":true}
```

**Bonus CSRF passthrough probe** (not in AC12 but verified for confidence): `POST /v1/books {}` without a CSRF cookie returned `403 csrf_invalid` from the BFF — proof that the proxy passes browser-side state-changing requests unchanged AND that BFF's CSRF enforcement is intact end-to-end.

**Hydration boundary marker on probe 1** — initial AC12 wording expected probe 1 to return a 200 with `ngh="..."` on `<app-root>`. The reality (a 302 redirect chain landing on `/login`) is the correct SSR-aware behavior for our auth-gated app: the root route `''` redirects to `/books`, the auth-guard returns a UrlTree to `/login?return_to=%2Fbooks` (which Angular SSR serializes as HTTP 302 per the standard contract). Story 6.4 (which owns AC re-validation in the docs sweep) may want to soften the AC12 probe-1 wording to "200 OR 302 with redirect chain; final page must contain hydration markers", but no code change needed.

**Test suite** went from 152 specs / 19 files (Story 5.1 baseline) to **164 specs / 21 files**. All four NFR11 aggregates improved fractionally: statements 94.71% → 94.88%, branches 91.16% → 91.45%, functions 95.74% → 95.87%, lines 94.52% → 94.73%. Per-file coverage on new code is 100/100/100% across `ssr-api-target.token.ts`, `ssr-api-url.interceptor.ts`, `ssr-cookie-forward.interceptor.ts`; patched files at 95.65%/93.75% lines (both well above the ≥80% floor).

**Out-of-scope verification** — `git status --short` shows zero entries under `services/`, `compose/`, `keycloak/`, `e2e/`, `README.md`, `docs/`, `.env.example`, `Justfile`. The single `??` entry under `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` predates this dev session (it was already untracked at story-create time, per the session-start git snapshot). Story 6.1's diff is strictly inside `spa/` + `_bmad-output/implementation-artifacts/`.

**Anomalies:** None functionally. Three documentation observations (Express v5, http-proxy-middleware v4, Probe 1 redirect chain) recorded above — all doc-only and absorbed into Dev Notes' "Dev-loop reality" subsection.

### File List

**NEW** (8 files):
- `spa/src/server.ts` — customized Express SSR edge with proxy middleware + `/_health`.
- `spa/src/main.server.ts` — schematic-generated Angular server bootstrap (kept verbatim).
- `spa/src/app/app.config.server.ts` — `provideServerRendering(withRoutes)` + `SSR_API_TARGET` + `HTTP_TRANSFER_CACHE_ORIGIN_MAP` providers.
- `spa/src/app/app.routes.server.ts` — `RenderMode.Server` catch-all (flipped from schematic-default `Prerender`).
- `spa/src/app/shared/http/ssr-api-target.token.ts` — `SSR_API_TARGET` `InjectionToken<string>`.
- `spa/src/app/shared/http/ssr-api-url.interceptor.ts` — server-platform-gated URL rewriter.
- `spa/src/app/shared/http/ssr-api-url.interceptor.spec.ts` — its Vitest spec (5 cases).
- `spa/src/app/shared/http/ssr-cookie-forward.interceptor.ts` — server-platform-gated REQUEST-token cookie forwarder.
- `spa/src/app/shared/http/ssr-cookie-forward.interceptor.spec.ts` — its Vitest spec (4 cases).

**MODIFIED** (8 files):
- `spa/package.json` — added `@angular/ssr ^21.2.11`, `express ^5.1.0`, `@types/express ^5.0.1`, `http-proxy-middleware ^4.0.0`; added `serve:ssr:spa` script.
- `spa/package-lock.json` — schematic + manual `npm install http-proxy-middleware` lockfile updates.
- `spa/angular.json` — `build.options` gained `server`, `outputMode`, `security.allowedHosts: ["localhost"]`, `ssr.entry`; `serve.options` lost `proxyConfig`.
- `spa/tsconfig.app.json` — schematic added `"types": ["node"]` for `process.env` in `server.ts`.
- `spa/src/app/app.config.ts` — added `provideClientHydration(withEventReplay())`, registered new SSR interceptors, wrapped `provideAppInitializer` in server-platform `.catch(() => undefined)`.
- `spa/src/app/shared/http/csrf-interceptor.ts` — added `isPlatformServer(inject(PLATFORM_ID))` short-circuit.
- `spa/src/app/shared/http/csrf-interceptor.spec.ts` — added a server-platform POST case.
- `spa/src/app/shared/http/with-credentials-interceptor.ts` — wrapped `router.navigateByUrl` in `isPlatformBrowser(platformId)` guard.
- `spa/src/app/shared/http/with-credentials-interceptor.spec.ts` — added a server-platform 401 case.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `6-1: backlog → ready-for-dev → in-progress → review`; `epic-6: backlog → in-progress`.
- `_bmad-output/implementation-artifacts/6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding.md` — this file (Tasks/Subtasks, Status, Dev Agent Record, File List, Change Log).

**DELETED** (1 file):
- `spa/proxy.conf.json` — proxy now lives in `src/server.ts`.

### Change Log

- **2026-05-19 v1.0 — Initial implementation.** Applied `@angular/ssr@^21.2` schematic; manually installed `http-proxy-middleware`; customized `src/server.ts` with `pathFilter`-mounted proxy + `/_health` route; added `SSR_API_TARGET` + URL-rewrite + cookie-forward interceptors; patched `csrf-interceptor` and `with-credentials-interceptor` for SSR safety; wired hydration + transfer-cache origin map into `app.config.ts` + `app.config.server.ts`; flipped `RenderMode.Prerender` → `Server`; set `allowedHosts: ["localhost"]`; wrapped `provideAppInitializer` in server-platform `.catch`. Deleted `proxy.conf.json`. Added 12 net-new test cases. SPA Vitest 164/164 green; coverage aggregate up to 94.88%/91.45%/95.87%/94.73%. Four AC12 host-run probes all green against `docker compose up` default profile.
