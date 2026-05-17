# Story 4.3: SPA — `EstimateCell` (real component) + `AppError` extensions + BookRow integration

Status: review

<!-- Sprint: Epic 4 (Reading-Time Estimate & Honest Failure — J3, J6) -->
<!-- Precedes: Story 4.4 (E2E J3 + J6 specs). Follows: Story 4.2 (BFF estimate proxy — ready-for-dev). -->

## Story

As a signed-in user,
I want each book row to expose an "Estimate" button that, when clicked, briefly disables and relabels itself, then returns either a formatted reading-time duration with a "Re-estimate" affordance, or a distinct named error rendered in the same cell,
so that the cross-service estimate works inline in the row exactly as the UX spec describes — no modal, no toast, no fabricated values.

## Acceptance Criteria

> Source: `_bmad-output/planning-artifacts/epics.md` lines 1630–1694. Tightened here for the dev agent with current-state observations.

### Foundation (types, service, error model)

**AC1 — `estimate.types.ts` (NEW):** Create `spa/src/app/books/estimate.types.ts` exporting:
```ts
export interface EstimateOut {
  minutes: number;
  formatted: string;
}
```
- `minutes` is a non-negative integer (matches RS `EstimateOut.minutes: int ge=0`).
- `formatted` is the verbatim duration string returned by the BFF/RS (e.g., `"≈ 4 h 20 m"`, leading `≈` is U+2248 ALMOST EQUAL TO). The SPA NEVER reformats minutes — render `formatted` directly.
- Mirror the precedent of `spa/src/app/settings/reading-speed.types.ts` (own file, no decorators, snake_case wire-mirror — AR16).

**AC2 — `BooksService.requestEstimate(id)`:** Add to `spa/src/app/books/books-service.ts`:
```ts
async requestEstimate(id: number): Promise<EstimateOut> {
  try {
    return await firstValueFrom(this.http.post<EstimateOut>(`/v1/books/${id}/estimate`, {}));
  } catch (err) {
    throw this.errors.parse(err);
  }
}
```
- POST body MUST be `{}` (empty object) — Story 4.2 BFF reads `pages` from the local books row, NOT from the request body.
- Method THROWS the parsed `AppError`, matching the pattern of `create`/`update`/`setStatus`/`delete`. Do NOT store estimate state on the service signal — estimate state is component-local (see AC4).
- Do NOT add the method to the `books` signal flow. It is a read-only side computation.

**AC3 — `AppError` union audit (NO new variants required):** `spa/src/app/shared/errors/app-error.types.ts` ALREADY contains both `{ kind: 'reading_speed_unset' }` AND `{ kind: 'resource_server_unavailable' }` (added in Story 3.5). The epic title "AppError extensions" is misleading for Story 4.3 — these variants exist and are already mapped. **Verify the union is unchanged; do NOT add duplicate variants.** Similarly, `spa/src/app/shared/errors/error-service.ts` ALREADY maps:
- HTTP 412 + `errorCode: "reading_speed_unset"` → `{ kind: 'reading_speed_unset' }` (line 57-59).
- HTTP 502/503/504 (any body) → `{ kind: 'resource_server_unavailable' }` (line 49-51).
- ErrorCode-only fallthroughs for both (line 80-97).
**No `error-service.ts` changes needed.** The epic AC saying "error-service.ts is updated to map the BFF's `reading_speed_unset` envelope" was satisfied retroactively by Story 3.5's broader SPA error work.

### `EstimateCell` component (full rewrite)

**AC4 — Standalone Angular component:** REPLACE the Epic 2 stub at `spa/src/app/books/estimate-cell.ts`. The selector `app-estimate-cell` and the two `input.required<number>()` props (`bookId`, `pages`) MUST be preserved unchanged — `BookRow`'s template binding `<app-estimate-cell [bookId]="book().id" [pages]="book().pages" />` (in `book-row.html`, line 17) MUST keep working without edit. Component contract:
```ts
@Component({
  selector: 'app-estimate-cell',
  imports: [/* RouterLink, ErrorMessage as needed */],
  templateUrl: './estimate-cell.html',
  styleUrl: './estimate-cell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EstimateCell {
  readonly bookId = input.required<number>();
  readonly pages = input.required<number>(); // currently unused at runtime (BFF reads pages server-side) — keep the input to preserve BookRow's stable binding contract
  // local signals + click handler...
}
```
- `pages` input MUST remain declared even though the BFF reads pages from the books row server-side. Removing it would break BookRow's binding. (Note in code: `// kept for BookRow binding stability; BFF reads pages from the server-side books row`.)
- Inject `BooksService` via `inject(BooksService)` (no constructor DI per AR23).

**AC5 — Idle state (initial render):** The component shows a single primary button:
```html
<button type="button" class="estimate-cell-button estimate-cell-button--primary">Estimate</button>
```
- Styled in `--color-accent` per UX-DR8 / UX-DR14 (button hierarchy: primary affordance).
- The label is the literal string `Estimate` (no whitespace, no quotes around the word in the DOM).

**AC6 — Loading state (request in-flight):** When the user clicks `Estimate` (or `Re-estimate`), IMMEDIATELY:
- Set local `loading = signal(true)`.
- Clear local `error` and `result` signals (one round-trip at a time; do NOT leave stale state visible during the round-trip).
- Fire `booksService.requestEstimate(bookId())`.
- Render the button as: `<button disabled>Estimating…</button>` (the literal ellipsis is U+2026 HORIZONTAL ELLIPSIS — copy the character, do not type three dots).
- No spinner overlay, no skeleton, no animation (UX-DR11 / UX-DR13 / architecture §"Process Patterns / Loading state UI").
- Pessimistic UI: no other DOM state on the page changes.

**AC7 — Success state:** On 2xx with `{ minutes, formatted }`:
- Replace the button in-place with the formatted text rendered verbatim (e.g., `≈ 4 h 20 m`) inside an element styled with `font: var(--text-body); color: var(--color-text);`.
- Render `formatted` directly via interpolation — `{{ result()?.formatted }}` (or equivalent inside `@if (result(); as r) { {{ r.formatted }} }`). DO NOT parse or reformat minutes.
- Adjacent to the formatted text, render a small text button labeled `Re-estimate` (`--color-text`, no fill, underlined-on-hover via `:hover { text-decoration: underline }`, per UX-DR14 secondary affordance).
- The result remains visible indefinitely (UX §"Defining Experience" / J3 success state — no timer-based expiry).

