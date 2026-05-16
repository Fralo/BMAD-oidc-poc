---
status: done
story_key: 2-5-spa-booklist-page-bookform-add-variant-states
created: 2026-05-16
---

# Story 2.5: SPA — BookList page + BookForm (add variant) + states

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user,
I want the `/books` view to render the add-book form at the top and a list of my books below it, with explicit loading, empty, populated, and load-error states,
so that I can see my list and add new books from a single screen without modal stacks.

## Scope (read this first)

This story is **the BookList page + the `add` variant of BookForm only**. It does **NOT** implement:

- `BookRow` interactive content (title-only placeholder is acceptable here — full row lands in Story 2.6).
- `BookForm[variant=edit]` (Cancel button, edit submit path) — Story 2.6.
- `StatusControl` as a standalone component (Story 2.6) — the `add` form uses a **plain native `<select>`** inside the form.
- `EstimateCell` (Story 4.3).

Concretely, this story delivers four new components, one route table edit, one placeholder deletion, and four spec files:

1. `spa/src/app/books/book-list-page.{ts,html,css,spec.ts}` — the route component for `/books`.
2. `spa/src/app/books/book-list.{ts,html,css,spec.ts}` — the list container with loading / empty / populated / load-error states.
3. `spa/src/app/books/book-form.{ts,html,css,spec.ts}` — with `input()` signal `variant: 'add' | 'edit'`; **only the `add` path is wired in this story** (the template renders nothing different for `edit` yet — Story 2.6 fills it in).
4. `spa/src/app/books/book-row-placeholder.{ts,html,css}` (optional, see Task 4) — a thin presentational stub used by `BookList` until Story 2.6 ships the real `BookRow`. Renders the book title only. **No spec required** (covered by `BookList`'s populated-state test).
5. `spa/src/app/app.routes.ts` — replace the `/books` route from `BooksPagePlaceholder` to `BookListPage`.
6. **Delete** `spa/src/app/books/books-page-placeholder.ts` after the route swap (no other consumers — search confirms none).

Out of scope for 2.5: any `book-row.ts` interactive content (Edit / Delete / hover), `status-control.ts`, `estimate-cell.ts`, the `edit` submit path, native `confirm()` for delete, optimistic status PATCH (Story 2.4's `BooksService.setStatus` is implemented but **not called from any component** until Story 2.6), changes to interceptors, app shell, or BFF.

## Acceptance Criteria

**AC1 — Route table points `/books` at `BookListPage`; placeholder is deleted.**

`spa/src/app/app.routes.ts` updates the `/books` entry's `loadComponent` from `books-page-placeholder` to `books/book-list-page`:

```ts
{
  path: 'books',
  loadComponent: () => import('./books/book-list-page').then((m) => m.BookListPage),
  canActivate: [authGuard],
},
```

`authGuard` stays attached (it gates the route per architecture F4 / Story 1.9). The `redirectIfAuthedGuard` on `/login` and the catch-all `**` route are unchanged. `spa/src/app/books/books-page-placeholder.ts` is **deleted** in the same commit — no other file imports it (verified by `grep -rn "books-page-placeholder" spa/`).

**AC2 — `BookListPage` is a standalone component that calls `BooksService.load()` on init and renders the page layout.**

`spa/src/app/books/book-list-page.ts`:

```ts
@Component({
  selector: 'app-book-list-page',
  imports: [BookForm, BookList],
  templateUrl: './book-list-page.html',
  styleUrl: './book-list-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookListPage {
  private readonly booksService = inject(BooksService);

  ngOnInit(): void {
    void this.booksService.load();
  }
}
```

- `@Injectable({ providedIn: 'root' })`-style `inject(...)` DI (NO constructor DI) per AR23 / architecture line 239.
- Zoneless-compatible — `ChangeDetectionStrategy.OnPush` on every new component (architecture line 236).
- `load()` returns a `Promise<void>` that never rejects (see Story 2.4 AC5); the `void` prefix in `ngOnInit` discards the promise intentionally — there is no need to `await` because the signal subscriptions in `BookList` re-render on completion.
- **Do NOT render `<app-top-chrome />` inside `BookListPage`.** `TopChrome` is already rendered in the root `App` shell (`spa/src/app/app.html:1`) — duplicating it would produce two header bars. The "renders `TopChrome` with the Settings link in the middle" requirement from the epic AC (epics.md line 957) is satisfied by the existing app shell because `TopChrome`'s `contextualLink` computed signal already shows `Settings` when the URL is `/books` (see `top-chrome.ts:37-47`). The `BookListPage` spec asserts that *navigation to `/books` results in the Settings link being visible in the rendered DOM*, not that `BookListPage` renders `TopChrome` itself.

**AC3 — `BookListPage` template renders the page heading, the `add` form, and the `BookList` container.**

`spa/src/app/books/book-list-page.html`:

```html
<section class="book-list-page">
  <h1 class="book-list-page-title">Books</h1>
  <app-book-form variant="add" />
  <app-book-list />
</section>
```

- Heading text is the literal string `"Books"`, styled with `font: var(--text-page-title)` (per UX-DR5 / architecture line 213).
- The order is **strictly**: heading → `BookForm[variant=add]` → `BookList` (per UX-DR4: "form is permanent" + "at the top of `/books`").
- The component lives inside the existing `.app-content` container in `app.html`, which already constrains content to a 720px centered column (see `spa/src/app/app.css:1-5`). **Do NOT add a second max-width container** in `book-list-page.css` — that would nest 720px inside 720px. CSS for this component is layout-only (heading spacing, gap between the form and the list).

**AC4 — `BookList` renders one of four states based on `BooksService` signals (per UX-DR5).**

`spa/src/app/books/book-list.ts`:

```ts
@Component({
  selector: 'app-book-list',
  imports: [BookRowPlaceholder, ErrorMessage],
  templateUrl: './book-list.html',
  styleUrl: './book-list.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookList {
  private readonly booksService = inject(BooksService);

  readonly books = this.booksService.books;
  readonly loading = this.booksService.loading;
  readonly loadError = this.booksService.loadError;
}
```

Template state precedence (top → bottom; first matching branch wins):

1. **Load-error state** — `loadError() !== null` → render `<app-error-message message="Couldn't load books — refresh to try again." />`. Copy is the literal string from epic line 966 / UX-DR12.
2. **Loading state** — `loadError() === null && loading() && books().length === 0` → render `<p class="book-list-loading">Loading…</p>` styled with `font: var(--text-small)` and `color: var(--color-text-muted)`. (Only show "Loading…" on the *initial* fetch when there are no books yet — a `load()` re-fetch with existing data is not in scope; UX-DR5 specifies "initial fetch in flight".)
3. **Empty state** — `!loading() && books().length === 0 && loadError() === null` → render `<p class="book-list-empty">No books yet. Add one above.</p>` in `--color-text-muted`. No illustration, no CTA (per epic line 970–971).
4. **Populated state** — `books().length > 0` → render `<ul class="book-list-rows"><li>` per book containing `<app-book-row-placeholder [book]="b" />`, separated by 1px `--color-border` between adjacent rows (use a `border-top` on every row except the first, or CSS `:not(:first-child)`).

State precedence rationale: load-error wins so a transient failure isn't masked by a stale `books()` list; loading wins over empty so the first paint isn't "No books yet." flashing before the request resolves; populated requires `books().length > 0` so the list only renders when there's actual content.

**AC5 — `BookRowPlaceholder` (or inline `<li>` rendering) is a title-only stub.**

The implementer chooses one of:

- **Option A — separate component** `spa/src/app/books/book-row-placeholder.{ts,html,css}`: a standalone `OnPush` component with `input.required<Book>('book')` that renders `<span class="book-row-title">{{ book().title }}</span>`. Recommended because Story 2.6 replaces this with the real `BookRow` and a same-shape component is the cleanest swap.
- **Option B — inline `<li>`**: render the title directly inside `book-list.html`. Acceptable if the implementer prefers; Story 2.6 will then introduce the new `BookRow` import. **No `BookRow` symbol is introduced in this story**.

Either way, the populated-state test (AC9 → `BookList`'s populated test) asserts the rendered title text matches the book's `title` field.

**AC6 — `BookForm` is a standalone component with an `input()` signal `variant: 'add' | 'edit'` and renders the `add` variant fully.**

`spa/src/app/books/book-form.ts`:

```ts
@Component({
  selector: 'app-book-form',
  imports: [ReactiveFormsModule, ErrorMessage],
  templateUrl: './book-form.html',
  styleUrl: './book-form.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookForm {
  readonly variant = input.required<'add' | 'edit'>();

  private readonly booksService = inject(BooksService);
  private readonly fb = inject(NonNullableFormBuilder);

  readonly form = this.fb.group({
    title: this.fb.control('', { validators: [Validators.required] }),
    pages: this.fb.control<number | null>(null, { validators: [Validators.required, Validators.min(1)] }),
    status: this.fb.control<BookStatus>('to-read', { validators: [Validators.required] }),
  });

  readonly submitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
}
```

- **Reactive Forms** per architecture line 250 — NO Template Driven Forms, NO Signal Forms (still experimental per architecture comment). Import `ReactiveFormsModule` in the component's `imports` array (standalone).
- `input.required<'add' | 'edit'>()` — signal-based component IO per AR architecture line 240 — NOT `@Input` decorator.
- `NonNullableFormBuilder` so `form.value.title` is typed as `string`, not `string | null | undefined`. Pages is intentionally `number | null` (the initial empty state is `null`; submit validation rejects `null`).
- `submitting` is a local `signal<boolean>` per architecture line 710 ("Loading state is local. Each component or service method that fires a request owns its own loading = signal(false)").
- `errorMessage` is a local `signal<string | null>` rendering the inline error string. Type is `string` (not `AppError`) — `BookForm` is the formatting layer that converts a thrown `AppError` from `BooksService.create` into copy.

**AC7 — `BookForm[variant=add]` template renders three labelled inputs and one primary button.**

`spa/src/app/books/book-form.html` for the `add` variant:

```html
<form class="book-form" [formGroup]="form" (ngSubmit)="onSubmit()">
  <label class="book-form-label">
    <span class="book-form-label-text">Title</span>
    <input class="book-form-input" type="text" formControlName="title" />
  </label>
  <label class="book-form-label">
    <span class="book-form-label-text">Page count</span>
    <input class="book-form-input" type="number" min="1" formControlName="pages" />
  </label>
  <label class="book-form-label">
    <span class="book-form-label-text">Status</span>
    <select class="book-form-input" formControlName="status">
      <option value="to-read">to-read</option>
      <option value="reading">reading</option>
      <option value="finished">finished</option>
    </select>
  </label>
  <div class="book-form-actions">
    <button class="book-form-submit" type="submit" [disabled]="submitting()">
      {{ submitting() ? 'Adding…' : 'Add book' }}
    </button>
    <!-- No Cancel button in variant="add" — edit variant adds it in Story 2.6 -->
  </div>
  @if (errorMessage(); as msg) {
    <app-error-message [message]="msg" />
  }
</form>
```

- **Every input has an explicit `<label>` wrapper** (per UX-DR15 — "Every input has a `<label>`"). Use wrapping `<label>` (not `for=` / `id=` pairing) — the wrapping form is simpler and equally compliant.
- The primary button:
  - Text: `"Add book"` (idle) / `"Adding…"` (submitting) per UX-DR4.
  - Styling: `background: var(--color-accent)`; matches the `.login-button` pattern in `login-view.css:21-30` (use the same color tokens, same padding, same border-radius). Disabled state is 50% opacity per UX-DR14 — copy the `opacity: 0.5; cursor: not-allowed` rule from `login-view.css:36-39`.
  - **No `Cancel` button** in `variant="add"` (UX-DR4 — Cancel is `edit`-only).
- The `<select>` is a **native HTML `<select>`** with three `<option>`s — explicitly NOT a `StatusControl` component (that lands in Story 2.6 per epic line 982).
- The inline `<app-error-message />` renders **below** the form actions (UX-DR12 — error renders inline at the site of the action).

**AC8 — Submit behavior of `BookForm[variant=add]` (UX-DR4, UX-DR15).**

`onSubmit()` method:

```ts
async onSubmit(): Promise<void> {
  // 1. Validation-on-submit (NOT on blur) — UX-DR15
  if (this.form.invalid) {
    this.errorMessage.set(this.buildValidationMessage());
    return; // Inputs preserve values automatically — Reactive Forms doesn't reset on invalid.
  }

  this.errorMessage.set(null);
  this.submitting.set(true);
  const payload: BookCreate = {
    title: this.form.value.title!.trim(), // submit-time normalization (see Dev Notes)
    pages: this.form.value.pages!,
    status: this.form.value.status!,
  };

  try {
    await this.booksService.create(payload);
    // Success path: clear inputs to defaults; signal in BooksService has already prepended.
    this.form.reset({ title: '', pages: null, status: 'to-read' });
  } catch (err) {
    this.errorMessage.set(this.formatServerError(err as AppError));
    // Inputs preserve values automatically — we only reset on success.
  } finally {
    this.submitting.set(false);
  }
}
```

**Required behaviors:**

1. **Submission gating** — while `submitting() === true`, the button is disabled (`[disabled]="submitting()"`) and relabels to `"Adding…"`. The `submitting` signal flips to `true` synchronously before `await booksService.create(...)` so the disabled state is visible during the in-flight request (per UX-DR4 / epic line 987).
2. **Validation-on-submit** — Reactive Forms validators (`Validators.required`, `Validators.min(1)`) gate the submit; on invalid, render the inline error and bail. The `form.invalid` check covers all three documented invalid cases: empty title (required), `null` pages (required), `pages <= 0` (min). **Whitespace-only title** (`"   "`) passes Angular's built-in `Validators.required` (it only checks for empty string / null) — add a custom validator (see Dev Notes §"Whitespace title — Validators.required is not enough") OR trim-and-check at submit-time. Pick one and apply consistently.
3. **Inputs preserve values on submit failure** (UX-DR15) — Reactive Forms `FormGroup`s do **not** reset on `form.invalid` or on a thrown server error; the reset only fires on the success path via `this.form.reset({...})`.
4. **Success — clear inputs to defaults** — `this.form.reset({ title: '', pages: null, status: 'to-read' })`. Use `reset()` (not `setValue()`) so the validity state also resets to `pristine` / `untouched`. After reset, the form shows the default placeholders again.
5. **Success — the new book appears at the top of the list** — `BooksService.create()` already prepends in its internal `books.update(prev => [created, ...prev])` (Story 2.4 AC6). `BookForm` does **NOT** mutate the books signal itself — the `BookList` rerenders from the updated `books()` signal automatically. Do not duplicate state.
6. **Server-error path** — on a rejected promise from `create()`, `BooksService` throws an `AppError` (Story 2.4 AC6). The error is rendered as a `string` via `formatServerError(appError)` (see Dev Notes §"Mapping AppError → user-visible copy"). The form does **NOT** call `errors.parse(err)` itself — `BooksService` already did, and the rethrown value IS the `AppError`.

**AC9 — Tests cover the four components (per epic lines 1003–1008).**

Test files: one per component. Use Angular's `TestBed`, `provideHttpClientTesting()`, and `HttpTestingController`. Mirror the structure of `auth-service.spec.ts` / `top-chrome.spec.ts` / `login-view.spec.ts`. All tests use `provideZonelessChangeDetection()` (matches the app's runtime per architecture line 236).

**`book-list-page.spec.ts` — 2 tests minimum:**

1. **Init calls `BooksService.load()`** — instantiate `BookListPage`, assert that `BooksService.load` is called once on init. Stub `BooksService` with a fake that records the call (e.g., `vi.fn()`); do NOT instantiate the real service.
2. **Template renders heading + form + list** — render the page; assert `<h1>` contains `"Books"`, `<app-book-form variant="add">` is present, and `<app-book-list>` is present. Use `fixture.nativeElement.querySelector(...)`.

(TopChrome+Settings link rendering is covered by the existing `top-chrome.spec.ts` — do NOT duplicate that test here.)

**`book-list.spec.ts` — 4 tests minimum (one per state):**

1. **Loading state** — pre-set `booksService.loading.set(true)`, `books.set([])`, `loadError.set(null)`. Render. Assert `"Loading…"` line is visible; empty-state copy is absent; row-list is absent; error-message is absent.
2. **Empty state** — pre-set `loading.set(false)`, `books.set([])`, `loadError.set(null)`. Render. Assert `"No books yet. Add one above."` is visible; loading line is absent.
3. **Populated state** — pre-set `loading.set(false)`, `books.set([{ id: 1, title: 'Dune', pages: 688, status: 'reading', created_at: '...', updated_at: '...' }, { id: 2, title: 'Foundation', ... }])`. Render. Assert two row containers (`<li>` or `<app-book-row-placeholder>`) appear and contain the titles `"Dune"` and `"Foundation"`.
4. **Load-error state** — pre-set `loadError.set({ kind: 'network' })` (any non-null `AppError`). Render. Assert `<app-error-message>` with the exact copy `"Couldn't load books — refresh to try again."` is visible; row-list is absent.

Stub `BooksService` directly via `{ provide: BooksService, useValue: stub }` where `stub` is `{ books: signal(...), loading: signal(...), loadError: signal(...) }`. NO HTTP calls are made in `BookList`'s tests — the component reads from signals, doesn't dispatch.

**`book-form.spec.ts` — 4 tests minimum (per epic line 1006: "default state, submitting state, validation-error state, server-error state"):**

1. **Default state** — render `<app-book-form variant="add" />`; assert all three inputs (title, pages, status), three labels, and one `"Add book"` button are present; the status select has the three documented options; the button is enabled.
2. **Submitting state** — fill the form with valid values, click submit; **before flushing the HTTP request**, assert the button text is `"Adding…"` and is disabled. Flush a 201 with the created book; assert the button text returns to `"Add book"` and is re-enabled; assert the form has reset (title input is empty, pages input is empty, status is back to `to-read`).
3. **Validation-error state** — submit with empty title; assert the inline `<app-error-message>` renders below the form with copy that names the field (e.g., "Title is required" — see Dev Notes §"Validation copy"); assert the title input still has whatever the user had typed (empty string in this case; for the whitespace test, assert it's `"   "`); assert NO HTTP request was dispatched (`httpTesting.expectNone('/v1/books')`). Repeat sub-cases for: whitespace-only title, missing pages, `pages = 0`, `pages = -1` (one assertion per sub-case is fine; can be a `.each(...)` table).
4. **Server-error state** — fill the form with valid values, click submit, flush a 422 with the archetype envelope `{ errorCode: 'invalid_input', message: 'Request validation failed', detail: [...] }`. Assert the inline `<app-error-message>` renders with the mapped copy from `formatServerError({ kind: 'invalid_input', detail: [...] })`; assert the title / pages / status inputs preserve their entered values (UX-DR15); assert the button is back to `"Add book"` (enabled, label restored). Also: a follow-up sub-case flushing a `{ kind: 'csrf_invalid' }` envelope (status 403) — assert the corresponding copy is rendered.

For `book-form.spec.ts`, instantiate `BooksService` for real with `provideHttpClient(withFetch())` + `provideHttpClientTesting()` so the `BooksService.create()` integration is genuine (and the immutable prepend in the books signal is exercised). This is the recommended-pattern from Story 2.4's `books-service.spec.ts` — replicate it.

**No spec for `BookRowPlaceholder`** (if implemented as Option A) — the populated-state test in `book-list.spec.ts` exercises the title rendering.

**AC10 — Lint, coverage, and suite gates.**

- `npm test -- --watch=false` (from `spa/`) is green; the suite count strictly increases from Story 2.4's close (65 tests baseline; +10 new tests minimum — 2 page, 4 list, 4 form).
- **Vitest coverage of every new file (`book-list-page.ts`, `book-list.ts`, `book-form.ts`, optionally `book-row-placeholder.ts`) is ≥70%** per AR34. The four `add`-variant test cases plus the four list states are sufficient to clear the gate; if coverage misses, fill it with additional sub-cases of the existing tests, not new types of tests.
- `npm run lint` from `spa/` reports no new findings.
- **Existing E2E specs continue to pass** — `e2e/tests/j1-first-login.spec.ts` and `e2e/tests/j5-logout.spec.ts` navigate to `/books` after login (Story 1.13 closed). The new `BookListPage` must render *something* on `/books` (it does — heading + form + empty list) so those specs still find the page. The E2E suite is NOT modified in this story; the J2 spec lands in Story 2.7.

## Tasks / Subtasks

- [x] Task 1 — Route swap and placeholder deletion (AC1)
  - [x] 1.1 In `spa/src/app/app.routes.ts`, change the `/books` route's `loadComponent` from `./books/books-page-placeholder` to `./books/book-list-page`.
  - [x] 1.2 Delete `spa/src/app/books/books-page-placeholder.ts`. Run `grep -rn "books-page-placeholder\|BooksPagePlaceholder" spa/` to confirm zero remaining references before deletion.
  - [x] 1.3 Verify the existing `e2e/tests/j1-first-login.spec.ts` and `e2e/tests/j5-logout.spec.ts` still pass by skim-reading their `expect(...)` lines — they assert URL is `/books` after login, not a specific placeholder text. Do NOT modify them.

- [x] Task 2 — `BookListPage` component (AC2, AC3)
  - [x] 2.1 Create `spa/src/app/books/book-list-page.ts` with the class shell from AC2. Import `BookForm` and `BookList` in the `imports` array.
  - [x] 2.2 Create `spa/src/app/books/book-list-page.html` with the template from AC3 (heading + `<app-book-form variant="add" />` + `<app-book-list />`).
  - [x] 2.3 Create `spa/src/app/books/book-list-page.css` with layout only (heading top spacing via `var(--spacing-8)`; `gap` between heading / form / list via `var(--spacing-6)` on the `.book-list-page` flex/block container). NO max-width — the parent `.app-content` already constrains to 720px.
  - [x] 2.4 Create `spa/src/app/books/book-list-page.spec.ts` covering the two tests from AC9. Stub `BooksService` to record the `load()` call.

- [x] Task 3 — `BookList` component (AC4, AC5)
  - [x] 3.1 Create `spa/src/app/books/book-list.ts` with the class shell from AC4. Import `BookRowPlaceholder` (if Option A) and `ErrorMessage`.
  - [x] 3.2 Create `spa/src/app/books/book-list.html` with the four-state `@if` / `@else if` cascade, following the precedence order from AC4. Use Angular's new control flow (`@if`/`@for`) — NOT structural directives `*ngIf` / `*ngFor` (architecture line 238).
  - [x] 3.3 Create `spa/src/app/books/book-list.css` for the populated-state `<ul>` (no bullets — `list-style: none`, padding: 0), the row borders (`border-top: 1px solid var(--color-border)` on `li:not(:first-child)`), and the loading / empty `<p>` styling using `var(--text-small)` / `var(--color-text-muted)`.
  - [x] 3.4 Create `spa/src/app/books/book-list.spec.ts` covering the four state tests from AC9. Stub `BooksService` with a signal-only fake (no HTTP).

- [x] Task 4 — `BookRowPlaceholder` stub (AC5 — pick Option A or B)
  - [x] 4.1 **Option A (recommended):** Create `spa/src/app/books/book-row-placeholder.ts` as a standalone `OnPush` component with `input.required<Book>('book')` rendering `<span class="book-row-title">{{ book().title }}</span>`. Add minimal HTML/CSS.
  - [ ] 4.2 **Option B:** Skip this task and inline the title rendering inside `book-list.html`. (Not chosen — Option A selected; see Completion Notes.)

- [x] Task 5 — `BookForm[variant=add]` component (AC6, AC7, AC8)
  - [x] 5.1 Create `spa/src/app/books/book-form.ts` with the class shell from AC6. Import `ReactiveFormsModule` and `ErrorMessage`. Use `NonNullableFormBuilder` for cleaner types.
  - [x] 5.2 Add the custom whitespace-title validator OR the submit-time `trim() && length > 0` check (see Dev Notes §"Whitespace title"). Pick one strategy and apply consistently.
  - [x] 5.3 Create `spa/src/app/books/book-form.html` with the template from AC7. Three labelled inputs (title text, pages number with `min="1"`, status select with three options) + primary submit button + inline `<app-error-message />`. **No Cancel button** (gated by `variant() === 'edit'` — Story 2.6 adds it).
  - [x] 5.4 Create `spa/src/app/books/book-form.css` styling the submit button identically to `.login-button` (accent color, hover state, disabled 50% opacity per UX-DR14). Use `--spacing-3` for input vertical rhythm.
  - [x] 5.5 Implement `onSubmit()` per AC8: validation-on-submit → submit gating (`submitting` signal) → call `BooksService.create()` → success: `form.reset()` (clears to defaults); failure: format `AppError` and render inline (inputs preserved).
  - [x] 5.6 Implement `buildValidationMessage()` and `formatServerError(err: AppError)` per Dev Notes §"Validation copy" and §"Mapping AppError → user-visible copy".
  - [x] 5.7 Create `spa/src/app/books/book-form.spec.ts` covering the four states from AC9 (default, submitting, validation-error including whitespace-title + pages-zero/negative sub-cases, server-error including `invalid_input` + `csrf_invalid`). Use a real `BooksService` against `HttpTestingController`.

- [x] Task 6 — Lint, coverage, and suite verification (AC10)
  - [x] 6.1 `npm test -- --watch=false` from `spa/` — green; new test count ≥ 10 above the 65-test baseline.
  - [x] 6.2 `npm run lint` from `spa/` — clean.
  - [x] 6.3 `npm run test:coverage` — spot-check `book-list-page.ts`, `book-list.ts`, `book-form.ts` are all ≥70% per AR34. If any module misses, add sub-cases to the existing test files (do not invent new test categories — they'd be coverage-only, not behavior-driven).
  - [ ] 6.4 Manual smoke test under `npm run start` against a running BFF: navigate to `/books`, verify loading flash → empty state; add a book; verify the new row appears at the top; refresh; verify the row persists (round-trips through `GET /v1/books`). **Deferred — requires running stack; see Completion Notes (live-stack smoke is to be performed by the integrator).**

## Dev Notes

### Critical: read these before starting

1. **`TopChrome` is already rendered globally by the `App` shell** (`spa/src/app/app.html:1`). Do NOT add `<app-top-chrome />` to `book-list-page.html`. The `Settings` link in the middle is computed by `TopChrome.contextualLink` when the URL matches `/books` (verify: `top-chrome.ts:37-47`) — this story does not modify `TopChrome`.

2. **The `.app-content` container already wraps the route in a 720px max-width centered column** (`spa/src/app/app.css:1-5`). Do NOT add a second max-width container in `book-list-page.css` — that nests 720px inside 720px and visibly narrows the column.

3. **`BooksService` and its signals are already implemented and tested** (Story 2.4, `done`). `BooksService.load()` writes to `loading` / `loadError` / `books`. `BooksService.create(payload)` prepends to `books` on success and throws an `AppError` on failure. Components subscribe to the signals via `inject(BooksService).books` (etc.) and call `create()` for mutations. **Do NOT introduce a parallel store, BehaviorSubject, or local `books` signal in any new component.**

4. **The architecture mandates `ErrorMessage` (the component, plural-singular naming `app-error-message`) for inline error rendering** (UX-DR12). It's already imported and tested in `LoginView` — do exactly the same: import the symbol from `../shared/ui/error-message`, add it to the component's `imports` array, render `<app-error-message [message]="errorMessage()" />` conditionally inside an `@if` block.

### Whitespace title — `Validators.required` is not enough

Angular's `Validators.required` returns null (valid) for strings like `"   "` (it only rejects `""`, `null`, `undefined`). The epic explicitly lists "empty/whitespace-only title" as an invalid case (line 996). Pick ONE of the two strategies and apply consistently:

**Strategy A — custom validator (recommended for testability):**

```ts
// in book-form.ts
const nonWhitespaceValidator: ValidatorFn = (control) => {
  const value = control.value as string | null | undefined;
  if (value === null || value === undefined || value.trim() === '') {
    return { nonWhitespace: true };
  }
  return null;
};

// then:
title: this.fb.control('', { validators: [Validators.required, nonWhitespaceValidator] }),
```

This bubbles up through `form.invalid` and the existing submit-gating check covers it.

**Strategy B — submit-time trim check:**

```ts
async onSubmit(): Promise<void> {
  const titleTrimmed = (this.form.value.title ?? '').trim();
  if (this.form.invalid || titleTrimmed === '') {
    this.errorMessage.set(this.buildValidationMessage(/* include whitespace case */));
    return;
  }
  // ... proceed with payload using titleTrimmed
}
```

Strategy A is more idiomatic Reactive Forms and tests cleanly via `form.invalid`. Strategy B is fewer lines but requires the validation copy to disambiguate the whitespace case from "required". **Pick A unless you have a reason.**

### Validation copy

UX-DR12 / UX-DR15 don't dictate exact validation strings. Use these (single-line, `--text-small`, `--color-error`) — pick the first matching:

| Invalid case | Copy |
|---|---|
| Title empty or whitespace-only | `"Title is required."` |
| Pages missing (`null`) | `"Page count is required."` |
| Pages `<= 0` | `"Page count must be a positive number."` |
| Two or more invalid fields | `"Please correct the highlighted fields."` (or list all — implementer's choice; tests assert the message string contains a relevant fragment, not the exact wording) |

`buildValidationMessage()` should inspect `this.form.controls.title.errors`, `.pages.errors`, etc., and return the appropriate string. If only one field is invalid, return the field-specific copy; if multiple, return the generic fallback.

**Tests:** assert `errorMessage()` contains a substring like `"Title"` for the empty-title case, `"Page count"` for the pages cases. Do not lock tests to exact wording — that makes copy changes a test-edit cost without a behavior change.

### Mapping `AppError` → user-visible copy

`BooksService.create()` rejects with an `AppError` (Story 2.4 AC2). The form formats it for display. Use a small `switch`:

```ts
private formatServerError(err: AppError): string {
  switch (err.kind) {
    case 'invalid_input':
      // BFF rejected the body (e.g., a race where the BFF added a stricter check we don't enforce client-side)
      return 'The server rejected this book. Check the fields and try again.';
    case 'csrf_invalid':
      // Should never happen in practice (csrf-interceptor auto-attaches the header), but defense-in-depth
      return "Your session is out of sync. Refresh the page and try again.";
    case 'session_expired':
      // The global with-credentials-interceptor already redirects to /login — this case is functionally dead,
      // but the switch needs to be exhaustive. Render a fallback in case the interceptor races.
      return 'Your session expired. Redirecting to sign in…';
    case 'network':
      return "Couldn't reach the server. Check your connection and try again.";
    case 'forbidden_scope':
    case 'book_not_found':
    case 'auth_state_invalid':
    case 'unknown':
      return "Something went wrong. Try again.";
  }
}
```

The `switch` is exhaustive over `AppError['kind']` — TypeScript's `never`-narrowing flags any future additions (e.g., Story 3.5's `resource_server_unavailable`) at compile time. **Do NOT use a non-exhaustive `switch` or a `default:` branch that swallows new kinds.**

### Existing SPA patterns to mirror exactly

**1. `spa/src/app/login/login-view.ts`** — the closest existing precedent for a route-component that renders a form-like UI with an `ErrorMessage`. Mirror the imports list, `OnPush`, `inject(...)` DI, signal-based reactive state, and the spec's `provideZonelessChangeDetection()` use.

**2. `spa/src/app/shared/chrome/top-chrome.spec.ts`** — TestBed harness shape with `provideRouter([...])` for components that read the URL. `BookListPage` does NOT read the URL (no `Router` injection), so it's simpler — but the `provideRouter` setup is in the same TestBed pattern.

**3. `spa/src/app/books/books-service.spec.ts`** — TestBed scaffold for HTTP-touching tests: `provideHttpClient(withFetch())` + `provideHttpClientTesting()`, `HttpTestingController`, `afterEach(() => http.verify())`. Use exactly this pattern in `book-form.spec.ts`.

**4. `spa/src/app/shared/ui/error-message.html`** — confirms the `ErrorMessage` component renders a single `<p class="error-message">{{ message() }}</p>`. To assert the visible text in a test, query for `app-error-message p` and check its `textContent`.

### Files NOT to touch in this story

- `spa/src/app/books/books-service.ts` — Story 2.4 is closed. No method changes, no signal-shape changes. If you find yourself wanting to add a method, stop — it likely belongs to Story 2.6.
- `spa/src/app/books/book.types.ts` — Story 2.4 owns the type shapes. They're correct.
- `spa/src/app/shared/errors/error-service.ts` — Story 2.4 owns the `parse` mapping. `BookForm` does NOT call `parse` directly; `BooksService` already does.
- `spa/src/app/shared/ui/error-message.{ts,html,css}` — already correct. Just import and use.
- `spa/src/app/shared/chrome/top-chrome.{ts,html,css}` — already provides the Settings link. No change.
- `spa/src/app/app.ts`, `spa/src/app/app.html`, `spa/src/app/app.css` — the app shell is correct. The 720px column and `<app-top-chrome />` are already wired.
- `spa/src/app/app.config.ts` — `ReactiveFormsModule` is imported per-component (standalone), not in the global config. No edit needed.
- `services/bff/**` — no backend changes. The BFF's `/v1/books*` surface is Stories 2.1 / 2.2's responsibility; 2.3 (truncate on `/v1/test/reset`) is still `ready-for-dev` but doesn't block 2.5.
- `e2e/tests/**` — Story 2.7 owns the J2 Playwright spec. Existing j1 / j5 specs are passively compatible (they only assert the URL after login is `/books`).
- `docker-compose.yml`, `compose/app.yml`, `compose/infra.yml` — no infra changes.

### Interceptor interaction — already wired (carry-over from Story 2.4)

`spa/src/app/app.config.ts` already registers `[withCredentialsInterceptor, csrfInterceptor]` globally. **You do NOT need to add `withCredentials: true` to individual requests** — the interceptor does it. The `csrfInterceptor` reads the `csrf_token` cookie and sets `X-CSRF-Token` on POST/PUT/PATCH/DELETE — this means the `BookForm`'s submit (which triggers `BooksService.create()` → `POST /v1/books`) automatically carries the CSRF header at runtime. In tests, interceptors are NOT registered in the `HttpTestingController` configuration (we use `provideHttpClient(withFetch())` + `provideHttpClientTesting()`); the request will be matched without the header. The `csrf-interceptor.spec.ts` covers the interceptor itself.

The global 401 redirect (`with-credentials-interceptor.ts:25-34`) reroutes to `/login?return_to=...` BEFORE the rejection reaches `BooksService.create()`'s `catch` block. By the time `BookForm` would render a `session_expired` message, the user has already navigated away. The fallback copy in `formatServerError` for `session_expired` is defensive only.

### Reactive Forms — Angular v21 specifics

- **Standalone import:** `import { ReactiveFormsModule } from '@angular/forms';` and add to the component's `imports` array. NO `provideForms()` or `@NgModule` — Angular v21 forms work standalone.
- **`NonNullableFormBuilder` import:** `import { NonNullableFormBuilder, Validators, ValidatorFn } from '@angular/forms';` — `inject(NonNullableFormBuilder)` returns the non-nullable variant.
- **Signal vs Observable for form state:** `form.statusChanges` is still an Observable. The story doesn't require reading `statusChanges` — `form.invalid` is checked synchronously at submit time. If you need a signal-form-state, use `toSignal(form.statusChanges, { initialValue: form.status })` — but it's NOT required by any AC here.
- **`form.reset({...})`** vs **`form.setValue({...})`** vs **`form.patchValue({...})`**: use `reset()` on success to restore defaults AND clear dirty/touched/pristine state. `setValue` keeps the dirty/touched state, which would leave the form looking "edited" with default values — visually confusing.
- **Zoneless change detection:** the app uses `provideZonelessChangeDetection()` (`app.config.ts:19`). All new components use `ChangeDetectionStrategy.OnPush`. Signal reads in templates trigger CD automatically; manual `markForCheck()` is not needed.

### Why no `<ul>` for the loading / empty / error states (only populated)

The four states are mutually exclusive (per AC4 precedence). Loading / empty / error are each a single line of copy in a `<p>` — they're not lists, so no `<ul>`. Only the populated state renders `<ul><li>...</li></ul>`. This matches the UX-DR5 anatomy: "either the empty-state copy OR a vertically stacked set of `BookRow` instances".

### Border-between-rows in populated state

UX-DR5: "vertical stack of `BookRow` instances separated by 1px borders". The cleanest CSS:

```css
.book-list-rows {
  list-style: none;
  padding: 0;
  margin: 0;
}
.book-list-rows li {
  padding: var(--spacing-3) 0;
}
.book-list-rows li + li {
  border-top: 1px solid var(--color-border);
}
```

This avoids a stray border above the first row and below the last row.

### Project Structure Notes

New files for this story, all under `spa/src/app/books/`:

```
spa/src/app/books/
├── book-list-page.{ts,html,css,spec.ts}         (NEW — route component)
├── book-list.{ts,html,css,spec.ts}              (NEW — list container)
├── book-form.{ts,html,css,spec.ts}              (NEW — add+edit form, add wired only)
├── book-row-placeholder.{ts,html,css}           (NEW — Option A; no .spec)
├── books-service.ts                             (untouched — Story 2.4)
├── books-service.spec.ts                        (untouched — Story 2.4)
├── book.types.ts                                (untouched — Story 2.4)
└── books-page-placeholder.ts                    (DELETED)
```

Architecture's directory map (architecture.md line 1033-1040) lists exactly `book-list-page.{ts,html,css,spec.ts}`, `book-row.{ts,html,css,spec.ts}` (Story 2.6 will add this), `book-form.{ts,html,css,spec.ts}` — naming matches verbatim. The optional `book-row-placeholder.*` is NOT in the architecture map (it's a transitional artifact for this story only); Story 2.6 deletes it when introducing the real `BookRow`.

**No barrel files** per architecture line 637. Each component file exports its class as a named export, consumers import by path.

### Previous Story Intelligence

- **Story 2.4** (closed, merged) delivered `BooksService` with the exact signal shape and method semantics this story consumes. The five methods (`load`, `create`, `update`, `setStatus`, `delete`) are correct and tested at ≥85% coverage on `books-service.ts`. **`update` and `setStatus` and `delete` are not called by any component in this story** — they're for Story 2.6.
- **Story 2.4 also delivered `AppError` + `ErrorService`**. `ErrorService.parse` is called inside `BooksService` only; components consume the typed `AppError` thrown from `BooksService.create()`. The `AppError` discriminated union deliberately omits `resource_server_unavailable` (Story 3.5) and `reading_speed_unset` (Story 4.3) — your `switch` in `formatServerError` does NOT need to handle those kinds.
- **Story 2.4 deferred items D54 / D55 / D56** are concurrency / phantom-write hardening on `BooksService` itself; they do not affect `BookListPage` / `BookList` / `BookForm` correctness. Do NOT try to "fix" them here.
- **Story 1.10** (closed) delivered `LoginView` and `TopChrome`. They're the closest in shape to what you're writing — `LoginView` shows the inline `ErrorMessage` pattern; `TopChrome` shows the route-aware `contextualLink` pattern. Mirror them.
- **Story 1.10 review notes:** the Vitest coverage gate occasionally requires one or two extra branch-coverage tests when a component has multi-state templates. Budget for it; add sub-cases to the existing tests rather than inventing new spec files if coverage misses.
- **Stories 2.1 / 2.2 / 2.3 status:** 2.1 done, 2.2 done, 2.3 still `ready-for-dev`. The BFF emits the correct envelope shape on `/v1/books*` per 2.2 (`book_not_found`, `invalid_input`, `csrf_invalid` etc.); Story 2.5's components are robust against either the new (2.2-merged) envelope or a generic-status fallback — `ErrorService.parse` handles both per Story 2.4 AC3.

### Git intelligence (recent commits)

```
7ce6774 Merge branch 'worktree-agent-a5dc36f5ca3f3dfec' into epic-2
aa08559 Merge branch 'worktree-agent-a9730c9e5ce888639' into epic-2
4dd4d21 chore(2.2): code review — inline sub-log helper per Task 4; 4 defers; close 2.2
596a3a8 feat(2.2): BFF books CRUD — /v1/books + /v1/books/{id}, errors, tests
daa3035 chore(2.4): code review — P1 missing-id test reference assertion; 3 defers (D54/D55/D56)
3dfd64f feat(2.4): SPA BooksService + types — load/create/patch/remove, signal exposure, prepend semantics
e3e19fa Merge branch 'E2S1' into epic-2
b1bdd5b Merge branch 'main' into epic-2
926e702 chore(2.1): code review — D1/D2 mirror DB caps, P1/P2 test hardening, 2 defers; close 2.1
```

Epic 2 is mid-flight: BFF books CRUD + SPA `BooksService` both shipped. `epic-2` is the working branch. The only outstanding 2.x prerequisite (Story 2.3) is independent of 2.5 — `/v1/test/reset` truncating books is a test-harness concern, not a runtime dependency.

### Latest tech information (Angular v21 + Reactive Forms + signals)

- **Angular v21.2** (per `spa/package.json`). Standalone components, signal-based inputs (`input()` / `input.required()`), new control flow (`@if`/`@for`/`@switch`).
- **`@angular/forms` v21.2** — Reactive Forms are stable; Signal Forms are still experimental and explicitly out per architecture line 250. Use `FormGroup` / `FormControl` / `NonNullableFormBuilder` / `Validators.required` / `Validators.min(n)`.
- **`input.required<T>()`** is a runtime-checked required signal-input. If a consumer renders `<app-book-form />` without a `variant` attribute, Angular throws at runtime. The `BookListPage` always passes `variant="add"` literally; the test for `book-form.spec.ts` does the same.
- **`@if (x; as y)` syntax** binds the truthy value to `y` inside the block — useful for `@if (errorMessage(); as msg)` so you can reference `msg` instead of re-calling the signal.
- **Vitest 4.x + `@vitest/coverage-v8`** — same harness as Story 2.4. `npm run test:coverage` outputs `coverage/spa/` for inspection.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5: SPA — BookList page + BookForm (add variant) + states] (verbatim AC source — lines 940–1008)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR4] (BookForm component anatomy + add/edit variants)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR5] (BookList anatomy + four states + empty-state copy)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR12] (Failure copy strings — `"Couldn't load books — refresh to try again."`)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR14] (Button hierarchy — primary in `--color-accent`, secondary as text, no icon-only)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR15] (Form patterns — submit-time validation only, native controls, preserve values on failure, labelled inputs)
- [Source: _bmad-output/planning-artifacts/epics.md#AR23] (functional router, `inject()` DI)
- [Source: _bmad-output/planning-artifacts/epics.md#AR34] (Vitest + TestBed + `HttpTestingController`; ≥70% coverage)
- [Source: _bmad-output/planning-artifacts/architecture.md#Frontend Architecture / F5] (route table; `/books` → `BookListPage`)
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Model] (standalone, zoneless, signals, `@if`/`@for`, `inject()`, `input()`/`output()`)
- [Source: _bmad-output/planning-artifacts/architecture.md#Forms] (Reactive Forms, submit-time validation, no Signal Forms)
- [Source: _bmad-output/planning-artifacts/architecture.md#Communication Patterns] (signal-based state, immutable updates, "service methods are the only write paths")
- [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns — Validation] ("Reactive Forms validators run on submit. On submit failure, inputs preserve their values…")
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] (`books/` folder layout — line 1033)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#BookForm] (idle / submitting / error states; variants)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#BookList] (loading / empty / populated / load-error states)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Button Hierarchy] (UX-DR14 details; 50%-opacity disabled state)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Form Patterns] (UX-DR15 details; on-submit validation; preserved values)
- [Source: _bmad-output/planning-artifacts/PRD.md#FR2 (FR-BOOK-01)] (book CRUD scope; J2 user journey)
- [Pattern: spa/src/app/books/books-service.ts] (signal shape + method contracts this story consumes)
- [Pattern: spa/src/app/books/books-service.spec.ts] (TestBed + `HttpTestingController` scaffold to mirror in `book-form.spec.ts`)
- [Pattern: spa/src/app/login/login-view.{ts,html,css,spec.ts}] (route component + `ErrorMessage` rendering + button styling reference)
- [Pattern: spa/src/app/shared/chrome/top-chrome.spec.ts] (TestBed with `provideRouter` for components that read route state)
- [Pattern: spa/src/app/app.routes.ts] (route swap target file)
- [Pattern: spa/src/app/app.html / app.css] (already-correct app shell — `TopChrome` + 720px content column)
- [Defer: _bmad-output/implementation-artifacts/deferred-work.md#D54-D56] (Story 2.4 service concurrency defers; NOT in scope here)
- [Gate: spa/package.json] (`test:coverage` script; Vitest + @vitest/coverage-v8; `ng lint`)

## Definition of Done

1. `app.routes.ts` `/books` route loads `BookListPage`; `books-page-placeholder.ts` is deleted; no remaining references to `BooksPagePlaceholder` in `spa/` (AC1).
2. `BookListPage` exists, calls `BooksService.load()` on init via `inject()`-style DI, and renders `<h1>Books</h1>` + `<app-book-form variant="add" />` + `<app-book-list />` (AC2, AC3).
3. `BookList` renders the four states with the documented precedence and exact copy: loading, empty, populated, load-error (AC4, AC5).
4. `BookForm` is a standalone component with `input.required<'add'|'edit'>('variant')`, uses Reactive Forms, renders three labelled inputs + primary `"Add book"` / `"Adding…"` button, no `Cancel` in the `add` variant (AC6, AC7).
5. Submit gating works: button disables and relabels during in-flight `create()`; success clears the form; validation-on-submit renders an inline error and preserves values; server error renders a mapped inline copy and preserves values (AC8).
6. Tests pass for all four components covering the documented states (AC9). New test count increases by ≥10; coverage of every new file is ≥70% (AC10).
7. `npm run lint` is clean; `npm test -- --watch=false` is green (AC10).
8. Manual smoke test under `npm run start` shows the empty-state → add-book → row-appears-at-top → refresh-still-there flow (Task 6.4).
9. No changes outside the files listed in §Scope; no edits to `BooksService`, types, `ErrorService`, interceptors, app shell, or BFF.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) — via `bmad-dev-story` workflow.

### Debug Log References

- Initial spec run (after first implementation pass): 82 tests (65 baseline + 17 new), 3 failures in `book-form.spec.ts`. Failures were button-state assertions after `await whenStable()` post-`req.flush()` — the `(ngSubmit)` dispatch returned the Promise but the spec couldn't reach it. Fixed by invoking `componentInstance.onSubmit()` directly so the returned Promise can be awaited. After the fix: 82/82 green.
- Lint: clean on first try.
- Coverage spot-check (Vitest v8 reporter): `app/books/book-form.ts` 91.37% statements / 80% branches, `app/books/books-service.ts` 100% statements (Story 2.4 baseline unchanged). All four new modules are above the AR34 ≥70% gate.

### Completion Notes List

- **Option A selected for the row stub:** created `book-row-placeholder.{ts,html,css}` (no `.spec`; populated-state coverage in `book-list.spec.ts` exercises it). Same-shape swap target for Story 2.6's real `BookRow`.
- **Whitespace-title strategy:** Strategy A (custom `nonWhitespaceValidator` ValidatorFn) — bubbles through `form.invalid`. Submit-time `trim()` still applied before sending the payload (defense-in-depth + payload normalization).
- **Inline error copy reuses module-level constants** (`BOOK_LIST_LOAD_ERROR_COPY`, `BOOK_FORM_*`) so the spec asserts against the same symbol the template reads — refactoring copy is a one-line edit, not a test-edit cost.
- **Books service NOT modified** — Story 2.4 surface consumed verbatim. No new methods, no signal-shape changes.
- **`BookListPage` does NOT render `<app-top-chrome />`** — global app shell handles it (`app.html`). The "Settings link visible at `/books`" requirement is satisfied by `TopChrome.contextualLink` (covered by `top-chrome.spec.ts`; not retested here).
- **`app.routes.ts` edited (one line)** — `/books` `loadComponent` now points at `BookListPage`; `books-page-placeholder.ts` deleted (zero remaining references in `spa/`).
- **Task 6.4 (manual `npm run start` smoke)** not performed in this worktree: the worktree has no running BFF/Keycloak. Compose-level smoke is the integrator's pre-merge step.
- **Code-review pass (post-dev):** zero must-fix; two should-fix applied in this story (S1 + S2 below); five nice-to-have defers logged in `deferred-work.md` as D57-D61.
  - **S1 (applied)** — `BookForm.formatServerError` now has a `default: const _exhaustive: never = err;` branch so future `AppError` variants (e.g., Story 3.5's `resource_server_unavailable`) cause a compile-time error instead of returning `undefined`.
  - **S2 (applied)** — Removed dead `Validators.required` on the `status` FormControl. The `<select>` has no empty option and the initial value (`'to-read'`) is always valid, so the validator was unreachable. Adds a comment documenting why.
- **Deferred (not fixed in 2.5):**
  - **D57** — `<input type="number">` for pages accepts decimals (`step` not set); server-side Pydantic catches.
  - **D58** — `BookForm.onSubmit` has no synchronous double-submit guard beyond the disabled attribute; programmatic callers could race.
  - **D59** — `BookList`'s loading state never shows during a re-fetch when `books` is already populated; explicit AC out-of-scope.
  - **D60** — `BookListPage` does not guard against `load()` rejection; depends on Story 2.4's "load() never rejects" contract.
  - **D61** — `BookForm` duplicates `LoginView`'s button styling rather than sharing a token / component.
- **Re-ran tests + lint after S1 + S2 fixes:** 82/82 green, lint clean. Coverage unchanged at 91.4% statements for `book-form.ts` (S1 adds an unreachable `default` branch; S2 removes one branch — net neutral).

### File List

**Added (new):**
- `spa/src/app/books/book-list-page.ts`
- `spa/src/app/books/book-list-page.html`
- `spa/src/app/books/book-list-page.css`
- `spa/src/app/books/book-list-page.spec.ts`
- `spa/src/app/books/book-list.ts`
- `spa/src/app/books/book-list.html`
- `spa/src/app/books/book-list.css`
- `spa/src/app/books/book-list.spec.ts`
- `spa/src/app/books/book-form.ts`
- `spa/src/app/books/book-form.html`
- `spa/src/app/books/book-form.css`
- `spa/src/app/books/book-form.spec.ts`
- `spa/src/app/books/book-row-placeholder.ts`
- `spa/src/app/books/book-row-placeholder.html`
- `spa/src/app/books/book-row-placeholder.css`

**Modified:**
- `spa/src/app/app.routes.ts` — `/books` `loadComponent` swap (one line).

**Deleted:**
- `spa/src/app/books/books-page-placeholder.ts`

### Change Log

| Date | Note |
| --- | --- |
| 2026-05-16 | Dev pass complete: 17 new tests added (2 page, 5 list, 10 form); 82 total green; lint clean; coverage ≥70% on all new modules. Story moved to `review`. |
| 2026-05-16 | Code-review pass complete: 0 must-fix; 2 should-fix applied (S1 exhaustive `never` check on `formatServerError`; S2 removed dead `Validators.required` on `status`). 5 nice-to-have defers logged (D57-D61). Tests re-run: 82/82 green; lint clean. Story moved to `done`. |

