import { expect, Page, test } from '@playwright/test';

import { logInAs, logOut, resetState } from '../fixtures/helpers';
import { freshuser, testuser } from '../fixtures/users';

/**
 * E2E spec for journey J2 (manage books) — Story 2.7.
 *
 * Drives the full manage-books journey against the real Keycloak + BFF
 * + SPA stack. Every test starts with `sessions`, `auth_states`, and
 * `books` truncated via `/v1/test/reset` (Story 2.3 extension of the
 * Story 1.12 endpoint), then logs `testuser` in via the real OAuth
 * round-trip (`logInAs` from Story 1.11). No mocks at any layer.
 *
 * Exercises BFF surfaces:
 *   - GET    /v1/books             (Story 2.2)
 *   - POST   /v1/books             (Story 2.2)
 *   - PATCH  /v1/books/{id}        (Story 2.2)
 *   - DELETE /v1/books/{id}        (Story 2.2)
 *
 * Exercises SPA surfaces:
 *   - BookListPage / BookList      (Story 2.5)
 *   - BookForm[variant=add|edit]   (Stories 2.5 + 2.6)
 *   - BookRow / StatusControl      (Story 2.6)
 *   - BooksService                 (Story 2.4)
 */

/**
 * Required env vars (fail-fast on missing). The compose `e2e` profile
 * fail-fasts on `TEST_RESET_TOKEN` via `${TEST_RESET_TOKEN:?...}`, but
 * the host-side workflow (per `e2e/README.md`) has no such guard — a
 * missing var would surface as `Bearer undefined`, producing a
 * misleading 401 from the BFF. Throw a clear, env-var-named error.
 *
 * Duplicated verbatim from `j1-first-login.spec.ts` / `j5-logout.spec.ts`
 * — Story 1.13 declined to extract this helper to `fixtures/helpers.ts`;
 * Story 2.7 honors that decision. Revisit when the duplicate count >=4.
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
 * Selector helpers. Angular renders custom-element tags (`app-book-row`,
 * `app-book-form`, `app-status-control`, `app-error-message`) verbatim
 * into the DOM, paired with project-stable CSS classes from the
 * Story 2.5 / 2.6 templates. We compose them here so the test bodies
 * read as journey steps, not selector mechanics.
 */
function addForm(page: Page) {
  return page.locator('app-book-form[variant="add"]');
}

function editForm(page: Page) {
  return page.locator('app-book-form[variant="edit"]');
}

function firstRow(page: Page) {
  return page.locator('app-book-row').first();
}

async function fillAddForm(
  page: Page,
  args: { title: string; pages: string; status: 'to-read' | 'reading' | 'finished' },
): Promise<void> {
  await addForm(page).locator('input[formcontrolname="title"]').fill(args.title);
  await addForm(page).locator('input[formcontrolname="pages"]').fill(args.pages);
  await addForm(page).locator('select[formcontrolname="status"]').selectOption(args.status);
}

/**
 * Seed exactly one book by driving the add form, then wait for the row
 * to render. Returns once a single `app-book-row` is on screen with the
 * expected title — proves the POST /v1/books round-trip succeeded.
 */
async function seedOneBook(
  page: Page,
  args: { title: string; pages: string; status: 'to-read' | 'reading' | 'finished' },
): Promise<void> {
  await fillAddForm(page, args);
  await page.getByRole('button', { name: 'Add book' }).click();
  await expect(page.locator('app-book-row')).toHaveCount(1);
  await expect(firstRow(page).locator('.book-row-title')).toHaveText(args.title);
}

