import { expect, test } from '@playwright/test';

import { killRs, logInAs, resetState, startRs } from '../fixtures/helpers';
import { testuser } from '../fixtures/users';

/**
 * E2E spec for journey J6 (resource server unavailable) — Story 4.4.
 *
 * Drives the honest-failure surface across both action sites:
 *   - estimate (EstimateCell, Story 4.3) on /books while the RS is down;
 *   - settings save (SettingsPage, Story 3.5) on /settings while the RS is down.
 *
 * The RS is stopped via the host docker daemon (socket-bound `killRs` from
 * Story 3.6), then restarted in a per-test `afterEach startRs()` guard for
 * cross-test isolation — pattern copied verbatim from j4-adjust-speed.spec.ts.
 *
 * `workers: 1` (playwright.config.ts:14) is load-bearing here: the kill /
 * restart sequence fundamentally requires sequential execution because the
 * RS is a singleton in the compose stack.
 */

/**
 * Required env vars (fail-fast on missing) — mirrors j1/j2/j3/j4/j5. Story
 * 1.13 / 2.7 / 3.6 deferred extracting this shim to fixtures/helpers.ts;
 * Story 4.4 honors that decision (revisit at duplicate count >=5).
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

test.describe('J6: resource server unavailable', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  test.afterEach(async () => {
    // Defensive: a test that called killRs and threw before startRs would
    // leave the RS dead. startRs is idempotent — cheap when RS is already
    // running. Mirrors the Story 3.6 J4 pattern.
    await startRs();
  });

  test('estimate while RS is down renders the named J6 error', async ({ page }) => {
    // 1. With RS up: set speed=30, add a book.
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    await page.goto('/books');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('RS Down Target');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('400');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    // 2. Kill the RS container.
    await killRs();

    // 3. Re-navigate to /books — the books list itself comes from the BFF
    // (no RS in the path), so it remains visible. CRITICAL: assert the books
    // list re-rendered before clicking Estimate, so we know we're not asserting
    // against a transient empty state.
    await page.goto('/books');
    await expect(page.locator('app-book-row')).toHaveCount(1);

    const row = page.locator('app-book-row').first();
    await row.locator('button.estimate-cell-button--primary').click();

    // 4. Assert J6 copy in the row's estimate cell — same string used by
    // SettingsPage (Story 3.5) and EstimateCell (Story 4.3) for 503 /
    // resource_server_unavailable. Em dash is U+2014.
    await expect(row.locator('app-error-message')).toBeVisible();
    await expect(row.locator('app-error-message')).toContainText('Service unavailable — try again shortly');

    // 5. Error color check — assert via the rendered CSS color.
    // <app-error-message> emits <p class="error-message"> with
    // `color: var(--color-error)` (--color-error: #B91C1C in spa/src/styles.css).
    // Browsers compute CSS variables, so the resolved color is the rgb form.
    const colorValue = await row
      .locator('app-error-message p.error-message')
      .evaluate((el) => window.getComputedStyle(el).color);
    // #B91C1C → rgb(185, 28, 28). Some browsers emit `rgb(185, 28, 28)` and
    // some `rgb(185 28 28)` (CSS Color 4 spec). Match either.
    expect(colorValue).toMatch(/rgb\(\s*185[,\s]\s*28[,\s]\s*28\s*\)/);

    // 6. No fabricated duration anywhere in the row — UX §"Defining
    // Experience" + epic AC.
    await expect(row).not.toContainText('≈');

    // 7. Estimate button is restored beneath the error.
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimate');
  });

  test('retry succeeds after RS recovery', async ({ page }) => {
    // Setup identical to the previous test — speed=30, one book, RS down,
    // error rendered.
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    await page.goto('/books');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('Retry After Recovery');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('300');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    await killRs();
    await page.goto('/books');
    await expect(page.locator('app-book-row')).toHaveCount(1);

    const row = page.locator('app-book-row').first();
    await row.locator('button.estimate-cell-button--primary').click();
    await expect(row.locator('app-error-message')).toContainText('Service unavailable — try again shortly');
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimate');

    // Recover: startRs() waits for the RS /health to report 200
    // (waitForRsHealthy polls docker inspect for healthy status — see
    // e2e/fixtures/services.ts).
    await startRs();

    // Click Estimate again. The SPA does NOT silently retry — the user
    // re-clicks. This proves architecture §"Retry & failure":
    // "User retries by clicking the action again. The BFF does not silently
    // retry; it does not fabricate a result. The SPA does not auto-poll."
    await row.locator('button.estimate-cell-button--primary').click();
    await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
    await expect(row.locator('.estimate-cell-result')).toHaveText(/≈\s*[1-9]\d*\s*[hm]/);
    await expect(row.locator('app-error-message')).toHaveCount(0);
  });

  test('settings save while RS is down also renders the named J6 error', async ({ page }) => {
    await killRs();

    await page.goto('/settings');

    // The 503 may surface from BOTH the initial GET /v1/reading-speed
    // (load-error) AND the subsequent PUT (save-error). Both produce
    // the same UX-DR12 copy via SettingsPage's
    // loadErrorMessage / saveErrorMessage computed signals (Story 3.5).
    //
    // The input is NOT disabled even after the 503 load-error, per Story 3.5
    // SettingsPage: finally{} sets loading.set(false) regardless of outcome.
    // We can type and click freely.
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();

    // Use .first() because there may be two <app-error-message> elements
    // with the same copy (one for loadError, one for saveError) on the page
    // momentarily. .first() resolves to either — toBeVisible passes when at
    // least one matches. Identical to the j4-adjust-speed.spec.ts pattern.
    await expect(
      page.getByText('Service unavailable — try again shortly').first(),
    ).toBeVisible();
  });
});
