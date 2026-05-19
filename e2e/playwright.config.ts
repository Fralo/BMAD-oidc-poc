import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the Reading Time Estimator E2E harness (Story 1.11;
 * routing flipped to the SPA SSR edge in Story 6.4 / Epic 6 close).
 *
 * `workers: 1` is LOAD-BEARING: every spec calls `resetState(request, { resetToken })`
 * in a `beforeEach` (per Story 1.13 onward). Parallel workers would have two specs
 * simultaneously truncating + re-seeding the BFF's sessions/auth_states tables,
 * producing nondeterministic interleavings. Do NOT raise this without first
 * redesigning the test-reset contract.
 *
 * Post-Epic-6 routing (Story 6.4):
 *   The browser-facing origin is the SPA SSR edge on host `:4000`
 *   (compose service `spa`). The SPA SSR Express server reverse-proxies
 *   `/auth/* /api/* /v1/*` to the BFF over compose DNS via
 *   `http-proxy-middleware`; the BFF no longer publishes a host port
 *   (Story 6.2 dropped it). Keycloak's registered redirect_uri for the
 *   `bmad-books-bff` client is now `http://localhost:${SPA_HOST_PORT:-4000}/auth/callback`
 *   (Story 6.2 realm flip), so the post-auth callback also lands at `:4000`.
 *
 *   Inside the playwright container, `localhost` is the runner's own loopback
 *   (Chromium hardcodes localhost → 127.0.0.1 and ignores /etc/hosts). Remap
 *   the SPA-edge host (`:4000`) and the Keycloak authorize host (`:8080`) to
 *   their compose-DNS names so the browser reaches them via the compose
 *   network without changing OIDC_AUTHORIZE_URL_BROWSER (which would break
 *   the BFF's iss check against KC_HOSTNAME) or Keycloak's registered
 *   redirect_uri host (which would invalidate Keycloak's redirect_uri check).
 *   The BFF is internal-only on the compose network — the browser never
 *   needs to resolve `localhost:8000`, and the back-channel `resetState`
 *   helper uses Playwright's Node-side `request` fixture with
 *   `BFF_BASE_URL=http://bff:8000` (which does NOT honor `--host-resolver-rules`).
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:4000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--host-resolver-rules=MAP localhost:8080 keycloak:8080, MAP localhost:4000 spa:4000',
          ],
        },
      },
    },
  ],
});
