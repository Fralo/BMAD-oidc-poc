import { APIRequestContext, Page, expect } from '@playwright/test';

import {
  isRsRunning,
  startRs as startRsService,
  stopRs,
  waitForRsHealthy,
} from './services';
import { SeededUser } from './users';

/**
 * Drives the SPA + Keycloak through the J1 login round-trip.
 *
 * Story 7.4 removed the in-app `/login` view: navigating to any protected
 * route while anonymous now triggers the auth guard to redirect straight
 * to the BFF's `/auth/login` (Keycloak). This helper hits `/books` and
 * follows the redirect chain into the Keycloak login form.
 *
 * Precondition: the BFF and Keycloak are reachable at `baseURL`. The user
 * must already be seeded in the realm (see `keycloak/realm-bmad-books.json`).
 */
export async function logInAs(page: Page, user: SeededUser): Promise<void> {
  await page.goto('/books');
  await page.waitForURL(/\/realms\/bmad-books\/protocol\/openid-connect\/auth/);
  await page.locator('input[name="username"]').fill(user.username);
  await page.locator('input[name="password"]').fill(user.password);
  await page.locator('button[type="submit"], input[type="submit"]').first().click();
  await page.waitForURL(/\/books$/);
  // TopChrome identity block — selector matches `Signed in as <username>` per UX-DR2 (Story 1.10).
  await expect(page.getByText(`Signed in as ${user.username}`)).toBeVisible();
}

/**
 * Truncates auth-related tables on both the BFF (Story 1.12 — books,
 * sessions, auth_states) and the RS (Story 3.4 — reading_speeds) via
 * their respective test-reset endpoints. Story 3.6 wired the RS side in.
 *
 * The `opts` parameter shape is forward-compatible: extra fields may be
 * added without breaking existing call sites that pass only
 * `{ resetToken }`. The bearer token is shared across both services per
 * architecture.md §"Operational Details" line 1359.
 *
 * The compose runner reaches the RS at `http://resource-server:8000`;
 * for host-side workflows the RS has no published port (see
 * `e2e/README.md` "RS killswitch (J4 + J6)") — override with
 * `RS_BASE_URL` if needed, otherwise the helper throws clearly when the
 * RS POST fails.
 */
export async function resetState(
  request: APIRequestContext,
  opts: { resetToken: string },
): Promise<void> {
  // BFF reset — truncates books, sessions, auth_states (Story 1.12 / 2.3).
  //
  // The Playwright `request` fixture uses Node's networking, not Chromium's;
  // it does NOT honor the chromium `--host-resolver-rules` that remap
  // `localhost:4000` → `spa:4000` for browser navigation. Inside the compose
  // runner, Node resolves `localhost:4000` to its own loopback — the SPA edge
  // is on the compose network, not the runner's loopback. Setting
  // `BFF_BASE_URL=http://bff:8000` on the playwright service routes the
  // reset directly through compose DNS, bypassing the SPA proxy. Host-side
  // workflows leave it unset → the helper falls back to the request's
  // baseURL (typically `http://localhost:4000` per playwright.config.ts,
  // which would route the POST via the SPA edge proxy).
  const bffBaseUrl = process.env.BFF_BASE_URL ?? '';
  const bffResp = await request.post(`${bffBaseUrl}/v1/test/reset`, {
    headers: { Authorization: `Bearer ${opts.resetToken}` },
  });
  if (bffResp.status() !== 204) {
    const body = await bffResp.text();
    throw new Error(
      `resetState: BFF expected HTTP 204 from POST ${bffBaseUrl}/v1/test/reset, got ${bffResp.status()}. Body: ${body}`,
    );
  }

  // RS reset — truncates reading_speeds (Story 3.4). Story 3.6 wires this in.
  // Compose runner reaches RS at http://resource-server:8000; host-side
  // workflow targets the RS's published port (set RS_BASE_URL accordingly).
  const rsBaseUrl = process.env.RS_BASE_URL ?? 'http://resource-server:8000';
  const rsResp = await request.post(`${rsBaseUrl}/v1/test/reset`, {
    headers: { Authorization: `Bearer ${opts.resetToken}` },
  });
  if (rsResp.status() !== 204) {
    const body = await rsResp.text();
    throw new Error(
      `resetState: RS expected HTTP 204 from POST ${rsBaseUrl}/v1/test/reset, got ${rsResp.status()}. Body: ${body}`,
    );
  }
}

/**
 * Drives the SPA-side logout flow from any page where the authenticated
 * TopChrome is rendered (e.g., /books). Clicks the `Log out` button, then
 * waits for the identity block to disappear. Post-logout the SPA does a
 * full-page navigation to `/`, where the auth guard either bounces back
 * to Keycloak (if Keycloak SSO cleared) or silently re-authenticates and
 * lands on `/books` (Story 7.4 accepts either outcome).
 *
 * Counterpart to `logInAs`. Used by the J2 spec's cross-user isolation
 * case (Story 2.7) and by any future spec that needs a mid-test user
 * swap.
 */
export async function logOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Log out' }).click();
  await expect(page.getByText(/Signed in as /)).toHaveCount(0);
}

/**
 * Stops the resource-server container via the host docker daemon
 * (socket-bound). Idempotent: if the container is already stopped, no-op.
 *
 * Used by J4's "RS down" tests (Story 3.6) and J6 (Story 4.4).
 */
export async function killRs(): Promise<void> {
  if (!(await isRsRunning())) return;
  await stopRs();
}

/**
 * Starts the resource-server container and waits for its /health probe to
 * report 200. Idempotent: if the container is already running, just waits
 * for healthy (cheap if already there) and returns.
 *
 * The J4 spec uses this in an `afterEach` to guard against a previous test
 * having left the RS stopped.
 */
export async function startRs(): Promise<void> {
  if (!(await isRsRunning())) {
    await startRsService();
  }
  await waitForRsHealthy();
}
