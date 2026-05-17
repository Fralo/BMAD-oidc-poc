import { expect, test } from '@playwright/test';

import { logInAs, resetState } from '../fixtures/helpers';
import { testuser } from '../fixtures/users';

/**
 * E2E spec for journey J5 (logout and re-protection) — Story 1.13.
 *
 * Each test enters with a fresh authenticated session via `logInAs`. AC2.1
 * exercises the SPA-side logout flow (cookie clear + /login redirect +
 * protected-route re-protection). AC2.2 captures the refresh_token via
 * the test-only `GET /v1/test/session-debug` endpoint (Story 1.13 BFF
 * extension), then asserts Keycloak rejects the refresh-grant request
 * with `error=invalid_grant` — wire-level proof that BFF /auth/logout
 * actually revoked at the AS (Story 1.7).
 */

/**
 * Fail-fast on required env vars. The compose `e2e` profile already
 * fail-fasts on `BFF_CLIENT_SECRET` via `${BFF_CLIENT_SECRET:?...}`, but
 * the host-side workflow (`cd e2e && npm test` per README) has no such
 * guard — a missing var would surface as `Bearer undefined` or
 * `client_secret=undefined`, producing a misleading 401/400 from Keycloak.
 * Throw a clear, env-var-named error here so the failure points at the
 * actual cause.
 */
function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Required env var ${name} is not set. See e2e/README.md "Environment variables" for the expected values.`,
    );
  }
  return value;
}

test.describe('J5: logout and re-protection', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  test('clicking Log out terminates session and re-protects routes', async ({ page }) => {
    await page.getByRole('button', { name: 'Log out' }).click();

    // TopChrome.logout() navigates via router.navigateByUrl('/login')
    // (top-chrome.ts:56). No return_to is appended on this path.
    await page.waitForURL(/\/login$/);

    // Product name remains; identity affordances disappear.
    // `{ exact: true }` disambiguates the top-chrome brand span from the
    // LoginView heading 'Sign in to Reading Time Estimator' (added by Story 1.10).
    await expect(page.getByText('Reading Time Estimator', { exact: true })).toBeVisible();
    await expect(page.getByText(/Signed in as /)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Log out' })).toHaveCount(0);

    // BFF /auth/logout emits Set-Cookie bff_session=; Max-Age=0 — the
    // cookie should no longer be present in the browser context.
    const cookies = await page.context().cookies();
    expect(cookies.find((c) => c.name === 'bff_session')).toBeUndefined();

    // Re-protection: navigating to /books bounces back to /login with the
    // standard return_to construction.
    await page.goto('/books');
    await expect(page).toHaveURL(/\/login\?return_to=%2Fbooks/);
  });

  test('refresh token is revoked at Keycloak after logout', async ({ page, request }) => {
    // 1. Capture the refresh_token BEFORE logout via the test-only
    //    `GET /v1/test/session-debug` endpoint. The test-level `request`
    //    fixture is an **isolated** APIRequestContext (per Playwright's
    //    type doc: "Isolated APIRequestContext instance for each test")
    //    and does NOT share the browser-context cookie jar. Use
    //    `page.request` instead — that one IS bound to `page.context()`
    //    so the `bff_session` cookie set by `logInAs` is forwarded.
    const debugResp = await page.request.get('/v1/test/session-debug', {
      headers: { Authorization: `Bearer ${requireEnv('TEST_RESET_TOKEN')}` },
    });
    expect(debugResp.status()).toBe(200);
    const debugBody = (await debugResp.json()) as { refresh_token: string; sub: string };
    expect(debugBody.refresh_token).toBeTruthy();
    const capturedRefreshToken = debugBody.refresh_token;

    // 2. Click Log out and wait for the SPA to land on /login (same shape
    //    as the first J5 test).
    await page.getByRole('button', { name: 'Log out' }).click();
    await page.waitForURL(/\/login$/);

    // 3. Attempt to use the captured refresh_token directly against
    //    Keycloak's /token endpoint. Use KEYCLOAK_INTERNAL_URL (compose-
    //    network URL) because `localhost` from inside the runner
    //    container resolves to the runner itself, not Keycloak. The
    //    host-side workflow sets it to http://localhost:8080 (see README).
    //    Required, no fallback — a misconfigured runner must fail fast
    //    rather than emit a confusing DNS error mid-test.
    const keycloakUrl = requireEnv('KEYCLOAK_INTERNAL_URL');
    const tokenUrl = `${keycloakUrl}/realms/bmad-books/protocol/openid-connect/token`;
    const tokenResp = await request.post(tokenUrl, {
      form: {
        grant_type: 'refresh_token',
        refresh_token: capturedRefreshToken,
        client_id: process.env.OIDC_CLIENT_ID ?? 'bmad-books-bff',
        client_secret: requireEnv('BFF_CLIENT_SECRET'),
      },
    });

    // Keycloak returns 400 with `error=invalid_grant` for revoked /
    // expired / unknown refresh tokens (OAuth2 §5.2). The exact
    // error_description varies across Keycloak minor versions, so we
    // assert only on the stable `error` field.
    expect(tokenResp.status()).toBe(400);
    const tokenBody = (await tokenResp.json()) as { error: string };
    expect(tokenBody.error).toBe('invalid_grant');
  });
});
