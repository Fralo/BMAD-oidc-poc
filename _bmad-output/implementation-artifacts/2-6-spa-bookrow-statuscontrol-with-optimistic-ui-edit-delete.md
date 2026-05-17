---
status: review
story_key: 2-6-spa-bookrow-statuscontrol-with-optimistic-ui-edit-delete
created: 2026-05-17
---

# Story 2.6: SPA — BookRow + StatusControl with optimistic UI + Edit/Delete

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a signed-in user,
I want each book in my list to display as a row with title, page count, a status control, an estimate cell placeholder (until Epic 4), and `Edit` / `Delete` secondary controls — with status changes being immediate (optimistic) and edits opening an inline form that replaces the row,
so that I can manage my books fluidly without page navigations or modals.

## Scope (read this first)

This story closes the **J2 UI surface** that Story 2.5 stubbed. It delivers the real interactive row, the optimistic `StatusControl`, the `EstimateCell` stub, and the `edit` variant of `BookForm`.

Concretely, this story:

1. **Adds** four new components (one of which is a stub for Epic 4):
   - `spa/src/app/books/book-row.{ts,html,css,spec.ts}` — the real interactive row, replacing `BookRowPlaceholder`.
   - `spa/src/app/books/status-control.{ts,html,css,spec.ts}` — native `<select>` calling `BooksService.setStatus(...)` (the optimistic path from Story 2.4).
   - `spa/src/app/books/estimate-cell.{ts,html,css,spec.ts}` — a Story 4.3 stub: a disabled `<button>Estimate</button>` with `title="Available in Epic 4"`. **No click behavior.**
2. **Extends** `BookForm` (Story 2.5) with the `variant="edit"` surface:
   - Renders the same three inputs pre-filled from an `input.required<Book>('book')` signal (the input shape must be discoverable from the type, not implicit) — see AC6.
   - Renders a primary `"Save"` / `"Saving…"` button + a secondary text `Cancel` button (UX-DR14).
   - On submit calls `BooksService.update(book.id, payload)` (already implemented in Story 2.4, `spa/src/app/books/books-service.ts:42-51`).
   - Emits two outputs (`save`, `cancel`) so the parent `BookRow` can swap back to display mode.
3. **Edits** `BookList` to render `<app-book-row [book]="book" />` instead of `<app-book-row-placeholder [book]="book" />` (`spa/src/app/books/book-list.html:10`) — one-line component swap + the `imports:` and TypeScript import update in `book-list.ts`.
4. **Deletes** `spa/src/app/books/book-row-placeholder.{ts,html,css}` — its single consumer (the populated branch in `book-list.html`) is now `BookRow`; `grep -rn "book-row-placeholder\|BookRowPlaceholder" spa/` must return zero results before the delete commit.
5. **Updates** `book-list.spec.ts` to assert against `<app-book-row>` instead of `<app-book-row-placeholder>` (currently `spa/src/app/books/book-list.spec.ts:98`).

Out of scope for 2.6:

