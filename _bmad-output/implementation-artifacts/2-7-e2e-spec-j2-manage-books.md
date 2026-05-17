---
status: review
story_key: 2-7-e2e-spec-j2-manage-books
created: 2026-05-17
---

# Story 2.7: E2E spec — J2 manage books

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer of the OAuth/OIDC reference,
I want a Playwright E2E spec that exercises the full J2 journey against the running compose stack — add, optimistic status change, edit, delete with confirm, inline-error rendering, and cross-user isolation,
So that the second user journey is demonstrably correct on every CI-style run from the day Epic 2 ships.

## Scope (read this first)

This story closes Epic 2 by adding the **only** missing piece: the J2 Playwright spec exercising the full stack end-to-end. Stories 2.1–2.6 delivered the BFF surface (`/v1/books` CRUD, the `books`-table truncation in `/v1/test/reset`) and the SPA surface (`BookListPage`, `BookRow`, `StatusControl`, `BookForm[add|edit]`, `BooksService`); this story consumes all of them from a real browser against the real stack — no mocks at any layer.

Concretely, this story:

1. **Adds** a single new spec file: `e2e/tests/j2-manage-books.spec.ts`. The spec uses `test.describe('J2: manage books', () => { ... })`, a `beforeEach` calling `resetState(...)` then `logInAs(page, testuser)`, and (per the epic) AT MINIMUM eight test cases — see ACs below.
2. **Extends** `e2e/fixtures/helpers.ts` with one new helper: `logOut(page: Page): Promise<void>`. Required by the cross-user isolation case (epic line 1104 enumerates `logOut` as a helper the spec calls). The implementation is three lines (click `Log out`, wait for `/login`); it lives in `helpers.ts` rather than inline in the spec so future J5-adjacent specs reuse it.
3. **Updates** `e2e/README.md`'s "Specs in this directory" section to add a one-paragraph entry for `j2-manage-books.spec.ts` mirroring the J1 / J5 paragraphs. No new env vars, no compose changes — the e2e profile already plumbs everything (Story 1.13 wired `TEST_RESET_TOKEN`, Story 2.3 extended `/v1/test/reset` to truncate `books`).

Out of scope for 2.7:

- Any change to BFF code. `/v1/books` CRUD (Story 2.2), `/v1/test/reset` truncating `books` (Story 2.3) are frozen.
- Any change to SPA code. `BookListPage` (Story 2.5), `BookRow` / `StatusControl` / `BookForm[add|edit]` (Story 2.6) are frozen — the spec drives them via the DOM, NEVER by importing or stubbing Angular code.
- Race-window assertions for the optimistic status change. The "the select shows the new value before the network round-trip completes" claim is hard to assert deterministically against a sub-millisecond local stack; the AC below scopes the optimistic-UI assertion to the conventional Playwright pattern (`route.continue()` with a small delay) rather than promising sub-resolution race detection. Decimal-pages client-side validation (Story 2.5 D57) is out of scope — the J2 spec exercises the integer happy path and the `pages=0` validation path only.
- Concurrent-action races (D54, D58, D62) — explicitly deferred in their parent stories and out of scope here.
- Per-test trace/screenshot/video customization. The harness-wide config (Story 1.11 `playwright.config.ts`: `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'`) is correct and unchanged. **Do not override per-test.**
- Visual regression / screenshot comparison. Accessibility and responsive-design are explicitly out of scope for the project (per `_bmad/custom` user memory).
- J3, J4, J6 specs. Owned by their respective epic stories (3.6, 4.4, etc.).

## Existing patterns to mirror

These are the load-bearing prior-art references the dev agent must consume before writing a single line of spec:

- **`e2e/fixtures/helpers.ts`** (Story 1.11) — `logInAs(page, user)` performs the full OAuth round-trip (clicks `Log in`, waits for the Keycloak `/realms/bmad-books/protocol/openid-connect/auth` URL, fills credentials, waits for `/books`, asserts the `Signed in as <username>` identity block). `resetState(request, { resetToken })` POSTs to `/v1/test/reset` with bearer auth and throws on non-204. The `request.post('/v1/test/reset', ...)` call uses Playwright's `APIRequestContext` which honors the `baseURL` from `playwright.config.ts`. **Do not inline either of these flows in the spec.**
- **`e2e/fixtures/users.ts`** (Story 1.11) — `testuser` (`testpassword`) and `freshuser` (`freshpassword`) are the two seeded users. Both have `subPattern` regexes for sub-uuid assertions, but the J2 spec never needs to assert on `sub`.
- **`e2e/tests/j1-first-login.spec.ts`** (Story 1.13) — the canonical `requireEnv(name)` helper pattern for fail-fast on missing `TEST_RESET_TOKEN`. **Copy this helper into the J2 spec file** (not yet extracted to `helpers.ts` — Story 1.13 declined that refactor; the duplication is intentional per Story 1.13 Dev Notes).
- **`e2e/tests/j5-logout.spec.ts`** (Story 1.13) — the shape of a `beforeEach` that calls both `resetState` AND `logInAs`, in that order. The J2 spec mirrors this verbatim (reset → login).
- **`spa/src/app/books/book-form.ts`** (Story 2.6) — **Story 2.6 renamed `BookForm`'s outputs from `save`/`cancel` to `bookSaved`/`editCancelled`.** The J2 spec interacts with `BookForm` exclusively via the DOM (clicking the Save / Cancel buttons), NOT via these outputs, so this rename does not change the spec's API surface — but the dev agent must be aware of it when reading the BookForm code as ground truth for selectors / button labels (`book-form.html`: `<button class="book-form-submit">{{ idleButtonLabel }}</button>` where `BOOK_FORM_ADD_BUTTON_IDLE === 'Add book'`, `BOOK_FORM_EDIT_BUTTON_IDLE === 'Save'`, `BOOK_FORM_EDIT_CANCEL_LABEL === 'Cancel'`).
- **`spa/src/app/books/book-row.ts`** (Story 2.6) — `BOOK_ROW_DELETE_CONFIRM_MESSAGE === 'Delete this book?'`. The SPA uses native `window.confirm`, so Playwright handles it via `page.on('dialog', d => d.accept())` / `d.dismiss()`. The Edit/Delete buttons render as text buttons inside `.book-row-actions`. The status `<select>` is `<app-status-control>` inside the row.
- **`spa/src/app/books/book-list.ts`** (Story 2.6) — `BOOK_LIST_EMPTY_COPY === 'No books yet. Add one above.'`. This is the literal string the cross-user isolation case asserts visible.
- **`services/bff/src/bff/api/books.py`** (Story 2.2) — wire shape the spec implicitly relies on: `POST /v1/books` returns 201 + `Location: /v1/books/{id}` + body `{id, title, pages, status, created_at, updated_at}`; `PATCH /v1/books/{id}` returns 200 + updated body; `DELETE /v1/books/{id}` returns 204 empty; `GET /v1/books` returns the user's array.
- **`services/bff/src/bff/api/test_reset.py`** (Stories 1.12 + 2.3) — `/v1/test/reset` truncates `sessions`, `auth_states`, and `books`. After Story 2.3 the spec relies on this to start each test from zero books. **Do not call `/v1/books` directly to clean up** — `resetState` is the contract.

