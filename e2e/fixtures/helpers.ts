import { APIRequestContext, Page, expect } from '@playwright/test';
import { SeededUser } from './users';

/**
 * Drives the SPA + Keycloak through the J1 login round-trip.
 *
 * Precondition: the BFF and Keycloak are reachable at `baseURL` and the
 * SPA's `LoginView` (Story 1.10) and `TopChrome` (Story 1.10) are
 * rendered. The user must already be seeded in the realm
 * (see `keycloak/realm-bmad-books.json`).
 */
export async function logInAs(page: Page, user: SeededUser): Promise<void> {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
  await page.locator('input[name="username"]').fill(user.username);
  await page.locator('input[name="password"]').fill(user.password);
  await page.locator('button[type="submit"], input[type="submit"]').first().click();
  await page.waitForURL(/\/books$/);
  // TopChrome identity block — selector matches `Signed in as <username>` per UX-DR2 (Story 1.10).
  await expect(page.getByText(`Signed in as ${user.username}`)).toBeVisible();
}

/**
 * Truncates the BFF's auth-related tables via the test-reset endpoint
 * (Story 1.12). Story 3.4 extends this helper to also hit the RS-side
 * `/v1/test/reset` (reading_speeds). The `opts` parameter shape is forward-
 * compatible: extra fields may be added in Story 3.4 without breaking
 * existing call sites that pass only `{ resetToken }`.
 */
export async function resetState(
  request: APIRequestContext,
  opts: { resetToken: string },
): Promise<void> {
  const response = await request.post('/v1/test/reset', {
    headers: { Authorization: `Bearer ${opts.resetToken}` },
  });
  if (response.status() !== 204) {
    const body = await response.text();
    throw new Error(
      `resetState: expected HTTP 204 from POST /v1/test/reset, got ${response.status()}. Body: ${body}`,
    );
  }
}

/**
 * Placeholder — will be implemented in Story 3.6 once the Resource Server
 * exists and the e2e compose profile knows how to stop/start it.
 */
export function killRs(): never {
  throw new Error('RS not yet present (Epic 3)');
}

/**
 * Placeholder — see `killRs`.
 */
export function startRs(): never {
  throw new Error('RS not yet present (Epic 3)');
}