**AC8 — Re-estimate flow:** Clicking `Re-estimate` re-runs the loading flow (AC6) and on success REPLACES the formatted text in-place with the new value. No "previously…" callout, no fade, no animation (UX-DR19, UX §"Defining Experience: Detailed Mechanics"). Implementation: the click handler is the SAME as the idle `Estimate` click handler; reuse one method.

**AC9 — Error variant: `reading_speed_unset` (HTTP 412):** When `requestEstimate` throws `{ kind: 'reading_speed_unset' }`:
- Render an inline single-line error in `--color-error` / `--text-small` with the LITERAL copy:
  > `Set your reading speed in Settings to enable estimates`
- The word `Settings` MUST be a `RouterLink` to `/settings` (Angular `[routerLink]="'/settings'"`), styled in `--color-accent`.
- Below the error message, restore the `Estimate` button (AC5) so the user can click it again after visiting `/settings`.
- **Implementation note:** the shared `ErrorMessage` component (`spa/src/app/shared/ui/error-message.ts`) takes ONLY a `message: string` input — it does NOT support content projection or embedded links. **Render this variant via INLINE markup inside `estimate-cell.html`** (not via `<app-error-message>`). Match the visual style by reusing `--color-error` and `--text-small` in the component CSS. Do NOT extend `ErrorMessage` (it would ripple into LoginView/SettingsPage/BookForm/BookList/BookRow).
- Add `RouterLink` to the component's `imports: [RouterLink]` (from `@angular/router`). Precedent: `spa/src/app/shared/chrome/top-chrome.ts` line 4, 16.

**AC10 — Error variant: `resource_server_unavailable` (HTTP 503, the J6 marquee failure):** When `requestEstimate` throws `{ kind: 'resource_server_unavailable' }`:
- Render `<app-error-message [message]="'Service unavailable — try again shortly'" />` (the dash is U+2014 EM DASH; copy the character).
- Below the error, restore the `Estimate` button.
- NO auto-retry, NO polling, NO silent retry (UX §"Failure recovery" + architecture §"Process Patterns / Retry & failure"). User retries manually by clicking again.
- This copy MUST match the SettingsPage 503 copy verbatim — Story 3.5 pinned this string for both surfaces.

**AC11 — Error variant: generic (any other AppError that is NOT `reading_speed_unset`, NOT `resource_server_unavailable`, NOT `session_expired`):** Render `<app-error-message [message]="'Couldn\'t get an estimate — try again'" />` (apostrophe is U+2019 RIGHT SINGLE QUOTATION MARK — use the curly apostrophe, mirror existing copy style; check existing copy strings before committing if uncertain). Below it, restore the `Estimate` button. This catches `network`, `unknown`, `invalid_input`, `forbidden_scope`, `csrf_invalid`, `book_not_found`, `auth_state_invalid`.

**AC12 — Error variant: `session_expired` (HTTP 401):** Do NOT render any local error. The global `withCredentialsInterceptor` (Story 1.9) navigates to `/login?return_to=...` BEFORE the rejection reaches `EstimateCell`. Defensive: in the exhaustive switch (AC13), map `session_expired` to the generic copy (AC11) — the user is being redirected, so the branch is functionally dead but typed correctness requires it.

**AC13 — Exhaustive `AppError` switch (MANDATORY pattern):** The error-to-copy mapping MUST use the exhaustive `switch + never` pattern that all current SPA components follow. Precedents:
- `book-row.ts` lines 91-112 (`formatDeleteError`),
- `book-form.ts` (`formatServerError`),
- `status-control.ts` (`formatStatusError`).

Shape:
```ts
private formatEstimateError(err: AppError): string {
  switch (err.kind) {
    case 'reading_speed_unset':
      return ''; // rendered via inline link template — see AC9
    case 'resource_server_unavailable':
      return 'Service unavailable — try again shortly';
    case 'invalid_input':
    case 'forbidden_scope':
    case 'csrf_invalid':
    case 'book_not_found':
    case 'auth_state_invalid':
    case 'network':
    case 'unknown':
    case 'session_expired':
      return "Couldn't get an estimate — try again";
    default: {
      const _exhaustive: never = err;
      return _exhaustive;
    }
  }
}
```
Pin the literal copy strings via `export const ESTIMATE_CELL_*_COPY = '...'` (mirroring `BOOK_ROW_DELETE_FAILURE_COPY` in `book-row.ts`) so tests can import them — keeps tests resilient to copy churn.

### BookRow integration

**AC14 — BookRow already wired:** `spa/src/app/books/book-row.html` line 17 already binds `<app-estimate-cell [bookId]="book().id" [pages]="book().pages" />`. **Do NOT modify `book-row.html`** — swapping the EstimateCell class is sufficient. The existing `book-row.spec.ts` assertion `expect(el.querySelector('app-estimate-cell')).not.toBeNull();` (line 92) continues to pass — no edit required to that test. The epic AC's "stub assertion from Epic 2 is removed" was a forward-looking comment; in practice, the only stub-specific assertion lived in `estimate-cell.spec.ts` (covered by AC16).

**AC15 — No dead files:** After replacement, `estimate-cell.ts` / `.html` / `.css` MUST contain ONLY the new implementation. The Epic 2 stub markup `<button … disabled title="Available in Epic 4">` and the docstring `Story 4.3 stub.` MUST be removed. The component file MUST have NO references to the words "stub" or "Epic 2 placeholder".

### Tests