- The real `EstimateCell` (Story 4.3 replaces this story's stub).
- Any change to `BooksService` (`books-service.ts` is frozen at Story 2.4's surface — see "Files NOT to touch").
- Any change to the BFF (`PATCH /v1/books/{id}` and `DELETE /v1/books/{id}` are live from Story 2.2 — this story only consumes them).
- The J2 Playwright spec (Story 2.7 — `e2e/tests/j2-manage-books.spec.ts`).
- Defers D57–D61 from Story 2.5 (decimal pages, double-submit, refetch loading, `load()` rejection, button-styling token) — owned by their respective future stories.

## Acceptance Criteria

**AC1 — `BookRow` exists as a standalone OnPush component with one input.**

`spa/src/app/books/book-row.ts`:

```ts
@Component({
  selector: 'app-book-row',
  imports: [BookForm, StatusControl, EstimateCell, ErrorMessage],
  templateUrl: './book-row.html',
  styleUrl: './book-row.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookRow {
  readonly book = input.required<Book>();

  private readonly booksService = inject(BooksService);

  readonly editing = signal<boolean>(false);
  readonly rowError = signal<string | null>(null);
  // ...
}
```

- `input.required<Book>('book')` — same signal-IO pattern as `BookRowPlaceholder` (`book-row-placeholder.ts:12`) and `BookForm.variant` (`book-form.ts:54`). NO `@Input` decorator (architecture line 240).
- `@Injectable({ providedIn: 'root' })`-style `inject(...)` DI — NO constructor DI (AR23 / architecture line 239).
- `ChangeDetectionStrategy.OnPush` on the component (every new component, architecture line 236).
- `editing` is a local `signal<boolean>` controlling display-vs-edit mode (architecture line 710 — local UI state, no service).
- `rowError` is a local `signal<string | null>` for inline error copy under the row (UX-DR6 — "row-level inline error renders below normal row content on action failures").

**AC2 — `BookRow` template renders the documented anatomy in display mode (UX-DR6).**

`spa/src/app/books/book-row.html` (display mode):

```html
@if (editing()) {
  <app-book-form
    variant="edit"
    [book]="book()"
    (save)="onEditSave()"
    (cancel)="onEditCancel()"
  />
} @else {
  <div class="book-row" [class.has-error]="rowError() !== null">
    <span class="book-row-title">{{ book().title }}</span>
    <span class="book-row-pages">{{ book().pages }} pages</span>
    <app-status-control
      [bookId]="book().id"
      [status]="book().status"
      (statusChangeFailed)="onStatusChangeFailed($event)"
    />
    <app-estimate-cell [bookId]="book().id" [pages]="book().pages" />
    <div class="book-row-actions">
      <button class="book-row-action" type="button" (click)="onEditClick()">Edit</button>
      <button class="book-row-action" type="button" (click)="onDeleteClick()">Delete</button>
    </div>
  </div>
  @if (rowError(); as msg) {
    <app-error-message [message]="msg" />
  }
}
```

- The row is a CSS flex container (`display: flex; align-items: center; gap: var(--spacing-3)`) per UX-DR6. Order is **strictly** title → `<n> pages` → `StatusControl` → `EstimateCell` → action group.
- Page count copy is `{{ book().pages }} pages` (always plural — UX spec does not require singular "1 page"; the page count of `1` is a valid but unlikely real-world case and the plural-only rule mirrors the UX spec's literal example from epic line 1027).
- Title uses `--text-body` / `--color-text`; the `<n> pages` span uses `--text-body` / `--color-text-muted` (UX-DR6 verbatim).
- The action group renders **two text buttons** (`Edit`, `Delete`) per UX-DR14: `color: var(--color-text); background: transparent; border: none; text-decoration: underline on hover`. **No fill, no surrounding box, no red on Delete** (UX-DR14 — "destructive actions are NOT red").
- Hover state: the `.book-row` background uses `var(--color-surface-muted)` on `:hover` (UX-DR6 / epic line 1031).
- The inline `<app-error-message>` for `rowError()` renders **below** the row's normal content per UX-DR6 ("a row-level inline error renders below normal row content on action failures").
- Use Angular's new control flow (`@if`/`@for`) — NOT `*ngIf` / `*ngFor` (architecture line 238 / mirrors `book-list.html:1-13`).

**AC3 — `StatusControl` exists as a standalone OnPush component with two inputs and one output.**

`spa/src/app/books/status-control.ts`:

```ts
@Component({
  selector: 'app-status-control',
  imports: [],
  templateUrl: './status-control.html',
  styleUrl: './status-control.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusControl {
  readonly bookId = input.required<number>();
  readonly status = input.required<BookStatus>();
  readonly statusChangeFailed = output<string>();

  private readonly booksService = inject(BooksService);

  readonly busy = signal<boolean>(false);

  async onChange(next: BookStatus): Promise<void> {
    if (next === this.status() || this.busy()) {
      return;
    }
    this.busy.set(true);
    try {
      await this.booksService.setStatus(this.bookId(), next);
    } catch (err) {
      // setStatus has already reverted the books signal; surface inline copy upward.
      this.statusChangeFailed.emit(this.formatStatusError(err as AppError));
    } finally {
      this.busy.set(false);
    }
  }
}
```

- Uses Story 2.4's optimistic method `BooksService.setStatus(id, next)` (`books-service.ts:53-85`) — **do NOT reimplement optimistic logic here**. `setStatus` already (a) writes the optimistic row synchronously before the PATCH, (b) reverts to the prior status on rejection, and (c) replaces the optimistic row with the authoritative server row on success (`books-service.ts:66-84`).
- `output()` API (new Angular v21 signal-output) — NOT `@Output() EventEmitter` (architecture line 240). Emits a `string` (the formatted error copy) so the parent `BookRow` can render it under the row.
- `busy` is a local `signal<boolean>` controlling the disabled state of the `<select>` during the in-flight PATCH (UX-DR7).
- `imports: []` — the component does not consume `ErrorMessage`; the error renders on the parent `BookRow`, not inside `StatusControl` itself (UX-DR6 says "row-level error", not "control-level").

**AC4 — `StatusControl` template renders a native `<select>` with three options.**

`spa/src/app/books/status-control.html`:

```html
<select
  class="status-control-select"
  [value]="status()"
  [disabled]="busy()"
  (change)="onChange($any($event.target).value)"
>
  <option value="to-read">to-read</option>
  <option value="reading">reading</option>
  <option value="finished">finished</option>
</select>
```

- Native HTML `<select>` (UX-DR15 — "Native HTML controls only, no UI component library"). Three `<option>` values **must** match `BookStatus = 'to-read' | 'reading' | 'finished'` from `book.types.ts:1` verbatim.
- `[value]` reads from the `status()` signal so the current value always reflects the optimistic-updated row in `BooksService.books()` (after `setStatus` writes synchronously per `books-service.ts:66-68`).
- `[disabled]="busy()"` is set during the in-flight PATCH (UX-DR7 / epic line 1037).
- The implementer **MAY** substitute a three-button segmented control built from `<button>` elements per UX-DR7 ("at the implementer's discretion"). The native `<select>` is recommended (smaller surface, fewer tests). If the segmented variant is chosen: the `busy` disabled state applies to all three buttons; the `(change)` semantics map to `(click)` per button.

**AC5 — `EstimateCell` is a disabled stub for Epic 4 (per epic line 1021).**

`spa/src/app/books/estimate-cell.ts`:

```ts
@Component({
  selector: 'app-estimate-cell',
  imports: [],
  templateUrl: './estimate-cell.html',
  styleUrl: './estimate-cell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EstimateCell {
  readonly bookId = input.required<number>();
  readonly pages = input.required<number>();
}
```

Template (`estimate-cell.html`):

```html
<button class="estimate-cell-button" type="button" disabled title="Available in Epic 4">
  Estimate
</button>
```

- Inputs (`bookId`, `pages`) are declared so Story 4.3 can fill in the real component **without changing `BookRow`'s template binding** (Story 4.3's AC at epic line 1683-1686 explicitly states `BookRow.html` swaps the stub binding's `app-estimate-cell` for the real component — keeping the same `[bookId]` / `[pages]` props means that's a one-line CSS edit, not a template rewrite).
- No `(click)` handler — the button is `disabled` at the HTML level, so the click event does not fire in any browser.
- Visual styling: secondary text-button per UX-DR14 (not primary) — `color: var(--color-text-muted)` to make "this is inert" visually obvious. **Do NOT** style it as a primary `--color-accent` button — that misleads users into thinking it works.

**AC6 — `BookForm` gains the `variant="edit"` surface.**

The existing `BookForm` class (`spa/src/app/books/book-form.ts`) is extended with:

1. **A new `book` input** that is **required only when variant is `edit`**. Because Angular's `input.required<T>()` cannot be conditionally-required, use an **optional** `input<Book | undefined>('book')` and validate in a `constructor` or `effect` that `variant() === 'edit'` implies `book() !== undefined`:

   ```ts
   readonly book = input<Book | undefined>(undefined);

   // In the class body — runtime safety net for the edit variant
   constructor() {
     effect(() => {
       if (this.variant() === 'edit' && this.book() === undefined) {
         throw new Error("BookForm[variant=edit] requires a 'book' input.");
       }
     });
   }
   ```

   The `effect` runs in the component's injection context (architecture line 236 — zoneless) and fails fast in test/dev if the consumer forgets to pass `book`.

2. **Two new `output()`s** so the parent `BookRow` can react to save success and cancel without coupling to the form's internals:

   ```ts
   readonly save = output<void>();
   readonly cancel = output<void>();
   ```

3. **Form initialization for the `edit` variant** — when `variant() === 'edit'`, pre-fill the form with the current `book()` values. Use an `effect` (NOT `ngOnInit` — the `book` signal is the source of truth and may change):

   ```ts
   constructor() {
     effect(() => {
       const v = this.variant();
       const b = this.book();
       if (v === 'edit' && b !== undefined) {
         // Use setValue (not patchValue) so all three fields are reset
         this.form.setValue({ title: b.title, pages: b.pages, status: b.status });
       }
     });
   }
   ```

   **Idempotence note:** the effect re-fires whenever `book()` changes — for the row-replacement flow that is exactly once on `editing.set(true)`, because the parent `BookRow` mounts a fresh `<app-book-form />` instance (the form lives behind an `@if`, not as a persistent overlay). The form is then unmounted on cancel/save, so there is no "form was edited then book signal changed under it" race.

**AC7 — `BookForm[variant=edit]` template renders the same three inputs plus a primary `Save` and a secondary `Cancel` button.**

`spa/src/app/books/book-form.html` is updated to render variant-specific actions:

```html
<form class="book-form" [formGroup]="form" (ngSubmit)="onSubmit()">
  <!-- (three labelled inputs — unchanged from Story 2.5) -->
  <div class="book-form-actions">
    <button class="book-form-submit" type="submit" [disabled]="submitting()">
      @if (variant() === 'add') {
        {{ submitting() ? submittingButtonLabel : idleButtonLabel }}
      } @else {
        {{ submitting() ? editSubmittingButtonLabel : editIdleButtonLabel }}
      }
    </button>
    @if (variant() === 'edit') {
      <button
        class="book-form-cancel"
        type="button"
        [disabled]="submitting()"
        (click)="onCancel()"
      >Cancel</button>
    }
  </div>
  @if (errorMessage(); as msg) {
    <app-error-message [message]="msg" />
  }
</form>
```

Add the new copy constants to `book-form.ts` (mirroring the existing `BOOK_FORM_ADD_BUTTON_IDLE` / `BOOK_FORM_ADD_BUTTON_SUBMITTING` pattern at `book-form.ts:16-17`):

```ts
export const BOOK_FORM_EDIT_BUTTON_IDLE = 'Save';
export const BOOK_FORM_EDIT_BUTTON_SUBMITTING = 'Saving…';
export const BOOK_FORM_EDIT_CANCEL_LABEL = 'Cancel';
```

- Primary button copy: `"Save"` (idle) / `"Saving…"` (submitting) per UX-DR4 / epic line 1055.
- Cancel button: `type="button"` so it does NOT submit the form. Styled as a **text button** (`color: var(--color-text); background: transparent; border: none; text-decoration: underline on hover`) per UX-DR14. **No icon.** Disabled while `submitting()` is true (otherwise a click during in-flight `update()` could leave the row in a half-state).
- The `Cancel` button calls `onCancel()` (defined in AC8.3) which emits the `cancel` output.

**AC8 — Submit behavior of `BookForm[variant=edit]`.**

The existing `onSubmit()` (`book-form.ts:77-102`) is generalized to dispatch on `variant()`:

```ts
async onSubmit(): Promise<void> {
  if (this.form.invalid) {
    this.errorMessage.set(this.buildValidationMessage());
    return;
  }

  this.errorMessage.set(null);
  this.submitting.set(true);

  const payload = {
    title: this.form.controls.title.value.trim(),
    pages: this.form.controls.pages.value as number,
    status: this.form.controls.status.value,
  };

  try {
    if (this.variant() === 'add') {
      await this.booksService.create(payload);
      this.form.reset({ title: '', pages: null, status: 'to-read' });
    } else {
      // variant === 'edit' — book() is non-undefined per the constructor effect
      await this.booksService.update(this.book()!.id, payload);
      this.save.emit();
      // No form.reset here — the parent BookRow unmounts the form on save.
    }
  } catch (err) {
    this.errorMessage.set(this.formatServerError(err as AppError));
  } finally {
    this.submitting.set(false);
  }
}

onCancel(): void {
  this.cancel.emit();
}
```

**Required behaviors (variant=edit):**

1. **Submission gating** — while `submitting() === true`, both the `Save` button and the `Cancel` button are disabled (`[disabled]="submitting()"`). The button relabels to `"Saving…"` (UX-DR4).
2. **Validation-on-submit** — Reactive Forms validators (`Validators.required`, `nonWhitespaceValidator` for title, `Validators.required` + `Validators.min(1)` for pages — already declared in `book-form.ts:60-69`) gate the submit. On invalid, render the inline error and bail. Same `buildValidationMessage()` as add — no new copy.
3. **Submit success** — `BooksService.update(book.id, payload)` resolves (Story 2.4 / `books-service.ts:42-51` already replaces the row in the `books` signal). The form emits `save` and is unmounted by the parent — no need to reset.
4. **Inputs preserve values on submit failure** (UX-DR15) — same as add: Reactive Forms does NOT reset on `form.invalid` or on a thrown server error. The reset is only on success, and for `edit` the parent unmounts before reset is observable.
5. **Cancel** — emits `cancel`. The parent `BookRow` listens and flips `editing.set(false)`. No service call, no form reset (the form is unmounted).
6. **Server-error copy** — `formatServerError` (`book-form.ts:137-157`) already handles every `AppError` kind including the new-for-edit `book_not_found` (404 — the row was deleted in another tab between `Edit` open and `Save`). The exhaustive `switch` (S1 from Story 2.5 review) maps `book_not_found` to `BOOK_FORM_SERVER_GENERIC` ("Something went wrong. Try again.") today; **this is acceptable for 2.6 — do NOT add a row-was-deleted-elsewhere-specific copy unless it appears in the epic AC** (it does not). The user can refresh to discover the row is gone.

**AC9 — `BookRow` integrates `StatusControl` failure into its inline row error.**

The `BookRow.onStatusChangeFailed(msg: string)` handler sets `rowError.set(msg)`. The next status change attempt clears the error: in `StatusControl.onChange()` the in-flight call always re-enters; in `BookRow` the next successful status change OR the next render after `editing` toggles MUST clear `rowError`.

**Minimum clear behavior (required):**

- When the user toggles into edit mode (`editing.set(true)` in `onEditClick()`), clear `rowError.set(null)`.
- When the user clicks `Edit` or `Delete` again (any subsequent row action), clear `rowError.set(null)` at the start of the handler.
- A successful status change (`BooksService.setStatus` resolves without throwing) does NOT clear via `BookRow` — the error was never set in that case. `StatusControl.onChange` only emits `statusChangeFailed` on error.

**Implementer note:** the parent's `(statusChangeFailed)` handler receives the formatted copy string (not the raw `AppError`) — formatting happens inside `StatusControl.formatStatusError()` (see AC10). This keeps `BookRow` agnostic of the error taxonomy.

**AC10 — `StatusControl` maps `AppError` → user-visible copy.**

A small private method on `StatusControl` mirroring `BookForm.formatServerError` (`book-form.ts:137-157`):

```ts
private formatStatusError(err: AppError): string {
  switch (err.kind) {
    case 'invalid_input':
    case 'book_not_found':
    case 'csrf_invalid':
    case 'forbidden_scope':
    case 'auth_state_invalid':
    case 'network':
    case 'unknown':
    case 'session_expired':
      return STATUS_CONTROL_FAILURE_COPY;
    default: {
      const _exhaustive: never = err;
      return _exhaustive;
    }
  }
}
```

with `export const STATUS_CONTROL_FAILURE_COPY = "Couldn't change status — try again";` (UX-DR12 — single inline-error copy per epic line 1045 / UX spec; no need to disambiguate by kind for a binary control).

The exhaustive `switch` is the same defensive pattern as Story 2.5's S1 patch — any future `AppError` variant (e.g., Story 3.5's `resource_server_unavailable`) causes a TypeScript compile error at build, NOT a silent `undefined` at runtime.

**AC11 — Delete uses native `window.confirm()`.**

`BookRow.onDeleteClick()`:

```ts
async onDeleteClick(): Promise<void> {
  this.rowError.set(null);
  if (!window.confirm('Delete this book?')) {
    return; // user pressed Cancel — no network call, no state change
  }
  try {
    await this.booksService.delete(this.book().id);
    // Success — BooksService.delete already filtered the row out of the books signal.
    // BookRow is unmounted by BookList's @for as a consequence; this method returns
    // into nothing because the component is gone. No further state mutation needed.
  } catch (err) {
    this.rowError.set(this.formatDeleteError(err as AppError));
  }
}
```

- **Use `window.confirm()` directly** (UX-DR17 — "No in-app modal, no slide-over, no dialog system"; epic line 1068 — "a native `window.confirm("Delete this book?")` dialog is invoked").
- The dialog message is the literal string `"Delete this book?"` (epic line 1068).
- On Cancel (`confirm()` returns `false`), do NOTHING — no network call, no state change, no error message.
- On OK + 2xx, `BooksService.delete` (Story 2.4 / `books-service.ts:87-94`) removes the row from `books` immutably; the parent `BookList` `@for` rerenders and `BookRow` unmounts itself.
- On OK + 4xx/5xx, `BooksService.delete` throws an `AppError` (`books-service.ts:91`); render `formatDeleteError(err)` inline via `rowError`. Use the same exhaustive `switch` pattern; copy:

  ```ts
  export const BOOK_ROW_DELETE_FAILURE_COPY = "Couldn't delete this book — try again.";
  ```

  All `AppError` kinds map to this single copy (per UX-DR12 — failure copy is the named string, not a per-kind disambiguation).

**AC12 — `BookRow` integrates `BookForm[variant=edit]` for edit mode.**

When `editing()` is `true`, the row renders `<app-book-form variant="edit" [book]="book()" (save)="..." (cancel)="...">` and the display row is hidden (`@if (editing()) { ... } @else { ... }` — AC2 template).

`BookRow` handlers:

```ts
onEditClick(): void {
  this.rowError.set(null);
  this.editing.set(true);
}

onEditSave(): void {
  // BooksService.update already replaced the row in the books signal.
  // The `book` input on this BookRow has updated by signal flow.
  this.editing.set(false);
}

onEditCancel(): void {
  this.editing.set(false);
}
```

**Critical:** the parent `BookList` `@for` uses `track book.id` (`book-list.html:9`), so the `BookRow` instance is **preserved** across `book.title` / `book.pages` / `book.status` updates from `BooksService.update` — only the inner template re-renders. This means `editing` stays a `signal` on the same component instance (no flicker, no state loss).

**AC13 — `BookList` is updated to render `BookRow` instead of `BookRowPlaceholder`; the placeholder is deleted.**

1. In `spa/src/app/books/book-list.ts`:
   - Replace `import { BookRowPlaceholder } from './book-row-placeholder';` with `import { BookRow } from './book-row';`
   - In `imports: [BookRowPlaceholder, ErrorMessage]` (line 13), replace `BookRowPlaceholder` with `BookRow`.
2. In `spa/src/app/books/book-list.html` (line 10):
   - Replace `<app-book-row-placeholder [book]="book" />` with `<app-book-row [book]="book" />`.
3. Delete the three placeholder files:
   - `spa/src/app/books/book-row-placeholder.ts`
   - `spa/src/app/books/book-row-placeholder.html`
   - `spa/src/app/books/book-row-placeholder.css`
4. Verify zero remaining references in `spa/`:
   ```
   grep -rn "book-row-placeholder\|BookRowPlaceholder" spa/
   ```
   must return no matches before the delete commit. (Story 2.5 already verified the placeholder has no other consumers — see `_bmad-output/implementation-artifacts/2-5-spa-booklist-page-bookform-add-variant-states.md` line 314.)
5. In `spa/src/app/books/book-list.spec.ts`:
   - Update the `populated state` assertion at line 98 (`querySelectorAll('app-book-row-placeholder')`) to `querySelectorAll('app-book-row')`.
   - The TextContent assertion (titles rendered) is preserved because `BookRow` also exposes the title in its template (AC2).

**AC14 — Tests cover `BookRow`, `StatusControl`, `EstimateCell`, and the edit-variant of `BookForm`.**

Test files: one per component. Use Angular's `TestBed`, `provideHttpClientTesting()`, and `HttpTestingController` (same harness as Story 2.5 / `book-form.spec.ts`). All tests use `provideZonelessChangeDetection()`.

**`book-row.spec.ts` — 8 tests minimum:**

1. **Display mode renders the documented anatomy** — render `<app-book-row [book]="mkBook({ title: 'Dune', pages: 688, status: 'to-read' })" />`; assert `.book-row-title` contains `"Dune"`, `.book-row-pages` contains `"688 pages"`, `app-status-control` is present, `app-estimate-cell` is present, two `.book-row-action` buttons exist labeled `"Edit"` and `"Delete"`. No initial `app-error-message`.
2. **`editing` toggles to edit mode** — click the `Edit` button; assert `app-book-form` is now rendered with `variant="edit"`; assert the display `.book-row` is NOT rendered.
3. **Cancel returns to display mode** — enter edit mode; emit the form's `cancel` output (or click the form's `Cancel` button); assert `editing() === false` and the display row is rendered again.
4. **Save returns to display mode and `BooksService.update` is called** — enter edit mode; modify the title via the form's input; submit; flush a 200 with the updated book; assert `editing() === false`, the new title is shown, and `BooksService.books()` was updated by Story 2.4's `update()` semantics.
5. **`statusChangeFailed` from `StatusControl` populates `rowError`** — programmatically emit `statusChangeFailed` from the child `StatusControl` (via `fixture.debugElement.query(...).componentInstance.statusChangeFailed.emit('msg')` or trigger a real failure via the test below); assert `<app-error-message>` renders below the row with the emitted message.
6. **Delete confirm-cancel: no network call, row preserved** — spy on `window.confirm` returning `false`; click `Delete`; assert `expectNone('/v1/books/{id}')` and the row is still rendered.
7. **Delete confirm-OK happy path: row is removed via `BooksService.delete`** — spy on `window.confirm` returning `true`; pre-seed `BooksService.books.set([mkBook()])`; click `Delete`; flush a 204; assert `BooksService.books()` no longer contains the book.
8. **Delete confirm-OK error path: renders `rowError`, row preserved** — spy on `window.confirm` returning `true`; click `Delete`; flush a 404 `{ errorCode: 'book_not_found' }`; assert `<app-error-message>` renders with `BOOK_ROW_DELETE_FAILURE_COPY`; assert the row is still rendered (the `delete()` call threw, `BooksService.books()` was not filtered).

