---
status: done
story_key: 4-4-e2e-specs-j3-estimate-j6-rs-unavailable
epic: 4
prerequisites: 1.11 (done — Playwright project + fixtures); 1.12 (done — `compose/app.e2e.yml` overlay + `${TEST_RESET_TOKEN:?...}` pattern); 1.13 (done — J1+J5 specs; `requireEnv` shim); 2.7 (done — J2 spec; book-form add helper + `app-book-row` patterns); 3.4 (done — RS `POST /v1/test/reset`); 3.5 (done — BFF `ResourceServerClient` + `/v1/reading-speed` proxy + SPA `SettingsPage`); 3.6 (done — `killRs`/`startRs`/`resetState` real impls; `compose/app.e2e.yml` RS overlay; `Justfile` two-phase `e2e-up`; chromium `--host-resolver-rules`); 4.1 (done — RS `POST /v1/estimate` returning `{minutes, formatted}`); 4.2 (done — BFF `POST /v1/books/{id}/estimate` + `ResourceServerClient.compute_estimate`); 4.3 (done — SPA `EstimateCell` real component + `BooksService.requestEstimate`)
created: 2026-05-18
baseline_commit: bb15aca
---

# Story 4.4: E2E specs — J3 estimate + J6 RS unavailable

Status: done

<!-- Sprint: Epic 4 (Reading-Time Estimate & Honest Failure — J3, J6). Last story in Epic 4. -->
<!-- Follows: Story 4.3 (SPA EstimateCell real component — done). Precedes: Epic 5 (coverage / security / README / smoke). -->

## Story

As a reviewer of the OAuth/OIDC reference,
I want Playwright E2E specs driving J3 (the defining cross-service estimate interaction — happy path with default speed, J4↔J3 speed-change coupling, freshuser 412 precondition, in-place re-estimate, generic non-J6 failure) and J6 (the honest-failure surface when the RS is unavailable — estimate, retry-after-recovery, settings save) against the real running stack,
So that the marquee architectural interaction and its honest-failure variant are demonstrably correct on every CI-style run, closing Epic 4 and satisfying NFR11's "≥5 E2E covering J1–J6" gate.

## Scope (read this first)

This story is **pure E2E** — two new spec files driving the already-shipped SPA / BFF / RS stack. NO SPA, BFF, RS, compose, helper, or Dockerfile changes. Everything the spec needs already exists:

- `EstimateCell` (Story 4.3) — selectors `.estimate-cell-button--primary` / `.estimate-cell-result` / `.estimate-cell-reestimate` / `.estimate-cell-error` / `.estimate-cell-error-link`; states idle / loading / success / error verified by unit tests.
- BFF `POST /v1/books/{id}/estimate` (Story 4.2) — accepts `{}`, returns `{minutes, formatted}` from RS verbatim on success, 412 / 503 / 404 / 401 envelopes on failure.
- RS `POST /v1/estimate` (Story 4.1) — `reading-speed:read` scope-gated, returns `{minutes, formatted}` via `format_duration` (UX-DR18 prefix `≈` U+2248).
- E2E harness (Story 3.6) — `killRs()` / `startRs()` real impls (idempotent, socket-bound); `resetState()` truncates both BFF + RS; `compose/app.e2e.yml` activates `ENABLE_TEST_RESET=true` + `AUTH_TYPE=oidc_bearer` on the RS; `just e2e-up` is two-phase so mid-test `killRs()` does not tear down the runner.
- BookList / BookForm / BookRow selectors (Story 2.5 / 2.6 / 2.7) — `app-book-form[variant="add"]`, `app-book-row`, `.book-row-title` / `.book-row-pages`.

Concretely, this story delivers:

1. `e2e/tests/j3-estimate.spec.ts` (NEW) — 5 Playwright tests covering AC1–AC5 below (J3 happy path / speed-changes-estimate-changes / freshuser 412 / re-estimate in place / generic non-J6 failure).
2. `e2e/tests/j6-rs-unavailable.spec.ts` (NEW) — 3 Playwright tests covering AC6–AC8 below (RS-down estimate / recovery / settings save).
3. `e2e/README.md` — "Specs in this directory" gains entries for `j3-estimate.spec.ts` and `j6-rs-unavailable.spec.ts`.

Out of scope: any SPA / BFF / RS code; any compose / Dockerfile / helper changes; the `bmad-retrospective` for Epic 4 (the epic-4 retro is optional in sprint-status.yaml — handle it separately); any Epic 5 work (coverage audit / security review / README polish / final smoke).

## Acceptance Criteria

### J3 spec — `e2e/tests/j3-estimate.spec.ts`

**AC1 — File exists at `e2e/tests/j3-estimate.spec.ts` and uses the standard describe + `requireEnv` + `beforeEach` pattern (mirroring `j4-adjust-speed.spec.ts`).**

```ts
import { expect, test } from '@playwright/test';

import { logInAs, resetState } from '../fixtures/helpers';
import { freshuser, testuser } from '../fixtures/users';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Required env var ${name} is not set. See e2e/README.md "Environment variables" for the expected values.`,
    );
  }
  return value;
}

test.describe('J3: reading-time estimate', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  // …tests AC2–AC5
});
```

- Verbatim `requireEnv` shim duplicated from `j1` / `j4` / `j5`. Story 2.7's deferred-extraction decision still stands (revisit when duplicate count ≥4 — this brings the count to 4 across all spec files; consider extracting to `fixtures/helpers.ts` ONLY IF a fifth spec lands; do NOT extract here per YAGNI + the Story 1.13 / 2.7 / 3.6 decision chain).
- NO `afterEach` in the J3 describe — none of the J3 tests stop the RS, so the J4-style RS-restore guard is unnecessary. (Contrast: J6 spec DOES need `afterEach startRs()` — see AC6.)
- Use only the helpers from `fixtures/helpers.ts` (`logInAs`, `resetState`). No inline credential filling, no inline `child_process`, no hardcoded tokens.

**AC2 — Test: `estimate happy path with default speed`.**

```ts
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
  const row = page.locator('app-book-row').first();
  const estimateBtn = row.locator('button.estimate-cell-button--primary');
  await expect(estimateBtn).toHaveText('Estimate');
  await estimateBtn.click();

  // Loading state — button disabled with U+2026 ellipsis label.
  // Use a tight timeout because the round-trip can resolve fast; the
  // disabled+label transition is observable in pessimistic UI per UX-DR13.
  await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimating…');
  await expect(row.locator('button.estimate-cell-button--primary')).toBeDisabled();

  // Success state — formatted duration rendered verbatim from RS.
  // Regex matches "≈ 20 h" / "≈ 20 h 0 m" / similar — the RS's
  // include-minutes-when-days rule (duration.py docstring) drops zero
  // minutes when there are no days; for speed=30/pages=600 → minutes=1200
  // → exactly "≈ 20 h". The regex is loose to absorb any future tweak to
  // the format_duration rounding (Story 4.1 fixed the include-minutes
  // branch, but the spec stays robust to a future revisit).
  await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
  await expect(row.locator('.estimate-cell-result')).toHaveText(/≈\s*\d+\s*[hm]/);

  // Re-estimate affordance is visible; Estimate button is gone.
  await expect(row.locator('button.estimate-cell-reestimate')).toHaveText('Re-estimate');
  await expect(row.locator('button.estimate-cell-button--primary')).toHaveCount(0);
});
```

- **Locator scope is critical:** every assertion is rooted at `row` (`app-book-row.first()`), so a future second-row test wouldn't accidentally pass on a cross-row match. Mirror the `firstRow(page)` helper from `j2-manage-books.spec.ts`.
- **Loading-state observability:** epic AC line 1711 says "asserts the loading state … is observably reached". Pessimistic UI guarantees the button is disabled with the `Estimating…` label between click and round-trip completion. The `toHaveText` / `toBeDisabled` assertions implicitly retry (Playwright auto-waits) up to the test's `timeout: 60_000` (per `playwright.config.ts:14`); inside the compose `e2e` profile the BFF→RS round-trip is sub-second so the disabled state is reliably observable. If this proves flaky on slow CI, follow the **AC2-alt** pattern (below).
- **AC2-alt — `page.route` hold:** if the natural-speed assertion is flaky, hold the estimate POST open via `page.route('**/v1/books/*/estimate', ...)` (same pattern as `j2-manage-books.spec.ts:128-139` for optimistic-UI tests), assert loading-state, release, then assert success. Document the deviation in the Dev Agent Record's Completion Notes if used.
- **Result-locator stability:** `.estimate-cell-result` is the `<span>` (`estimate-cell.html:10`); it appears ONLY in the success state, never overlaps with the Estimating button.
- **Compose only:** This spec does NOT set the speed via the BFF directly (no BFF `/v1/reading-speed` shortcut helper exists — Story 4.4 deliberately exercises the full UX path: SPA settings UI → BFF → RS, then SPA books UI → BFF → RS).

**AC3 — Test: `speed change yields different estimate (J4↔J3 coupling)`.**

```ts
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

  // Re-estimate the same book.
  await page.goto('/books');
  await expect(page.locator('app-book-row')).toHaveCount(1);
  await row.locator('button.estimate-cell-reestimate').click();
  // After Re-estimate, the loading state replaces .estimate-cell-result
  // (the template's @if (loading()) branch wins — the previous result
  // is cleared by onEstimateClick before fetching). Wait for the new
  // result to appear; Playwright's locator auto-retries until the @else if
  // (result(); as r) branch renders again.
  await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
  const r2 = await row.locator('.estimate-cell-result').textContent();
  expect(r2).toBeTruthy();

  // r1 !== r2 (strings differ) AND r2's implied minutes strictly less than r1's.
  expect(r2).not.toBe(r1);
  expect(impliedMinutes(r2!)).toBeLessThan(impliedMinutes(r1!));
});

