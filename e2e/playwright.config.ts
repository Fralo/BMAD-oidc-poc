import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the Reading Time Estimator E2E harness (Story 1.11).
 *
 * `workers: 1` is LOAD-BEARING: every spec calls `resetState(request, { resetToken })`
 * in a `beforeEach` (per Story 1.13 onward). Parallel workers would have two specs
 * simultaneously truncating + re-seeding the BFF's sessions/auth_states tables,
 * producing nondeterministic interleavings. Do NOT raise this without first
 * redesigning the test-reset contract.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
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
          // KC_HOSTNAME=localhost + BFF's registered redirect_uri
          // (http://localhost:8000/auth/callback) mean both the OIDC
          // authorize redirect AND the post-auth callback point at
          // `localhost`. Inside the playwright container, `localhost` is
          // the runner's own loopback (Chromium hardcodes localhost →
          // 127.0.0.1 and ignores /etc/hosts). Remap both endpoints to
          // their compose-DNS names so the browser reaches them via the
          // compose network without changing OIDC_AUTHORIZE_URL_BROWSER
          // (which would break the BFF's iss check against KC_HOSTNAME)
          // or the BFF's registered redirect_uri (which would invalidate
          // Keycloak's redirect_uri validation).
          args: [
            '--host-resolver-rules=MAP localhost:8080 keycloak:8080, MAP localhost:8000 bff:8000',
          ],
        },
      },
    },
  ],
});