For `book-row.spec.ts`, use a real `BooksService` instance against `HttpTestingController` (same pattern as `book-form.spec.ts`) so the `BooksService.delete` / `BooksService.update` integrations are genuine.

**`status-control.spec.ts` — 5 tests minimum (per epic line 1080 — "default, optimistic update, optimistic-then-revert"):**

1. **Default state** — render `<app-status-control [bookId]="1" status="to-read" />` (with a `BooksService` providing a book with `id=1` in `books()`); assert the `<select>` is enabled and its value is `"to-read"`; assert the three `<option>` values are `to-read`, `reading`, `finished` in that order.
2. **Disabled state during in-flight PATCH** — change the `<select>` value to `"reading"`; assert the `<select>` is now `disabled` BEFORE flushing the HTTP response; assert `BooksService.books()[0].status === 'reading'` (optimistic visibility); flush 200; assert the `<select>` is re-enabled.
3. **Optimistic-update happy path** — pre-seed `BooksService.books.set([mkBook({ id: 1, status: 'to-read' })])`; change `<select>` to `'reading'`; before flush: assert `books()[0].status === 'reading'`; flush a 200 with the server row; assert `books()[0]` equals the server row exactly.
4. **Optimistic-then-revert** — pre-seed `mkBook({ id: 1, status: 'to-read' })`; change `<select>` to `'reading'`; flush a 422 `{ errorCode: 'invalid_input' }`; assert `books()[0].status === 'to-read'` (reverted by `BooksService.setStatus` per `books-service.ts:75-80`); assert `statusChangeFailed` was emitted with `STATUS_CONTROL_FAILURE_COPY`.
5. **No-op skip** — change the `<select>` to the same value that's already current (e.g., status is `'to-read'`, user clicks the already-selected `to-read` option — browser fires `change` regardless); assert `expectNone('/v1/books/1')` (no HTTP call — `BooksService.setStatus` has a `prev === next` skip at `books-service.ts:60-63`); assert `statusChangeFailed` was NOT emitted.