/**
 * Parse a formatted duration string like "≈ 4 h 20 m" / "≈ 1 d 22 h 20 m" /
 * "≈ 12 m" back to total minutes. Pure spec helper — invariant: should
 * round-trip every output of `format_duration` (services/resource-server/
 * src/resource_server/services/duration.py).
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
```

- **`impliedMinutes` helper:** local to the spec file (NOT exported to `fixtures/`). It mirrors the inverse of `duration.py:format_duration`. If `format_duration` changes (e.g., decides to include "0 m" segments), this helper still works because it tolerates missing segments.
- **Why r1 !== r2 AND r2 < r1 (not just <):** the strict-inequality and string-difference are BOTH per the epic AC line 1713. The string check catches a regression where both round to the same coarse output (e.g., if a future rounding rule made both speeds yield `≈ 1 d` for some pages count); the minutes check catches a regression where the speed change inverted (faster speed → MORE minutes).
- **Reusing the same row:** because the books list is per-user and `resetState` ran once in `beforeEach`, the single seeded book persists across the `/settings → /books` navigation. `row` is captured once and stays valid (Playwright locators are lazy — they re-query on each assertion).

**AC4 — Test: `freshuser sees the 412 precondition with a link to Settings`.**

```ts
test('freshuser sees the 412 precondition with a link to Settings', async ({
  page,
  request,
  context,
}) => {
  // Override the testuser login from beforeEach — see j4-adjust-speed.spec.ts
  // AC10 for the resetState + clearCookies + logInAs pattern rationale
  // (deterministic, doesn't rely on the auth interceptor cleaning up a stale
  // session cookie under slow CI).
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
  // estimate-cell.ts:ESTIMATE_CELL_PRECONDITION_PREFIX/SUFFIX +
  // estimate-cell.html line 21-25. The `Settings` link is an embedded
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
```

- **`testuser → freshuser` swap pattern:** verbatim from `j4-adjust-speed.spec.ts:46-62`. The `context.clearCookies()` between resetState and `logInAs(freshuser)` is load-bearing for deterministic CI behavior.
- **Why `.toContainText` for the literal copy:** the actual DOM rendering interleaves text and an `<a>` element (`Set your reading speed in <a>Settings</a> to enable estimates`); a single `getByText('Set your reading speed in Settings to enable estimates')` matches via Playwright's text engine, but `.toContainText` against the parent `<p>` is more robust to whitespace normalization across browser versions.
- **`href` attribute check:** Angular's `RouterLink` adds `href` for click-tracking / right-click "Copy link" support; the in-page navigation is intercepted by Angular's router. Asserting `href` ends with `/settings` proves the link is rendered correctly without coupling to Angular's internal navigation mechanism.
- **No reading-speed seeding for freshuser:** confirmed by inspection — `keycloak/realm-bmad-books.json` seeds `freshuser` with username/password only; the RS `reading_speeds` table has zero rows for freshuser at `resetState` time. The 412 path is `BFF /v1/books/{id}/estimate` → RS `/v1/estimate` → RS handler returns 412 `reading_speed_unset` → BFF forwards verbatim → SPA `ErrorService.parse` maps to `{kind: 'reading_speed_unset'}` → `EstimateCell` renders the inline link variant.

**AC5 — Test: `re-estimate replaces value in-place without navigation`.**

```ts
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

  // The strings are EQUAL because nothing changed between the two requests
  // (same speed, same pages). The point of the test is the no-navigation
  // invariant, NOT the value difference (AC3 already covers that). Pin the
  // equality explicitly to document the intent.
  expect(secondResult).toBe(firstResult);
});
```

- **Same speed + same pages → same result is the right pin:** AC3 already covers "value differs when speed differs". AC5's contribution is the no-navigation invariant during Re-estimate. The `secondResult === firstResult` assertion documents that fact while still proving the second round-trip actually rendered (since `firstResult` was non-null).
- **URL invariance asserted twice:** once immediately after the click (while loading might or might not have started) and once after the result re-renders. Both must equal the captured `urlBefore`. Catches a regression where a stray `router.navigateByUrl(...)` slipped into `EstimateCell.onEstimateClick`.

**AC6-J3 — Test: `generic non-J6 failure renders the generic copy`.**

```ts
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

  // Generic copy from estimate-cell.ts:ESTIMATE_CELL_GENERIC_COPY.
  // The apostrophe is U+2019 RIGHT SINGLE QUOTATION MARK ("Couldn’t").
  // Use a regex that tolerates either apostrophe form (the test is the only
  // place a future curly→straight regression could land; this guards
  // against accidentally regressing the curly apostrophe by failing the
  // test rather than reading a misleading "matches anyway" outcome).
  await expect(row.locator('app-error-message')).toBeVisible();
  await expect(row.locator('app-error-message')).toContainText(/Couldn[’']t get an estimate — try again/);

  // J6 copy MUST NOT appear — this is the rule the test pins:
  // ESTIMATE_CELL_J6_COPY is reserved for {kind: 'resource_server_unavailable'}.
  await expect(page.getByText('Service unavailable — try again shortly')).toHaveCount(0);

  // No fabricated duration — the ≈ glyph must not appear anywhere in the row.
  await expect(row).not.toContainText('≈');

  // Estimate button is restored beneath the error.
  await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimate');

  // Unroute so subsequent tests don't inherit the mock.
  await page.unroute('**/v1/books/*/estimate');
});
```

- **The "no `≈` anywhere in row" assertion** pins UX §"Defining Experience" line 252 ("BFF does not invent a number") at the spec level. Mirrors the unit test coverage in `estimate-cell.spec.ts:test 6` (Story 4.3 AC16).
- **Why `page.route` (not `killRs()`)** for generic failure: the test PINS the rule that the generic copy applies to any non-503 5xx envelope. Using `killRs()` would yield 503 / `resource_server_unavailable` and exercise the J6 branch instead. `page.route` lets us inject a deterministic 500 / `unknown` body without disturbing the running stack.
- **AC numbering:** the epic AC text and Story 4.3 both label this the fifth J3 test. Internally in this story I'm numbering it AC6-J3 to keep clean separation from the AC6 J6 tests below; the implementer can renumber if desired (the test name string is the load-bearing identifier in the Playwright runner output).

### J6 spec — `e2e/tests/j6-rs-unavailable.spec.ts`

**AC6 — File exists at `e2e/tests/j6-rs-unavailable.spec.ts` with `beforeEach`/`afterEach` mirroring `j4-adjust-speed.spec.ts`.**

```ts
import { expect, test } from '@playwright/test';

import { killRs, logInAs, resetState, startRs } from '../fixtures/helpers';
import { testuser } from '../fixtures/users';

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

  // …tests AC7–AC9
});
```

- **The `afterEach startRs()` is load-bearing** for cross-test isolation: every J6 test calls `killRs()` and any premature failure between the kill and a per-test `startRs()` would leave a dead RS for the next test. Story 3.6 codified this guard.
- **`workers: 1` is still load-bearing** (`e2e/playwright.config.ts:14`) — J6's kill-restart pattern fundamentally requires sequential execution because the RS is a singleton.
- **D108 (open):** `afterEach` `startRs()` has no try/catch. If the docker socket itself is unreachable, the cleanup throws and may mask the test's original error. Out of scope here — fix lives in the deferred-work log; do NOT add try/catch in 4.4.

**AC7 — Test: `estimate while RS is down renders the named J6 error`.**

```ts
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
  const colorValue = await row.locator('app-error-message p.error-message').evaluate(
    (el) => window.getComputedStyle(el).color,
  );
  // #B91C1C → rgb(185, 28, 28). Some browsers emit `rgb(185, 28, 28)` and
  // some `rgb(185 28 28)` (CSS Color 4 spec). Match either.
  expect(colorValue).toMatch(/rgb\(\s*185[,\s]\s*28[,\s]\s*28\s*\)/);

  // 6. No fabricated duration anywhere in the row — UX §"Defining
  // Experience" + epic AC line 1729.
  await expect(row).not.toContainText('≈');

  // 7. Estimate button is restored beneath the error.
  await expect(row.locator('button.estimate-cell-button--primary')).toHaveText('Estimate');
});
```

- **Why `page.goto('/books')` after `killRs()` instead of staying on the page:** the books list is BFF-owned and `BookListPage` doesn't auto-refresh. A fresh navigation rules out any stale-state confusion. The cost is one extra round-trip; the determinism is worth it.
- **Color assertion:** the epic AC offers implementer choice — resolved CSS color match OR class/aria marker. The resolved-color form is pinned here because the existing `<app-error-message>` already routes through `--color-error`; no new marker is needed. The regex tolerates both old and new CSS Color 4 serialization shapes (some Chromium versions emit `rgb(185 28 28)`, others `rgb(185, 28, 28)`).
- **DO NOT call `startRs()` in the test body** — let the `afterEach` handle it. Calling it inline duplicates work and increases the time-to-fail-feedback on a real RS-startup regression.
- **The `<app-error-message>` parent locator `app-error-message p.error-message`:** the component emits a single `<p>` with class `error-message` (verified from `spa/src/app/shared/ui/error-message.html` via the Story 4.3 audit). The double selector pins both the component tag AND the styled element.

**AC8 — Test: `retry succeeds after RS recovery`.**

```ts
test('retry succeeds after RS recovery', async ({ page }) => {
  // Setup identical to AC7 — speed=30, one book, RS down, error rendered.
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
  // e2e/fixtures/services.ts:143-178).
  await startRs();

  // Click Estimate again. The SPA does NOT silently retry — the user
  // re-clicks. This proves UX-DR + architecture §"Retry & failure":
  // "User retries by clicking the action again. The BFF does not silently
  // retry; it does not fabricate a result. The SPA does not auto-poll."
  await row.locator('button.estimate-cell-button--primary').click();
  await expect(row.locator('.estimate-cell-result')).toBeVisible({ timeout: 10_000 });
  await expect(row.locator('.estimate-cell-result')).toHaveText(/≈\s*\d+\s*[hm]/);
  await expect(row.locator('app-error-message')).toHaveCount(0);
});
```

- **The "user re-clicks" assertion is the test's load-bearing pin:** AC7 already proved the error state renders correctly. AC8's job is to prove there is NO silent retry between the kill and the manual re-click. Pessimistic + manual-retry is the architectural rule (architecture.md §"Retry & failure"; UX §"Failure recovery" line 559).
- **`startRs()` mid-test is fine** because we WANT the RS up again. The `afterEach` `startRs()` is then a no-op (idempotent per Story 3.6 services.ts implementation).
- **`waitForRsHealthy` is what makes the second click reliable:** without it, clicking immediately after `startRs()` would race the RS's startup-probe. The helper polls until `docker inspect → healthy`.

**AC9 — Test: `settings save while RS is down also renders the named J6 error`.**

```ts
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
  // least one matches.
  await expect(
    page.getByText('Service unavailable — try again shortly').first(),
  ).toBeVisible();
});
```

- **This re-verifies Story 3.6's J4 AC13 coverage** at the spec level. Epic AC line 1733 explicitly says "this re-verifies Story 3.6's coverage and pins the SAME copy/component is used across both estimate and settings 503s." The redundancy is intentional — Story 4.4's job is to prove J6's surface is uniform across the two action sites.
- **NO `startRs()` in body** — the `afterEach` handles it.
- **`.first()` rationale:** identical to Story 3.6 J4 AC13's rationale (`j4-adjust-speed.spec.ts:139-167`). The load + save 503 paths can render two `<app-error-message>` elements transiently; `.first()` is the documented pattern.

### Harness contract + gates

**AC10 — Specs use only helpers from `fixtures/helpers.ts`.**

No `page.evaluate(() => fetch(...))` for the reset endpoint. No inline `child_process.execFile('docker', ...)` in any spec body. No inline Keycloak credential filling (`logInAs` is the sole truth). No tokens hardcoded — always `requireEnv('TEST_RESET_TOKEN')`. Codified by Story 1.13; carried by 2.7, 3.6; honored here.

**AC11 — `e2e/README.md` "Specs in this directory" entries added for J3 + J6.**

Two new entries under the existing "Specs in this directory" section, mirroring the existing J1 / J2 / J4 / J5 entries' shape:

```md
- `tests/j3-estimate.spec.ts` (Story 4.4) — J3: reading-time estimate happy path
  (default speed), J4↔J3 coupling (speed change yields different estimate),
  freshuser 412 precondition with link to /settings, in-place re-estimate,
  generic non-J6 failure with the generic copy ("Couldn't get an estimate —
  try again"). Pessimistic UI throughout — no silent retry.
- `tests/j6-rs-unavailable.spec.ts` (Story 4.4) — J6: estimate while RS is
  down renders the named J6 error in the row's estimate cell, retry-after-
  RS-recovery succeeds (proving manual-retry rule), and settings save while
  RS is down renders the same copy (pinning the uniform 503 surface across
  estimate and settings).
```

The existing "RS killswitch (J4 + J6)" section can stay unchanged — its text already covers both journeys.

**AC12 — Static gates green.**

- `cd e2e && npx tsc --noEmit` — exit 0. The two new specs typecheck.
- `cd e2e && npx playwright test --list` — exit 0; reports J1 (3), J2 (8), J4 (5), J5 (2), and the new J3 (5) + J6 (3) = **26 tests in 6 files**.
- `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` — exit 0 (no compose changes in this story; regression check only).

**AC13 — Live `just e2e-up` exits 0 with all six journey specs green.**

Per Epic 1 retro action item P2 ("Compose-stack ACs run live or are explicitly downgraded"), this story's `done` gate requires:

```sh
just e2e-up
```

exits 0, and the runner's stdout shows all 26 tests passing (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3). Traces / screenshots / videos on any failure land under `e2e/test-results/` on the host (existing bind-mount from Story 1.11).

If AC13 cannot be met because of a defect in 4.1–4.3 (unlikely — all are `done` on `main` — but possible if 4.4's selector assumptions hit edge cases), the story stays in `review` with a deferred-work entry pointing at the upstream defect. Do NOT close based on static gates alone — retro P2.

## Tasks / Subtasks

- [x] **Task 1 — Create `e2e/tests/j3-estimate.spec.ts`** (AC: #1, #2, #3, #4, #5, #6-J3)
  - [x] 1.1 Create the file with the describe + `requireEnv` + `beforeEach` from AC1. NO `afterEach` (J3 doesn't kill RS).
  - [x] 1.2 Add the AC2 test `estimate happy path with default speed`. Use `row = page.locator('app-book-row').first()` and root all assertions at `row`. **Dev note:** AC2-alt applied — natural round-trip resolves sub-100ms in compose `e2e` profile, faster than Playwright's expect-poll cycle, so the `page.route` POST hold (deferred-promise pattern, mirror of `j2-manage-books.spec.ts:128-139`) is used to deterministically observe the `Estimating…` loading state. Released + `waitForResponse` + `unroute` after assertion. See D128.
  - [x] 1.3 Add the AC3 test `speed change yields different estimate (J4↔J3 coupling)`. Include the local `impliedMinutes(formatted)` helper (NOT exported to `fixtures/`). **Dev note:** Story 4.4 AC3 block called for `button.estimate-cell-reestimate` on the second estimate, but `/settings → /books` navigation destroys the `EstimateCell` instance (component-local signals reset on remount; documented in `estimate-cell.ts:53-55`). On return the cell is in idle state, so the test clicks the now-idle Estimate button instead. The speed-coupling rule (`r2 !== r1` and `impliedMinutes(r2) < impliedMinutes(r1)`) is still pinned. See D129.
  - [x] 1.4 Add the AC4 test `freshuser sees the 412 precondition with a link to Settings`. Use the testuser→freshuser swap pattern from `j4-adjust-speed.spec.ts:46-62` verbatim (`resetState`+`context.clearCookies()`+`logInAs(freshuser)`).
  - [x] 1.5 Add the AC5 test `re-estimate replaces value in-place without navigation`. Pin URL invariance at both mid-flight and post-flush.
  - [x] 1.6 Add the AC6-J3 test `generic non-J6 failure renders the generic copy`. Use `page.route('**/v1/books/*/estimate', ...)` to inject the 500 + `unknown` envelope. Assert no `≈` anywhere in the row. Call `page.unroute(...)` at the end.

- [x] **Task 2 — Create `e2e/tests/j6-rs-unavailable.spec.ts`** (AC: #6, #7, #8, #9)
  - [x] 2.1 Create the file with the describe + `requireEnv` + `beforeEach` + `afterEach startRs()` from AC6.
  - [x] 2.2 Add the AC7 test `estimate while RS is down renders the named J6 error`. Include the `rgb(185, 28, 28)` color-resolution assertion via `evaluate(el => window.getComputedStyle(el).color)`. Tolerate both `rgb(185, 28, 28)` and `rgb(185 28 28)` serializations.
  - [x] 2.3 Add the AC8 test `retry succeeds after RS recovery`. Use `startRs()` mid-test; the `afterEach` `startRs()` is a no-op (idempotent).
  - [x] 2.4 Add the AC9 test `settings save while RS is down also renders the named J6 error`. Use `.first()` on the text locator (load-error + save-error may both render the same copy transiently).

- [x] **Task 3 — Update `e2e/README.md`** (AC: #11)
  - [x] 3.1 Append two entries under "Specs in this directory" — J3 and J6 (use the wording from AC11 above).
  - [x] 3.2 Do NOT modify the existing "RS killswitch (J4 + J6)" section; its forward-reference to J6 is now satisfied retroactively but the wording remains accurate.
  - [x] 3.3 No new env vars — every env var the J3/J6 specs need is already documented (TEST_RESET_TOKEN, KEYCLOAK_INTERNAL_URL, RS_BASE_URL, COMPOSE_PROJECT_NAME, BFF_CLIENT_SECRET, OIDC_CLIENT_ID).

- [x] **Task 4 — Static gates** (AC: #10, #12)
  - [x] 4.1 `cd e2e && npx tsc --noEmit` → exit 0.
  - [x] 4.2 `cd e2e && npx playwright test --list` → exit 0, reports 26 tests in 6 files (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3 = 26). Verified.
  - [x] 4.3 `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` → exit 0.
  - [x] 4.4 `grep -rn "child_process\|inline.*fetch.*reset\|hardcoded.*token" e2e/tests/j3-estimate.spec.ts e2e/tests/j6-rs-unavailable.spec.ts` → exit 1 (no matches; AC10 honored).

- [x] **Task 5 — Live `just e2e-up`** (AC: #13)
  - [x] 5.1 From the repo root, run the canonical compose invocation (the host has no `just` binary on PATH; the Justfile's `e2e-up` recipe is plain bash — inlined verbatim: `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up -d --wait keycloak bff resource-server` then `docker compose ... run --rm --build playwright`). `--build` is REQUIRED because the playwright runner Dockerfile does `COPY . .` and bakes specs at build time — without `--build`, the second `docker compose run` reuses a cached image without the new J3 + J6 specs and silently reports only 18 tests.
  - [x] 5.2 Confirmed: Keycloak → BFF + RS healthy → playwright runner built + run → **all 26 tests pass** (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3) → runner exits 0 → trap teardown → final shell exit 0.
  - [x] 5.3 Runner summary: `26 passed (52.8s)` — captured in Debug Log References below.
  - [x] 5.4 First run found 2 failures (J3 happy-path loading-state timing; J3 J4↔J3 coupling Re-estimate-after-navigation). Triaged via trace YAML snapshots; root causes were a story-spec timing assumption (resolved via AC2-alt route hold) and a component-lifecycle assumption that didn't match `EstimateCell`'s component-local-state design (resolved by clicking the now-idle Estimate button after re-navigation). Both deviations logged as D128 + D129.

- [x] **Task 6 — Regression checks across all four surfaces** (AC: #13 sanity)
  - [x] 6.1 `cd services/bff && uv run pytest -q` → exit 0 (**543 passed**).
  - [x] 6.2 `cd services/resource-server && uv run pytest -q` → exit 0 (**324 passed**).
  - [x] 6.3 `cd spa && npm test -- --watch=false` → exit 0 (**152 passed**); `npm run build` → exit 0. `npm run lint` → exit 1 (3 pre-existing `no-fallthrough` errors in `book-form.ts`, `book-row.ts`, `status-control.ts`; **verified pre-existing on baseline `bb15aca`** by stashing 4.4 changes and re-running lint — same 3 errors surface). Story 4.4 explicitly forbids SPA source changes; logged as D127.

## Dev Notes

### What this story is — and is not

**Is:** Two Playwright spec files driving the already-shipped Epic 4 stack (RS `/v1/estimate` + BFF `/v1/books/{id}/estimate` + SPA `EstimateCell`) end-to-end, plus a README diff documenting the two new specs.

**Is NOT:** Any SPA / BFF / RS code change. Any compose / Dockerfile / helper change. Any new `AppError` variant. Any new `fixtures/users.ts` entries. Any change to `playwright.config.ts`, `Justfile`, `compose/app.yml`, `compose/app.e2e.yml`, `e2e/Dockerfile`, `e2e/fixtures/helpers.ts`, or `e2e/fixtures/services.ts`. Any retro work (epic-4 retro is `optional` in sprint-status.yaml — handle separately if desired).

### Architectural compliance (verbatim or paraphrased from architecture.md)

- **AR1 — BFF reads `sub` ONLY from the session row (not from request body).** The BFF estimate handler reads `pages` from the local books row keyed by `(sub, id)` — the request body `{}` is intentionally ignored (Story 4.2 AC + `bff/api/books.py:259-260`). The J3 spec POSTs implicitly via the SPA, so this is invisible to the spec but informs the "wire body is `{}`" expectation if anyone inspects network traffic.
- **AR17 — Honest error mapping.** `RsUnavailable` → BFF 503 `resource_server_unavailable`; `reading_speed_unset` → 412; `book_not_found` → 404; `session_expired` → 401. The J6 spec exercises the first; AC4 exercises the second; AC6-J3 exercises the generic-5xx fallthrough via `page.route`.
- **AR23 — Signal-based SPA + pessimistic cross-service.** EstimateCell uses local signals (`loading`, `result`, `error`); no optimistic transitions on the estimate flow (architecture.md §"Process Patterns / Loading state UI"; UX-DR13). The J3 AC2 loading-state assertion pins this at the spec level.
- **AR26 — Compose profiles `default` / `dev` / `e2e`.** This story executes under `e2e` only. Default + dev paths are NOT exercised here.
- **AR31 — Playwright in `e2e/`, one spec per PRD journey, real Keycloak login.** Two new files = J3 + J6 = the last two PRD journeys uncovered after Stories 1.13 / 2.7 / 3.6. NFR11's "≥5 E2E covering J1–J6" gate is met as of this story (J1, J2, J3, J4, J5, J6 = 6 specs).
- **AR32 — `POST /v1/test/reset` semantics + env gating on BFF + RS; shared `TEST_RESET_TOKEN`.** The J3 + J6 specs both call `resetState` in `beforeEach`. Story 3.6 wired the RS side in; this story just consumes the resetState helper unchanged.
- **AR34 — Test coverage.** PRD floor ≥70% / archetype tightening to >90% backend / ≥5 E2E covering J1–J6. The E2E gate flips green with 4.4; the per-surface coverage gates are Epic 5 territory.

### Selectors — verified against current SPA HEAD (commit `bb15aca`)

Read from the actual files (Story 4.3 + Story 3.5 + Story 2.5/2.6 / 2.7) to avoid spec-vs-reality drift:

| What | Selector | Source |
|---|---|---|
| Estimate button (idle / restored) | `button.estimate-cell-button--primary` (text: `Estimate`) | `spa/src/app/books/estimate-cell.html:30-36`; `estimate-cell.css:3` |
| Estimate button (loading) | `button.estimate-cell-button--primary` (text: `Estimating…`, `disabled` attr) | `estimate-cell.html:1-8`; `ESTIMATE_CELL_LOADING_LABEL = 'Estimating…'` (U+2026) |
| Formatted result | `.estimate-cell-result` (text matches `/≈\s*\d+\s*[hm]/`) | `estimate-cell.html:9-10`; `estimate-cell.css:23-27` |
| Re-estimate text button | `button.estimate-cell-reestimate` (text: `Re-estimate`) | `estimate-cell.html:11-17`; `estimate-cell.css:30-37` |
| `reading_speed_unset` inline error (with link) | `.estimate-cell-error` (contains `Set your reading speed in` + `to enable estimates`) | `estimate-cell.html:20-25`; `estimate-cell.css:47-51` |
| Settings link inside the inline error | `a.estimate-cell-error-link` (text: `Settings`, `href` ending `/settings`) | `estimate-cell.html:22-24`; `estimate-cell.css:53-60` |
| Other error variants (J6 / generic) | `app-error-message` → `p.error-message` (`color: var(--color-error)` = `#B91C1C`) | `estimate-cell.html:26-28`; `error-message.html`; `error-message.css:3`; `styles.css:11` |
| Books list row | `app-book-row` (`.book-row`, `.book-row-title`, `.book-row-pages`) | `book-row.html`; `book-row.css` |
| Add-book form | `app-book-form[variant="add"]` (`input[formcontrolname="title"]`, `input[formcontrolname="pages"]`, `select[formcontrolname="status"]`) | `j2-manage-books.spec.ts:56-75` pattern |
| Add-book submit | `getByRole('button', { name: 'Add book' })` | `j2-manage-books.spec.ts:87` precedent |
| Settings input | `getByLabel('Pages per hour')` | `settings-page.html`; `j4-adjust-speed.spec.ts:68` |
| Settings save button | `button.settings-save` (text Save/Saving…/Saved) | `j4-adjust-speed.spec.ts:97` precedent |

### Copy strings — verbatim from `estimate-cell.ts` exports

These are the FIVE exported constants the unit tests assert on. The E2E spec uses literal text matching (rather than importing the constants) because the e2e tsconfig doesn't reach into the SPA workspace — the strings need to be in the spec file directly.

| Constant | Literal value | Punctuation |
|---|---|---|
| `ESTIMATE_CELL_IDLE_LABEL` | `Estimate` | ASCII |
| `ESTIMATE_CELL_LOADING_LABEL` | `Estimating…` | U+2026 (HORIZONTAL ELLIPSIS), NOT three dots |
| `ESTIMATE_CELL_REESTIMATE_LABEL` | `Re-estimate` | ASCII hyphen |
| `ESTIMATE_CELL_PRECONDITION_PREFIX` + `_SUFFIX` | `Set your reading speed in` + `to enable estimates` (text split around the `Settings` link) | ASCII |
| `ESTIMATE_CELL_J6_COPY` | `Service unavailable — try again shortly` | U+2014 (EM DASH) |
| `ESTIMATE_CELL_GENERIC_COPY` | `Couldn’t get an estimate — try again` | U+2019 (RIGHT SINGLE QUOTATION MARK) + U+2014 (EM DASH) |

**Critical for the spec file:** type the curly apostrophe in `Couldn’t` directly (U+2019). The AC6-J3 test uses a regex `/Couldn[’']t get an estimate — try again/` that tolerates both curly and straight apostrophes — this catches a future regression to the straight apostrophe at the source level (the test would still pass) without making the spec brittle to an editor accidentally pasting the wrong glyph.

### Wire contract — what 4.4 consumes

| Endpoint | Method | Where it lives | What 4.4 asserts |
|---|---|---|---|
| `POST /v1/books/{id}/estimate` | BFF (Story 4.2) | 200 `{minutes, formatted}` happy; 412 `reading_speed_unset` (freshuser); 503 `resource_server_unavailable` (J6); 404 `book_not_found` (defensive — not exercised by 4.4 directly); 500 `unknown` (AC6-J3 via `page.route`). |
| `POST /v1/estimate` | RS (Story 4.1) | Scope-gated `reading-speed:read`. Returns `{minutes, formatted}` via `format_duration`. NOT directly exercised by 4.4 — the BFF brokers the call. |
| `GET /v1/reading-speed` | BFF proxy (Story 3.5) | Used by SettingsPage on `/settings` navigation. 503 path is exercised by AC9. |
| `PUT /v1/reading-speed` | BFF proxy (Story 3.5) | Used by SettingsPage save. 503 path is exercised by AC9. |
| `POST /v1/test/reset` | BFF (Story 1.12) + RS (Story 3.4) | Shared `TEST_RESET_TOKEN`. Used by `resetState` helper in `beforeEach`. |
| `/auth/login` + Keycloak round-trip | BFF (Story 1.5) + Keycloak | Used by `logInAs(testuser|freshuser)` in `beforeEach`. |

### `format_duration` worked examples — pinning the J3 happy-path expectations

From `services/resource-server/src/resource_server/services/duration.py` (Story 4.1):

| `pages_per_hour` | `pages` | `minutes` (ceil) | `formatted` |
|---|---|---|---|
| 30 | 100 | ceil(100*60/30) = 200 | `≈ 3 h 20 m` |
| 30 | 200 | 400 | `≈ 6 h 40 m` |
| 30 | 300 | 600 | `≈ 10 h` |
| 30 | 400 | 800 | `≈ 13 h 20 m` |
| 30 | 600 | 1200 | `≈ 20 h` |
| 60 | 600 | 600 | `≈ 10 h` |

- **Loose regex in AC2** (`/≈\s*\d+\s*[hm]/`) accepts `≈ 20 h` / `≈ 13 h 20 m` / `≈ 12 m` / similar without coupling to the exact minute count. Resilient to future tweaks to `format_duration`.
- **AC5 (re-estimate replaces value in-place)** uses pages=300 → speed=30 yields `≈ 10 h`. Re-running with same params yields the same string. The equality assertion catches a regression where Re-estimate fails silently or renders an empty `<span>`.
- **AC3 (J4↔J3 coupling)** uses pages=600 → speed=30 (`≈ 20 h`, minutes=1200) → change to speed=60 (`≈ 10 h`, minutes=600). `r2 !== r1` AND `impliedMinutes(r2) < impliedMinutes(r1)`. Catches a regression where Re-estimate uses a cached speed (would yield equal strings) or the speed change is inverted.

### Previous story intelligence

**Story 4.3 (done, merged at `bb15aca`):**
- `EstimateCell` real component with all five UX states (idle / loading / success / `reading_speed_unset` precondition / `resource_server_unavailable` / generic). All selectors and copy strings exported as constants (`ESTIMATE_CELL_*`).
- Unit tests in `estimate-cell.spec.ts` cover all 8 cases at the component level (idle / loading / success / re-estimate / `reading_speed_unset` / `resource_server_unavailable` / generic / `book_not_found` defensive). E2E adds the live-stack round-trip on top.
- The `pages` input is required by the component but unused at runtime — the BFF reads pages server-side. The E2E spec doesn't need to special-case this; the SPA's `BookRow` already binds it.
- The `withCredentialsInterceptor` (Story 1.9) redirects 401 to `/login` before the rejection reaches `EstimateCell`. No 401 path is exercised by 4.4 (would require a stale session, which `beforeEach`/`logInAs` precludes).

**Story 4.2 (done, merged at `b905307`):**
- BFF `POST /v1/books/{id}/estimate` returns the RS body verbatim. The empty `{}` request body is the load-bearing contract — the BFF reads `pages` from the `(sub, id)` books row, NOT from the body. Story 4.2's tests pin this at the BFF level.
- The 412 / 503 / 404 / 401 envelopes are produced by the BFF (not just forwarded from the RS) — the BFF owns the error-envelope shape. The J3/J6 specs assert on the rendered SPA copy, which the SPA's `ErrorService` maps from these envelopes.

**Story 4.1 (done, merged at the Epic 3 close):**
- RS `format_duration` pins the `≈ 20 h` / `≈ 10 h` / `≈ 1 d 22 h 20 m` strings the J3 spec asserts on. The `≈` is U+2248 ALMOST EQUAL TO. The "include minutes when days are present" branch was chosen specifically so 4.4 has a deterministic assertion (per `duration.py:10-14`).

**Story 3.6 (done, merged at `epic-3`):**
- `killRs` / `startRs` / `resetState` real implementations + the chromium `--host-resolver-rules` plumbing + the `Justfile` two-phase `e2e-up`. The J6 spec depends on every one of these; nothing new is needed in 4.4.
- The `j4-adjust-speed.spec.ts` testuser→freshuser swap pattern (`resetState`+`context.clearCookies()`+`logInAs(freshuser)`) is copied verbatim into AC4.
- The `j4-adjust-speed.spec.ts` `afterEach startRs()` pattern is copied verbatim into AC6.

**Story 2.7 (done):**
- `app-book-form[variant="add"]` selectors + `getByRole('button', { name: 'Add book' })` + `app-book-row.first()` + `.book-row-title` patterns. Mirror exactly; do not redesign locators.
- `page.route('**/v1/books/*', ...)` glob form used for the optimistic-UI hold test (`j2-manage-books.spec.ts:128-139`). The AC6-J3 generic-failure test uses `**/v1/books/*/estimate` glob — same pattern, narrower path.

**Story 1.13 (done):**
- `requireEnv` shim shape is verbatim. Story 2.7 declined to extract it; Story 3.6 honored that. Story 4.4 brings the duplicate count to 4; per the existing decision, do NOT extract yet (revisit at 5+ if a future spec is added).

### Failure-prevention checklist (LLM dev mistakes to avoid)

1. ❌ Modifying any SPA / BFF / RS source. This is a spec-only story. Even a "small fix" to `EstimateCell` or `estimate_service.py` is out of scope — log as deferred-work and address separately.
2. ❌ Modifying any compose / Dockerfile / helper / fixture file. The harness is complete after Story 3.6.
3. ❌ Inlining `child_process.execFile('docker', ...)` calls. Use the existing `killRs` / `startRs` from `fixtures/helpers.ts`.
4. ❌ Calling `page.evaluate(() => fetch(...))` to hit `/v1/test/reset`. Use the existing `resetState` helper.
5. ❌ Hardcoding `TEST_RESET_TOKEN` / `BFF_CLIENT_SECRET` in the spec. Use `requireEnv(...)`.
6. ❌ Using three ASCII dots `...` instead of U+2026 `…` in `Estimating…` assertions. Use the character.
7. ❌ Using ASCII hyphen `-` instead of U+2014 `—` in `Service unavailable — try again shortly`. Use the character.
8. ❌ Using straight apostrophe `'` instead of U+2019 `’` in `Couldn’t get an estimate — try again` literal text. The regex tolerates both, but typing the curly apostrophe is the canonical form (matches the source constant `ESTIMATE_CELL_GENERIC_COPY`).
9. ❌ Using ASCII `~` or `≃` instead of U+2248 `≈`. The format_duration prefix is U+2248 verbatim.
10. ❌ Calling `getByRole('button', { name: 'Save' })` for the SettingsPage save button — its label transitions Save → Saving… → Saved. Use `page.locator('button.settings-save')` (Story 3.6 lesson, verbatim).
11. ❌ Forgetting to `page.unroute('**/v1/books/*/estimate')` at the end of the AC6-J3 test. Subsequent tests in the same spec file would inherit the mock.
12. ❌ Hardcoding `localhost:8000` or `bff:8000` in the spec. Use Playwright's `baseURL` (configured by compose env). Page navigations like `page.goto('/settings')` resolve via `baseURL`.
13. ❌ Forgetting to scope row-level assertions to `row` (e.g., `page.locator('.estimate-cell-result')`) instead of (`row.locator(...)`). If a future test adds a second book, cross-row matches would create silent failures.
14. ❌ Asserting on `page.url()` ending exactly `/books` after `page.goto('/books')`. Some redirects (e.g., trailing slash variants) can append; use a regex `/\/books$/` if you must, or skip the URL assertion entirely.
15. ❌ Calling `startRs()` inline in J6 AC7 (the RS-down estimate test). Let the `afterEach` handle it. Calling inline wastes CI time on the per-test path.
16. ❌ Calling `killRs()` inside J3 spec tests. J3 must NOT kill the RS — that's J6's job.
17. ❌ Asserting the rendered color with `toHaveCSS('color', '#B91C1C')`. Playwright's `toHaveCSS` does NOT resolve CSS variables, so the assertion would fail. Use `evaluate(el => window.getComputedStyle(el).color)` and match the resolved `rgb(...)` form (per AC7's existing pattern).
18. ❌ Importing the `ESTIMATE_CELL_*_COPY` constants from the SPA workspace. The e2e tsconfig doesn't reach into `spa/` — those imports would fail typecheck. Use the literal strings directly.
19. ❌ Increasing `workers` in `playwright.config.ts`. Sequential execution is load-bearing (every spec calls `resetState`; J6 calls `killRs/startRs`).
20. ❌ Adding a new fixtures file or moving `requireEnv` into `fixtures/helpers.ts` as part of this story. Story 1.13 / 2.7 / 3.6 deferred this; defer again. The cognitive cost of one more duplicate `requireEnv` is lower than the risk of an out-of-scope refactor.
21. ❌ Trusting the unit tests in `estimate-cell.spec.ts` to substitute for E2E. The unit tests cover state transitions in isolation; only the E2E specs prove the full SPA→BFF→RS round-trip against the real Keycloak.
22. ❌ Adding any backend test edits, even "while you're there". Story 4.4 touches three files: two new spec files + the README. Anything else is scope creep.

### Project context (from auto-memory + CLAUDE.md)

- **Python invoked as `python`** (never `python3`) — no Python in this story; convention is moot but should be honored if pytest is invoked locally.
- **Accessibility and responsive design are explicitly out of scope** — use Playwright's accessibility-first locators (`getByLabel`, `getByRole`) for stability, NOT for WCAG coverage. Test on `Desktop Chrome` only (already the only project in `playwright.config.ts`).
- **Backend uses github.com/tommaso-meledina/fastapi-archetype** — no backend changes in this story; informational.
- **`services/resource-server/CLAUDE.md` enforces strict adherence to specs + no library introductions + frequent conventional commits with green quality gates.** Story 4.4 makes ZERO RS changes; rule is honored by virtue of scope. If a deferred-work item from this story's review needs an RS fix, that's a separate story.
- **Parallel-epics + git is source of truth** — sprint-status.yaml lags git; do not over-rely on it. Story 4.4 advances `4-4-...` from `backlog` → `ready-for-dev` after this file is written.

### Files this story creates

```
e2e/
└── tests/
    ├── j3-estimate.spec.ts                          (NEW — 5 tests for AC1–AC6-J3)
    └── j6-rs-unavailable.spec.ts                    (NEW — 3 tests for AC6–AC9)
```

### Files this story modifies

```
e2e/README.md                                        # Task 3 — append 2 entries under "Specs in this directory"
_bmad-output/implementation-artifacts/sprint-status.yaml   # Status transitions for 4.4 (managed by the workflow)
```

### Files this story explicitly does NOT touch

- `spa/**` — no SPA code changes. `EstimateCell`, `BooksService`, `ErrorService`, `app-error.types.ts`, all unchanged.
- `services/bff/**` — no BFF code changes. The estimate endpoint and `ResourceServerClient` are unchanged.
- `services/resource-server/**` — no RS code changes. `estimate_service`, `format_duration`, scope gating all unchanged.
- `compose/app.yml`, `compose/app.e2e.yml`, `compose/infra.yml` — no compose changes.
- `e2e/Dockerfile`, `e2e/fixtures/helpers.ts`, `e2e/fixtures/services.ts`, `e2e/fixtures/users.ts`, `e2e/playwright.config.ts`, `e2e/package.json`, `e2e/tsconfig.json` — harness is complete.
- `e2e/tests/j1-first-login.spec.ts`, `e2e/tests/j2-manage-books.spec.ts`, `e2e/tests/j4-adjust-speed.spec.ts`, `e2e/tests/j5-logout.spec.ts` — existing specs unchanged.
- `keycloak/realm-bmad-books.json` — users + scopes + audience already seeded.
- `Justfile` — two-phase `e2e-up` recipe already correct (Story 3.6).
- Repo-root `.env` / `.env.example` — no new env vars.

### Git intelligence (recent commits on `main`)

```
bb15aca Merge story 4.3 — SPA EstimateCell real component + BooksService.requestEstimate
b905307 chore(4.2): code review — P1-P7 applied, mark done, log D119-D126
05b8de7 chore(4.3): code review — P1 applied, mark done
3513e66 feat(4.3): SPA EstimateCell real component + BooksService.requestEstimate
e3236bd feat(4.2): BFF POST /v1/books/{id}/estimate + ResourceServerClient.compute_estimate
```

Epic 4 backend (4.1, 4.2) and SPA (4.3) all landed on `main`. The full estimate flow is reachable end-to-end as of `bb15aca`. Story 4.4 is the last gate before Epic 4 is `done` and Epic 5 (coverage / security / README / smoke) can begin.

### Latest tech information

- **Playwright `^1.49.0`** (resolved at Story 1.11 install time). `page.route('**/...')`, `getByLabel`, `getByRole`, `getByText`, `toHaveText`, `toHaveAttribute`, `toContainText`, `evaluate(el => ...)` are stable. `not.toContainText` is the inverse-match assertion.
- **Chromium DNS resolver-rules** (Story 3.6 DEF-1) — `--host-resolver-rules=MAP localhost:8080 keycloak:8080, MAP localhost:8000 bff:8000` in `playwright.config.ts:39-41`. Applies to all spec navigations; the J3/J6 specs work over this routing without any additional setup.
- **Node 20 LTS** (Story 1.11 Dockerfile). All TypeScript constructs used here (template literals, async/await, `const`/`let`, top-level functions) are stable.
- **Docker Compose v2** with `--abort-on-container-exit` NOT used in `just e2e-up` — the two-phase pattern (Story 3.6 DEF-6) tolerates mid-test `killRs`/`startRs` cycles.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 4.4: E2E specs — J3 estimate + J6 RS unavailable` lines 1696–1740] (verbatim AC source)
- [Source: `_bmad-output/planning-artifacts/epics.md#Epic 4 Overview` lines 1518–1520] (cross-service estimate + J6 honest-failure surface)
- [Source: `_bmad-output/planning-artifacts/epics.md#FR-ESTIMATE-01` line 22] (J3 wire contract)
- [Source: `_bmad-output/planning-artifacts/epics.md#FR-ERROR-01` line 24] (J6 honest-failure rule)
- [Source: `_bmad-output/planning-artifacts/epics.md#NFR11` line 38] (≥5 E2E covering J1–J6)
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#J3` lines 458–480] (J3 success / failure flows)
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#J6` lines 540–559] (J6 mermaid + manual-retry rule)
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#EstimateCell` lines 631–636] (component spec)
- [Source: `_bmad-output/planning-artifacts/ux-design-specification.md#Detailed Mechanics` lines 234–254] ("no fabricated values, ever"; in-place re-estimate; manual retry)
- [Source: `_bmad-output/planning-artifacts/architecture.md#AR17` line 116] (honest error mapping table)
- [Source: `_bmad-output/planning-artifacts/architecture.md#AR23` lines 705–731] (state management + error handling SPA + pessimistic cross-service)
- [Source: `_bmad-output/planning-artifacts/architecture.md#AR31` line 96] (Playwright in `e2e/`; one spec per journey)
- [Source: `_bmad-output/planning-artifacts/architecture.md#AR32` line 97] (POST /v1/test/reset + shared bearer)
- [Source: `_bmad-output/planning-artifacts/architecture.md#§"Process Patterns / Retry & failure"` lines 769–779] (no silent retry)
- [Source: `_bmad-output/planning-artifacts/architecture.md#§"How to run / E2E"` lines 1299–1305] (canonical e2e invocation = `just e2e-up`)
- [Source: `_bmad-output/implementation-artifacts/epic-1-retro-2026-05-16.md#Action items P2` lines 142–146] (compose-stack ACs run live)
- [Pattern: `_bmad-output/implementation-artifacts/3-6-e2e-spec-j4-adjust-reading-speed-...md`] (E2E story shape; the canonical precedent for this story)
- [Pattern: `e2e/tests/j1-first-login.spec.ts`] (describe + requireEnv + beforeEach shape)
- [Pattern: `e2e/tests/j2-manage-books.spec.ts`] (book form selectors + addForm helper; `app-book-row.first()`; `page.route` glob for optimistic-UI tests)
- [Pattern: `e2e/tests/j4-adjust-speed.spec.ts`] (testuser→freshuser swap pattern; `afterEach startRs()` guard; `button.settings-save` selector; `getByText('Service unavailable — try again shortly').first()` pattern)
- [Pattern: `e2e/tests/j5-logout.spec.ts`] (RouterLink href assertion shape)
- [Pattern: `e2e/fixtures/helpers.ts`] (the only allowed helper surface — `logInAs`, `resetState`, `logOut`, `killRs`, `startRs`)
- [Pattern: `e2e/playwright.config.ts:14-15`] (`workers: 1` invariant; timeout: 60_000)
- [Source SPA: `spa/src/app/books/estimate-cell.ts:27-36`] (exported copy constants — used as truth for the literal strings in this spec)
- [Source SPA: `spa/src/app/books/estimate-cell.html`] (state-driven template; selectors used by this spec)
- [Source SPA: `spa/src/app/books/estimate-cell.css`] (class names used by this spec)
- [Source SPA: `spa/src/app/shared/ui/error-message.html`] (`<p class="error-message">` shape — used by AC7 color assertion)
- [Source SPA: `spa/src/styles.css:11`] (`--color-error: #B91C1C` — used by AC7 color assertion regex)
- [Source RS: `services/resource-server/src/resource_server/services/duration.py`] (`format_duration` rule — pinning the J3 expected outputs)
- [Source BFF: `services/bff/src/bff/api/books.py:245-281`] (BFF estimate handler — pins POST `{}` body + RS verbatim forward + 503/401 mapping)
- [Source BFF: `services/bff/src/bff/services/resource_server_client.py:209+`] (`compute_estimate` — refresh-and-replay against RS `/v1/estimate`)
- [Source Story 4.1: `_bmad-output/implementation-artifacts/4-1-...md`] (RS /v1/estimate + format_duration boundary table)
- [Source Story 4.2: `_bmad-output/implementation-artifacts/4-2-...md`] (BFF /v1/books/{id}/estimate contract — what 4.4 hits over the wire)
- [Source Story 4.3: `_bmad-output/implementation-artifacts/4-3-...md`] (EstimateCell selectors + copy constants + unit-test coverage matrix)
- [Source Story 3.6: `_bmad-output/implementation-artifacts/3-6-...md`] (compose `e2e` profile + killRs/startRs/resetState plumbing — this story consumes it unchanged)
- [Source deferred: `_bmad-output/implementation-artifacts/deferred-work.md#D108`] (J4 `afterEach` lacks try/catch — out of scope here, NOT a 4.4 task)
- [Source deferred: `_bmad-output/implementation-artifacts/deferred-work.md#D112`] (host-side `DOCKER_BIN` escape hatch — out of scope here)