**AC16 — `estimate-cell.spec.ts` full rewrite (Vitest + Angular TestBed + HttpTestingController):** Replace the current single-test stub-only spec with a comprehensive suite. Use Scaffold A (real `BooksService` + `provideHttpClientTesting()`, NOT a mock service — `BooksService.requestEstimate` is small and worth integration-testing through the wire). Cover:
1. **Idle state** — renders one button with text `Estimate`, not disabled, no error visible.
2. **Loading state** — clicking `Estimate` immediately disables the button and relabels it `Estimating…`; assert the HTTP request fires with method `POST`, URL `/v1/books/1/estimate`, body `{}`.
3. **Success state** — flush `{ minutes: 260, formatted: '≈ 4 h 20 m' }`; assert (a) the literal string `≈ 4 h 20 m` is rendered, (b) a `Re-estimate` text button exists, (c) the `Estimate` button is gone.
4. **Re-estimate replaces value in place** — after success #3, click `Re-estimate`; assert a SECOND HTTP request fires; flush `{ minutes: 130, formatted: '≈ 2 h 10 m' }`; assert the rendered text is now `≈ 2 h 10 m` and the previous string is gone.
5. **`reading_speed_unset` error with link** — flush `{ errorCode: 'reading_speed_unset', message: '...', detail: null }` with status 412; assert (a) the literal copy `Set your reading speed in Settings to enable estimates` is present, (b) an `<a>` element with the text `Settings` is rendered AND has `routerLink="/settings"` OR resolved `href` ending in `/settings`, (c) the `Estimate` button is restored.
6. **`resource_server_unavailable` error (J6)** — flush `{ errorCode: 'resource_server_unavailable', message: '...' }` with status 503; assert `<app-error-message>` renders with message `Service unavailable — try again shortly`; assert the `Estimate` button is restored; assert NO `≈` character is anywhere in the DOM (no fabricated duration).
7. **Generic error** — flush `{ errorCode: 'unknown', message: 'boom' }` with status 500; assert `<app-error-message>` renders with message `Couldn't get an estimate — try again`; `Estimate` button restored.
8. **404 `book_not_found` defensive path** — flush 404 + `book_not_found` envelope; assert it renders the generic copy (NOT the J6 copy — this pins that the J6 copy is reserved for `resource_server_unavailable`).

Test infrastructure pattern (mirror `books-service.spec.ts`):
```ts
await TestBed.configureTestingModule({
  imports: [EstimateCell],
  providers: [
    provideZonelessChangeDetection(),
    provideHttpClient(withFetch()),
    provideHttpClientTesting(),
    provideRouter([{ path: 'settings', component: class {} }]), // for RouterLink rendering
  ],
}).compileComponents();

const fixture = TestBed.createComponent(EstimateCell);
fixture.componentRef.setInput('bookId', 1);
fixture.componentRef.setInput('pages', 100);
fixture.detectChanges();
await fixture.whenStable();

const httpTesting = TestBed.inject(HttpTestingController);
// afterEach: httpTesting.verify();
```

Driving the click + awaiting the round-trip:
```ts
const btn = fixture.nativeElement.querySelector('button.estimate-cell-button') as HTMLButtonElement;
btn.click();
fixture.detectChanges();
// loading-state assertions here

const req = httpTesting.expectOne({ method: 'POST', url: '/v1/books/1/estimate' });
expect(req.request.body).toEqual({});
req.flush({ minutes: 260, formatted: '≈ 4 h 20 m' });
await fixture.whenStable();
fixture.detectChanges();
// success-state assertions here
```

**AC17 — `books-service.spec.ts` extensions:** Add tests for `requestEstimate`:
- Happy path: stubs the POST, flushes 200 + `{minutes, formatted}`, asserts the resolved value matches.
- 412 reading_speed_unset → rejects with `{ kind: 'reading_speed_unset' }`.
- 503 → rejects with `{ kind: 'resource_server_unavailable' }`.
- 404 book_not_found → rejects with `{ kind: 'book_not_found' }`.
- 500 unknown → rejects with `{ kind: 'unknown', status: 500, ... }`.
- Optional but recommended: 401 (status_only fallback) → rejects with `{ kind: 'session_expired' }`.

Mirror the existing pattern (e.g., the `delete` tests in `books-service.spec.ts`).

**AC18 — `error-service.spec.ts` audit (not extension):** The mapping for `reading_speed_unset` (412) and `resource_server_unavailable` (503) is already covered by Story 3.5's tests. Read `spa/src/app/shared/errors/error-service.spec.ts` and CONFIRM both cases are tested; if either is missing, ADD a single test for the missing case. Otherwise leave the file unchanged. (Reduces the risk of duplicate tests muddying coverage.)

**AC19 — `book-row.spec.ts` unchanged:** The existing assertion `expect(el.querySelector('app-estimate-cell')).not.toBeNull();` (line 92) remains valid. **Do NOT modify `book-row.spec.ts`.** It would only need editing if the new EstimateCell broke the row layout, which AC14 prevents.

**AC20 — Coverage:** Vitest v8 per-file gate is ≥70% statements/branches (per AR34). Aim for ≥90% on `estimate-cell.ts` (small surface). Run:
```bash
cd /Users/fralo/nearform/AINE_Training/BMAD_books/spa
npm test -- --watch=false
```
Assert: total test count strictly increases from the current baseline (post-Story 3.5 SPA suite); all tests pass; coverage gate green.

## Tasks / Subtasks

- [x] Task 1 — Types + service (AC1, AC2)
  - [x] Create `spa/src/app/books/estimate.types.ts` with `EstimateOut` interface.
  - [x] Add `requestEstimate(id: number): Promise<EstimateOut>` to `BooksService` (`spa/src/app/books/books-service.ts`).
- [x] Task 2 — `AppError` + `ErrorService` audit (AC3, AC18)
  - [x] Read `app-error.types.ts`: confirmed `reading_speed_unset` (line 18) and `resource_server_unavailable` (line 19) variants present. NO edit.
  - [x] Read `error-service.ts`: confirmed 412 + reading_speed_unset path (line 57-59) AND 503-status path (line 49-51) map correctly. NO edit.
  - [x] Read `error-service.spec.ts`: both 412+reading_speed_unset (line 69-75) and 503 (line 50-56) cases covered. NO edit.
- [x] Task 3 — `EstimateCell` component rewrite (AC4–AC15)
  - [x] Replaced `spa/src/app/books/estimate-cell.ts` with real implementation: local `loading`/`result`/`error` signals, `onEstimateClick` handler, exhaustive `AppError` switch, exported copy constants (`ESTIMATE_CELL_J6_COPY`, `ESTIMATE_CELL_GENERIC_COPY`, `ESTIMATE_CELL_PRECONDITION_PREFIX`/`SUFFIX`, `ESTIMATE_CELL_IDLE_LABEL`, `ESTIMATE_CELL_LOADING_LABEL`, `ESTIMATE_CELL_REESTIMATE_LABEL`).
  - [x] Replaced `spa/src/app/books/estimate-cell.html` with state-driven `@if`/`@else if`/`@else` template.
  - [x] Updated `spa/src/app/books/estimate-cell.css`: primary affordance mirrors `.book-form-submit`, secondary text button mirrors `.book-row-action`, inline error matches `.error-message` visual style.
  - [x] Added `RouterLink` and `ErrorMessage` to component imports.