For `status-control.spec.ts`, use a real `BooksService` against `HttpTestingController` so the optimistic-then-revert is exercised end-to-end (mirrors `books-service.spec.ts:211-291` patterns).

**`estimate-cell.spec.ts` — 1 test minimum:**

1. **Renders a disabled `Estimate` button with the documented `title` attribute** — render `<app-estimate-cell [bookId]="1" [pages]="100" />`; assert `<button>` with `textContent === 'Estimate'`, `disabled === true`, `title === 'Available in Epic 4'`.

(This is intentionally trivial — Story 4.3 will replace this component wholesale; do NOT over-test a stub that's about to be deleted.)

**`book-form.spec.ts` — additional tests for the edit variant (5 new tests minimum, added to the existing file):**

1. **Edit-variant renders pre-filled inputs + Save + Cancel** — render `<app-book-form variant="edit" [book]="mkBook({ title: 'Dune', pages: 688, status: 'reading' })" />`; assert all three inputs hold the book's values (`title` is `"Dune"`, `pages` is `688`, `status` selected is `"reading"`); assert the primary button label is `BOOK_FORM_EDIT_BUTTON_IDLE` ("Save"); assert a second `Cancel` button is rendered.
2. **Edit-variant submitting state** — fill valid values, click Save; **before** flush assert the button label is `BOOK_FORM_EDIT_BUTTON_SUBMITTING` ("Saving…") and both buttons are disabled; flush 200; assert the `save` output was emitted exactly once; assert no `cancel` was emitted.
3. **Edit-variant Cancel emits `cancel` and does NOT call the service** — modify a field; click Cancel; assert `expectNone('/v1/books/...')`; assert the `cancel` output was emitted exactly once; assert `save` was NOT emitted.
4. **Edit-variant validation-error preserves entered values + emits nothing** — clear the title; click Save; assert the inline error renders (`BOOK_FORM_VALIDATION_TITLE_REQUIRED`); assert NO HTTP request was dispatched; assert neither `save` nor `cancel` was emitted; assert the entered (cleared) title input is still empty (UX-DR15 — values preserved).
5. **Edit-variant server-error preserves values + emits nothing + button restores** — fill valid values; click Save; flush a 422 `{ errorCode: 'invalid_input' }`; assert the inline error renders with `BOOK_FORM_SERVER_INVALID_INPUT`; assert the inputs preserve their entered values; assert the button is back to `"Save"` and enabled; assert NEITHER `save` nor `cancel` was emitted.

For listening to outputs in tests, use the runtime `OutputRef.subscribe` pattern (Angular v21 `output()` exposes a `.subscribe(...)` method) — same as how other v21 codebases test `output()`. Alternative: assign a Jest/Vitest spy via `vi.spyOn(componentInstance.save, 'emit')` if needed.

**`book-list.spec.ts` — UPDATE existing populated-state test:**

- Change line 98 selector from `app-book-row-placeholder` to `app-book-row`. The titles assertion (lines 99-101) still works because `BookRow` also exposes `.book-row-title` containing the book title — the test's assertion shape can either query `app-book-row` and read `textContent` (which will now include the title, pages, and the static action button labels because `app-status-control` and `app-estimate-cell` are also nested children), OR query `.book-row-title` directly and assert against the title text. **Recommendation: query `.book-row-title` to avoid coupling to the entire row's text dump.** Update the assertion to:

  ```ts
  const titles = Array.from(el.querySelectorAll('app-book-row .book-row-title')).map(
    (n) => n.textContent?.trim(),
  );
  expect(titles).toEqual(['Dune', 'Foundation']);
  ```

- The existing `BooksService` stub in `book-list.spec.ts` (`makeBooksServiceStub()` at line 32) only provides `books`/`loading`/`loadError` signals — but `BookRow` also injects `BooksService` and calls `delete` / `update` / `setStatus`. **No real HTTP is triggered by render**, only by user action, so the stub is still sufficient for the populated-state test (which only renders, never clicks).

**AC15 — Lint, coverage, and suite gates.**

- `npm test -- --watch=false` (from `spa/`) is green. The suite count strictly increases from Story 2.5's close (82 tests baseline; +19 new tests minimum — 8 BookRow + 5 StatusControl + 1 EstimateCell + 5 BookForm edit-variant additions).
- **Vitest coverage of every new file (`book-row.ts`, `status-control.ts`, `estimate-cell.ts`) is ≥70%** per AR34. The minimum-test allocations above are tuned to exceed 70%; if any module misses, fill gaps with sub-cases of the existing tests (NOT new test types — that would be coverage-only, not behavior-driven).
- **Vitest coverage of the modified file `book-form.ts` does NOT regress below Story 2.5's 91.37% statements / 80% branches baseline** (per Story 2.5 Dev Agent Record at `2-5-spa-booklist-page-bookform-add-variant-states.md:591`). The edit-variant adds ~30 lines and 5 tests — coverage should hold or rise.
- `npm run lint` from `spa/` reports no new findings.
- **Existing E2E specs continue to pass** — `e2e/tests/j1-first-login.spec.ts` and `e2e/tests/j5-logout.spec.ts` navigate to `/books` after login; the new `BookRow` does not regress the empty-state render (they don't add books, so the populated state is untouched).
- `grep -rn "book-row-placeholder\|BookRowPlaceholder" spa/` returns ZERO matches.

## Tasks / Subtasks

- [x] Task 1 — `EstimateCell` stub (AC5)
  - [x] 1.1 Create `spa/src/app/books/estimate-cell.ts` with the class shell from AC5 (two required signal inputs, OnPush, empty imports).
  - [x] 1.2 Create `spa/src/app/books/estimate-cell.html` with the disabled `<button>Estimate</button>` + the `title="Available in Epic 4"` attribute (verbatim).
  - [x] 1.3 Create `spa/src/app/books/estimate-cell.css` with secondary-button styling (text-button per UX-DR14; `color: var(--color-text-muted)` to signal inert).
  - [x] 1.4 Create `spa/src/app/books/estimate-cell.spec.ts` with the single test from AC14.

- [x] Task 2 — `StatusControl` (AC3, AC4, AC10)
  - [x] 2.1 Create `spa/src/app/books/status-control.ts` with the class shell from AC3. `inject(BooksService)`; declare `STATUS_CONTROL_FAILURE_COPY` constant; declare the `output<string>()` for `statusChangeFailed`.
  - [x] 2.2 Implement `onChange(next: BookStatus)` per AC3, using `BooksService.setStatus(id, next)` (Story 2.4 — `books-service.ts:53-85`). NO new optimistic logic.
  - [x] 2.3 Implement `formatStatusError(err: AppError)` per AC10 with the exhaustive `switch + never` pattern (mirrors `book-form.ts:137-157`).
  - [x] 2.4 Create `spa/src/app/books/status-control.html` with the native `<select>` from AC4 (or the segmented-button alternative — pick one).
  - [x] 2.5 Create `spa/src/app/books/status-control.css` with input-shaped styling (`padding`, `border`, `border-radius`, `font: var(--text-body)`) consistent with `book-form.css:18-23`. Disabled state: `opacity: 0.5; cursor: not-allowed` (UX-DR14).
  - [x] 2.6 Create `spa/src/app/books/status-control.spec.ts` with the five tests from AC14. Use a real `BooksService` against `HttpTestingController`.

- [x] Task 3 — `BookForm[variant=edit]` (AC6, AC7, AC8)
  - [x] 3.1 In `spa/src/app/books/book-form.ts`: add `import { effect, output } from '@angular/core';` (the existing import already pulls `Component`, `inject`, `input`, `signal` — verify line 1).
  - [x] 3.2 Add the `book` optional input (`input<Book | undefined>(undefined)`) and the two outputs (`bookSaved`, `editCancelled` — renamed from `save`/`cancel` to satisfy `@angular-eslint/no-output-native`; both `save` and `cancel` are native DOM event names).
  - [x] 3.3 Add the runtime-required `effect` in the `constructor()` enforcing `variant() === 'edit' ⇒ book() !== undefined`. Add the second `effect` pre-filling the form with `book()`'s values via `form.setValue(...)`.
  - [x] 3.4 Add the three new copy constants (`BOOK_FORM_EDIT_BUTTON_IDLE`, `BOOK_FORM_EDIT_BUTTON_SUBMITTING`, `BOOK_FORM_EDIT_CANCEL_LABEL`).
  - [x] 3.5 Update `onSubmit()` to dispatch on `variant()`: `add` ⇒ `create(...)` + `form.reset(...)`; `edit` ⇒ `update(book().id, ...)` + `bookSaved.emit()`. Preserve the existing validation + error-formatting + submitting-signal flow.
  - [x] 3.6 Add `onCancel(): void { this.editCancelled.emit(); }`.
  - [x] 3.7 Update `spa/src/app/books/book-form.html` to render the variant-conditional button labels and the `@if (variant() === 'edit') { <Cancel button> }` block (AC7).
  - [x] 3.8 Update `spa/src/app/books/book-form.css` with `.book-form-cancel` styling (text-button per UX-DR14: `background: transparent; border: none; color: var(--color-text); cursor: pointer;` + underlined-on-hover; disabled 50% opacity).
  - [x] 3.9 Extend `spa/src/app/books/book-form.spec.ts` with the five new edit-variant tests from AC14 plus four coverage-protecting tests (multi-field validation, session_expired, network, book_not_found mappings). Added a helper `renderEditForm(book: Book)` mirroring the existing `renderForm()`.

- [x] Task 4 — `BookRow` (AC1, AC2, AC9, AC11, AC12)
  - [x] 4.1 Create `spa/src/app/books/book-row.ts` with the class shell from AC1: `input.required<Book>('book')`, `inject(BooksService)`, local `editing` and `rowError` signals, all five handler methods (`onEditClick`, `onEditSave`, `onEditCancel`, `onStatusChangeFailed`, `onDeleteClick`).
  - [x] 4.2 Implement `onDeleteClick()` per AC11 using `window.confirm('Delete this book?')` and `BooksService.delete(book.id)`. Use the exhaustive `formatDeleteError` switch (mirror `book-form.ts:137-157`).
  - [x] 4.3 Implement `onEditClick`, `onEditSave`, `onEditCancel`, and `onStatusChangeFailed(msg: string)` per AC9 + AC12. Clear `rowError` on `onEditClick` and `onDeleteClick`.
  - [x] 4.4 Create `spa/src/app/books/book-row.html` with the template from AC2: `@if (editing()) { <BookForm variant=edit> } @else { <display row> }` + the conditional inline error.
  - [x] 4.5 Create `spa/src/app/books/book-row.css` — flex layout, hover, text-button actions, muted page count. Dropped explicit `padding` on `.book-row` because `book-list.css:14` already gives each `li` vertical padding.
  - [x] 4.6 Create `spa/src/app/books/book-row.spec.ts` with the eight tests from AC14. Use a real `BooksService` + `HttpTestingController`; spy on `window.confirm` via `vi.spyOn(window, 'confirm').mockReturnValue(...)` per test.

- [x] Task 5 — `BookList` swap + `BookRowPlaceholder` delete (AC13)
  - [x] 5.1 Edit `spa/src/app/books/book-list.ts`: replace the `BookRowPlaceholder` import with `BookRow`; replace it in the `imports:` array.
  - [x] 5.2 Edit `spa/src/app/books/book-list.html` line 10: `<app-book-row-placeholder ... />` → `<app-book-row ... />`.
  - [x] 5.3 Edit `spa/src/app/books/book-list.spec.ts` line 98 per AC14: change the selector to `app-book-row .book-row-title` and assert against the title text.
  - [x] 5.4 Delete the three files: `book-row-placeholder.ts`, `book-row-placeholder.html`, `book-row-placeholder.css`.
  - [x] 5.5 Verify zero remaining references: `grep -rn "book-row-placeholder\|BookRowPlaceholder" spa/src` returns no matches (build cache under `spa/.angular/cache/` is excluded — it clears on next clean build).

- [x] Task 6 — Lint, coverage, and suite verification (AC15)
  - [x] 6.1 `npm test -- --watch=false` from `spa/` — green; 105 tests passing (23 above the 82-test baseline — 4 above the AC's 19 minimum).
  - [x] 6.2 `npm run lint` from `spa/` — clean (after renaming `save`/`cancel` outputs to `bookSaved`/`editCancelled`).
  - [x] 6.3 `npm run test:coverage` — `book-row.ts` 92.3%/91.66%; `status-control.ts` 90.9%/96.15%; `estimate-cell.ts` is template-only (no instrumented lines); `book-form.ts` 94.04%/90.74% (above Story 2.5's 91.37%/80% baseline).
  - [ ] 6.4 Manual smoke test under `npm run start` against a running BFF: **Deferred — requires running stack; integrator's pre-merge step**, same as Story 2.5 Task 6.4.

## Dev Notes

### Critical: read these before starting

1. **Story 2.5 already shipped the form, the list, and the row stub.** Do not re-implement the form's submit gating, the list's four-state cascade, or the row stub's anatomy. Read these files in full before touching anything: `book-form.ts`, `book-list.ts`, `book-list.html`, `book-row-placeholder.ts`. The patterns this story extends are visible there.

2. **`BooksService` is frozen at Story 2.4's surface.** Do NOT add new methods, do NOT change signal shapes, do NOT change return types. Re-read `spa/src/app/books/books-service.ts:1-95` — it already provides:
   - `setStatus(id, next): Promise<void>` with **the optimistic write at line 66-68**, the **revert on error at line 75-80**, and the **server-row replacement at line 84**.
   - `update(id, payload): Promise<Book>` with **the immutable replace at line 49**.
   - `delete(id): Promise<void>` with **the immutable filter at line 93**.
   - All three throw a parsed `AppError` on HTTP failure.

3. **`AppError` is frozen at Story 2.4's discriminated union shape.** It is exactly nine kinds (`spa/src/app/shared/errors/app-error.types.ts:1-9`):
   - `session_expired`, `forbidden_scope`, `invalid_input` (with optional `detail`), `book_not_found`, `csrf_invalid`, `auth_state_invalid`, `network`, `unknown` (with `status: number`).
   - The exhaustive `switch + never` pattern from Story 2.5 review (`book-form.ts:138-156`) is **mandatory** in any new `format*Error` method this story adds — Stories 3.5 / 4.3 will add new kinds, and we want the compiler to flag them at that point.

4. **`<app-book-row-placeholder>` is currently rendered ONCE** — at `book-list.html:10`. After this story's deletion, the file system search `grep -rn "book-row-placeholder" spa/` must be empty. Verify before deleting.

5. **The architecture's directory map (`architecture.md:1033-1040`) names this story's files verbatim** — `book-row.{ts,html,css,spec.ts}`, `status-control.{ts,html,css,spec.ts}`, `estimate-cell.{ts,html,css,spec.ts}`. No barrel files (architecture line 637).

6. **Outputs use the new `output()` API**, not `@Output() EventEmitter` (architecture line 240). Signal-style component IO is the only allowed pattern in this codebase. The `OutputRef.subscribe(...)` method is what tests use to receive emissions.

7. **No accessibility / responsive design work** in this story. Per project scope (`CLAUDE.md`-equivalent), a11y is out of scope. Do NOT add `aria-*` attributes beyond what falls out naturally from native HTML (`<button>`, `<select>`, `<input>`), do NOT add focus-management code, do NOT add responsive breakpoints.

### Optimistic UI — leave the math to the service

`BooksService.setStatus` is the **only** optimistic write path in the entire SPA (architecture line 773, line 91; UX-DR13). It is responsible for:

1. The synchronous optimistic update of the `books` signal (`books-service.ts:66-68`).
2. The PATCH request to `/v1/books/{id}` with body `{ status: next }` (`books-service.ts:72-74`).
3. The revert to the prior status on failure (`books-service.ts:75-80`).
4. The replacement of the optimistic row with the authoritative server row on success (`books-service.ts:84`).

`StatusControl` is a **dumb adapter** — it owns:

1. The disabled state of the `<select>` during the in-flight call (the `busy` signal).
2. The translation of the rejected `AppError` into a user-visible copy string.
3. The emission of that copy upward via the `statusChangeFailed` output.

`StatusControl` does NOT own:

- Any direct write to the `books` signal (the service does it).
- Any "settle the optimistic value" logic (the service replaces the optimistic row on success, so `<select>`'s `[value]="status()"` reflects the server's authoritative row automatically once the parent re-renders with the updated `book` input).
- Any retry logic (the SPA does not retry — architecture line 777-779).

This separation is non-negotiable. If you find yourself writing `this.booksService.books.update(...)` inside `StatusControl`, stop — that's a regression.

### Edit-form mounting & the `effect` pattern

Story 2.5's `BookForm` lives at the top of `/books` permanently. Story 2.6's `BookForm[variant=edit]` is mounted **inside** `BookRow` only when `editing() === true`. This means:

- Each time the user clicks `Edit` on a row, a fresh `BookForm` instance is created (the `@if (editing()) { <app-book-form ... /> }` block tears down + remounts).
- The `book` signal input is set to `book()` at mount time and does not change during the form's lifetime (the parent `BookRow`'s `book` input flows through unchanged; if the user clicks `Save`, the form unmounts before `BooksService.update` returns the new row).
- The `effect` pre-filling `form.setValue(...)` (AC6) runs once at mount and is **idempotent** — it would re-run only if `book()` changed, which doesn't happen during edit. The cost of running `setValue` once per mount is acceptable.

**Anti-pattern:** do NOT use `ngOnInit` for pre-filling. `ngOnInit` runs before signal inputs are first read in some Angular timings; the `effect` is reactive and deterministic.

### Why `book` is `input<Book | undefined>(undefined)` instead of `input.required<Book>()`

`input.required<T>()` cannot be conditionally required. `BookForm[variant=add]` does NOT provide a `book`. Forcing `input.required<Book>()` would break the `add` variant at runtime. Two patterns work:

**Chosen (this story):** Optional input + `effect`-based runtime check. Defends against misuse with a clear error message; works with both variants; survives Angular's signal-input compile checks.

**Rejected:** Two separate components (`BookFormAdd`, `BookFormEdit`). The architecture (line 1036) names `book-form.{ts,html,css,spec.ts}` — singular — and Story 2.5 implemented it as a single component with a `variant` input. Splitting now would invalidate Story 2.5's test file structure for no behavioral benefit.

### Server-error mapping in the edit variant

`BooksService.update` throws an `AppError` on rejection. The existing `formatServerError` (`book-form.ts:137-157`) handles every kind including `book_not_found` (404 — the row was deleted in another tab between Edit and Save). The mapping today is:

- `book_not_found` → `BOOK_FORM_SERVER_GENERIC` ("Something went wrong. Try again.")

This is acceptable: the user retries, the network call returns 404 again, eventually they refresh and discover the row is gone. **Do NOT** add a row-was-deleted-elsewhere-specific message — it's not in the epic AC and would require a "refresh the list" CTA that doesn't exist in this codebase's design vocabulary.

### `window.confirm` in tests

`vi.spyOn(window, 'confirm').mockReturnValue(true)` or `.mockReturnValue(false)` works in jsdom. Reset the spy in `afterEach` so subsequent tests are not contaminated. Example:

```ts
let confirmSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  confirmSpy = vi.spyOn(window, 'confirm');
});

afterEach(() => {
  confirmSpy.mockRestore();
});

// in a test:
confirmSpy.mockReturnValue(true);
```

The argument to `window.confirm` is the dialog message (the literal string `"Delete this book?"` per AC11). Tests can additionally assert `expect(confirmSpy).toHaveBeenCalledWith('Delete this book?')`.

### Listening to signal `output()`s in tests

Angular v21's `output()` returns an `OutputRef` with a `.subscribe(fn): { unsubscribe(): void }` method. Pattern:

```ts
const saveSpy = vi.fn();
const sub = fixture.componentInstance.save.subscribe(saveSpy);
// ... trigger the emission ...
expect(saveSpy).toHaveBeenCalledTimes(1);
sub.unsubscribe();
```

Alternative: `vi.spyOn(fixture.componentInstance.save, 'emit')` works because `output()` exposes `emit` on the OutputRef.

### Files NOT to touch in this story

- `spa/src/app/books/books-service.ts` — frozen at Story 2.4 (`done`). All five methods are correct.
- `spa/src/app/books/books-service.spec.ts` — frozen.
- `spa/src/app/books/book.types.ts` — frozen. Types are correct.
- `spa/src/app/shared/errors/app-error.types.ts` — frozen.
- `spa/src/app/shared/errors/error-service.ts` — Story 2.4 owns the `parse` mapping; `BooksService` already calls it.
- `spa/src/app/shared/ui/error-message.{ts,html,css}` — already correct. Just import.
- `spa/src/app/shared/chrome/top-chrome.{ts,html,css}` — unchanged.
- `spa/src/app/app.ts`, `app.html`, `app.css`, `app.routes.ts`, `app.config.ts` — unchanged. `/books` already loads `BookListPage`.
- `services/bff/**` — no backend changes. `PATCH /v1/books/{id}` and `DELETE /v1/books/{id}` are live from Story 2.2.
- `e2e/tests/**` — Story 2.7 owns the J2 spec.

### Interceptor interaction — already wired (carry-over)

`spa/src/app/app.config.ts` registers `[withCredentialsInterceptor, csrfInterceptor]` globally. The `csrfInterceptor` auto-attaches `X-CSRF-Token` on POST/PUT/PATCH/DELETE, so this story's `BooksService.update` (PATCH) and `BooksService.delete` (DELETE) carry the header at runtime without any per-call code. In tests, the interceptors are not registered (we use the bare `provideHttpClient(withFetch()) + provideHttpClientTesting()` stack) — the request will be matched without the header. This is the established Story 2.4 / Story 2.5 pattern; do not deviate.

The global 401-redirect (in `with-credentials-interceptor.ts:25-34`) navigates to `/login?return_to=...` BEFORE rejection reaches `BookRow`'s catch handlers. The `session_expired` mapping in `formatStatusError` / `formatDeleteError` is defensive — by the time a user could see it, they've navigated away.

### Existing SPA patterns to mirror exactly

**1. `spa/src/app/books/book-form.ts:137-157`** — the exhaustive `switch + never` for `AppError`. Copy this pattern verbatim into `StatusControl.formatStatusError` and `BookRow.formatDeleteError`. Lift the constants into module-level `export const` declarations (`STATUS_CONTROL_FAILURE_COPY`, `BOOK_ROW_DELETE_FAILURE_COPY`) so specs can import them and assert exact copy strings — same pattern as `book-list.ts:7-9` and `book-form.ts:16-28`.

**2. `spa/src/app/books/book-row-placeholder.ts`** — the simplest possible `OnPush` standalone with `input.required<Book>('book')`. `BookRow` extends this shape with: more inputs/outputs, local signals, event handlers. Mirror the import order and the class declaration order.

**3. `spa/src/app/books/book-form.spec.ts`** — `renderForm()` helper at lines 34-56 is the canonical TestBed scaffold for HTTP-touching component specs. Mirror it in `book-row.spec.ts` and `status-control.spec.ts`.

**4. `spa/src/app/books/books-service.spec.ts:211-291`** — the `setStatus` test cases are the canonical pattern for asserting optimistic-then-success and optimistic-then-revert. `status-control.spec.ts`'s tests are observers of the same code path one layer up; the assertion shape is identical (synchronous read, flush, assert post-flush).

**5. `spa/src/app/books/book-list.spec.ts:32-53`** — the `BooksServiceStub` pattern (signal-only fake, no HTTP) is used for components that render but do not dispatch. `book-row.spec.ts`'s display-mode-only tests COULD use this pattern, but tests 6/7/8 (delete) need real HTTP, so use the real-`BooksService` pattern from `book-form.spec.ts` throughout for consistency.

### Why no separate "row-error" component

UX-DR6 says "a row-level inline error renders below normal row content on action failures." The inline error is rendered by the existing `ErrorMessage` component (`shared/ui/error-message.ts`) — there is no separate `BookRowError` component. The `rowError` signal lives on `BookRow` (not on the children) so a single inline message slot exists for the union of status-change-failure / delete-failure.

### Architecture: signal-based outputs vs `EventEmitter`

Architecture line 240: "Use `input()` / `input.required()` and `output()` — NOT `@Input` / `@Output` decorators." The Angular v21 `output()` function returns an `OutputRef<T>` with `.emit(value: T)` and `.subscribe(fn)` methods. It is **NOT** an `EventEmitter` (which is an RxJS Subject). The interop is one-way: `output()` can be subscribed to like an `Observable`, but you cannot pass an `output()` where an `EventEmitter` is expected. Components consuming `output()`s in templates use the standard `(eventName)="handler($event)"` syntax — no syntactic difference from `@Output`.

### Project Structure Notes

New files for this story, all under `spa/src/app/books/`:

```
spa/src/app/books/
├── book-list-page.{ts,html,css,spec.ts}         (untouched — Story 2.5)
├── book-list.ts                                  (MODIFIED — import swap, line 4 + line 13)
├── book-list.html                                (MODIFIED — line 10)
├── book-list.css                                 (untouched — Story 2.5)
├── book-list.spec.ts                             (MODIFIED — line 98 selector)
├── book-form.ts                                  (MODIFIED — variant=edit additions)
├── book-form.html                                (MODIFIED — conditional Cancel + button labels)
├── book-form.css                                 (MODIFIED — .book-form-cancel styling)
├── book-form.spec.ts                             (MODIFIED — +5 edit-variant tests)
├── book-row.{ts,html,css,spec.ts}                (NEW — real row, replaces placeholder)
├── status-control.{ts,html,css,spec.ts}          (NEW — optimistic select)
├── estimate-cell.{ts,html,css,spec.ts}           (NEW — Story 4.3 stub)
├── book-row-placeholder.ts                       (DELETED)
├── book-row-placeholder.html                     (DELETED)
├── book-row-placeholder.css                      (DELETED)
├── books-service.ts                              (untouched — Story 2.4)
├── books-service.spec.ts                         (untouched — Story 2.4)
└── book.types.ts                                 (untouched — Story 2.4)
```

Architecture's directory map (`architecture.md:1033-1040`) lists these files verbatim. No barrel files (line 637).

### Previous Story Intelligence

- **Story 2.5** (closed, merged 2026-05-17, commit `f9e90c8`) delivered `BookListPage`, `BookList` (four states), `BookForm[variant=add]`, and `BookRowPlaceholder`. The handover is clean: `BookList` renders `<app-book-row-placeholder>` at the populated branch, which this story swaps for the real `BookRow`. Two should-fix patches were applied during 2.5 review (S1 — exhaustive `never` check on `formatServerError`; S2 — removed dead `Validators.required` on `status`); **keep both patterns** when extending the same code in this story.
- **Story 2.5 deferred D57-D61** are NOT in scope here:
  - D57 (decimal pages in `<input type="number">`) — pages input shared between add and edit; both variants inherit the same behavior; out of scope.
  - D58 (synchronous double-submit guard) — the `submitting()` disabled attribute on the button still gates user-driven double-submit; programmatic callers would already have a race; out of scope.
  - D59 (loading state never shows during re-fetch) — `BookList` concern, not this story's.
  - D60 (`BookListPage.load()` rejection) — out of scope.
  - D61 (button-styling token deduplication) — design concern; out of scope.
- **Story 2.4** delivered `BooksService` with the surface this story consumes. `setStatus` / `update` / `delete` are tested at ≥85% coverage on `books-service.ts`; the integration this story adds (component → service → HTTP) is what `book-row.spec.ts` and `status-control.spec.ts` exercise.
- **Story 2.4 deferred D54 / D55 / D56** are concurrency / phantom-write hardening on `BooksService` itself; they do not affect this story's correctness.
- **Story 2.2** (BFF books CRUD) shipped `PATCH /v1/books/{id}` with the documented error codes: `book_not_found` (404), `invalid_input` (422), `csrf_invalid` (403), `session_expired` (401). All four are mapped by `ErrorService.parse` (Story 2.4). The `delete()` endpoint shares the same error codes (404 if already deleted, 403 if CSRF, 401 if session expired).
- **Story 2.5 review notes mentioned button-state assertion timing in test 5.7** — the workaround was invoking `componentInstance.onSubmit()` directly (so the returned `Promise` could be awaited) instead of dispatching the form's `submit` event. The same workaround applies in `book-row.spec.ts`'s edit-mode submit tests; mirror the pattern from `book-form.spec.ts:151-213`.

### Git intelligence (recent commits)

```
5f29197 Merge branch 'worktree-agent-af52cf97b51ccdedf' into epic-2
f9e90c8 Merge branch 'worktree-agent-a4c977ec9f1509f1f' into epic-2
2f34a22 chore(2.5): code review — S1 exhaustive AppError switch, S2 dead status validator; 5 defers (D57-D61); close 2.5
3a5f604 feat(2.5): SPA BookList page + BookForm add variant — states, BookRowPlaceholder, unit tests
0dadb46 chore(2.3): code review — no must-fix, 10/10 ACs verified; 2 defers; close 2.3
0e08d44 feat(2.3): BFF /v1/test/reset truncates books — handler extension, seed/count helpers, scenario 14b test
94e07e3 chore(2.5): create story — SPA BookList page + BookForm spec ready-for-dev
```

Epic 2 is in-progress: 2.1, 2.2, 2.3, 2.4, 2.5 all closed. This story (2.6) is the second-to-last in Epic 2; Story 2.7 (J2 Playwright spec) lands after. The `epic-2` branch is the working branch; no merge from `main` is needed between 2.5 and 2.6.

### Latest tech information (Angular v21 + signals + Reactive Forms)

- **Angular v21.2** (per `spa/package.json`). Standalone components, `input.required()`, `input()`, `output()`, new control flow (`@if`/`@for`/`@switch`), `effect()`.
- **`output()` is stable in v21** — the function-based API replaces the decorator. Templates use the same `(name)="handler($event)"` syntax. The runtime `OutputRef.subscribe(fn)` API is the test hook.
- **`effect()` for reactive side-effects** — runs in the component's injection context, auto-tracks signal reads, re-runs on signal changes. Use it for the `variant`-aware form pre-fill (AC6). Do NOT use `effect()` for things that should run once-per-mount and never re-run — for that, use a plain `constructor()` body. The pre-fill effect IS once-per-mount in practice because `book()` never changes during the form's lifetime.
- **`@for` `track` is mandatory** — `book-list.html:9` already uses `track book.id`; this preserves `BookRow` component instances across `book` updates (critical for the `editing` signal to survive `BooksService.update` rewriting the `books` array).
- **`@if (x; as y)`** binds the truthy value to `y` inside the block — used for `@if (errorMessage(); as msg) { ... }` and `@if (rowError(); as msg) { ... }`. Mirrors `book-form.html:23` and `book-list.html:1`.
- **Vitest 4.x + `@vitest/coverage-v8`** — same harness as Story 2.5. `npm run test:coverage` outputs `coverage/spa/` for inspection.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.6: SPA — BookRow + StatusControl with optimistic UI + Edit/Delete] (verbatim AC source — lines 1010-1082)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR6] (BookRow anatomy + hover state + row-level inline error)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR7] (StatusControl — native `<select>` or segmented control; optimistic PATCH; disabled during in-flight)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR8] (EstimateCell anatomy — for the Story 4.3 reference, this story uses the stub only)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR12] (Failure copy strings)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR13] (Optimistic vs pessimistic UI rule)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR14] (Button hierarchy — primary in `--color-accent`, secondary as text-buttons, destructive NOT red, no icon-only)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR15] (Form patterns — submit-time validation, native controls, preserve values on failure)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR17] (No modals — native `confirm()` for destructive actions)
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Model] (line 235: standalone, zoneless, signals, `@if`/`@for`, `inject()`, `input()`/`output()`)
- [Source: _bmad-output/planning-artifacts/architecture.md#Forms] (line 250: Reactive Forms, submit-time validation, no Signal Forms)
- [Source: _bmad-output/planning-artifacts/architecture.md#Loading state UI / Optimistic UI] (lines 769-773: optimistic only for same-service low-stakes mutations)
- [Source: _bmad-output/planning-artifacts/architecture.md#Process Patterns — Validation] (lines 766-767: validators on submit, inputs preserve on failure)
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] (line 1033-1040: `books/` folder layout — `book-row.{ts,html,css,spec.ts}` named verbatim)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#BookRow] (display anatomy, edit-mode swap, action affordances)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#StatusControl] (optimistic UI behavior, disabled state)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Button Hierarchy] (UX-DR14 details)
- [Source: _bmad-output/planning-artifacts/PRD.md#FR2 (FR-BOOK-01)] (book CRUD scope; J2 user journey)
- [Pattern: spa/src/app/books/books-service.ts:53-85] (the optimistic `setStatus` implementation — the source of truth for AC3/AC4/AC10)
- [Pattern: spa/src/app/books/books-service.ts:42-51] (the `update(id, payload)` method — the source of truth for AC6/AC8)
- [Pattern: spa/src/app/books/books-service.ts:87-94] (the `delete(id)` method — the source of truth for AC11)
- [Pattern: spa/src/app/books/book-form.ts:137-157] (exhaustive `switch + never` for `AppError` — the source of truth for `formatStatusError` and `formatDeleteError`)
- [Pattern: spa/src/app/books/book-form.ts:77-102] (existing `onSubmit` — the source of the variant-dispatch refactor in AC8)
- [Pattern: spa/src/app/books/book-form.spec.ts:34-56] (`renderForm()` helper — mirror in `book-row.spec.ts` and `status-control.spec.ts`)
- [Pattern: spa/src/app/books/book-row-placeholder.ts:1-13] (the minimal OnPush + `input.required<Book>` shape — `BookRow` extends this)
- [Pattern: spa/src/app/books/book-list.html:9-11] (the `@for` populated branch — site of AC13's one-line swap)
- [Pattern: spa/src/app/books/books-service.spec.ts:211-291] (`setStatus` optimistic-then-revert assertion patterns — mirror in `status-control.spec.ts`)
- [Defer: _bmad-output/implementation-artifacts/deferred-work.md#D57-D61] (Story 2.5 defers; NOT in scope here)
- [Defer: _bmad-output/implementation-artifacts/deferred-work.md#D54-D56] (Story 2.4 `BooksService` concurrency defers; NOT in scope here)
- [Gate: spa/package.json] (`test:coverage` script; Vitest 4.x + @vitest/coverage-v8; `ng lint`)

## Definition of Done

1. `BookRow` exists as a standalone OnPush component with `input.required<Book>('book')`, renders the documented anatomy in display mode (title, `<n> pages`, `StatusControl`, `EstimateCell`, `Edit`/`Delete` text-buttons, hover state), and swaps to `<app-book-form variant="edit">` in edit mode (AC1, AC2, AC12).
2. `StatusControl` exists as a standalone OnPush component with two inputs + one `output()`, dispatches to `BooksService.setStatus`, disables during the in-flight PATCH, and emits a formatted copy string on failure (AC3, AC4, AC10).
3. `EstimateCell` exists as a disabled-button stub with `title="Available in Epic 4"` and two inputs ready for Story 4.3 (AC5).
4. `BookForm` supports `variant="edit"` with pre-fill via `effect`, primary `Save`/`Saving…` button, secondary `Cancel` text-button (disabled during submit), and dispatches `BooksService.update(book.id, payload)` on submit. Emits `save` on success and `cancel` on user-cancel; preserves inputs on validation or server error (AC6, AC7, AC8).
5. `BookList` renders `<app-book-row>` instead of `<app-book-row-placeholder>`, and the three `book-row-placeholder.*` files are deleted (AC13). `grep -rn "book-row-placeholder\|BookRowPlaceholder" spa/` returns no matches.
6. Native `window.confirm('Delete this book?')` gates DELETE; cancel skips network; OK + 2xx removes the row; OK + 4xx/5xx renders inline `rowError` and preserves the row (AC11).
7. `StatusControl` failure surfaces as a row-level inline error via the `(statusChangeFailed)` output → `BookRow.rowError` (AC9).
8. Tests pass for all four touched/new components: `book-row.spec.ts` (8 tests), `status-control.spec.ts` (5 tests), `estimate-cell.spec.ts` (1 test), and `book-form.spec.ts` extended with 5 edit-variant tests. `book-list.spec.ts`'s populated-state selector is updated. Suite count strictly ≥ 19 tests above Story 2.5's 82-test baseline (AC14, AC15).
9. Coverage of every new module ≥70% per AR34. `book-form.ts` coverage does not regress below 91.37% / 80% branches. `npm run lint` is clean. `npm test -- --watch=false` is green (AC15).
10. Manual smoke under `npm run start` shows: open `/books` → add a book → change its status (synchronous select update) → click Edit (form replaces row, pre-filled) → modify title → Save (row returns with new title) → click Delete → native confirm → OK → row disappears. Cancel paths verified at every step (Task 6.4 — integrator's pre-merge step).
11. No changes outside the scope listed in §Scope. No edits to `BooksService`, `book.types.ts`, `AppError`, `ErrorService`, interceptors, app shell, BFF, RS, or E2E.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) — `bmad-dev-story` skill.

### Debug Log References

- Pre-implementation baseline: `npm test -- --watch=false` → 82 tests passing (Story 2.5 close-state).
- Post-implementation: `npm test -- --watch=false` → 105 tests passing (+23 above baseline).
- Coverage final: All-files 96.4% stmts / 93.12% branches.
- Lint: clean after one rename — see Completion Notes.

### Completion Notes List

- **Naming deviation from the story spec (lint enforcement):** The story called for `output<void>()` named `save` and `cancel`. Both names are blocked by `@angular-eslint/no-output-native` (they collide with native DOM events `save` on Window and `cancel` on HTMLDialogElement). Renamed to `bookSaved` and `editCancelled`; updated the BookRow template bindings (`(bookSaved)="onEditSave()"`, `(editCancelled)="onEditCancel()"`) and tests accordingly. Behaviour is unchanged.
- **Native `<select>` chosen over segmented buttons** for `StatusControl` (the spec's recommended path; smaller surface, fewer tests).
- **`input<Book | undefined>(undefined)` plus constructor `effect`** for `BookForm.book` (the spec's documented design call; runtime safety net throws when `variant=edit` is passed without a `book`).
- **Coverage hardening:** added four extra `BookForm` edit-variant tests (multi-field validation, session_expired, network, book_not_found mappings) to keep `book-form.ts` above Story 2.5's 91.37%/80% baseline. Final 94.04%/90.74%.
- **AC13 placeholder deletion confirmed:** `grep -rn "book-row-placeholder\|BookRowPlaceholder" spa/src` returns no matches. The only hits in `spa/` are inside `spa/.angular/cache/.../tsbuildinfo` (TypeScript incremental-compilation cache, regenerated on next clean build — not source).
- **Task 6.4 deferred:** manual stack smoke is an integrator's pre-merge step, same posture as Story 2.5's Task 6.4.
- **All 15 ACs validated** against implementation: AC1-AC2 (BookRow class + template), AC3-AC4 (StatusControl + native `<select>`), AC5 (EstimateCell stub with `title="Available in Epic 4"`), AC6-AC8 (BookForm edit variant — input, outputs, pre-fill effect, runtime guard effect, variant-dispatching submit, Cancel), AC9 (statusChangeFailed → rowError), AC10 (formatStatusError exhaustive switch), AC11 (native confirm + delete + error path), AC12 (BookRow edit integration), AC13 (BookList swap + placeholder deletion), AC14 (8 BookRow tests + 5 StatusControl tests + 1 EstimateCell test + 5 base edit-variant + 4 coverage tests + 1 BookList selector update), AC15 (lint clean, coverage ≥70% all new files, suite +23 above baseline).

### File List

New files:
- `spa/src/app/books/book-row.ts`
- `spa/src/app/books/book-row.html`
- `spa/src/app/books/book-row.css`
- `spa/src/app/books/book-row.spec.ts`
- `spa/src/app/books/status-control.ts`
- `spa/src/app/books/status-control.html`
- `spa/src/app/books/status-control.css`
- `spa/src/app/books/status-control.spec.ts`
- `spa/src/app/books/estimate-cell.ts`
- `spa/src/app/books/estimate-cell.html`
- `spa/src/app/books/estimate-cell.css`
- `spa/src/app/books/estimate-cell.spec.ts`

Modified files:
- `spa/src/app/books/book-form.ts` — added `book` input, `bookSaved`/`editCancelled` outputs, two effects, variant-dispatching `onSubmit`, `onCancel`, three edit-copy constants.
- `spa/src/app/books/book-form.html` — variant-conditional button labels + conditional Cancel button.
- `spa/src/app/books/book-form.css` — added `.book-form-cancel` text-button styling.
- `spa/src/app/books/book-form.spec.ts` — added `renderEditForm()` helper + 9 edit-variant tests.
- `spa/src/app/books/book-list.ts` — swapped `BookRowPlaceholder` import for `BookRow`.
- `spa/src/app/books/book-list.html` — swapped `<app-book-row-placeholder>` for `<app-book-row>`.
- `spa/src/app/books/book-list.spec.ts` — updated populated-state assertion to query `app-book-row .book-row-title`.

Deleted files:
- `spa/src/app/books/book-row-placeholder.ts`
- `spa/src/app/books/book-row-placeholder.html`
- `spa/src/app/books/book-row-placeholder.css`

Coordination files:
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 2-6 status → in-progress → review; `last_updated` bumped.

### Change Log

| Date | Note |
| --- | --- |
| 2026-05-17 | Story created from epic AC + Story 2.5 implementation files. Status: ready-for-dev. |
| 2026-05-17 | Dev complete. 12 new files, 7 modified, 3 deleted. 105 tests passing (+23 above 82 baseline). Lint clean. Coverage book-form 94.04%/90.74%, book-row 92.3%/91.66%, status-control 90.9%/96.15%. Status: review. |