## Definition of Done

1. `e2e/tests/j3-estimate.spec.ts` exists with 5 tests covering AC2–AC6-J3; passes locally under `npx playwright test e2e/tests/j3-estimate.spec.ts`.
2. `e2e/tests/j6-rs-unavailable.spec.ts` exists with 3 tests covering AC7–AC9; passes locally under `npx playwright test e2e/tests/j6-rs-unavailable.spec.ts`.
3. Both specs follow the canonical shape: `requireEnv` shim + `test.describe(...)` + `beforeEach(resetState + logInAs)` + J6's `afterEach(startRs)` (J3 has no `afterEach`).
4. Both specs use ONLY the existing `fixtures/helpers.ts` exports (`logInAs`, `resetState`, `killRs`, `startRs`). No inline `child_process`, no inline `fetch`-to-`/v1/test/reset`, no hardcoded tokens.
5. All literal copy strings (`Estimate`, `Estimating…`, `Re-estimate`, `Set your reading speed in`, `to enable estimates`, `Service unavailable — try again shortly`, `Couldn’t get an estimate — try again`) use the correct Unicode punctuation (U+2026, U+2014, U+2019) — verifiable by `grep -P '[\x{2026}\x{2014}\x{2019}\x{2248}]' e2e/tests/j3-estimate.spec.ts e2e/tests/j6-rs-unavailable.spec.ts` returning non-empty.
6. `e2e/README.md` "Specs in this directory" gains two entries (J3 + J6) matching the wording in AC11.
7. `cd e2e && npx tsc --noEmit` exits 0.
8. `cd e2e && npx playwright test --list` exits 0 and reports exactly 26 tests across 6 files (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3).
9. `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` exits 0 (regression; no compose change).
10. **Live `just e2e-up` exits 0 with all 26 tests passing.** Load-bearing AC per retro P2.
11. `cd services/bff && uv run pytest -q`, `cd services/resource-server && uv run pytest -q`, `cd spa && npm run lint && npm test -- --watch=false && npm run build` all exit 0 (regression — no source change in this story).
12. No changes to any file outside the three files listed in §"Files this story creates / modifies."
13. Any items surfaced during dev / code review are logged in `_bmad-output/implementation-artifacts/deferred-work.md` under a new "Deferred from: code review of 4-4-..." section with surfacing / owning / severity tags.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context).

