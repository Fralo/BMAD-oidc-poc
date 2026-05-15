import { expect, test } from '@playwright/test';

import { logInAs, resetState } from '../fixtures/helpers';
import { testuser } from '../fixtures/users';

/**
 * E2E spec for journey J1 (first-time login) — Story 1.13.
 *
 * Drives the real Keycloak OAuth round-trip from the SPA's `LoginView`
 * (Story 1.10) through the BFF's cookie-session OIDC plugin (Story 1.5),
 * back to the SPA's `/books` placeholder. Every test starts with the
 * BFF's auth tables truncated via the test-reset endpoint (Story 1.12)
 * so the OAuth code/state pair issued by Keycloak has nowhere to collide.
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

  test('unauthenticated user navigating to / is redirected to /login', async ({ page }) => {
    await page.goto('/');

    // The route table maps `/` → `redirectTo: 'books'` (Story 1.10 /
    // app.routes.ts:7), then `authGuard` builds /login?return_to=<state.url>
    // (auth-guard.ts:20) on the 401 from /api/me. state.url is /books at
    // that point, so the encoded query string is ?return_to=%2Fbooks.
    // Accept both `/login` and `/login?return_to=...` to keep this AC
    // resilient to future redirect-chain refactors.
    await expect(page).toHaveURL(/\/login(\?|$)/);

    await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible();
    // Identity block must NOT be present in TopChrome when unauthenticated.
    await expect(page.getByText(/Signed in as /)).toHaveCount(0);
  });

  test('clicking Log in completes the OAuth round-trip and returns the user to /books', async ({
    page,
  }) => {
    await page.goto('/login');

    // inline form fill — exercises the assertions logInAs hides
    await page.getByRole('button', { name: 'Log in' }).click();
    await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
    await page.locator('input[name="username"]').fill(testuser.username);
    await page.locator('input[name="password"]').fill(testuser.password);
    await page.locator('button[type="submit"], input[type="submit"]').first().click();
    await page.waitForURL(/\/books$/);

    await expect(page.getByText(`Signed in as ${testuser.username}`)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
    // Books placeholder copy is the literal string from Story 1.10
    // (spa/src/app/books/books-page-placeholder.ts:5).
    await expect(page.getByText('Books — coming in Epic 2')).toBeVisible();
  });

  test('protected route while unauthenticated redirects with return_to and returns user after login', async ({
    page,
  }) => {
    await page.goto('/books');
    // `authGuard` builds /login?return_to=${encodeURIComponent('/books')} —
    // encoded path is %2Fbooks (auth-guard.ts:20).
    await expect(page).toHaveURL(/\/login\?return_to=%2Fbooks/);

    await logInAs(page, testuser);

    // `redirectIfAuthedGuard` (Story 1.10) bounces the now-authed visitor
    // from /login to /books — same destination the user originally asked
    // for, so the return_to is functionally honored even though the SPA
    // does not consume it through the LoginView path.
    await expect(page).toHaveURL(/\/books$/);
  });
});
