import { expect, test } from '@playwright/test';

import { logInAs, resetState } from '../fixtures/helpers';
import { testuser } from '../fixtures/users';

/**
 * E2E spec for journey J5 (logout and re-protection) — Story 1.13.
 *
 * Each test enters with a fresh authenticated session via `logInAs`.
 * AC2.1 exercises the SPA-side logout flow: the SPA clears local state,
 * does a full-page nav to `/` (Story 7.4), and the auth guard then
 * either bounces the user back to Keycloak (SSO cleared) or silently
 * re-authenticates. The cookie clear + protected-route re-protection
 * assertion is the durable contract.
 *
 * AC2.2 captures the refresh_token via the test-only
 * `GET /v1/test/session-debug` endpoint (Story 1.13 BFF extension),
 * then asserts Keycloak rejects the refresh-grant request with
 * `error=invalid_grant` — wire-level proof that BFF /auth/logout
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

  test('clicking Log out terminates the local session and re-protects routes', async ({ page }) => {
    await page.getByRole('button', { name: 'Log out' }).click();

    // Story 7.4: TopChrome.logout() POSTs /auth/logout then sets
    // window.location.href = '/'. The auth guard re-evaluates and either
    // redirects to Keycloak (SSO cleared) or silently re-authenticates.
    // The durable assertion: the SPA chrome no longer renders an identity
    // block (we may end up on Keycloak's login form, where the SPA chrome
    // isn't rendered at all).
    await expect(page.getByText(/Signed in as /)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Log out' })).toHaveCount(0);

    // BFF /auth/logout emits Set-Cookie bff_session=; Max-Age=0 — the
    // cookie should no longer be present in the browser context.
    const cookies = await page.context().cookies();
    expect(cookies.find((c) => c.name === 'bff_session')).toBeUndefined();

    // Re-protection: navigating to /books bounces back to Keycloak with
    // the auth guard's return_to. We don't assert the intermediate
    // /auth/login hop because the BFF immediately follows it with a 302
    // to Keycloak.
    await page.goto('/books');
    await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
  });

  test('refresh token is revoked at Keycloak after logout', async ({ page, request }) => {
    // 1. Capture the refresh_token BEFORE logout via the test-only
    //    `GET /v1/test/session-debug` endpoint. Both Playwright `request`
    //    fixtures (test-level and `page.request`) use Node networking, not
    //    Chromium — Node does not honor the chromium `--host-resolver-rules`
    //    (e2e/playwright.config.ts) that route `localhost:4000` → `spa:4000`;
    //    inside the compose runner Node resolves `localhost:4000` to its own
    //    loopback (the SPA edge is on the compose network). Issue the fetch
    //    from inside the page instead — the browser DOES honor resolver-rules AND auto-attaches
    //    the same-origin `bff_session` cookie.
    const captured = await page.evaluate(async (token: string) => {
      const resp = await fetch('/v1/test/session-debug', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const body = (await resp.json()) as { refresh_token?: string };
      return { status: resp.status, refresh_token: body.refresh_token ?? '' };
    }, requireEnv('TEST_RESET_TOKEN'));
    expect(captured.status).toBe(200);
    expect(captured.refresh_token).toBeTruthy();
    const capturedRefreshToken = captured.refresh_token;

    // 2. Click Log out and wait for the SPA's identity block to clear.
    //    Story 7.4: post-logout lands either on Keycloak (SSO cleared) or
    //    /books (silent re-auth); the durable signal is "Signed in as"
    //    disappearing from the chrome.
    await page.getByRole('button', { name: 'Log out' }).click();
    await expect(page.getByText(/Signed in as /)).toHaveCount(0);

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