## Acceptance Criteria

**AC1 — `e2e/tests/j2-manage-books.spec.ts` exists with the spec'd shape.**

- File path: `e2e/tests/j2-manage-books.spec.ts` (sibling to `j1-first-login.spec.ts` and `j5-logout.spec.ts`).
- Uses `test.describe('J2: manage books', () => { ... })`.
- The file's imports are EXACTLY (no others, no inline Keycloak / `/v1/test/reset` plumbing):
  ```ts
  import { expect, Page, test } from '@playwright/test';
  import { logInAs, logOut, resetState } from '../fixtures/helpers';
  import { freshuser, testuser } from '../fixtures/users';
  ```
- A `requireEnv(name: string): string` helper is included at the top of the file (verbatim copy of the J1 spec's, including the "See e2e/README.md" error message), used to fail-fast on missing `TEST_RESET_TOKEN`. **Do not extract this helper to `helpers.ts` in this story** — Story 1.13 declined that refactor; consistency wins.
- `beforeEach` (in this order):
  1. `await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') })` — truncates `sessions`, `auth_states`, AND `books` (Story 2.3 extension).
  2. `await logInAs(page, testuser)` — leaves the page on `/books` with a valid `bff_session` cookie and the `Signed in as testuser` identity block visible.

**AC2 — `adding a book makes it appear at the top of the list` test case.**

1. (Page is on `/books`, books list is empty, the `BOOK_LIST_EMPTY_COPY === 'No books yet. Add one above.'` is visible.)
2. Locate the add-form's three inputs by formControlName via CSS (the labels do not declare `for=` so `getByLabel` would require DOM restructure):
   - `page.locator('app-book-form[variant="add"] input[formcontrolname="title"]')`,
   - `page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]')`,
   - `page.locator('app-book-form[variant="add"] select[formcontrolname="status"]')`.
3. Fill `title = "Dune"`, `pages = "688"`, select `status = "to-read"`. (Note: type `"688"` — `page.locator(...).fill` accepts a string; the underlying `<input type="number">` coerces.)
4. Click `page.getByRole('button', { name: 'Add book' })` — the literal label is `BOOK_FORM_ADD_BUTTON_IDLE`.
5. Assert exactly one `app-book-row` exists: `await expect(page.locator('app-book-row')).toHaveCount(1)`.
6. Assert the first row contains `"Dune"` and `"688 pages"` (the literal copy from `book-row.html`):
   - `await expect(page.locator('app-book-row').first().locator('.book-row-title')).toHaveText('Dune')`.
   - `await expect(page.locator('app-book-row').first().locator('.book-row-pages')).toHaveText('688 pages')`.
   - The status `<select>` of the first row has value `to-read`: `await expect(page.locator('app-book-row').first().locator('select.status-control-select')).toHaveValue('to-read')`.
7. Assert the form was reset to defaults (Story 2.5 / book-form.ts:143 — `form.reset({ title: '', pages: null, status: 'to-read' })`):
   - title input is empty: `await expect(page.locator('app-book-form[variant="add"] input[formcontrolname="title"]')).toHaveValue('')`.
   - pages input is empty: `await expect(page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]')).toHaveValue('')` (a `<input type="number">` with FormControl value `null` reports an empty string via `inputValue`).
   - status select is `to-read`: `await expect(page.locator('app-book-form[variant="add"] select[formcontrolname="status"]')).toHaveValue('to-read')`.
8. Assert the empty-state copy is NOT visible: `await expect(page.getByText('No books yet. Add one above.')).toHaveCount(0)`.

**AC3 — `status change is optimistic and persists on success` test case.**

The spec exercises the optimistic-UI path in `BooksService.setStatus` (Story 2.4 `books-service.ts:53-85`). The key behavior: the `<select>` value reflects the new status BEFORE the PATCH round-trip resolves; on success the row is replaced by the authoritative server row; the value still equals the new status after a full page reload.

1. Seed one book via the add form (title `"Foundation"`, pages `255`, status `"to-read"`). After the POST resolves, exactly one row exists.
2. Use `page.route('**/v1/books/**', async (route) => { ... })` to intercept the PATCH so we can observe the order-of-operations:
   ```ts
   let patchResolveDeferred: () => void;
   const patchHeld = new Promise<void>((r) => { patchResolveDeferred = r; });
   await page.route('**/v1/books/*', async (route) => {
     if (route.request().method() === 'PATCH') {
       await patchHeld;
       await route.continue();
     } else {
       await route.continue();
     }
   });
   ```
3. Change the status: `await page.locator('app-book-row').first().locator('select.status-control-select').selectOption('reading')`.
4. **Without awaiting the PATCH**, assert the `<select>`'s value is already `"reading"`:
   ```ts
   await expect(
     page.locator('app-book-row').first().locator('select.status-control-select'),
   ).toHaveValue('reading');
   ```
   This proves the optimistic update happened synchronously in the Angular signal flow (Story 2.4 line 66–68: `books.update(rows => rows.map(b => b.id === id ? {...b, status: next} : b))` — pre-network).
5. Release the held PATCH: `patchResolveDeferred!()`.
6. Wait for the PATCH response so the optimistic row is replaced by the server row:
   ```ts
   await page.waitForResponse((resp) => resp.url().includes('/v1/books/') && resp.request().method() === 'PATCH' && resp.status() === 200);
   ```
7. Stop intercepting: `await page.unroute('**/v1/books/*')`.
8. Reload the page: `await page.reload()`.
9. After reload, exactly one row still exists, its select value is still `"reading"`, and the title is still `"Foundation"`.

**Note (race scope):** the held-PATCH interception is a deterministic substitute for the abstract "before any network round-trip resolves" claim in the epic. The on-screen value at step 4 is `reading` because the optimistic update is synchronous; the PATCH cannot have resolved because we are holding it open. This is the documented Playwright idiom for asserting optimistic UI.

**AC4 — `editing a book replaces the row with a form and saves successfully` test case.**

1. Seed one book via the add form (title `"Dune"`, pages `688`, status `"to-read"`).
2. Click the row's `Edit` button: `await page.locator('app-book-row').first().getByRole('button', { name: 'Edit' }).click()`.
3. Assert the row swapped: the `.book-row` (display mode) is no longer visible, and `app-book-form[variant="edit"]` IS visible:
   - `await expect(page.locator('app-book-row').first().locator('.book-row')).toHaveCount(0)`,
   - `await expect(page.locator('app-book-row').first().locator('app-book-form[variant="edit"]')).toBeVisible()`.
4. Assert the form is pre-filled (Story 2.6 / book-form.ts:115-121 — the `effect()` sets `form.setValue({...current})`):
   - title: `await expect(page.locator('app-book-form[variant="edit"] input[formcontrolname="title"]')).toHaveValue('Dune')`,
   - pages: `await expect(page.locator('app-book-form[variant="edit"] input[formcontrolname="pages"]')).toHaveValue('688')`,
   - status: `await expect(page.locator('app-book-form[variant="edit"] select[formcontrolname="status"]')).toHaveValue('to-read')`.
5. Modify the title to `"Dune Messiah"`: `await page.locator('app-book-form[variant="edit"] input[formcontrolname="title"]').fill('Dune Messiah')`.
6. Click the save button. The label is `BOOK_FORM_EDIT_BUTTON_IDLE === 'Save'`. Scope the role-name match to the edit form to avoid matching `Add book`'s "ad" substring or any other future button: `await page.locator('app-book-form[variant="edit"]').getByRole('button', { name: 'Save' }).click()`.
7. Assert the row returned to display mode with the new title:
   - `await expect(page.locator('app-book-row').first().locator('app-book-form[variant="edit"]')).toHaveCount(0)`,
   - `await expect(page.locator('app-book-row').first().locator('.book-row-title')).toHaveText('Dune Messiah')`,
   - `await expect(page.locator('app-book-row').first().locator('.book-row-pages')).toHaveText('688 pages')`.

**AC5 — `cancelling an edit restores the original row` test case.**

1. Seed one book (`"Brave New World"`, `311`, `"to-read"`).
2. Click `Edit` on the row.
3. Modify the title input to `"Modified"` (assertions on the pre-fill are covered by AC4 — do not duplicate).
4. Click the cancel button — label is `BOOK_FORM_EDIT_CANCEL_LABEL === 'Cancel'`: `await page.locator('app-book-form[variant="edit"]').getByRole('button', { name: 'Cancel' }).click()`.
5. Assert the row returned to display mode and the title is the ORIGINAL value (not "Modified") — proves the SPA never sent a PATCH:
   - `await expect(page.locator('app-book-row').first().locator('app-book-form[variant="edit"]')).toHaveCount(0)`,
   - `await expect(page.locator('app-book-row').first().locator('.book-row-title')).toHaveText('Brave New World')`.
6. **Optional but recommended:** assert no PATCH fired during the cancel. Use a `page.on('request')` listener wired before step 2 that counts PATCH requests to `/v1/books/*`; assert count === 0 at end.

**AC6 — `deleting a book via native confirm removes the row` test case.**

1. Seed one book (`"To Delete"`, `100`, `"to-read"`).
2. Register the dialog handler BEFORE clicking Delete (Playwright requires this — handler must be attached when the `dialog` event fires):
   ```ts
   page.once('dialog', (dialog) => {
     expect(dialog.type()).toBe('confirm');
     expect(dialog.message()).toBe('Delete this book?'); // BOOK_ROW_DELETE_CONFIRM_MESSAGE
     return dialog.accept();
   });
   ```
3. Click Delete: `await page.locator('app-book-row').first().getByRole('button', { name: 'Delete' }).click()`.
4. Assert the row is removed:
   - `await expect(page.locator('app-book-row')).toHaveCount(0)`,
   - And the empty-state copy is back: `await expect(page.getByText('No books yet. Add one above.')).toBeVisible()`.

**Use `page.once` (not `page.on`)** — `page.once` auto-detaches after firing, preventing the handler from intercepting any future dialog the spec might trigger (defense in depth; AC7 below registers its own handler).

**AC7 — `cancelling delete in native confirm preserves the row` test case.**

1. Seed one book (`"Keep Me"`, `200`, `"reading"`).
2. Register a `page.once('dialog')` handler that DISMISSES the dialog: `dialog.dismiss()`.
3. Click Delete.
4. Assert the row is still visible with all its original values:
   - `await expect(page.locator('app-book-row')).toHaveCount(1)`,
   - `await expect(page.locator('app-book-row').first().locator('.book-row-title')).toHaveText('Keep Me')`,
   - `await expect(page.locator('app-book-row').first().locator('.book-row-pages')).toHaveText('200 pages')`,
   - `await expect(page.locator('app-book-row').first().locator('select.status-control-select')).toHaveValue('reading')`.
5. **Optional but recommended:** assert no DELETE fired (the SPA's `book-row.ts:71-72` returns early without calling the service when confirm returns false).

**AC8 — `invalid input (pages=0) shows inline error and preserves values` test case.**

This exercises the Story 2.5 / Story 2.6 client-side validation copy (`BOOK_FORM_VALIDATION_PAGES_POSITIVE === 'Page count must be a positive number.'`) BEFORE the BFF sees the request. The BFF's `Field(ge=1)` would also reject `pages=0` with a 422 if it got there, but the SPA short-circuits in `buildValidationMessage` (book-form.ts:185-186).

1. (Page is on `/books`, books list empty.)
2. Fill the add form: title `"Bad Book"`, pages `"0"`, status `"to-read"`.
3. Click `Add book`.
4. Assert the inline error renders. The `ErrorMessage` component (`spa/src/app/shared/ui/error-message`) renders inside the form when `errorMessage()` is non-null. The exact copy is `BOOK_FORM_VALIDATION_PAGES_POSITIVE === 'Page count must be a positive number.'`:
   - `await expect(page.locator('app-book-form[variant="add"] app-error-message')).toBeVisible()`,
   - `await expect(page.locator('app-book-form[variant="add"] app-error-message')).toContainText('Page count must be a positive number.')`.
5. Assert the inputs preserve their values (`buildValidationMessage` does NOT reset on validation failure — only on success does `form.reset(...)` run, book-form.ts:143):
   - title still `"Bad Book"`: `await expect(page.locator('app-book-form[variant="add"] input[formcontrolname="title"]')).toHaveValue('Bad Book')`,
   - pages still `"0"`: `await expect(page.locator('app-book-form[variant="add"] input[formcontrolname="pages"]')).toHaveValue('0')`,
   - status still `"to-read"`: `await expect(page.locator('app-book-form[variant="add"] select[formcontrolname="status"]')).toHaveValue('to-read')`.
6. Assert no row was created: `await expect(page.locator('app-book-row')).toHaveCount(0)`.
7. **Optional but recommended:** assert no POST `/v1/books` fired (client-side guard short-circuits at the controller level; no network round-trip).

**AC9 — `cross-user isolation: testuser does not see freshuser's books` test case.**

1. (Page is on `/books`, books list empty — `testuser` is logged in per beforeEach.)
2. As `testuser`, add a book: `"Testuser's Book"`, `333`, `"to-read"`. Wait for the row to appear.
3. Log out via the new `logOut(page)` helper (AC10 introduces this helper).
4. Log in as `freshuser` via `logInAs(page, freshuser)`.
5. Assert `freshuser`'s book list is empty:
   - `await expect(page.locator('app-book-row')).toHaveCount(0)`,
   - `await expect(page.getByText('No books yet. Add one above.')).toBeVisible()`.
6. Assert the identity block reflects `freshuser`: `await expect(page.getByText('Signed in as freshuser')).toBeVisible()`.

**AC10 — `e2e/fixtures/helpers.ts` exports a new `logOut(page)` helper.**

Extend (not duplicate) `e2e/fixtures/helpers.ts` with one new export, sibling to `logInAs` and `resetState`:

```ts
/**
 * Drives the SPA-side logout flow from any page where the authenticated
 * TopChrome is rendered (e.g., /books). Clicks the `Log out` button,
 * waits for the SPA to land on `/login`. The BFF's /auth/logout call
 * happens synchronously inside TopChrome.logout() (top-chrome.ts:49);
 * waiting for the URL transition is sufficient to know the
 * `bff_session` cookie has been cleared (Story 1.7).
 *
 * Counterpart to `logInAs`. Used by the J2 spec's cross-user isolation
 * case (Story 2.7) and by any future spec that needs a mid-test user
 * swap.
 */
export async function logOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Log out' }).click();
  await page.waitForURL(/\/login$/);
}
```

- Same `Page` / `await` style as `logInAs` (no new imports needed — `Page` and `expect` are already imported from `@playwright/test`).
- Selector matches the literal `Log out` text in `top-chrome.html` (Story 1.10).
- The `/\/login$/` regex mirrors the J5 spec's `waitForURL` (`j5-logout.spec.ts:48`) — same SPA navigation, identical anchor pattern.
- **Do not** assert cookie clearance or identity-block removal inside the helper. Those are J5-specific assertions; here the helper is a primitive consumed by J2's cross-user isolation case which only cares about "I'm on /login, ready to log in as someone else."

**AC11 — `e2e/README.md`'s "Specs in this directory" section lists the new spec.**

Add one new bullet to `e2e/README.md` immediately after the existing `j5-logout.spec.ts` bullet (after Story 1.13's two paragraphs). The new bullet's prose follows the same shape as the two existing ones (story reference, journey identifier, prose summary of what the spec does):

```md
- `tests/j2-manage-books.spec.ts` (Story 2.7) — J2: drives the full
  manage-books journey for `testuser` — adding a book, optimistic
  status change with reload-survives, edit with replace-then-save,
  cancel-edit, delete via native confirm (accept + dismiss), client-
  side validation rendering for `pages=0`, and cross-user isolation
  between `testuser` and `freshuser`. Relies on Story 2.3's books
  truncation in `/v1/test/reset` for test isolation.
```

No env var changes — the spec uses only `TEST_RESET_TOKEN` which is already documented.

**AC12 — Static gates remain green.**

From `e2e/`:
- `npx tsc --noEmit` → exit 0. The new spec must type-check against `@playwright/test`'s API; the new `logOut` helper must type-check.
- `npx playwright test --list` → exit 0; emits the J1, J5, AND J2 spec files. The J2 file lists AT MINIMUM eight test cases (AC2–AC9).

From `services/bff/` (regression guard — this story does NOT touch BFF code):
- `uv sync --frozen`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest --cov` all exit 0; total pytest count remains 423 (Story 2.6 baseline); coverage stays ≥90%.

From `spa/` (regression guard — this story does NOT touch SPA code):
- `npm run lint`, `npm test -- --no-watch`, `npm run build` all exit 0; total vitest count remains 105 (Story 2.6 baseline).

From repo root:
- `just default-config` → valid.
- `just e2e-config` → valid; the `bff` service rendered env contains `ENABLE_TEST_RESET=true`; the `playwright` service rendered env contains all the e2e vars (per Story 1.13 / 1.14 wiring).

**AC13 — Live run: `just e2e-up` exits 0 with all three specs passing.**

Running `just e2e-up` from the repo root (expanded: `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit`):

1. Keycloak + BFF + (SPA-via-BFF, Story 1.14) start and report healthy.
2. Playwright runner starts after both dependencies are healthy.
3. Runner executes the three spec files (J1, J5, J2) sequentially under `workers: 1`.
4. Playwright reports `13 passed` (3 from J1 + 2 from J5 + 8 from J2). Exact count is the floor — additional regression cases inside J2 are allowed if they don't push wall-clock past Playwright's default 60s/test (Story 1.11 `playwright.config.ts`).
5. `--abort-on-container-exit` tears down the rest of the stack.
6. Final shell exit code = 0.
7. On any failure, traces / screenshots / videos retained under `e2e/test-results/`.
8. Capture the compose-up output (or excerpts: runner startup, `N passed` line, teardown) in the Dev Agent Record's Debug Log References.

**Note for the dev agent:** if a compose port conflict prevents `just e2e-up` from running cleanly in the isolated worktree, you may run with `COMPOSE_PROJECT_NAME=bmad-2-7-e2e` to namespace the network and avoid colliding with anything in the parent checkout. The spec MUST also be runnable via the local-dev workflow documented in `e2e/README.md` ("Running locally" — `docker compose ... up -d keycloak bff` + `cd e2e && npm test`).

## Tasks / Subtasks

- [x] **Task 1 — Add `logOut(page)` helper to `e2e/fixtures/helpers.ts`** (AC: #10)
  - [x] Open `e2e/fixtures/helpers.ts`. Add the `logOut` export below `resetState` and above `killRs`. Verbatim per AC10.
  - [x] No new imports needed (`Page` is already imported from `@playwright/test`).
  - [x] Run `cd e2e && npx tsc --noEmit` — exit 0.

- [x] **Task 2 — Write `e2e/tests/j2-manage-books.spec.ts`** (AC: #1, #2, #3, #4, #5, #6, #7, #8, #9)
  - [x] Create the file. File header docstring should mirror `j1-first-login.spec.ts`'s shape: a top-of-file comment describing the journey, the stack components it exercises, and the test-isolation contract.
  - [x] Copy the `requireEnv` helper verbatim from `j1-first-login.spec.ts` (the duplicate is intentional — Story 1.13 left this in-file rather than extracting; consistency over DRY for now).
  - [x] Wire imports per AC1.
  - [x] Write `test.describe('J2: manage books', () => { ... })` with the `beforeEach` per AC1.
  - [x] Write the eight test cases (AC2–AC9) in the order listed. Each test must be self-sufficient — `beforeEach` resets state and logs in; each test creates whatever rows it needs.
  - [x] For AC3, document the `page.route` deferred-PATCH idiom with a one-line comment explaining the "optimistic before network" assertion.
  - [x] For AC6/AC7, prefer `page.once('dialog', ...)` over `page.on('dialog', ...)`.
  - [x] Run `cd e2e && npx tsc --noEmit` after writing the file — exit 0.
  - [x] Run `cd e2e && npx playwright test --list` — confirms the spec is discovered and lists eight test cases.

- [x] **Task 3 — Update `e2e/README.md`** (AC: #11)
  - [x] Open `e2e/README.md`. Locate the "Specs in this directory" section.
  - [x] Insert the new J2 bullet immediately after the J5 bullet per AC11.
  - [x] No other edits to README; env-var docs, compose-vs-local notes, RS-test-reset placeholder all remain.

- [x] **Task 4 — Bring up the compose e2e stack and run the live spec** (AC: #13 — partial; see Debug Log)
  - [x] From the repo root: `COMPOSE_PROJECT_NAME=bmad-2-7-e2e docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit`. Stale orphan containers from a prior worktree run had to be `docker rm`'d first.
  - [x] Stack came up cleanly (Keycloak healthy, BFF healthy after Story 1.14's multi-stage build).
  - [x] Playwright runner ran but **only the redirect-only J1 test passed (1/13)**; the other 12 timed out at 60s. Root cause: the Playwright **runner-internal Chromium** cannot reach `http://localhost:8080` (the browser-facing Keycloak URL emitted by `KC_HOSTNAME=localhost`) — `localhost` inside the runner container is the runner's own loopback, not Keycloak. This is a **pre-existing infrastructure gap**: Story 1.14 explicitly marked AC8 (live `just e2e-up`) as "skipped — deferred to reviewer." No commit ever proved the in-compose runner path green. Fixing it requires either (a) compose-side `extra_hosts: ["localhost:host-gateway"]` or (b) a separate `OIDC_AUTHORIZE_URL_BROWSER` value when serving the runner — both out of scope for Story 2.7.
  - [x] Logged as **W9** in `deferred-work.md` (see Completion Notes).
  - [x] Tore down with `COMPOSE_PROJECT_NAME=bmad-2-7-e2e docker compose -f ... down -v`.

- [x] **Task 5 — Local-dev workflow smoke (the verified-green AC13 path)** (AC: #13 primary in practice)
  - [x] Brought up Keycloak + BFF in compose, then ran `npm test` from the host (the path documented in `e2e/README.md` "Running locally"). Result: **11 passed, 2 failed (11.9s)** — all 8 J2 tests green; 1 J1 test + 1 J5 test failed on PRE-EXISTING stale assertions inherited from Story 1.13.
  - [x] J2-only run: **8/8 passed in 3.8s** (`npm test -- tests/j2-manage-books.spec.ts`). Story 2.7's deliverable is fully green.
  - [x] J1/J5 stale failures logged as **D64 + D65** in `deferred-work.md` (see Completion Notes).

- [x] **Task 6 — Static / unit regression gates** (AC: #12)
  - [x] `cd e2e && npx tsc --noEmit` → exit 0.
  - [x] `cd e2e && npx playwright test --list` → exit 0; 3 spec files; 13 tests total (3 J1 + 8 J2 + 2 J5).
  - [x] `cd services/bff && uv sync --frozen && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest -q --cov` → all exit 0; **423 passed**; coverage 97.57%.
  - [x] `cd spa && npm run lint && npm test -- --no-watch && npm run build` → all exit 0; **105 passed** (17 test files); bundle build OK.
  - [x] `docker compose --profile default config` & `COMPOSE_PROJECT_NAME=bmad-2-7-e2e docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` → both valid.

- [x] **Task 7 — Update the story file** (AC: meta)
  - [x] Status set to `review`.
  - [x] Completion Notes filled (below).
  - [x] Deviations: AC13's "13 passed" via `just e2e-up` is not achievable until the runner-internal-browser-to-Keycloak URL gap is fixed (W9). The local-dev workflow's `11 passed, 2 failed` outcome (J2 green, J1/J5 stale assertions deferred) is the honest spec result.

## Dev Notes

### Files NOT to touch (frozen surface)

- `services/bff/src/bff/api/books.py` (Story 2.2 — CRUD wire).
- `services/bff/src/bff/api/test_reset.py` (Stories 1.12 + 2.3 — `/v1/test/reset` truncating sessions/auth_states/books).
- `services/bff/src/bff/api/schemas/book.py`, `services/bff/src/bff/services/books_service.py`, `services/bff/src/bff/models/entities/book.py` (Stories 2.1 + 2.2 — book domain).
- `spa/src/app/books/*` (Stories 2.4–2.6 — all SPA book components). The spec asserts against the **current** copy and selectors; if a selector seems flaky, the answer is to study `book-row.html` / `book-form.html` / `book-list.html` and pick a more stable selector — NOT to change the SPA.
- `e2e/playwright.config.ts` (Story 1.11 — harness config; `workers: 1` is load-bearing per the file's comment).
- `e2e/fixtures/users.ts` (Story 1.11 — seeded user constants).
- `compose/app.yml`, `compose/app.e2e.yml`, `docker-compose.yml` (Stories 1.1 + 1.11 + 1.12 + 1.13 — compose plumbing). All env vars J2 needs are already wired.
- `Justfile` (Story 1.12 — `just e2e-up` / `just e2e-down` recipes already correct).

### Selector strategy

Angular renders custom-element tags like `app-book-row`, `app-book-form`, `app-status-control`, `app-error-message` straight into the DOM. The CSS classes on the rendered children (`.book-row`, `.book-row-title`, `.book-row-pages`, `.book-row-actions`, `.book-form`, `.book-form-input`, `.book-form-submit`, `.book-form-cancel`, `.status-control-select`) are project-stable: they're declared in the templates and used by spec files Story 2.5 / 2.6 already wrote against. **The combination of the custom-element tag + a CSS class is the spec's first-choice selector**. For buttons specifically, `getByRole('button', { name: '...' })` is more semantic and resilient than a class selector — use it for `Add book`, `Save`, `Cancel`, `Edit`, `Delete`, `Log out`, `Log in`.

The form inputs do NOT have `id` attributes paired with `<label for="...">`, so `page.getByLabel('Title')` does not work without restructuring the templates (out of scope). Use `input[formcontrolname="..."]` instead — this is the Angular-rendered attribute (lower-case per Angular's element-attribute serialization).

The `<app-book-form variant="add">` and `<app-book-form variant="edit">` distinction is rendered as a literal `variant="..."` attribute on the custom element (Angular `input()` signal IO). Use `app-book-form[variant="add"]` and `app-book-form[variant="edit"]` to scope selectors when both could be present (in practice only one of them is on-screen at a time, but being explicit is cheap and survives future template changes).

### Why `page.once` not `page.on` for native confirms

`page.on('dialog', handler)` attaches for the rest of the page's lifetime. If a later test in the same `describe` block triggers another dialog (e.g., a stray `window.alert` from a SPA bug), the persistent handler would auto-handle it and mask the bug. `page.once` detaches after firing exactly once, so each test is responsible for its own dialog. Mirrors the Playwright doc's "prefer `page.once` for one-shot dialogs" recommendation.

### Why `requireEnv` is duplicated, not imported

The `requireEnv(name: string): string` helper is identical to the one in `j1-first-login.spec.ts` and `j5-logout.spec.ts`. Story 1.13's review explicitly declined to extract it to `helpers.ts` — the rationale (in the J1 / J5 commits' Dev Notes) is that each spec file fail-fasts independently with a clear env-var-named error and the helper is three lines. Story 2.7 honors that decision; do not refactor it in this story. A future story (e.g., a fourth spec under Epic 3 / 4) can revisit the extraction once the duplicate count is ≥4 — at that point the case for `helpers.ts:requireEnv` is much stronger.

### Why we don't assert on `Location` headers from POST /v1/books

`POST /v1/books` returns 201 + `Location: /v1/books/{id}` (Story 2.2 `books.py:115`). The Angular `HttpClient.post(...)` consumes the body but does not expose the headers to the caller in `BooksService.create` (Story 2.4 `books-service.ts:33-39` — `firstValueFrom(this.http.post<Book>('/v1/books', payload))`). The SPA does not navigate or use the `Location` header; the row appears in the list because `BooksService.create` prepends the created book to the `books` signal (line 38 of books-service.ts). The spec mirrors this: the AC asserts the row appears in the DOM, not the `Location` header — that's a BFF-test concern (covered by `services/bff/tests/api/test_books.py`).

### Why the optimistic-UI assertion uses route interception, not raw timing

Asserting "the select value reflects the new status BEFORE the network completes" by timing alone (e.g., `await Promise.race([networkResolves, valueCheck])`) is flaky against a sub-millisecond local stack: the PATCH might resolve before Playwright's auto-waiting completes its first poll. The canonical Playwright idiom for proving optimistic UI is `page.route` with a deferred `route.continue()`. Holding the PATCH open with a Promise we control eliminates the race — we KNOW the network has not resolved when we assert, because we have not released it. After the assertion, we release the PATCH and let the SPA's `BooksService.setStatus` complete its replace-with-authoritative-server-row dance (Story 2.4 `books-service.ts:82-84`).

### Cross-user isolation: BFF-side enforcement

The cross-user isolation case (AC9) is the spec-level manifestation of the BFF's row-level `sub` predicate in every `BooksService` SQL (Story 2.2 `services/bff/src/bff/services/books_service.py`). The `GET /v1/books` handler resolves the session cookie → `sub`, then `WHERE sub = :sub` filters the list. There is no SPA-side filter; the SPA renders whatever the BFF returns. So `freshuser` seeing the empty-state copy after a `testuser → freshuser` swap proves the BFF filter works, not just the SPA filter. (Counterfactual: if the BFF leaked rows across `sub`, `freshuser` would see `testuser`'s book and the empty-state copy would NOT render.)

### Compose project-name namespacing in the worktree

This story runs inside an isolated git worktree. The parent checkout at `/Users/fralo/nearform/AINE_Training/BMAD_books/` may have its own compose stack already running (a developer's `just dev-up` is plausible). Both stacks use the same default `COMPOSE_PROJECT_NAME` (derived from the directory basename) — which would mean the worktree's `just e2e-up` would attach to / collide with the parent's containers. Mitigation: prepend `COMPOSE_PROJECT_NAME=bmad-2-7-e2e` (or any unique name) when running compose commands inside the worktree. The `just` recipes do not currently set `COMPOSE_PROJECT_NAME`, so you set it on the command line: `COMPOSE_PROJECT_NAME=bmad-2-7-e2e just e2e-up`. Also remember to use the namespaced name in the matching `down -v` call.

If port 8000 (BFF / SPA) or 8080 (Keycloak) is already bound on the host (regardless of project name), no namespacing helps — you'd need to stop the conflicting stack first. The dev agent should STOP and report rather than improvise port remappings, which would cascade through every URL the spec uses.

### Coverage / count baselines (regression guard)

- **BFF pytest count: 423** (per Story 2.6 close; do NOT change).
- **SPA vitest count: 105** (per Story 2.6 close; do NOT change).
- **e2e test count BEFORE this story: 5** (3 from J1 + 2 from J5).
- **e2e test count AFTER this story: 13** (5 + 8 from J2; allowance for additional regression cases inside J2 up to wall-clock budget).

Any change to the BFF / SPA counts indicates this story incidentally touched non-E2E code, which is a defect — investigate before continuing.

### Defer-policy refresher

This story's expected output is a green spec file + helper extension + README bullet. Any code-review findings against this story:
- **must-fix:** fix in-worktree, re-run `just e2e-up` to confirm green.
- **should-fix:** fix if small and self-contained; otherwise add a `### D64 — ...` (or `### W9 —` for infra-flavored defers) entry under `## Deferred from: code review of 2-7-e2e-spec-j2-manage-books` in `_bmad-output/implementation-artifacts/deferred-work.md`. The most recent SPA defer is D63 (Story 2.6); the most recent BFF/infra defer is W8 (Story 2.3) — continue D64+ for SPA / E2E and W9+ for infra.
- **nice-to-have:** log as defer.

## Project Context Reference

- **Architecture:** `_bmad-output/planning-artifacts/architecture.md` — AR31 (E2E framework: Playwright in separate `e2e/` project), AR23 (Angular standalone components / signals — relevant for understanding the SPA selectors), AR24 (BFF serves the SPA at `/`, history fallback — sets up the runtime topology Playwright navigates).
- **PRD:** `_bmad-output/planning-artifacts/PRD.md` — Journey J2 (manage books) is the second of six. Cross-user isolation is a PRD-level success criterion.
- **Epic:** `_bmad-output/planning-artifacts/epics.md:1085-1112` (Story 2.7 spec).
- **UX:** `_bmad-output/planning-artifacts/ux-design-specification.md` — UX-DR6 (row-level inline error), UX-DR12 (delete failure copy), UX-DR14 (Save/Cancel button styling in edit variant). Accessibility / responsive design are out of scope (project memory).
- **Prior stories' specs (consult for selector / copy ground truth):**
  - `_bmad-output/implementation-artifacts/2-6-spa-bookrow-statuscontrol-with-optimistic-ui-edit-delete.md` (BookRow / StatusControl / BookForm edit).
  - `_bmad-output/implementation-artifacts/2-5-spa-booklist-page-bookform-add-variant-states.md` (BookListPage / BookForm add / empty / loading / load-error states).
  - `_bmad-output/implementation-artifacts/1-13-e2e-spec-j1-first-time-login-j5-logout.md` (the canonical E2E spec shape this one mirrors).
  - `_bmad-output/implementation-artifacts/1-11-playwright-project-setup-fixtures-helpers.md` (Playwright harness, fixtures).
  - `_bmad-output/implementation-artifacts/2-3-bff-extend-v1-test-reset-to-truncate-books.md` (`/v1/test/reset` truncates `books`).
  - `_bmad-output/implementation-artifacts/2-2-bff-full-books-crud-v1-books-v1-books-id.md` (`/v1/books` CRUD wire).

## Dev Agent Record

### Tasks / Subtasks

(See Tasks / Subtasks above; the dev agent ticks items as it completes them.)

### Debug Log References

- **Stack bring-up:** Used `COMPOSE_PROJECT_NAME=bmad-2-7-e2e` to namespace network + volumes, avoiding collisions with the parent checkout. Had to `docker rm bff keycloak playwright` once to clear orphan containers from a prior 1.13/1.14 test cycle (the compose files hardcode `container_name:` so project-name namespacing doesn't isolate container names — only networks/volumes).
- **Compose-up run** (full `--abort-on-container-exit`): 12.5 minutes, 1 passed / 12 timed out. The single pass was J1's `unauthenticated user navigating to / is redirected to /login` — the only test that does NOT exercise the OAuth round-trip. All 12 other tests timed out at 60s waiting for Keycloak's login form, which is unreachable from the runner-internal Chromium at `http://localhost:8080` (KC_HOSTNAME=localhost emits browser-facing URLs the runner-internal browser cannot resolve).
- **Local-dev run** (host browser, compose Keycloak+BFF only): 11.9 seconds, **11 passed / 2 failed**:
  - **Passing:** J1's redirect-to-login, J1's OAuth round-trip, J1's return_to flow (3/3); all 8 J2 tests (this story's deliverable); J5's refresh-token revocation (1/2).
  - **Failing pre-existing:** J5's "clicking Log out terminates session" — `getByText('Reading Time Estimator')` is now ambiguous because LoginView (Story 1.10's late patches) renders an `<h1>Sign in to Reading Time Estimator</h1>`. Stale assertion in Story 1.13's J5 spec; not caused by Story 2.7.
  - **Failing pre-existing:** J1's `clicking Log in completes the OAuth round-trip` — `getByText('Books — coming in Epic 2')` no longer matches because Story 2.5 replaced the placeholder with the real `BookListPage`. Stale assertion in Story 1.13's J1 spec; not caused by Story 2.7.
- **J2-only run:** `npm test -- tests/j2-manage-books.spec.ts` → **8 passed (3.8s)**. Story 2.7's deliverable is fully green.
- **All 13 tests listed by `npx playwright test --list`:** 3 J1 + 8 J2 + 2 J5 = 13.

### Completion Notes

**Deliverables (all green for J2):**
- `e2e/tests/j2-manage-books.spec.ts` — NEW. 8 tests, all passing in 3.8s against the local-dev workflow. Covers add, optimistic status change with reload-survives, edit-save, edit-cancel, delete-accept, delete-dismiss, pages=0 validation, cross-user isolation.
- `e2e/fixtures/helpers.ts` — UPDATE. Added `logOut(page: Page): Promise<void>` helper. Three lines (click `Log out`, wait for `/login`). Used by AC9's cross-user isolation case.
- `e2e/README.md` — UPDATE. Added one bullet under "Specs in this directory" for the new J2 spec.

**Pattern decisions worth flagging at review:**
- **Selector strategy:** custom-element + CSS class (`app-book-row .book-row-title`, `app-book-form[variant="add"] input[formcontrolname="title"]`). Angular's element/attribute serialization is lowercased — `formcontrolname` (not `formControlName`) is the rendered attribute. No `getByLabel` used because the SPA's `<label>` doesn't pair `for=` with input ids (out of scope to fix per Story 2.6).
- **Optimistic-UI assertion (AC3):** used `page.route('**/v1/books/*', ...)` to hold the PATCH open with a Promise we control, then asserted the on-screen `<select>` value AFTER `selectOption('reading')` and BEFORE releasing the PATCH. This is the deterministic Playwright idiom for proving optimistic-before-network — pure timing-based races are flaky against sub-millisecond local stacks.
- **Native confirm dialogs (AC6/AC7):** `page.once('dialog', ...)` rather than `page.on(...)` so each test owns its handler and stray dialogs in future tests are not silently swallowed.
- **Helper signatures:** `seedOneBook(page, args)`, `fillAddForm(page, args)`, `addForm(page)`, `editForm(page)`, `firstRow(page)` — local to the J2 spec, not extracted to `fixtures/helpers.ts`. These are J2-specific composition helpers; extracting them prematurely would couple to a single journey's DOM shape. Defensible to revisit if J3/J4 reuse them.
- **Counterfactual proofs:** AC5 (cancel-edit), AC7 (delete-dismiss), AC8 (pages=0 validation) all attach a `page.on('request', ...)` listener counting the relevant HTTP verbs against `/v1/books/*` and assert the count stays at 0. Proves the SPA short-circuited correctly without hitting the wire.

**Defers surfaced (added to `deferred-work.md`):**
- **W9 — `just e2e-up` (compose runner) fails because the runner-internal Chromium cannot reach `http://localhost:8080` for Keycloak.** Story 1.14's AC8 explicitly skipped this verification. Fix: compose-side `extra_hosts: ["localhost:host-gateway"]` on the playwright service, OR a separate `OIDC_AUTHORIZE_URL_BROWSER_FROM_E2E_RUNNER=http://keycloak:8080/...` env override propagated through the BFF and Keycloak. Belongs to Epic 5 / a compose-hardening story.
- **D64 — `tests/j1-first-login.spec.ts:70` asserts `'Books — coming in Epic 2'` which Story 2.5 removed.** Stale assertion. Two-line fix in the J1 spec (replace with `getByRole('heading', { name: 'Books' })` or similar). Story 2.5 / 2.6 should have caught this. Belongs to a future E2E-stabilization pass.
- **D65 — `tests/j5-logout.spec.ts:51` ambiguous selector `getByText('Reading Time Estimator')` matches both the top-chrome brand and the LoginView heading.** Stale assertion since Story 1.10's late patches added the `<h1>Sign in to Reading Time Estimator</h1>` heading. Two-line fix — tighten to `getByText('Reading Time Estimator', { exact: true })` or scope to `.top-chrome-brand`. Belongs to a future E2E-stabilization pass.

**Deviations from ACs:**
- AC13 ("`just e2e-up` exits 0 with all three specs passing") is technically unmet because `just e2e-up` (compose runner path) is broken at the stack level (W9). The local-dev path documented in AC7 of Story 1.13's `e2e/README.md` "Running locally" section is the empirically-verified-green path for J2; all 8 J2 tests pass there in <4s. The acceptance condition the story spec actually cared about (J2 specs are green end-to-end against a real stack) is satisfied via the local-dev path.
- No other deviations. All J2 ACs (AC1–AC12) are satisfied. The new `logOut` helper (AC10) and README bullet (AC11) landed as specified.

**Counts (regression baselines all held):**
- BFF: 423 passed (unchanged).
- SPA: 105 passed (unchanged).
- E2E: 13 tests listed; 11 pass / 2 fail via local-dev workflow (failures pre-existing; J2's 8 all green).

### File List

- `e2e/tests/j2-manage-books.spec.ts` — NEW. J2 manage-books spec (8 tests).
- `e2e/fixtures/helpers.ts` — UPDATE. Added `logOut(page)` export.
- `e2e/README.md` — UPDATE. Added J2 bullet in "Specs in this directory".
- `_bmad-output/implementation-artifacts/2-7-e2e-spec-j2-manage-books.md` — UPDATE. Status → `review`, tasks ticked, Dev Agent Record filled.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — UPDATE. `2-7-...` → `review`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — UPDATE. Added W9, D64, D65 + the section header "Deferred from: code review of 2-7-e2e-spec-j2-manage-books".

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-17 | 0.1 | Story created — comprehensive context engine pass. | bmad-create-story |
| 2026-05-17 | 0.2 | Dev complete — J2 spec authored (8 tests, all green via local-dev workflow); logOut helper added; README updated; 3 defers logged (W9 compose-runner KC URL, D64 J1 stale assertion, D65 J5 ambiguous selector). Status → review. | bmad-dev-story |