test.describe('J2: manage books', () => {
  test.beforeEach(async ({ page, request }) => {
    await resetState(request, { resetToken: requireEnv('TEST_RESET_TOKEN') });
    await logInAs(page, testuser);
  });

  test('adding a book makes it appear at the top of the list', async ({ page }) => {
    // Empty-state copy from `book-list.ts:8` (BOOK_LIST_EMPTY_COPY).
    await expect(page.getByText('No books yet. Add one above.')).toBeVisible();

    await fillAddForm(page, { title: 'Dune', pages: '688', status: 'to-read' });
    await page.getByRole('button', { name: 'Add book' }).click();

    // Exactly one row, top of list, with the typed values rendered.
    await expect(page.locator('app-book-row')).toHaveCount(1);
    await expect(firstRow(page).locator('.book-row-title')).toHaveText('Dune');
    await expect(firstRow(page).locator('.book-row-pages')).toHaveText('688 pages');
    await expect(firstRow(page).locator('select.status-control-select')).toHaveValue('to-read');

    // Form resets to defaults on success (book-form.ts:143).
    await expect(addForm(page).locator('input[formcontrolname="title"]')).toHaveValue('');
    await expect(addForm(page).locator('input[formcontrolname="pages"]')).toHaveValue('');
    await expect(addForm(page).locator('select[formcontrolname="status"]')).toHaveValue('to-read');

    // Empty-state copy is gone once a row exists (book-list.html:5).
    await expect(page.getByText('No books yet. Add one above.')).toHaveCount(0);
  });

  test('status change is optimistic and persists on success', async ({ page }) => {
    await seedOneBook(page, { title: 'Foundation', pages: '255', status: 'to-read' });

    // Hold the PATCH open so we can assert the optimistic UI BEFORE the
    // network round-trip completes. The on-screen <select> value
    // reflects `reading` because `BooksService.setStatus`
    // (books-service.ts:66-68) writes to the books signal synchronously
    // before awaiting the HTTP call.
    let patchResolveDeferred!: () => void;
    const patchHeld = new Promise<void>((resolve) => {
      patchResolveDeferred = resolve;
    });
    await page.route('**/v1/books/*', async (route) => {
      if (route.request().method() === 'PATCH') {
        await patchHeld;
        await route.continue();
      } else {
        await route.continue();
      }
    });

    await firstRow(page).locator('select.status-control-select').selectOption('reading');

    // Optimistic — asserted while the PATCH is still being held.
    await expect(firstRow(page).locator('select.status-control-select')).toHaveValue('reading');

    // Release the PATCH and wait for the BFF to acknowledge it.
    patchResolveDeferred();
    await page.waitForResponse(
      (resp) =>
        resp.url().includes('/v1/books/') &&
        resp.request().method() === 'PATCH' &&
        resp.status() === 200,
    );
    await page.unroute('**/v1/books/*');

    // Reload and verify the new status survived a full page round-trip.
    await page.reload();
    await expect(page.locator('app-book-row')).toHaveCount(1);
    await expect(firstRow(page).locator('.book-row-title')).toHaveText('Foundation');
    await expect(firstRow(page).locator('select.status-control-select')).toHaveValue('reading');
  });

  test('editing a book replaces the row with a form and saves successfully', async ({ page }) => {
    await seedOneBook(page, { title: 'Dune', pages: '688', status: 'to-read' });

    await firstRow(page).getByRole('button', { name: 'Edit' }).click();

    // Display mode is gone; edit form is rendered in its place.
    await expect(firstRow(page).locator('.book-row')).toHaveCount(0);
    await expect(firstRow(page).locator('app-book-form[variant="edit"]')).toBeVisible();

    // Form is pre-filled from the current row (book-form.ts:115-121).
    await expect(editForm(page).locator('input[formcontrolname="title"]')).toHaveValue('Dune');
    await expect(editForm(page).locator('input[formcontrolname="pages"]')).toHaveValue('688');
    await expect(editForm(page).locator('select[formcontrolname="status"]')).toHaveValue('to-read');

    // Modify and save. Scope the role-name match to the edit form to
    // avoid any cross-form collisions on the literal "Save".
    await editForm(page).locator('input[formcontrolname="title"]').fill('Dune Messiah');
    await editForm(page).getByRole('button', { name: 'Save' }).click();

    // Back to display mode with the updated title.
    await expect(firstRow(page).locator('app-book-form[variant="edit"]')).toHaveCount(0);
    await expect(firstRow(page).locator('.book-row-title')).toHaveText('Dune Messiah');
    await expect(firstRow(page).locator('.book-row-pages')).toHaveText('688 pages');
  });

  test('cancelling an edit restores the original row', async ({ page }) => {
    await seedOneBook(page, { title: 'Brave New World', pages: '311', status: 'to-read' });

    // Track PATCH requests to prove cancel never hits the wire.
    let patchCount = 0;
    page.on('request', (request) => {
      if (request.method() === 'PATCH' && request.url().includes('/v1/books/')) {
        patchCount += 1;
      }
    });

    await firstRow(page).getByRole('button', { name: 'Edit' }).click();
    await editForm(page).locator('input[formcontrolname="title"]').fill('Modified');
    await editForm(page).getByRole('button', { name: 'Cancel' }).click();

    // Back to display mode, title is the ORIGINAL (proves no PATCH sent).
    await expect(firstRow(page).locator('app-book-form[variant="edit"]')).toHaveCount(0);
    await expect(firstRow(page).locator('.book-row-title')).toHaveText('Brave New World');
    expect(patchCount).toBe(0);
  });

  test('deleting a book via native confirm removes the row', async ({ page }) => {
    await seedOneBook(page, { title: 'To Delete', pages: '100', status: 'to-read' });

    // `page.once` (not `page.on`) so the handler auto-detaches after
    // firing — defense in depth against future stray dialogs.
    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      // Literal from `book-row.ts:17` (BOOK_ROW_DELETE_CONFIRM_MESSAGE).
      expect(dialog.message()).toBe('Delete this book?');
      await dialog.accept();
    });

    await firstRow(page).getByRole('button', { name: 'Delete' }).click();

    await expect(page.locator('app-book-row')).toHaveCount(0);
    await expect(page.getByText('No books yet. Add one above.')).toBeVisible();
  });

  test('cancelling delete in native confirm preserves the row', async ({ page }) => {
    await seedOneBook(page, { title: 'Keep Me', pages: '200', status: 'reading' });

    // Track DELETE requests to prove dismiss never hits the wire.
    let deleteCount = 0;
    page.on('request', (request) => {
      if (request.method() === 'DELETE' && request.url().includes('/v1/books/')) {
        deleteCount += 1;
      }
    });

    page.once('dialog', async (dialog) => {
      expect(dialog.type()).toBe('confirm');
      await dialog.dismiss();
    });

    await firstRow(page).getByRole('button', { name: 'Delete' }).click();

    // Row still present, unchanged.
    await expect(page.locator('app-book-row')).toHaveCount(1);
    await expect(firstRow(page).locator('.book-row-title')).toHaveText('Keep Me');
    await expect(firstRow(page).locator('.book-row-pages')).toHaveText('200 pages');
    await expect(firstRow(page).locator('select.status-control-select')).toHaveValue('reading');
    expect(deleteCount).toBe(0);
  });

  test('invalid input (pages=0) shows inline error and preserves values', async ({ page }) => {
    // Client-side validator catches `min(1)` before the BFF sees the
    // request — `book-form.ts:185-186`. Watch POST count to prove this.
    let postCount = 0;
    page.on('request', (request) => {
      if (request.method() === 'POST' && request.url().endsWith('/v1/books')) {
        postCount += 1;
      }
    });

    await fillAddForm(page, { title: 'Bad Book', pages: '0', status: 'to-read' });
    await page.getByRole('button', { name: 'Add book' }).click();

    // Inline ErrorMessage rendered inside the form. Literal from
    // `book-form.ts:34` (BOOK_FORM_VALIDATION_PAGES_POSITIVE).
    await expect(addForm(page).locator('app-error-message')).toBeVisible();
    await expect(addForm(page).locator('app-error-message')).toContainText(
      'Page count must be a positive number.',
    );

    // Inputs preserve their values (form.reset only runs on success).
    await expect(addForm(page).locator('input[formcontrolname="title"]')).toHaveValue('Bad Book');
    await expect(addForm(page).locator('input[formcontrolname="pages"]')).toHaveValue('0');
    await expect(addForm(page).locator('select[formcontrolname="status"]')).toHaveValue('to-read');

    // No row created; no network round-trip happened.
    await expect(page.locator('app-book-row')).toHaveCount(0);
    expect(postCount).toBe(0);
  });

  test("cross-user isolation: testuser does not see freshuser's books", async ({ page }) => {
    // Add a book as `testuser` (logged in by beforeEach).
    await seedOneBook(page, { title: "Testuser's Book", pages: '333', status: 'to-read' });

    // Swap users via the new logOut helper + the existing logInAs.
    await logOut(page);
    await logInAs(page, freshuser);

    // `freshuser`'s list is empty — proves the BFF's `WHERE sub = :sub`
    // filter (books_service.py) is enforced cross-user.
    await expect(page.locator('app-book-row')).toHaveCount(0);
    await expect(page.getByText('No books yet. Add one above.')).toBeVisible();
    await expect(page.getByText('Signed in as freshuser')).toBeVisible();
  });
});
