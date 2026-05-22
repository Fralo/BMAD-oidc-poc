import { expect, test } from '@playwright/test';

import { killRs, logInAs, resetState, startRs } from '../fixtures/helpers';
import { freshuser, testuser } from '../fixtures/users';

/**
 * E2E spec for journey J4 (adjust reading speed) — Story 3.6.
 *
 * Drives the SettingsPage (Story 3.5) + the BFF `/v1/reading-speed`
 * proxy (Story 3.5) + the RS `/v1/reading-speed` endpoints (Story 3.3)
 * end-to-end against the real running stack. Each test starts with
 * `resetState` truncating BFF auth tables AND RS `reading_speeds` so
 * `freshuser`/`testuser` start from a known state.
 *
 * The "RS down" tests use `killRs` / `startRs` (Story 3.6 helpers) to
 * stop and restart the RS container via the host docker daemon
 * (socket-bound, see `compose/app.yml`).
 */

/**
 * Required env vars (fail-fast on missing) — mirrors j1/j5.
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

test.describe('J4: adjust reading speed', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  test.afterEach(async () => {
    // Defensive: a test that called killRs and threw before startRs would
    // leave the RS dead. startRs is idempotent — cheap when RS is already
    // running.
    await startRs();
  });

  test('freshuser sees the unset state on first /settings visit', async ({
    page,
    request,
    context,
  }) => {
    // Override the default testuser login from beforeEach. Order matters:
    //   1. resetState — truncates BFF sessions/auth_states + RS reading_speeds.
    //   2. context.clearCookies() — drops the testuser bff_session cookie that
    //      the beforeEach just set. Without this, the next logInAs call
    //      runs with a stale cookie that points to a now-deleted DB row;
    //      authGuard's /api/me call gets 401, the interceptor clears the
    //      cookie and redirects to /auth/login — works through the chain, but
    //      flakes under slow CI conditions. Clearing up front is deterministic.
    //   3. logInAs(freshuser) — fresh OAuth round-trip as freshuser.
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await context.clearCookies();
    await logInAs(page, freshuser);

    await page.goto('/settings');

    // Per Story 3.5 SettingsPage + UX-DR9: 412 unset renders empty input,
    // helper text "e.g., 30" as the only cue, NO ErrorMessage rendered.
    const input = page.getByLabel('Pages per hour');
    await expect(input).toBeVisible();
    await expect(input).toHaveValue('');
    await expect(page.getByText('e.g., 30')).toBeVisible();

    // The SettingsPage template (settings-page.html:15-23) renders
    // <app-error-message> only when validationError / loadErrorMessage /
    // saveErrorMessage is non-null. For freshuser's 412, all three are null
    // → zero <app-error-message> elements on the page.
    await expect(page.locator('app-error-message')).toHaveCount(0);
  });

  test('setting a value shows the Saved pulse and persists across reload', async ({
    page,
  }) => {
    await page.goto('/settings');

    await page.getByLabel('Pages per hour').fill('30');

    // CRITICAL: lock to a stable selector that survives the button-text change.
    //
    // The button's accessible name changes Save → Saving… → Saved → Save
    // (settings-page.html:24-30 + settings-page.ts:49-53 saveButtonLabel
    // computed). page.getByRole('button', { name: 'Save' }) re-queries each
    // assertion; once the text becomes "Saved", that query returns 0 matches
    // and the toHaveText assertion times out with "0 elements".
    //
    // Use the class-name selector instead — the .settings-save class is
    // stable across label transitions.
    const saveButton = page.locator('button.settings-save');
    await saveButton.click();

    // Per UX-DR9 + Story 3.5 ReadingSpeedService.save: the button briefly
    // relabels to "Saved" for ~1s (JUST_SAVED_PULSE_MS = 1000 in
    // reading-speed-service.ts:25). 2000ms timeout is comfortable headroom.
    await expect(saveButton).toHaveText('Saved', { timeout: 2000 });

    // Reload triggers ReadingSpeedService.load() → GET /v1/reading-speed →
    // 200 {pages_per_hour: 30} → input populated.
    await page.reload();
    await expect(page.getByLabel('Pages per hour')).toHaveValue('30');
  });

  test('validation rejects pages_per_hour = 0 and preserves the typed value', async ({
    page,
  }) => {
    await page.goto('/settings');

    // Track whether the PUT is fired. Register the route handler BEFORE the
    // click so the GET that already fired on page-load passes through; only
    // a subsequent PUT would flip the flag.
    let putWasFired = false;
    await page.route('**/v1/reading-speed', (route) => {
      if (route.request().method() === 'PUT') {
        putWasFired = true;
      }
      return route.continue();
    });

    await page.getByLabel('Pages per hour').fill('0');
    await page.locator('button.settings-save').click();

    // Per Story 3.5 settings-page.ts:116-118: the regex /^[1-9]\d*$/ rejects
    // '0' (leading zero blocked); _validationError.set('Enter a positive
    // number'); the function returns BEFORE calling save() — no PUT fires.
    // The ErrorMessage component renders the literal text.
    await expect(page.getByText('Enter a positive number')).toBeVisible();
    await expect(page.getByLabel('Pages per hour')).toHaveValue('0');
    expect(putWasFired).toBe(false);
  });

  test('save while RS is down renders the named 503 error', async ({ page }) => {
    await killRs();

    await page.goto('/settings');

    // ReadingSpeedService.load() fires on ngOnInit (settings-page.ts:102-104),
    // gets 503 from the BFF (BFF proxy → RS unreachable → 503
    // resource_server_unavailable per Story 3.5), and finally{} sets
    // loading.set(false) — so the input is NOT disabled when we try to fill it.
    //
    // The load-error renders the same 503 copy as the save-error (the load
    // and save error variants both surface "Service unavailable — try again
    // shortly" per settings-page.ts:60-67 + 76-86). That's expected; this
    // test focuses on the save-path 503 specifically by typing + clicking.
    await page.getByLabel('Pages per hour').fill('30');
    await page.locator('button.settings-save').click();

    // The named 503 copy per UX-DR12 — emitted by either loadErrorMessage or
    // saveErrorMessage (both produce the same string for kind:
    // 'resource_server_unavailable'). Use toBeVisible on the literal text;
    // multiple error messages with the same copy are fine — toBeVisible
    // passes when at least one matches.
    await expect(
      page.getByText('Service unavailable — try again shortly').first(),
    ).toBeVisible();

    // Restore so subsequent tests don't inherit a dead RS. The afterEach also
    // calls startRs — belt-and-suspenders, idempotent.
    await startRs();
  });

  test('load while RS is down renders the named 503 error', async ({ page }) => {
    await killRs();

    // Fresh navigation triggers ReadingSpeedService.load() → GET
    // /v1/reading-speed → BFF proxy → RS unreachable → BFF emits 503
    // resource_server_unavailable → SettingsPage's loadErrorMessage computed
    // produces "Service unavailable — try again shortly".
    await page.goto('/settings');

    await expect(
      page.getByText('Service unavailable — try again shortly'),
    ).toBeVisible();

    await startRs();
  });
});
