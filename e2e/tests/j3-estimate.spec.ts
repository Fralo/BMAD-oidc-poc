import { expect, test } from '@playwright/test';

import { logInAs, resetState } from '../fixtures/helpers';
import { freshuser, testuser } from '../fixtures/users';

/**
 * E2E spec for journey J3 (reading-time estimate) — Story 4.4.
 *
 * Drives the EstimateCell (Story 4.3) + BFF POST /v1/books/{id}/estimate
 * (Story 4.2) + RS POST /v1/estimate (Story 4.1) end-to-end against the
 * real running stack. Each test starts with `resetState` truncating BFF
 * auth/books tables AND RS `reading_speeds` so users start from a known
 * state.
 *
 * No RS kill/restart is performed in this spec — the generic-failure test
 * uses `page.route` to inject a deterministic 500 envelope while the RS
 * stays up. The RS-down branch lives in `j6-rs-unavailable.spec.ts`.
 */

/**
 * Required env vars (fail-fast on missing) — mirrors j1/j2/j4/j5. Story
 * 1.13 / 2.7 / 3.6 deferred extracting this shim to fixtures/helpers.ts
 * (revisit at duplicate count >=5). Story 4.4 brings the count to 4 — not
 * yet.
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

/**
 * Parse a formatted duration string like "≈ 4 h 20 m" / "≈ 1 d 22 h 20 m" /
 * "≈ 12 m" back to total minutes. Pure spec helper — invariant: should
 * round-trip every output of `format_duration` (services/resource-server/
 * src/resource_server/services/duration.py). Local to this spec file
 * (NOT exported to `fixtures/`) per Story 4.4 scope.
 */
function impliedMinutes(formatted: string): number {
  // Strip leading "≈ " (U+2248 ALMOST EQUAL TO + ASCII space).
  const body = formatted.replace(/^≈\s+/, '').trim();
  let minutes = 0;
  // Match "<n> d", "<n> h", "<n> m" segments — order is d → h → m per
  // duration.py's parts.append loop.
  const days = body.match(/(\d+)\s*d/);
  const hours = body.match(/(\d+)\s*h/);
  const mins = body.match(/(\d+)\s*m/);
  if (days) minutes += parseInt(days[1], 10) * 24 * 60;
  if (hours) minutes += parseInt(hours[1], 10) * 60;
  if (mins) minutes += parseInt(mins[1], 10);
  return minutes;
}