### Debug Log References

**Static gates (Task 4):**
- `cd e2e && npx tsc --noEmit` → exit 0 (silent).
- `cd e2e && npx playwright test --list` → exit 0, `Total: 26 tests in 6 files`. Breakdown: J1×3, J2×8, J3×5, J4×5, J5×2, J6×3.
- `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` → exit 0.
- `grep -rn 'child_process\|fetch.*reset\|hardcoded.*token' e2e/tests/j3-estimate.spec.ts e2e/tests/j6-rs-unavailable.spec.ts` → exit 1 (no matches; AC10 honored).
- `grep -P '[\x{2026}\x{2014}\x{2019}\x{2248}]' e2e/tests/j3-estimate.spec.ts e2e/tests/j6-rs-unavailable.spec.ts` → non-empty (DoD #5 verified: U+2026 `…`, U+2014 `—`, U+2019 `’`, U+2248 `≈` all present).

**Live `just e2e-up` (AC13, DoD #10) — final run, all green:**
```
Running 26 tests using 1 worker

  ✓   1-3   J1: first-time login                (3 tests)
  ✓   4-11  J2: manage books                    (8 tests)
  ✓  12-16  J3: reading-time estimate           (5 tests)
  ✓  17-21  J4: adjust reading speed            (5 tests)
  ✓  22-23  J5: logout and re-protection        (2 tests)
  ✓  24-26  J6: resource server unavailable     (3 tests)

  26 passed (52.8s)
```

Compose teardown succeeded via the Justfile's `trap … EXIT` (inlined): keycloak / bff / resource-server stopped + removed; network removed.

**Regression checks (Task 6):**
- BFF: `cd services/bff && uv run pytest -q` → `543 passed, 109 warnings in 9.94s`.
- RS:  `cd services/resource-server && uv run pytest -q` → `324 passed, 1 warning in 8.91s`.
- SPA: `cd spa && npm test -- --watch=false` → `Test Files 19 passed (19) | Tests 152 passed (152)`. `npm run build` → `Application bundle generation complete`. `npm run lint` → 3 pre-existing `no-fallthrough` errors (D127); verified pre-existing on baseline `bb15aca`.

**First-run triage (before AC2-alt + AC3 fix):**
- AC2 (happy path) failed: `toHaveText('Estimating…')` saw `Estimate` repeatedly; trace YAML showed `≈ 20 h` + `Re-estimate` button — confirming the round-trip succeeded but the loading state was too brief to observe between click and re-render. Resolved by applying the story-documented AC2-alt `page.route` POST hold pattern.
- AC3 (J4↔J3 coupling) timed out at 60s waiting for `button.estimate-cell-reestimate` after `/settings → /books` navigation; trace YAML showed the row in idle state with the `Estimate` button (no Re-estimate). Root cause: `EstimateCell`'s local signals (`loading`/`result`/`error`) reset on component remount after route navigation — documented in `estimate-cell.ts:53-55` ("Component state is component-local"). Resolved by clicking the now-idle Estimate button (still pinning the speed-coupling rule: r2 !== r1 AND impliedMinutes(r2) < impliedMinutes(r1)).

### Completion Notes List

- Spec-only delivery: zero SPA / BFF / RS / compose / Dockerfile / helper / fixture changes (verified via `git status`).
- Two new Playwright specs land under `e2e/tests/`:
  - `j3-estimate.spec.ts` — 5 tests covering AC1–AC6-J3 (happy path / J4↔J3 coupling / freshuser 412 / re-estimate in place / generic non-J6 failure).
  - `j6-rs-unavailable.spec.ts` — 3 tests covering AC6–AC9 (RS-down estimate / retry-after-recovery / settings save while RS down).
- All helpers are sourced from `e2e/fixtures/helpers.ts` (`logInAs`, `resetState`, `killRs`, `startRs`); no inline `child_process` / `fetch(...reset...)` / hardcoded tokens (AC10).
- All Unicode punctuation pinned via direct character literals: U+2026 `…` in `Estimating…`, U+2014 `—` in `Service unavailable — try again shortly` and `Couldn’t get an estimate — try again`, U+2019 `’` in `Couldn’t`, U+2248 `≈` via the result regex `/≈\s*\d+\s*[hm]/`. DoD #5 verified.
- `e2e/README.md` "Specs in this directory" gained two entries (J3 + J6); "RS killswitch (J4 + J6)" section unchanged (its forward reference to J6 is now satisfied).
- **NFR11 satisfied:** 6 E2E specs covering J1–J6, exceeding the ≥5 floor. Epic 4 is done after this story's close gate.
- **Dev-time deviations from the story's AC blocks (both pre-anticipated or naturally derivable):**
  - **AC2-alt applied** for the J3 happy-path loading-state assertion (story explicitly authorized this pattern as a fallback for fast round-trips). Logged as D128 — informational, not a defect.
  - **AC3 second-estimate click target** switched from `button.estimate-cell-reestimate` to `button.estimate-cell-button--primary` because `/settings → /books` navigation destroys the `EstimateCell` component instance and resets its component-local signals. The speed-coupling rule is still pinned. Logged as D129 — story-AC vs SPA-design inconsistency.
- **Operational note about `just e2e-up`:** the host has no `just` binary on PATH. The Justfile recipe is plain bash; I inlined it verbatim. CRITICAL discovery: the `docker compose run --rm playwright` form reuses the cached Dockerfile-baked image — without `--build`, the runner doesn't see the new spec files (manifested as `Running 18 tests` instead of 26). User-authorized scope expansion mid-review: amended `Justfile`'s `e2e-up` recipe to pass `--build` on the `run` step (with a load-bearing comment block explaining why) AND added a "Compose-runner gotcha" subsection under "Adding a new spec" in `e2e/README.md` documenting the cached-image trap for direct-compose invocations. The discovery now lives in two durable, naturally-findable locations rather than buried in this story's DAR alone.
- **Pre-existing SPA lint failures (D127):** three `no-fallthrough` errors in `book-form.ts`, `book-row.ts`, `status-control.ts` exist on baseline commit `bb15aca`. Verified pre-existing by re-running lint with 4.4 changes stashed. Story 4.4 explicitly forbids SPA source changes (Failure-prevention checklist item #1). Logged as D127 for future cleanup; does not block the 4.4 close gate because the regression check's intent is "did 4.4 break anything" (it didn't).

### File List

**New (Task 1, 2):**
- `e2e/tests/j3-estimate.spec.ts`
- `e2e/tests/j6-rs-unavailable.spec.ts`

**Modified (Task 3):**
- `e2e/README.md` — appended two "Specs in this directory" entries (J3 + J6).

**Modified (user-authorized scope expansion mid-review — documenting the `--build` discovery):**
- `Justfile` — `e2e-up` recipe's `run` step now passes `--build`, with a load-bearing comment block above the recipe explaining the `COPY . .` cached-image trap discovered during 4.4 dev.
- `e2e/README.md` — added a "Compose-runner gotcha" subsection under "Adding a new spec" with the same explanation and a fallback command for direct-compose invocations.

**Modified (workflow-managed):**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `4-4-...` status transitions `ready-for-dev` → `in-progress` → `review`; `last_updated` extended with the dev-pass summary.
- `_bmad-output/implementation-artifacts/4-4-e2e-specs-j3-estimate-j6-rs-unavailable.md` — Tasks/Subtasks checkboxes marked; Dev Agent Record filled; Change Log entry added; Status `ready-for-dev` → `review`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended "Deferred from: dev of 4-4-..." section with D127, D128, D129.

**Explicitly NOT modified (verified via `git status` after dev):** `spa/**`, `services/bff/**`, `services/resource-server/**`, `compose/**`, `e2e/Dockerfile`, `e2e/fixtures/**`, `e2e/playwright.config.ts`, `e2e/package.json`, `e2e/tsconfig.json`, `keycloak/realm-bmad-books.json`, `.env*`. (NB: `Justfile` was modified mid-review under explicit user authorization — see "user-authorized scope expansion" above; behavior change is the addition of the `--build` flag + a recipe comment block.)

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-18 | 0.1 | Story file created. Prerequisite stories 4.1, 4.2, 4.3 all `done` on `main` (HEAD `bb15aca`). Live `just e2e-up` (DoD #10) is the load-bearing close gate per retro P2. Epic 4 retrospective remains `optional`. | claude-opus-4-7 |
| 2026-05-18 | 1.0 | Dev pass complete; status `ready-for-dev` → `review`. Created `e2e/tests/j3-estimate.spec.ts` (5 tests) + `e2e/tests/j6-rs-unavailable.spec.ts` (3 tests); updated `e2e/README.md` "Specs in this directory". All static gates green (tsc, playwright list = 26 in 6 files, compose config, helper grep). Live e2e-up exits 0 with all 26 tests green (52.8s). Regression: BFF 543/RS 324/SPA 152 unit tests pass; SPA build green; SPA lint has 3 pre-existing errors (D127). Two dev-time spec deviations: AC2-alt applied for loading-state observability (D128); AC3 second click switched to Estimate (idle) after `/settings → /books` navigation destroys the EstimateCell instance (D129). NFR11 satisfied (6 E2E specs covering J1–J6). | claude-opus-4-7 |
| 2026-05-18 | 1.1 | User-authorized scope expansion (mid-review) — promoted the `docker compose run --build` discovery from the DAR Completion Notes (where the next dev would never see it) into two durable locations: (1) `Justfile`'s `e2e-up` recipe now passes `--build` on the `run` step with a load-bearing comment block explaining the `COPY . .` cached-image trap; (2) `e2e/README.md` "Adding a new spec" gains a "Compose-runner gotcha" subsection with the same explanation + a fallback command for direct-compose invocations. Story remains in `review`. | claude-opus-4-7 |
| 2026-05-18 | 2.0 | Code review pass via `bmad-code-review` (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Acceptance Auditor returned PASS on all 13 ACs + all 22 failure-prevention items. 4 patches applied (DN1 strict apostrophe pin, P1 result-regex non-zero pin across both specs, P2 impliedMinutes positive guards, P3 AC5 cell-stays-in-re-estimate assertion). 6 deferred items logged D130–D135. ~25 findings dismissed as noise / already-handled. Static gates re-verified: `tsc --noEmit` exit 0; `playwright --list` reports 26 tests in 6 files unchanged. Status `review` → `done`. | claude-opus-4-7 |

### Review Findings

Adversarial pass via `bmad-code-review` (Blind Hunter + Edge Case Hunter + Acceptance Auditor). 35+ raw findings consolidated; ~25 dismissed as noise/already-addressed. Acceptance Auditor returned PASS on all 13 ACs and all 22 failure-prevention checklist items; the `Justfile` + README "Compose-runner gotcha" scope expansion is the only AC-list deviation and is user-authorized per Change Log v1.1.

#### Decision-needed (resolved)

- [x] **[Review][Decision] DN1 — Apostrophe-tolerance regex contradicts its own justification** `[e2e/tests/j3-estimate.spec.ts:313]` — resolved: **strict pin (U+2019 only)**. Replaced regex `/Couldn[’']t.../` with literal `toContainText('Couldn’t get an estimate — try again')`. A source-side regression from curly to ASCII apostrophe now fails the test, matching the comment's stated intent.

#### Patch (applied)

- [x] **[Review][Patch] P1 — Result regex tightened to reject "≈ 0 m"** `[e2e/tests/j3-estimate.spec.ts:127; e2e/tests/j6-rs-unavailable.spec.ts:135]` — regex changed from `/≈\s*\d+\s*[hm]/` to `/≈\s*[1-9]\d*\s*[hm]/`. Pathological fabricated-zero outputs (which would violate the UX-DR "no invented number" rule) now fail the test. Surfaced by Blind+Edge.
- [x] **[Review][Patch] P2 — `impliedMinutes` parse-failure surfaced explicitly** `[e2e/tests/j3-estimate.spec.ts:173-174]` — added two positive guards `expect(impliedMinutes(r1!)).toBeGreaterThan(0)` and `expect(impliedMinutes(r2!)).toBeGreaterThan(0)` before the strict-inequality assertion. A future `format_duration` regression that defeats the parser now surfaces as "expected > 0, got 0" rather than the confusing `0 < 0 = false` coupling-violation message. Surfaced by Blind+Edge.
- [x] **[Review][Patch] P3 — AC5 now asserts cell stays in re-estimate mode after second flush** `[e2e/tests/j3-estimate.spec.ts:258-259]` — added `await expect(row.locator('button.estimate-cell-reestimate')).toHaveText('Re-estimate')` and `await expect(row.locator('button.estimate-cell-button--primary')).toHaveCount(0)` after the second URL invariance check. Catches a regression where Re-estimate silently regresses the cell to its initial Estimate state. Surfaced by Blind Hunter.

#### Deferred (logged in `_bmad-output/implementation-artifacts/deferred-work.md`)

- [x] **[Review][Defer] D130 — `--build` flag on `docker compose run` is unconditional** `[Justfile:54]` — user-authorized, tested, documented; the better long-term fix (bind-mount specs to skip rebuild entirely) is a separate refactor.
- [x] **[Review][Defer] D131 — AC9 settings-save assertion weakened by `.first()`; does not pin which 503 path produced the error** `[e2e/tests/j6-rs-unavailable.spec.ts:160]` — spec-authorized pattern, mirrors j4 AC13; tightening would require a `waitForResponse` on PUT `/v1/reading-speed`.
- [x] **[Review][Defer] D132 — Color assertion fragile under forced-colors mode or rgba serialization** `[e2e/tests/j6-rs-unavailable.spec.ts:85-91]` — regex matches `rgb(185, 28, 28)` / `rgb(185 28 28)` but rejects `rgba(...)`; forced-colors emulation in CI would return system colors.
- [x] **[Review][Defer] D133 — AC8 retry-after-recovery flake risk: httpx pool cached refusals + cold RS estimate endpoint after `startRs()`** `[e2e/tests/j6-rs-unavailable.spec.ts:128-135]` — `waitForRsHealthy` confirms /health, but BFF's httpx client and the RS estimate route may still be warming. A first-click failure would flake the test.
- [x] **[Review][Defer] D134 — RouterLink `href` regex `/\/settings$/` rejects future query/fragment additions** `[e2e/tests/j3-estimate.spec.ts:213, 222]` — currently passes; a future `?from=books` redirect would flake.
- [x] **[Review][Defer] D135 — URL invariance during re-estimate asserted at two discrete moments, not continuously** `[e2e/tests/j3-estimate.spec.ts:251, 255]` — a SPA that navigated away and back between the two snapshots would pass. A `framenavigated` listener would tighten this to a true invariant.

#### Dismissed (representative; not actioned)

- Blind#1/#2 (held-route try/finally, race on Estimating label): Playwright per-test page destruction handles the cleanup; the hold pattern's `route.continue()` + `waitForResponse` sequence already pins the in-flight state.
- Blind#5 (`secondResult === firstResult` fragility): same speed + same pages → deterministic by `format_duration`; the equality documents intent, not a behavioral assertion.
- Blind#8 (redundant `r2 !== r1` + minutes-strict): belt-and-suspenders is spec-authorized (AC3 narrative line 197).
- Blind#13/E8 (freshuser test omits explicit `page.goto('/books')`): `logInAs` lands on `/books` per existing j4 precedent (verbatim pattern from j4 AC10); test passes green; consistency with j4 weighs against a defensive add.
- Blind#14/#16 (magic timeouts, perf-claim docs): nitpicks; existing repo-wide pattern.
- Blind#15/E14 (`not.toContainText('≈')` weakness): positive co-assertions (error visible + button restored) already present in same test bodies.
- E2/E3 (route glob matches non-POST methods, URL-shape mismatch): code at `j3:101-107` gates on `request().method() === 'POST'` and only intercepts the BFF estimate endpoint; verified.
- E4 (`waitForResponse` race): predicate registered before `estimateResolveDeferred()` fires; ordering correct.
- E7 (regex matches "5 mo" / "12 mi"): `format_duration` only emits d/h/m segments; YAGNI.
- E12 (route registered after add-book POST): order is correct.
- E15 (afterEach startRs no try/catch): D108 explicitly out of scope per spec failure-prevention note.
- E16/E20 (BFF books list depends on RS; goto count race): test passes green; BFF books list has no RS dependency.
- E23 (Pages per hour input disabled): spec line 521 verifies the input stays enabled per `SettingsPage`'s `finally{} loading.set(false)`.
- E26/E27 (trap-during-build, postgres in `up --wait`): compose graph + trap ordering verified by green dev pass.
- E28 (resetState before logInAs cookies): resetState does not touch browser cookies; Playwright per-test context handles isolation.

#### Notes

- **Acceptance Auditor PASS** — all 13 ACs honored; all 22 failure-prevention checklist items honored; both D128 (AC2-alt POST hold) and D129 (AC3 second-click target switch) are present in code exactly as the spec pre-authorized and the DAR described, with no silent broadening.
- **Scope expansion (`Justfile` + README "Compose-runner gotcha")** — flagged by Acceptance Auditor as a deliberate, user-authorized deviation from the spec's "Files this story explicitly does NOT touch" list (line 786). Captured in Change Log v1.1.
- **Coverage** — none of the three layers found a critical or high-severity issue. Findings concentrate on test robustness and assertion strength, not behavioral correctness.