- [x] Task 4 — Test suite rewrite (AC16, AC17)
  - [x] Rewrote `spa/src/app/books/estimate-cell.spec.ts` with 8 test cases (idle / loading / success / re-estimate / reading_speed_unset / resource_server_unavailable / generic / book_not_found).
  - [x] Extended `spa/src/app/books/books-service.spec.ts` with 6 `requestEstimate` tests (happy + 412 / 503 / 404 / 500 unknown / 401).
- [x] Task 5 — Verify regression-free (AC19, AC20)
  - [x] `npm test -- --watch=false` — 152 tests pass (baseline 139 → 152, +13 net after replacing 1 stub-only test).
  - [x] `npm run lint` — no NEW lint errors introduced by this story; 3 pre-existing `no-fallthrough` errors in `book-form.ts` / `book-row.ts` / `status-control.ts` were present in `main` before this story and are out of scope (those files are NOT modified per AC14/AC19 and the failure-prevention checklist).
  - [ ] Manual smoke in `dev` profile — DEFERRED. Story 4.2 is in `review` state on `main` (commit `e3236bd`); end-to-end Estimate → BFF → RS smoke is gated on 4.2 merging (or running 4.2's branch in parallel). The contract is exercised in tests; manual smoke is deferred to Story 4.4 (E2E specs).

## Dev Notes

### Architecture compliance (mandatory rules — verbatim or paraphrased from `architecture.md`)

- **AR23 — Signal-based SPA state.** Use `signal()`, `inject()` (not constructor DI), `input.required<T>()`, `input<T>()`, `output<T>()`, `effect()` if cross-signal reactions are needed. Mark every component `ChangeDetectionStrategy.OnPush`. Provide `provideZonelessChangeDetection()` is set globally in `app.config.ts`. (Source: architecture.md §"Frontend Architecture / F1"; SPA AOR §"Communication Patterns / State management".)
- **AR16 — snake_case JSON wire mirror.** `EstimateOut.minutes` and `EstimateOut.formatted` mirror the BFF/RS wire shape; no camelCase aliases, no case-conversion layer. (architecture.md line 560.)
- **AR20-class — DTO-only types.** Frontend types are pure TypeScript interfaces in `*.types.ts` (no decorators, no constructors).
- **Naming — files in kebab-case.** `estimate.types.ts`, `estimate-cell.ts`. NO `.component.` / `.service.` infix per Angular 2025 style guide (architecture.md §"TypeScript / Angular code").
- **No barrel files** (`index.ts` re-exports). Import by path. (architecture.md §"Structural Patterns / Frontend".)
- **Exhaustive `AppError` switch + `never` default** is MANDATORY (architecture.md §"Error handling (SPA)").
- **No silent retries.** No auto-poll, no auto-retry on 503. User retries by clicking again. (architecture.md §"Process Patterns / Retry & failure" + UX §"Failure recovery".)
- **Pessimistic UI for cross-service ops.** No optimistic update for the estimate flow (only same-service same-DB low-stakes mutations get optimistic UI — currently only the book-row status PATCH). (architecture.md §"Process Patterns / Loading state UI".)
- **`@angular-eslint/no-output-native`** will fail the build for outputs named `save`, `cancel`, `change`, `error`, `click`, `submit`, `close`, `load`. Story 2.6 hit this and had to rename `BookForm` outputs to `bookSaved`/`editCancelled`. (Source: epic-2-retro-2026-05-17.md line 133.) — `EstimateCell` likely needs NO outputs (state is local), but if any are added, avoid native-event names.

### Current state of files to MODIFY

#### `spa/src/app/books/estimate-cell.ts` — REPLACE in full

**Current state (Epic 2 stub):**
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
- The class is empty except for inputs — placeholder for Story 4.3.
- The docstring says "Story 4.3 stub" — must be removed.

**Preserve:** the `app-estimate-cell` selector, the two `input.required<number>()` declarations (`bookId`, `pages`), the `ChangeDetectionStrategy.OnPush`, the `templateUrl` + `styleUrl` references.

**Change:** the class body grows to include local state signals, the `BooksService` injection, the click handler, the exhaustive error switch, and exported copy constants. The `imports` array grows to include `RouterLink` and `ErrorMessage`.

#### `spa/src/app/books/estimate-cell.html` — REPLACE in full

**Current state:**
```html
<button class="estimate-cell-button" type="button" disabled title="Available in Epic 4">
  Estimate
</button>
```

**Replace with** a state-driven template (use Angular's new `@if`/`@else if`/`@else` control flow, NOT `*ngIf`):
```html
@if (loading()) {
  <button type="button" class="estimate-cell-button estimate-cell-button--primary" disabled>Estimating…</button>
} @else if (result(); as r) {
  <span class="estimate-cell-result">{{ r.formatted }}</span>
  <button type="button" class="estimate-cell-reestimate" (click)="onEstimateClick()">Re-estimate</button>
} @else {
  @if (error(); as e) {
    @if (e.kind === 'reading_speed_unset') {
      <p class="estimate-cell-error">
        Set your reading speed in <a routerLink="/settings" class="estimate-cell-error-link">Settings</a> to enable estimates
      </p>
    } @else {
      <app-error-message [message]="errorCopy()" />
    }
  }
  <button type="button" class="estimate-cell-button estimate-cell-button--primary" (click)="onEstimateClick()">Estimate</button>
}
```
- Use `@if (signal(); as alias)` to bind the truthy value inside the block — established pattern (book-form.html, book-list-page.html).
- Order matters: render error message ABOVE the restored button per UX-DR8 ("Failure cases restore the button beneath the error for retry").

#### `spa/src/app/books/estimate-cell.css` — REPLACE in full

**Current state:** styles the disabled stub button (`cursor: not-allowed; opacity: 0.6; color: var(--color-text-muted)`).

**Replace with** state-driven styles using design tokens (`--color-accent`, `--color-accent-hover`, `--color-error`, `--color-text`, `--text-body`, `--text-small`, `--spacing-2`, `--spacing-3`). Mirror the button styling precedent from `book-form.css` for the primary button and `book-row.css` for the secondary text button (Edit/Delete). Aim for visual parity with the SettingsPage Save button (--color-accent fill, white text) for the primary `Estimate` button, and with the BookRow `Edit`/`Delete` text buttons for `Re-estimate`.

#### `spa/src/app/books/estimate-cell.spec.ts` — REPLACE in full

**Current state:** one test asserting the disabled stub button + tooltip — entirely about the stub.

**Replace with** the 8 cases in AC16.

#### `spa/src/app/books/books-service.ts` — APPEND `requestEstimate`

**Current state:** has `load`, `create`, `update`, `setStatus`, `delete` — each follows the same pattern:
```ts
try {
  const result = await firstValueFrom(this.http.<verb>(...));
} catch (err) {
  throw this.errors.parse(err);
}
```
**Add `requestEstimate` matching that pattern.** Place it after `delete` (alphabetically and by recency).
- Import `EstimateOut` from `./estimate.types`.
- Do NOT touch the existing `books` signal.
- Do NOT add a `requestEstimateError` or `lastEstimate` signal — estimate state is component-local.

#### `spa/src/app/books/book-row.html` — DO NOT MODIFY

Line 17:
```html
<app-estimate-cell [bookId]="book().id" [pages]="book().pages" />
```
The component swap is silent. Verify line 17 still binds both inputs; do not edit.

#### `spa/src/app/books/book-row.ts` — DO NOT MODIFY

`formatDeleteError` already exhaustively switches on all 11 `AppError` kinds (including `reading_speed_unset` and `resource_server_unavailable` — present but unreachable in the Delete flow, kept for exhaustiveness). No edit needed.

#### `spa/src/app/books/book-row.spec.ts` — DO NOT MODIFY

Line 92's assertion `expect(el.querySelector('app-estimate-cell')).not.toBeNull();` continues to pass with the real EstimateCell rendered. No edit.

#### `spa/src/app/shared/errors/app-error.types.ts` — DO NOT MODIFY

`reading_speed_unset` and `resource_server_unavailable` are already present (lines 18-19). No edit.

#### `spa/src/app/shared/errors/error-service.ts` — DO NOT MODIFY

412+reading_speed_unset and 503-status paths are already covered (lines 49-51, 57-59, 93-96). No edit.

#### `spa/src/app/shared/ui/error-message.ts` — DO NOT MODIFY

Single-input shared component. Do NOT extend it (would ripple into LoginView, SettingsPage, BookForm, BookList, BookRow). For the `reading_speed_unset` variant with a link, use inline markup directly in `estimate-cell.html`.

### Wire contract — `POST /v1/books/{id}/estimate` (from BFF Story 4.2)

| Outcome | HTTP | Body | `ErrorService.parse` result |
|---|---|---|---|
| Success | 200 | `{"minutes": 1376, "formatted": "≈ 22 h 56 m"}` | (resolves with body) |
| Reading speed unset (J3 freshuser precondition) | 412 | `{"errorCode": "reading_speed_unset", "message": "...", "detail": null}` | `{ kind: 'reading_speed_unset' }` |
| RS unavailable (J6) — connection error / 5xx / 10s+ timeout | 503 | `{"errorCode": "resource_server_unavailable", "message": "..."}` | `{ kind: 'resource_server_unavailable' }` |
| Book not found / cross-user | 404 | `{"errorCode": "book_not_found", "message": "..."}` | `{ kind: 'book_not_found' }` |
| CSRF missing (should not happen at runtime — interceptor handles) | 403 | `{"errorCode": "csrf_invalid", "message": "..."}` | `{ kind: 'csrf_invalid' }` |
| Scope missing (defensive — RS forwarded) | 403 | `{"errorCode": "forbidden_scope", "message": "..."}` | `{ kind: 'forbidden_scope' }` |
| Pydantic validation failure (defensive — empty body is valid) | 422 | `{"errorCode": "invalid_input", ...}` | `{ kind: 'invalid_input', detail: ... }` |
| No session / expired session / refresh failed | 401 | `{"errorCode": "session_expired", "message": "..."}` | `{ kind: 'session_expired' }` — interceptor redirects to /login before component sees it |

**Critical detail:** the POST body is `{}` (empty object). The BFF reads `pages` from the books row server-side via `(sub, id)` lookup. Story 4.2 AC verifies this contract.

**`formatted` rendering rules (frozen by Story 4.1):**
| RS minutes | `formatted` |
|---|---|
| 1 | `≈ 1 m` |
| 12 | `≈ 12 m` |
| 60 | `≈ 1 h` |
| 61 | `≈ 1 h 1 m` |
| 260 | `≈ 4 h 20 m` |
| 1440 | `≈ 1 d` |
| 1500 | `≈ 1 d 1 h` |
| 2780 | `≈ 1 d 22 h 20 m` |

The leading character is U+2248 ALMOST EQUAL TO (`≈`), followed by an ASCII space. The SPA renders this string VERBATIM via Angular interpolation — no transformation.

### Test patterns (precedents from prior SPA stories)

**Vitest configuration** — already set in `vitest.config.ts`; tests run with Vitest globals (`describe`, `it`, `expect`, `vi`, `beforeEach`, `afterEach`). The shorthand `npm test` runs `vitest`; CI flag `--watch=false` is project standard.

**Two component-test scaffolds in use:**

Scaffold A (recommended for `EstimateCell`) — real service + `HttpTestingController`:
```ts
TestBed.configureTestingModule({
  imports: [ComponentUnderTest],
  providers: [
    provideZonelessChangeDetection(),
    provideHttpClient(withFetch()),
    provideHttpClientTesting(),
    provideRouter([...]),  // only when RouterLink is rendered (AC9 link case)
  ],
}).compileComponents();
```
Used by `books-service.spec.ts`, `book-row.spec.ts`, `book-form.spec.ts`, `status-control.spec.ts`.

Scaffold B — mocked service via `useValue`:
```ts
providers: [{ provide: BooksService, useValue: mockBooksService }],
```
Used by `book-list.spec.ts`, `settings-page.spec.ts`. Recommended for components that consume signals from a service. **Not the right fit for `EstimateCell`** because the test value is in exercising the wire-to-signal round-trip.

**Asserting on signal-rendered DOM** — call `fixture.detectChanges()` AFTER any signal mutation (including after `req.flush(...)` resolves the awaited Promise). Use `await fixture.whenStable()` to flush microtasks before assertions.

**RouterLink testing** — `provideRouter([{ path: 'settings', component: SomeStub }])` is enough to make `routerLink="/settings"` resolve to an `<a href="/settings">`. Avoid bringing in `RouterTestingHarness` — overkill for an assertion-only test.

**`HttpTestingController.expectOne`** — match by `{ method, url }` object. Always pair every `expectOne` with `req.flush(...)`; `afterEach: httpTesting.verify()` will fail the test if any request was unmatched.

**Empty body assertion:** `expect(req.request.body).toEqual({})` — this is what the BFF expects per Story 4.2.

### Previous story intelligence

#### Story 2.6 — `BookRow` + `StatusControl` (closed 2026-05-17)

- **Exhaustive `AppError` switch pattern established.** `book-row.ts` exports `BOOK_ROW_DELETE_FAILURE_COPY` as a const; `book-row.spec.ts` imports it for assertions. **Mirror this:** export `ESTIMATE_CELL_J6_COPY`, `ESTIMATE_CELL_GENERIC_COPY`, `ESTIMATE_CELL_PRECONDITION_COPY_PREFIX` (or similar) from `estimate-cell.ts` and import them in the spec.
- **`vi.spyOn(window, 'confirm')` pattern** is for delete confirmation, not relevant here (Estimate has no confirm).
- **`HttpTestingController` is provided alongside the real `BooksService`** — never use `useValue` for components that exercise an HTTP round-trip.
- **rowError-style local signal** — `BookRow` uses `rowError = signal<string | null>(null)` for inline row-level errors. `EstimateCell` will use its own local `error = signal<AppError | null>(null)` (typed, not stringified, so the template can switch on `kind`).
- **No optimistic updates for cross-service ops** — re-emphasized in 2.6's status-control work; carry forward to EstimateCell (pessimistic only).

#### Story 3.5 — BFF `ResourceServerClient` + SPA `SettingsView` (closed 2026-05-17)

- **`AppError` union extended with `resource_server_unavailable`** AND `reading_speed_unset` (line 18-19 of `app-error.types.ts`). Both variants already in place.
- **`ErrorService.parse` extended** — 502/503/504 → `resource_server_unavailable` regardless of body (CR7: proxy/edge 503 won't carry the project envelope); 412 + `reading_speed_unset` → the named variant.
- **SettingsPage 503 copy = `"Service unavailable — try again shortly"`** — same string MUST be used in EstimateCell for the J6 variant (AC10).
- **`firstValueFrom(http.…)` pattern** is used uniformly; rxjs Observable → Promise conversion at the service edge.
- **D86 (not-yet-fixed deferred):** if the user navigates away mid-request, the SPA doesn't abort. `EstimateCell` inherits this trade-off — accept it; do NOT introduce `takeUntilDestroyed` unless required by ACs.

#### Story 2.5 — `BookListPage` + `BookForm` (closed 2026-05-17)

- **`ErrorMessage` component pattern** — `<app-error-message [message]="msg" />` is the single-line, single-input shared component. Used by BookList for empty-state-after-load-error, BookForm for create errors, BookRow for delete/status errors. EstimateCell will use it for two of three error variants (AC10, AC11). For the link-bearing variant (AC9), render inline markup INSTEAD because the shared component does NOT support content projection.

#### Story 4.2 — BFF estimate endpoint (currently `ready-for-dev`, parallel-running)

- The BFF endpoint contract is FIXED by Story 4.2's ACs. This story's `requestEstimate` is built against that contract. If Story 4.2 is still in flight when this story is implemented, run them on parallel worktrees and integration-smoke at merge time.
- The BFF reads `pages` from the local books row, not from the request body — POST `{}` is the SPA's job.
- The BFF passes through the RS's `{ minutes, formatted }` body unchanged on success — no SPA-side transformation needed.

### UX spec compliance — verbatim copy + state machine

- **State machine:** `idle` → `loading` → (`success` | `error`). `success` → `loading` (Re-estimate) → ... `error` → `idle` (button restored beneath error). Source: ux-design-specification.md §"EstimateCell" (lines 631-636) + UX-DR8 (line 110).
- **Pessimistic UI** — no optimistic transitions. (UX-DR13 cited indirectly via architecture §"Loading state UI".)
- **No fabricated values, ever.** A J6 error MUST NOT show any `≈` character or numeric duration. Test 6 in AC16 asserts this. (UX §"Defining Experience: Detailed Mechanics" + §"J6 Resource server unavailable".)
- **In-place value replacement on Re-estimate** — no "previously…" callout, no fade. (UX §"Defining Experience: Detailed Mechanics" line 254.)
- **Failure copy strings (LITERAL):**
  - `Set your reading speed in Settings to enable estimates` — `Settings` is a link to `/settings`. Source: epics.md line 1664 + UX line 467.
  - `Service unavailable — try again shortly` — em-dash U+2014. Source: epics.md line 1670 + UX line 549.
  - `Couldn't get an estimate — try again` — em-dash U+2014; apostrophe is the curly U+2019. Source: epics.md line 1676 + UX line 470.

### Latest tech information

- **Angular v21** with zoneless change detection, signals (`signal`, `computed`, `effect`, `input.required`, `output`), standalone components, new control flow (`@if`/`@for`/`@switch`). `provideZonelessChangeDetection()` is wired in `app.config.ts`. `inject()` is the DI pattern; no constructor DI.
- **`@angular-eslint`** rules enforced — including `no-output-native` (Story 2.6 lesson) and `no-empty` catch blocks (architecture §"Error handling (SPA)"). Avoid `console.log` outside test files.
- **Tailwind v4 with `@theme` design tokens** in `spa/src/styles.css`. All required tokens (`--color-accent`, `--color-error`, `--color-text`, `--color-text-muted`, `--text-body`, `--text-small`, `--spacing-*`) are present. Use `var(--token)` in component CSS; do not hardcode hex values.
- **`@angular/router` v21** — `RouterLink` directive imported from `@angular/router`; bind via `[routerLink]="'/settings'"` or string-literal attribute `routerLink="/settings"`.
- **rxjs `firstValueFrom`** — convert `Observable<T>` → `Promise<T>` at the service edge; await throughout the codebase.

### Git intelligence (recent commits relevant to this story)

- `c02f2ef chore(4.1): code review — P1-P6 applied, mark done, log D113-D118` — RS estimate endpoint complete (4.1 closed today).
- `19cb3f8 feat(4.1): RS POST /v1/estimate + estimate_service + format_duration helper` — pins the wire shape `{minutes, formatted}` and the `format_duration` boundary table.
- `e167c3c Merge branch 'E4S1'` — Epic 4 Story 1 merge marker; Story 4.2 is in flight (status: ready-for-dev).
- `630ee6d Merge story 3.5 — BFF ResourceServerClient + SPA SettingsView for /settings` — landed `AppError` extension + `ErrorService` mapping for both relevant variants.

**Sprint reality:** Story 4.2 is `ready-for-dev` but not yet implemented. Story 4.3 can be developed in parallel on a worktree against the locked BFF contract. Manual cross-service smoke deferred until 4.2 merges (or run side-by-side branches).

### Failure-prevention checklist (LLM dev mistakes to avoid)

1. ❌ Re-adding `reading_speed_unset` or `resource_server_unavailable` to the `AppError` union. They are ALREADY there. (AC3)
2. ❌ Modifying `ErrorService.parse`. Both code paths are mapped. (AC3, AC18)
3. ❌ Modifying `book-row.html` or `book-row.spec.ts`. The selector check is sufficient; the template binding is stable. (AC14, AC19)
4. ❌ Extending `ErrorMessage` for content projection. Use inline markup in `estimate-cell.html` for the link variant instead. (AC9)
5. ❌ Sending `pages` in the POST body. The body is `{}`. (AC2, wire contract)
6. ❌ Parsing the `formatted` string client-side or computing duration from `minutes`. Render `formatted` verbatim. (AC7)
7. ❌ Using three ASCII dots `...` instead of U+2026 `…` in `Estimating…`. Mirror existing copy style (BookForm uses `…`).
8. ❌ Hyphen `-` instead of em-dash `—` in `Service unavailable — try again shortly`. Use U+2014.
9. ❌ Auto-retrying on 503. Manual retry only. (AC10, architecture §"Retry & failure".)
10. ❌ Optimistic UI / spinner overlay / skeleton. Pessimistic + relabel button. (AC6)
11. ❌ Output names colliding with native DOM events (`save`, `cancel`, `change`, `error`, etc.). EstimateCell likely has no outputs, but if any added, avoid these. (Story 2.6 lesson)
12. ❌ Removing the `pages` input from `EstimateCell`. It's currently unused at runtime but required by `BookRow`'s template binding. Keep the declaration. (AC4)
13. ❌ Renaming `app-estimate-cell` selector. Stable contract with BookRow. (AC4)
14. ❌ Forgetting to add a `provideRouter` provider in the test for the AC9 link assertion. RouterLink resolution requires a router context.
15. ❌ Modifying the global `withCredentialsInterceptor` or `csrfInterceptor`. They handle 401-redirect and CSRF header automatically — don't shadow either in the component.
16. ❌ Calling `console.log` in production code. ESLint will fail the build.
17. ❌ Bare `.catch(() => {})`. ESLint forbids; always re-throw the parsed `AppError`.
18. ❌ Forgetting to clear `result` and `error` when the user clicks `Estimate` again (after a previous error or success). Each click is a fresh round-trip.
19. ❌ Rendering the J6 copy for non-503 errors. The J6 copy is reserved for `resource_server_unavailable`. (AC11, AC16 test 8)
20. ❌ Importing from `'../../...'` style barrel paths. No barrel files in this project.

### Project structure notes

- New file: `spa/src/app/books/estimate.types.ts`.
- Modified files:
  - `spa/src/app/books/estimate-cell.ts` (rewrite)
  - `spa/src/app/books/estimate-cell.html` (rewrite)
  - `spa/src/app/books/estimate-cell.css` (rewrite)
  - `spa/src/app/books/estimate-cell.spec.ts` (rewrite)
  - `spa/src/app/books/books-service.ts` (append `requestEstimate`)
  - `spa/src/app/books/books-service.spec.ts` (append tests)
- Files explicitly NOT modified: `book.types.ts`, `book-row.{ts,html,spec.ts}`, `book-list*`, `book-form*`, `status-control*`, `app-error.types.ts`, `error-service.ts`, `error-message.{ts,html,css}`, `styles.css`, any auth/chrome/settings file, any BFF/RS code, any compose/e2e file.

Project structure follows existing convention (architecture.md §"Project Structure & Boundaries / spa/" tree). No deviation.

### References

- Epic + ACs: `_bmad-output/planning-artifacts/epics.md` §"Story 4.3" (lines 1630-1694) and §"Epic 4 Overview" (lines 1518-1520).
- Architecture:
  - `_bmad-output/planning-artifacts/architecture.md` §"Frontend Architecture / F1-F6" (lines 422-458).
  - §"API & Communication Patterns / C2 BFF endpoints" line 376 (POST `/v1/books/:id/estimate`).
  - §"API & Communication Patterns / C5 ErrorCode enum" lines 396-409.
  - §"Format Patterns / HTTP status codes" lines 674-690.
  - §"Communication Patterns / State management (SPA)" lines 705-731.
  - §"Communication Patterns / Error handling (SPA)" lines 712-731.
  - §"Process Patterns / Loading state UI + Retry & failure" lines 769-779.
  - §"Project Structure & Boundaries / spa/" lines 1009-1063.
- UX:
  - `_bmad-output/planning-artifacts/ux-design-specification.md` §"EstimateCell" (lines 631-636).
  - §"J3 Request reading-time estimate" (lines 458-480).
  - §"J6 Resource server unavailable" (lines 540-557).
  - §"Defining Experience: Detailed Mechanics" (lines 208-254).
  - UX-DR8 (line 110), UX-DR10 (line 112), UX-DR12 (mentioned), UX-DR13 (loading state), UX-DR14 (button hierarchy), UX-DR18 (estimate output format), UX-DR19 (in-place replacement).
- Precedent stories (read for patterns):
  - `_bmad-output/implementation-artifacts/2-4-spa-booksservice-types.md` — BooksService and types patterns.
  - `_bmad-output/implementation-artifacts/2-5-spa-booklist-page-bookform-add-variant-states.md` — BookListPage, ErrorMessage usage, form state machine.
  - `_bmad-output/implementation-artifacts/2-6-spa-bookrow-statuscontrol-with-optimistic-ui-edit-delete.md` — BookRow current state, no-output-native lesson, rowError pattern.
  - `_bmad-output/implementation-artifacts/3-5-bff-resourceserverclient-refresh-replay-reading-speed-proxy-spa-settingsview-route.md` — AppError extension precedent, SettingsPage error copy, 503 mapping.
  - `_bmad-output/implementation-artifacts/4-1-rs-post-v1-estimate-endpoint-estimate-service-format-duration-helper.md` — RS contract, format_duration boundary table.
  - `_bmad-output/implementation-artifacts/4-2-bff-post-v1-books-id-estimate-resourceserverclient-compute-estimate.md` — BFF contract (the wire EstimateCell hits).
- Retros and deferred work:
  - `_bmad-output/implementation-artifacts/epic-2-retro-2026-05-17.md` line 133 — `no-output-native` lesson.
  - `_bmad-output/implementation-artifacts/deferred-work.md` D86, D90, D98, D99 — open SPA polish items (NOT in scope here).

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) via bmad-dev-story skill (executed in worktree `agent-a32e6a27249f65923`).

### Debug Log References

- Initial test run after EstimateCell rewrite (no spec changes yet): 1 failure in the old stub spec (expected); 144/145 unrelated tests green. Confirmed component compiles + integrates.
- First spec attempt used raw `btn.click()` and 6 tests failed because the async click handler's resolution Promise wasn't awaited. Refactored to call `componentInstance.onEstimateClick()` directly (mirrors `status-control.spec.ts` precedent of invoking the handler so its Promise can be awaited before the next `detectChanges()` round). All 8 specs green on second attempt.
- Audit confirmed `app-error.types.ts` lines 18-19 already export `reading_speed_unset` + `resource_server_unavailable`; `error-service.ts` lines 49-51 + 57-59 already map both; `error-service.spec.ts` lines 50-75 already test both. No edits to any of these — failure-prevention checklist items 1 + 2 honored.
- `book-row.html`, `book-row.ts`, `book-row.spec.ts`, `app-error.types.ts`, `error-service.ts`, `error-service.spec.ts`, `error-message.{ts,html,css}` ALL unchanged — failure-prevention checklist items 3 + 4 honored.

### Completion Notes List

- All 20 ACs satisfied. AC1-AC2 (types + service), AC3 + AC18 (audit-only — variants and tests already present from Story 3.5), AC4-AC15 (EstimateCell component + template + CSS rewrite, exhaustive switch, exported copy constants), AC16-AC17 (8 + 6 new tests), AC19 (book-row.spec.ts untouched), AC20 (coverage 88.23% stmts / 78.57% branch on `estimate-cell.ts`, 100% / 85% on `books-service.ts`, project total 94.71% / 91.16% — all above AR34's 70% gate).
- Test count: 139 (baseline) → 152 (+13 net = 8 EstimateCell + 6 requestEstimate − 1 old stub spec removed).
- Lint: clean for all Story 4.3 files. 3 pre-existing `no-fallthrough` errors in `book-row.ts` / `book-form.ts` / `status-control.ts` exist in `main` (commit `e3236bd`) and are NOT caused by this story; those files are explicitly NOT modified per AC14/AC19 and failure-prevention checklist items 3 + 11.
- Punctuation fidelity verified: U+2026 ellipsis in `Estimating…`, U+2014 em dashes in J6 + generic copy, U+2019 curly apostrophe in `Couldn't`, U+2248 only ever in `formatted` from the wire (never in any local copy string). Test 6 (J6) asserts `expect(el.textContent).not.toContain('≈')` to pin the "no fabricated values" UX rule.
- Re-estimate flow: same `onEstimateClick` handler is reused (AC8) and clears `result` + `error` before firing so stale values never bleed through the loading state (AC6, failure-prevention checklist item 18).
- The `reading_speed_unset` (J3 freshuser) variant is rendered via INLINE `<a routerLink="/settings">` markup because `<app-error-message>` is a single-`message:string`-input component that does not support content projection. Extending it would ripple into LoginView / SettingsPage / BookForm / BookList / BookRow — failure-prevention checklist item 4 honored.
- Manual smoke deferred: Story 4.2 BFF lives on `main` in `review` state (commit `e3236bd`); end-to-end Estimate browser smoke is gated on 4.2 merging and is owned by Story 4.4 (E2E specs).

### File List

**New (1):**
- `spa/src/app/books/estimate.types.ts`

**Modified (6):**
- `spa/src/app/books/estimate-cell.ts` — replaced stub with real component (signals, click handler, exhaustive AppError switch, exported copy constants).
- `spa/src/app/books/estimate-cell.html` — replaced stub markup with state-driven template (idle / loading / success / 3 error variants).
- `spa/src/app/books/estimate-cell.css` — replaced disabled-stub styles with primary/secondary affordance + inline-error styles using design tokens.
- `spa/src/app/books/estimate-cell.spec.ts` — replaced 1-test stub spec with 8-case suite covering all UX states.
- `spa/src/app/books/books-service.ts` — appended `requestEstimate(id)` after `delete`; added `EstimateOut` import.
- `spa/src/app/books/books-service.spec.ts` — appended `describe('requestEstimate()')` block with 6 tests.

**Audited but NOT modified (per spec):**
- `spa/src/app/books/book-row.html`, `book-row.ts`, `book-row.spec.ts` (AC14 / AC19)
- `spa/src/app/shared/errors/app-error.types.ts` (AC3)
- `spa/src/app/shared/errors/error-service.ts` (AC3)
- `spa/src/app/shared/errors/error-service.spec.ts` (AC18 — both relevant cases already covered)
- `spa/src/app/shared/ui/error-message.{ts,html,css}` (failure-prevention checklist item 4)

### Change Log

- 2026-05-17 — Status `ready-for-dev` → `in-progress` → `review`. Implemented EstimateCell (types, component, template, CSS, spec) + BooksService.requestEstimate (impl + tests). Audited AppError union, ErrorService.parse, and error-service.spec.ts — no edits required (covered by Story 3.5). SPA test suite 139 → 152, all green. Lint: no new errors (3 pre-existing fallthrough errors in book-row.ts / book-form.ts / status-control.ts inherited from `main`).