test.describe('J3: reading-time estimate', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  test('estimate happy path with default speed', async ({ page }) => {
    // 1. Set reading speed = 30 (testuser starts fresh — resetState truncated reading_speeds).
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    // 2. Add a book with pages=600 — yields minutes=1200 ("≈ 20 h") at speed=30.
    await page.goto('/books');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('Estimate Target');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('600');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    // 3. Click Estimate; assert observable loading state THEN the formatted result.
    //
    // AC2-alt — hold the POST open. The natural-speed round-trip resolves
    // sub-100ms in the compose `e2e` profile, faster than Playwright's
    // expect poll cycle can catch the intermediate "Estimating…" state.
    // Holding the response via `page.route` deterministically renders the
    // loading branch (mirrors the optimistic-UI hold pattern from
    // j2-manage-books.spec.ts:128-139). Story 4.4 dev note: AC2-alt
    // applied (loading-state observability was flaky on the natural-speed
    // path in CI / local docker desktop).
    let estimateResolveDeferred!: () => void;
    const estimateHeld = new Promise<void>((resolve) => {
      estimateResolveDeferred = resolve;
    });
    await page.route('**/v1/books/*/estimate', async (route) => {
      if (route.request().method() === 'POST') {
        await estimateHeld;
        await route.continue();
      } else {
        await route.continue();
      }
    });

    const row = page.locator('app-book-row').first();
    const estimateBtn = row.locator('button.estimate-cell-button--primary');
    await expect(estimateBtn).toHaveText('Estimate');
    await estimateBtn.click();

    // Loading state — button disabled with U+2026 ellipsis label.
    // Pessimistic UI per UX-DR13: between click and round-trip completion,
    // the button is observably disabled with the "Estimating…" label.
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimating…');
    await expect(row.locator('button.estimate-cell-button--primary')).toBeDisabled();

    // Release the POST and wait for the BFF to acknowledge it.
    estimateResolveDeferred();
    await page.waitForResponse(
      (resp) =>
        resp.url().endsWith('/estimate') &&
        resp.request().method() === 'POST' &&
        resp.status() === 200,
    );
    await page.unroute('**/v1/books/*/estimate');

    // Success state — formatted duration rendered verbatim from RS.
    // The regex is loose to absorb any future tweak to the `format_duration`
    // rounding (e.g., a future revisit of the include-minutes-when-days
    // branch in `duration.py`). The leading [1-9] rejects "≈ 0 m" — a
    // fabricated-zero output would violate the "no invented number" rule.
    await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
    await expect(row.locator('.estimate-cell-result')).toHaveText(/≈\s*[1-9]\d*\s*[hm]/);

    // Re-estimate affordance is visible; Estimate button is gone.
    await expect(row.locator('button.estimate-cell-reestimate')).toHaveText('Re-estimate');
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveCount(0);
  });

  test('speed change yields different estimate (J4↔J3 coupling)', async ({ page }) => {
    // Seed speed=30 + pages=600 → first estimate (≈ 20 h).
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    await page.goto('/books');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('Speed Coupling');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('600');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    const row = page.locator('app-book-row').first();
    await row.locator('button.estimate-cell-button--primary').click();
    await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
    const r1 = await row.locator('.estimate-cell-result').textContent();
    expect(r1).toBeTruthy();

    // Change speed to 60 → expected new estimate ≈ 10 h.
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('60');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    // Re-estimate the same book. Note: navigating away from /books to
    // /settings and back DESTROYS the EstimateCell component instance —
    // its local `loading` / `result` / `error` signals reset, so the cell
    // is back to its IDLE state on return (Estimate button, no Re-estimate
    // button). The intent of this test is the speed-coupling rule, not the
    // Re-estimate button specifically (that's pinned in the re-estimate
    // in-place test below). Click the now-idle Estimate button instead.
    await page.goto('/books');
    await expect(page.locator('app-book-row')).toHaveCount(1);
    await row.locator('button.estimate-cell-button--primary').click();
    await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
    const r2 = await row.locator('.estimate-cell-result').textContent();
    expect(r2).toBeTruthy();

    // Positive guards: if `format_duration` ever regresses to a shape
    // `impliedMinutes` cannot parse, BOTH sides resolve to 0 and the
    // strict-inequality below evaluates `0 < 0 = false` with an opaque
    // message. Surface parse failure as "expected > 0, got 0" instead.
    expect(impliedMinutes(r1!)).toBeGreaterThan(0);
    expect(impliedMinutes(r2!)).toBeGreaterThan(0);

    // r1 !== r2 (strings differ) AND r2's implied minutes strictly less than r1's.
    expect(r2).not.toBe(r1);
    expect(impliedMinutes(r2!)).toBeLessThan(impliedMinutes(r1!));
  });

  test('freshuser sees the 412 precondition with a link to Settings', async ({
    page,
    request,
    context,
  }) => {
    // Override the testuser login from beforeEach — same pattern as
    // j4-adjust-speed.spec.ts AC10 (resetState + clearCookies + logInAs).
    // Deterministic; doesn't rely on the auth interceptor cleaning up a
    // stale session cookie under slow CI.
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await context.clearCookies();
    await logInAs(page, freshuser);

    // Add a book — freshuser has NO reading_speed row, so the next estimate
    // request will resolve to BFF 412 reading_speed_unset.
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('Freshuser Book');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('200');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    const row = page.locator('app-book-row').first();
    await row.locator('button.estimate-cell-button--primary').click();

    // Inline error message visible — literal copy from
    // ESTIMATE_CELL_PRECONDITION_PREFIX/SUFFIX (estimate-cell.ts:29-32) +
    // estimate-cell.html lines 21-25. The `Settings` link is an embedded
    // <a routerLink="/settings"> — assert the link is present AND clickable.
    const errorMsg = row.locator('.estimate-cell-error');
    await expect(errorMsg).toBeVisible();
    await expect(errorMsg).toContainText('Set your reading speed in');
    await expect(errorMsg).toContainText('to enable estimates');

    const settingsLink = row.locator('a.estimate-cell-error-link');
    await expect(settingsLink).toHaveText('Settings');
    // Angular's RouterLink renders an <a href="..."> attribute even when
    // routing is intercepted client-side; assert the href ends with /settings.
    await expect(settingsLink).toHaveAttribute('href', /\/settings$/);

    // Estimate button is restored beneath the error so the user can retry
    // after visiting Settings (UX-DR8 + estimate-cell.html:30-36).
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimate');

    // Click the link, assert navigation to /settings.
    await settingsLink.click();
    await expect(page).toHaveURL(/\/settings$/);
  });

  test('re-estimate replaces value in-place without navigation', async ({ page }) => {
    // Setup: speed=30, pages=300 → first estimate.
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    await page.goto('/books');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('Re-estimate Target');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('300');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    const row = page.locator('app-book-row').first();
    await row.locator('button.estimate-cell-button--primary').click();
    await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
    const urlBefore = page.url();
    const firstResult = await row.locator('.estimate-cell-result').textContent();

    // Click Re-estimate; capture URL again immediately + the new result.
    await row.locator('button.estimate-cell-reestimate').click();
    // The mid-flight pessimistic-UI state clears the previous result
    // (onEstimateClick: this.result.set(null) at estimate-cell.ts:95).
    // We assert URL invariance during BOTH the loading and the post-flush
    // windows — the URL must never change because the operation is purely
    // an in-place mutation of the row's cell.
    expect(page.url()).toBe(urlBefore);

    await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
    const secondResult = await row.locator('.estimate-cell-result').textContent();
    expect(page.url()).toBe(urlBefore);

    // The cell stays in re-estimate mode after the second flush: the
    // Re-estimate affordance is still rendered and the primary Estimate
    // button is gone. Catches a regression where the cell silently falls
    // back to its initial idle state after Re-estimate completes.
    await expect(row.locator('button.estimate-cell-reestimate')).toHaveText('Re-estimate');
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveCount(0);

    // The strings are EQUAL because nothing changed between the two requests
    // (same speed, same pages). The point of the test is the no-navigation
    // invariant, NOT the value difference (the speed-coupling test already
    // covers that). Pin the equality explicitly to document the intent.
    expect(secondResult).toBe(firstResult);
  });

  test('generic non-J6 failure renders the generic copy', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();
    await expect(page.locator('button.settings-save')).toHaveText('Saved', { timeout: 2000 });

    await page.goto('/books');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="title"]').fill('Generic Failure');
    await page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]').fill('100');
    await page.getByRole('button', { name: 'Add book' }).click();
    await expect(page.locator('app-book-row')).toHaveCount(1);

    // Register a route handler BEFORE clicking. The glob matches the BFF's
    // POST /v1/books/{id}/estimate (any numeric id). Return a 500 with the
    // ErrorCode.unknown envelope — ErrorService.parse maps this to
    // {kind: 'unknown'} which the exhaustive switch in EstimateCell maps
    // to ESTIMATE_CELL_GENERIC_COPY ("Couldn’t get an estimate — try again").
    await page.route('**/v1/books/*/estimate', (route) =>
      route.fulfill({
        status: 500,
        body: JSON.stringify({ errorCode: 'unknown', message: 'boom' }),
        contentType: 'application/json',
      }),
    );

    const row = page.locator('app-book-row').first();
    await row.locator('button.estimate-cell-button--primary').click();

    // Generic copy from estimate-cell.ts:ESTIMATE_CELL_GENERIC_COPY. The
    // apostrophe is U+2019 RIGHT SINGLE QUOTATION MARK ("Couldn’t"). Pin
    // the curly form strictly: a regression of the source constant to a
    // straight ASCII apostrophe (U+0027) MUST fail the test rather than
    // silently match a tolerant pattern.
    await expect(row.locator('app-error-message')).toBeVisible();
    await expect(row.locator('app-error-message')).toContainText('Couldn’t get an estimate — try again');

    // J6 copy MUST NOT appear — ESTIMATE_CELL_J6_COPY is reserved for
    // {kind: 'resource_server_unavailable'}. This pins the rule that the
    // generic copy applies to any non-503 5xx envelope.
    await expect(page.getByText('Service unavailable — try again shortly')).toHaveCount(0);

    // No fabricated duration — the ≈ glyph must not appear anywhere in the row.
    await expect(row).not.toContainText('≈');

    // Estimate button is restored beneath the error.
    await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimate');

    // Unroute so subsequent tests don't inherit the mock.
    await page.unroute('**/v1/books/*/estimate');
  });
});
