import { expect, test } from '@playwright/test';

import { logInAs, resetState } from '../fixtures/helpers';
import { testuser } from '../fixtures/users';

/**
 * E2E spec for journey J1 (first-time login) — Story 1.13.
 *
 * Story 7.4 removed the in-app `LoginView`: anonymous traffic now lands
 * directly on Keycloak via the auth guard's redirect to `/auth/login`.
 * The BFF's cookie-session OIDC plugin (Story 1.5) handles the OAuth
 * round-trip and lands the user back on `/books`. Every test starts with
 * the BFF's auth tables truncated via the test-reset endpoint
 * (Story 1.12) so the OAuth code/state pair issued by Keycloak has
 * nowhere to collide.
 */
/**
 * Required env vars (fail-fast on missing). The compose `e2e` profile
 * fail-fasts on `TEST_RESET_TOKEN` via `${TEST_RESET_TOKEN:?...}`, but
 * the host-side workflow (per `e2e/README.md`) has no such guard — a
 * missing var would surface as `Bearer undefined`, producing a
 * misleading 401 from the BFF. Throw a clear, env-var-named error.
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

test.describe('J1: first-time login', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
  });

  test('unauthenticated user navigating to / is redirected to Keycloak', async ({ page }) => {
    // Story 7.4: the auth guard (`CanMatch`) sees no session, mutates the
    // SSR RESPONSE_INIT to 302 → /auth/login?return_to=%2F (or %2Fbooks
    // for any protected route). The BFF /auth/login endpoint then
    // immediately redirects to Keycloak's OIDC auth endpoint. We assert
    // we end up on Keycloak rather than poking the intermediate hop.
    await page.goto('/');
    await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
    // No identity block on Keycloak — the SPA chrome isn't rendered here.
    await expect(page.getByText(/Signed in as /)).toHaveCount(0);
  });

  test('completing the OAuth round-trip returns the user to /books', async ({ page }) => {
    await page.goto('/books');
    // Auth guard redirects to /auth/login → BFF redirects to Keycloak.
    await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
    await page.locator('input[name="username"]').fill(testuser.username);
    await page.locator('input[name="password"]').fill(testuser.password);
    await page.locator('button[type="submit"], input[type="submit"]').first().click();
    await page.waitForURL(/\/books$/);

    await expect(page.getByText(`Signed in as ${testuser.username}`)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Books' })).toBeVisible();
  });

  test('deep-link to a protected route while unauthenticated still returns user to /books after login', async ({
    page,
  }) => {
    // Story 7.4: the auth guard builds `return_to` from the requested
    // segments, so a deep-link to /books winds through Keycloak and back
    // to /books. The BFF's `/auth/callback` reads return_to from the
    // signed auth_state row (Story 1.5) and Location-redirects there.
    await logInAs(page, testuser);
    await expect(page).toHaveURL(/\/books$/);
  });
});
