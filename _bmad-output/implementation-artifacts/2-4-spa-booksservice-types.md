---
status: done
story_key: 2-4-spa-booksservice-types
created: 2026-05-16
---

# Story 2.4: SPA — BooksService + types

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer wiring SPA components to the books API,
I want a `BooksService` that owns the books signal and exposes typed CRUD methods (with optimistic status updates + revert-on-failure) plus a `book.types.ts` mirroring the wire shape,
so that Stories 2.5 / 2.6 components subscribe to the signal and call methods without dealing with HTTP state themselves.

## Scope (read this first)

This story is **the books data layer only**. It does **not** render any UI — `BookListPage`, `BookList`, `BookRow`, `BookForm`, `StatusControl` land in Stories 2.5 / 2.6 and consume this service.

Concretely, this story delivers:

1. `spa/src/app/books/book.types.ts` — `Book`, `BookStatus`, `BookCreate`, `BookUpdate`.
2. `spa/src/app/books/books-service.ts` — `BooksService` (signals + CRUD methods).
3. `spa/src/app/books/books-service.spec.ts` — service tests.
4. **`spa/src/app/shared/errors/app-error.types.ts`** — `AppError` discriminated union (NEW shared module — first consumer).
5. **`spa/src/app/shared/errors/error-service.ts`** — `ErrorService` with `parse(err)`.
6. **`spa/src/app/shared/errors/error-service.spec.ts`** — error-service tests.

`AppError` + `ErrorService` were scoped to Epic 1 (per epic doc line 153 — "baseline `ErrorService` parsing the archetype envelope") but Stories 1.9 / 1.10 did not deliver them. Story 2.4 is the first consumer and **must create the baseline `AppError` + `ErrorService` as part of this story**. See Dev Notes §"Critical: `AppError` and `ErrorService` do not yet exist".

Out of scope for 2.4: any `book-list-page.ts` / `book-list.ts` / `book-row.ts` / `book-form.ts` / `status-control.ts` / `estimate-cell.ts` / route-table edit (still points at `books-page-placeholder` until 2.5). No template wiring. No CSS. No new compose / docker changes.

## Acceptance Criteria

**AC1 — `book.types.ts` exports the documented type set.**

`spa/src/app/books/book.types.ts` exports:

- `export type BookStatus = 'to-read' | 'reading' | 'finished'`.
- `export interface Book { id: number; title: string; pages: number; status: BookStatus; created_at: string; updated_at: string }` — **`snake_case` field names** (per AR16 — no case-conversion layer; the wire JSON and the TS model are identical).
- `export interface BookCreate { title: string; pages: number; status: BookStatus }`.
- `export type BookUpdate = Partial<{ title: string; pages: number; status: BookStatus }>` — partial update (PATCH semantics).

No additional types, no helpers, no re-exports. Pure `.types.ts` per the existing `auth.types.ts` precedent.

**AC2 — `AppError` discriminated union exists at `shared/errors/app-error.types.ts`.**

`spa/src/app/shared/errors/app-error.types.ts` exports:

```ts
export type AppError =
  | { kind: 'session_expired' }
  | { kind: 'forbidden_scope' }
  | { kind: 'invalid_input'; detail?: unknown }
  | { kind: 'book_not_found' }
  | { kind: 'csrf_invalid' }
  | { kind: 'auth_state_invalid' }
  | { kind: 'network' }
  | { kind: 'unknown'; status: number };
```

**Do not** include `resource_server_unavailable` or `reading_speed_unset` in 2.4 — those variants are added later by Story 3.5 (`resource_server_unavailable`) and Story 4.3 (`reading_speed_unset`). Adding them now would create dead code paths that no downstream consumer has yet defined behavior for.

**AC3 — `ErrorService` parses HTTP errors at `shared/errors/error-service.ts`.**

`spa/src/app/shared/errors/error-service.ts` exports:

```ts
@Injectable({ providedIn: 'root' })
export class ErrorService {
  parse(err: unknown): AppError { /* ... */ }
}
```

Behavior of `parse(err)`:

- If `err` is an `HttpErrorResponse` with `status === 0` (transport / CORS / offline / aborted) → returns `{ kind: 'network' }`.
- If `err` is an `HttpErrorResponse` whose body matches the archetype envelope shape `{ errorCode: string, message?: string, detail?: unknown }`, look at `errorCode`:
  - `"session_expired"` → `{ kind: 'session_expired' }`
  - `"forbidden_scope"` → `{ kind: 'forbidden_scope' }`
  - `"invalid_input"` → `{ kind: 'invalid_input', detail: body.detail }` (passes through the validation detail array as-is)
  - `"book_not_found"` → `{ kind: 'book_not_found' }`
  - `"csrf_invalid"` → `{ kind: 'csrf_invalid' }`
  - `"auth_state_invalid"` → `{ kind: 'auth_state_invalid' }`
  - any other `errorCode` value → `{ kind: 'unknown', status: err.status }`
- If `err` is an `HttpErrorResponse` whose body is **not** the envelope shape (`errorCode` missing or not a string), fall back to the status code:
  - status 401 → `{ kind: 'session_expired' }` (defensive — interceptor should redirect first, but coverage of the underlying response matters)
  - status 403 → `{ kind: 'csrf_invalid' }`
  - status 404 → `{ kind: 'book_not_found' }` (a non-envelope 404 in the books surface is, by elimination, a not-found)
  - status 422 → `{ kind: 'invalid_input', detail: undefined }`
  - any other status → `{ kind: 'unknown', status: err.status }`
- If `err` is **not** an `HttpErrorResponse` (e.g., a thrown `Error` from inside RxJS) → `{ kind: 'unknown', status: 0 }`.

**Pure function, no signals, no DI on construction.** `parse(...)` is total (never throws), and is the single mapping point in the SPA from HTTP errors to typed `AppError`.

**AC4 — `BooksService` exists with the documented signals and methods.**

`spa/src/app/books/books-service.ts` exports `@Injectable({ providedIn: 'root' })` class `BooksService` with:

```ts
@Injectable({ providedIn: 'root' })
export class BooksService {
  private readonly http = inject(HttpClient);
  private readonly errors = inject(ErrorService);

  readonly books = signal<Book[]>([]);
  readonly loading = signal<boolean>(false);
  readonly loadError = signal<AppError | null>(null);

  async load(): Promise<void> { /* ... */ }
  async create(payload: BookCreate): Promise<Book> { /* ... */ }
  async update(id: number, payload: BookUpdate): Promise<Book> { /* ... */ }
  async setStatus(id: number, next: BookStatus): Promise<void> { /* ... */ }
  async delete(id: number): Promise<void> { /* ... */ }
}
```

**Dependencies acquired via `inject(...)` (no constructor DI)**, per AR4 / AR23 and matching the precedent in `auth-service.ts`. Signals are exposed as `readonly` directly (not `asReadonly()`); the architecture's convention is "service methods are the only write paths" (architecture §"Communication Patterns" line 709) — that's enforced by code review, not by type. (`AuthService` uses `asReadonly()` for `me`; the epic AC for `BooksService` shows direct exposure of `books`, `loading`, `loadError`. Follow the epic AC verbatim.)

**AC5 — `load()` semantics.**

`BooksService.load()`:

1. Sets `loading.set(true)` and `loadError.set(null)` synchronously before firing the request.
2. Fires `GET /v1/books` via `HttpClient`.
3. On 200: `books.set(response)` then `loading.set(false)`. Returns `void`.
4. On any error: `loadError.set(this.errors.parse(err))`, `loading.set(false)`. Returns `void` (does NOT rethrow — `load()` is the "initial fetch" entry point and the component shows the load-error state from the signal).

**`load()` is the ONLY method that writes to `loadError`.** Other methods throw `AppError` instead — components render row-level / form-level errors locally.

**AC6 — `create(payload)` semantics.**

`BooksService.create(payload: BookCreate): Promise<Book>`:

1. Fires `POST /v1/books` with `payload` as the JSON body.
2. On 201: **immutably prepends** the created book to the signal: `this.books.update(prev => [created, ...prev])`. Returns the created `Book`.
3. On any error: throws `this.errors.parse(err)` (an `AppError`). Does NOT touch the `books` signal. Does NOT touch `loadError`.

**Order matters:** prepend (newest first) is the epic's explicit choice (line 913). The BFF's `GET /v1/books` returns insertion order ascending (oldest first); the SPA reverses for display by prepending on create. After a `load()` followed by zero or more `create()` calls, the in-memory list has newest-first within session and oldest-first within `load()`. (When the page reloads, the next `load()` returns oldest-first and the session-only newest-first ordering is lost — Stories 2.5 / 2.6 / 2.7 do not depend on a specific cross-load ordering, only on insertion order within a session.)

**AC7 — `update(id, payload)` semantics.**

`BooksService.update(id: number, payload: BookUpdate): Promise<Book>`:

1. Fires `PATCH /v1/books/{id}` with `payload` as the JSON body.
2. On 200: replaces the matching row in the signal immutably: `this.books.update(prev => prev.map(b => b.id === id ? updated : b))`. Returns the updated `Book`.
3. On any error: throws `this.errors.parse(err)`. Does NOT touch the signal.

If `id` does not exist in the current `books()` value (race condition — the row was deleted by another tab), `prev.map` is a no-op for that id — no `books` mutation occurs even on a 200, but the method still returns the server's `updated` body. That's acceptable for 2.4; Stories 2.5 / 2.6 do not test cross-tab scenarios.

**AC8 — `setStatus(id, next)` is the OPTIMISTIC path (UX-DR7, UX-DR13).**

`BooksService.setStatus(id: number, next: BookStatus): Promise<void>`:

1. Snapshot the prior status of the target row: `const prev = this.books().find(b => b.id === id)?.status`. If the row doesn't exist in the signal, **don't fire the request** — return immediately (the caller has a stale id).
2. Optimistically apply the new status:
   `this.books.update(rows => rows.map(b => b.id === id ? { ...b, status: next } : b))` — note the `{ ...b, status: next }` spread (immutable update; no in-place mutation).
3. Fire `PATCH /v1/books/{id}` with body `{ status: next }`.
4. **On 2xx (the BFF returns the updated `BookOut`):** replace the optimistic row with the authoritative server row:
   `this.books.update(rows => rows.map(b => b.id === id ? updated : b))`. This ensures `updated_at` reflects the server's tick (the optimistic row had a stale `updated_at`). Returns `void`.
5. **On any 4xx/5xx:** revert the row to its `prev` status:
   `this.books.update(rows => rows.map(b => b.id === id ? { ...b, status: prev! } : b))`,
   then **throw** `this.errors.parse(err)` so the calling component (Story 2.6's `BookRow`) can render a row-level error.

If `prev === next` (no-op call), skip the network round-trip and the optimistic update. Return immediately. This is a small guard for the case where the user clicks the same value twice.

**AC9 — `delete(id)` semantics.**

`BooksService.delete(id: number): Promise<void>`:

1. Fires `DELETE /v1/books/{id}`.
2. On 204: removes the row immutably: `this.books.update(rows => rows.filter(b => b.id !== id))`. Returns `void`.
3. On any error: throws `this.errors.parse(err)`. Does NOT touch the signal (Story 2.6's `BookRow` shows the inline row-level error and leaves the row in place for retry, per UX-DR6 / UX-DR12).

**AC10 — Tests at `books-service.spec.ts` cover the methods.**

The test file uses Angular's `TestBed` with `provideHttpClient(withFetch())` + `provideHttpClientTesting()` and `HttpTestingController`. Mirrors the structure of `auth-service.spec.ts`.

For each of `load`, `create`, `update`, `setStatus`, `delete`, the file includes:

1. **Happy path** — fire the documented HTTP method/URL/body, flush a successful response, assert the books signal mutates as documented (use the signal as a getter: `service.books()`), and (for `create`/`update`) assert the returned promise resolves to the parsed body.
2. **Error path** — flush a 4xx/5xx with the archetype envelope; for `load` assert `loadError()` is set to the parsed AppError and the books signal is unchanged; for the other methods assert the returned promise rejects with the parsed AppError shape (e.g., `await expect(p).rejects.toEqual({ kind: 'book_not_found' })`).

For `setStatus` add at minimum:

3. **Optimistic-then-success** — pre-seed `books` with one row; call `setStatus`; before flushing the request, assert `books()[0].status === next` (optimistic update visible synchronously); flush 200 with an updated `BookOut`; await the returned promise; assert `books()[0]` is the server's authoritative row.
4. **Optimistic-then-revert** — pre-seed; call `setStatus`; assert optimistic update; flush 422 with `{ errorCode: 'invalid_input' }`; await rejection; assert `books()[0].status` matches the original snapshot.
5. **No-op skip** — pre-seed a row with `status='reading'`; call `setStatus(id, 'reading')`; assert NO HTTP request is enqueued (`httpTesting.expectNone(...)`); the returned promise resolves to `undefined`.
6. **Unknown id skip** — call `setStatus(999, 'reading')` against an empty signal; assert NO HTTP request is enqueued; promise resolves.

**Immutability assertions** — at least one test per write method captures `const before = service.books();` before the call and asserts `service.books() !== before` after (signal reference changed, no in-place mutation).

**AC11 — Tests at `error-service.spec.ts` cover the parse map.**

`spa/src/app/shared/errors/error-service.spec.ts` constructs `ErrorService` via `TestBed` and exercises `parse(...)` against synthetic `HttpErrorResponse` instances. Covers, at minimum:

- Transport / status-0 error → `{ kind: 'network' }`.
- Envelope `{ errorCode: "session_expired" }` (status 401) → `{ kind: 'session_expired' }`.
- Envelope `{ errorCode: "forbidden_scope" }` (status 403) → `{ kind: 'forbidden_scope' }`.
- Envelope `{ errorCode: "invalid_input", detail: [...] }` (status 422) → `{ kind: 'invalid_input', detail: [...] }` (detail passthrough exact).
- Envelope `{ errorCode: "book_not_found" }` (status 404) → `{ kind: 'book_not_found' }`.
- Envelope `{ errorCode: "csrf_invalid" }` (status 403) → `{ kind: 'csrf_invalid' }`.
- Envelope `{ errorCode: "auth_state_invalid" }` (status 400) → `{ kind: 'auth_state_invalid' }`.
- Envelope `{ errorCode: "totally_unknown_code" }` (status 500) → `{ kind: 'unknown', status: 500 }`.
- Non-envelope body (raw `{ detail: "Not Found" }`) status 404 → `{ kind: 'book_not_found' }` (status-fallback path).
- Non-envelope body status 401 → `{ kind: 'session_expired' }` (status-fallback path).
- Non-envelope body status 599 (unmapped) → `{ kind: 'unknown', status: 599 }`.
- A non-`HttpErrorResponse` thrown (e.g., `new Error('boom')`) → `{ kind: 'unknown', status: 0 }`.

**AC12 — Coverage and lint gates.**

- `npm test -- --watch=false` from `spa/` passes; the suite count strictly increases from the baseline at Story 1.10's close (12+ new tests across `books-service.spec.ts` and `error-service.spec.ts`).
- **Vitest coverage of `src/app/books/books-service.ts`, `src/app/books/book.types.ts`, `src/app/shared/errors/error-service.ts`, `src/app/shared/errors/app-error.types.ts` is ≥70%** (project threshold per AR34; `.types.ts` files trivially clear because they're type-only).
- `npm run lint` reports no new findings.

## Tasks / Subtasks

- [x] Task 1 — `book.types.ts` (AC1)
  - [x] 1.1 Create `spa/src/app/books/book.types.ts` exporting `BookStatus`, `Book`, `BookCreate`, `BookUpdate`. Use `snake_case` for `created_at` / `updated_at` — do NOT add a `camelCase` alias.
  - [x] 1.2 Delete `spa/src/app/books/books-page-placeholder.ts` only if Story 2.5 has already routed `/books` to `BookListPage`. **For this story leave the placeholder alone** — `app.routes.ts` still loads it, and Story 2.5 will replace the route entry.

- [x] Task 2 — `AppError` + `ErrorService` (AC2, AC3, AC11)
  - [x] 2.1 Create folder `spa/src/app/shared/errors/`.
  - [x] 2.2 Create `spa/src/app/shared/errors/app-error.types.ts` with the discriminated union from AC2. **Do not** add `resource_server_unavailable` or `reading_speed_unset` — those variants land in Stories 3.5 and 4.3.
  - [x] 2.3 Create `spa/src/app/shared/errors/error-service.ts` with the `parse(err: unknown): AppError` mapping from AC3. Use `import { HttpErrorResponse } from '@angular/common/http'` to type-check the `instanceof` branch.
  - [x] 2.4 Create `spa/src/app/shared/errors/error-service.spec.ts` covering AC11.

- [x] Task 3 — `BooksService` skeleton + `load` / `create` / `delete` (AC4, AC5, AC6, AC9)
  - [x] 3.1 Create `spa/src/app/books/books-service.ts` with the class shell from AC4 — signals declared, dependencies injected via `inject(...)`, methods stubbed with `throw new Error('not implemented')`.
  - [x] 3.2 Implement `load()` per AC5. Use `firstValueFrom(this.http.get<Book[]>('/v1/books'))` (matches the pattern in `auth-service.ts`).
  - [x] 3.3 Implement `create(payload)` per AC6. `this.http.post<Book>('/v1/books', payload)`. On error, `throw this.errors.parse(err)`.
  - [x] 3.4 Implement `delete(id)` per AC9. `this.http.delete('/v1/books/{id}', { observe: 'response' })` is NOT needed — a successful `firstValueFrom(this.http.delete(...))` resolves on any 2xx; the 204 body is empty and Angular handles it. Just throw on error.

- [x] Task 4 — `update(id, payload)` and `setStatus(id, next)` (AC7, AC8)
  - [x] 4.1 Implement `update(id, payload)` per AC7. `this.http.patch<Book>('/v1/books/{id}', payload)`.
  - [x] 4.2 Implement `setStatus(id, next)` per AC8. Critical sequence: snapshot prior → optimistic update → fire PATCH → on success replace with server row → on failure revert + throw. Include the no-op skip (`prev === next`) and the unknown-id skip.
  - [x] 4.3 Cross-check: every `books.update(...)` callsite uses an immutable update (spread, map, filter — never `.push`, `.splice`, or `arr[i] = x`).

- [x] Task 5 — `books-service.spec.ts` (AC10)
  - [x] 5.1 Create `spa/src/app/books/books-service.spec.ts`. Use the test scaffold from `auth-service.spec.ts` as a template (TestBed setup, `httpTesting.verify()` in `afterEach`).
  - [x] 5.2 Add the seven test categories from AC10 (happy + error for each of the five methods, plus the four `setStatus`-specific cases).
  - [x] 5.3 Add the immutability assertions called for in AC10's final paragraph.

- [x] Task 6 — Coverage & lint verification (AC12)
  - [x] 6.1 `npm test -- --watch=false` — green; new test count ≥ 12.
  - [x] 6.2 `npm run lint` — clean.
  - [x] 6.3 Spot-check coverage: open `src/app/books/books-service.ts` and `src/app/shared/errors/error-service.ts` in the Vitest coverage report; both ≥70%.

## Dev Notes

### Critical: `AppError` and `ErrorService` do not yet exist

Search the codebase before starting:

```bash
grep -rln "AppError\|ErrorService" spa/src/app
```

The only hits are `app-error-message` (the existing `ErrorMessage` component selector) — **no `AppError` type, no `ErrorService`**. The architecture (line 717) and the epic (lines 81, 153) reference them as if they existed; Stories 1.9 / 1.10 were scoped to deliver "baseline `ErrorService` parsing the archetype envelope" (epic line 153) but did not. Deferred-work item D16 (`deferred-work.md`) implicitly hangs on this gap. **Story 2.4 is the first consumer and must create them.**

This is the #1 thing the original create-story workflow could have missed. Do not assume they exist.

### Critical: do NOT touch `app.routes.ts` or `books-page-placeholder.ts`

`spa/src/app/app.routes.ts` currently loads `BooksPagePlaceholder` for `/books`. **Leave it alone.** Story 2.5 replaces the route entry to point at the new `BookListPage`. Touching the route here would break the current authenticated landing page (and break the J1 / J5 Playwright specs in `e2e/tests/`).

### Wire-error contract — what 2.4 expects from the BFF

By the time Story 2.4 runs in production, Stories 2.1 / 2.2 / 2.3 will have shipped (per sprint-status order). That means the BFF emits, on the `/v1/books*` surface:

| HTTP | `errorCode` (envelope) | When |
|---|---|---|
| 401 | `session_expired` | No session cookie / expired session (caught by global interceptor → navigates to `/login` BEFORE the rejection reaches `BooksService`; defensive AppError mapping still required). |
| 403 | `csrf_invalid` | Missing/mismatched `X-CSRF-Token` on POST/PATCH/DELETE. |
| 404 | `book_not_found` | `GET/PATCH/DELETE /v1/books/{id}` for a missing or cross-user id. |
| 422 | `invalid_input` | Pydantic validation failure (`pages <= 0`, unknown status, empty/whitespace title). The `detail` field carries the Pydantic detail array (with `input` values stripped per BFF Patch P3 in `services/bff/src/bff/core/errors.py:62-69`). |
| 201 / 200 / 204 | — | Happy paths. |

**Caveat — current BFF state at 2.4 dev time:** Story 2.2 is `backlog` per `sprint-status.yaml` at the moment Story 2.4 is *created*. The dev agent for 2.4 should treat the wire shape above as the contract per architecture §"Format Patterns" / AR16, even if the BFF doesn't yet emit `book_not_found` / `invalid_input` (currently it emits `VALIDATION_ERROR`). The `ErrorService.parse()` mapping is forward-looking: it codes against the *contracted* wire format, not the present BFF state. If you run the SPA against a not-yet-2.2-updated BFF, an `invalid_input` body becomes the status-fallback `{ kind: 'invalid_input', detail: undefined }` (status 422 → invalid_input) — that's by design and exactly the resilience AC3 specifies.

### Existing SPA patterns to mirror exactly

**1. `spa/src/app/auth/auth-service.ts`** — service style. Note:
- `@Injectable({ providedIn: 'root' })` (tree-shakeable singleton).
- `private readonly http = inject(HttpClient)` — `inject()` not constructor DI.
- `firstValueFrom(this.http.get<Me>('/api/me'))` — convert Observable to Promise (auth-service.ts:15).
- Try/catch around the await; rethrow non-401 errors. **For BooksService, do not duplicate auth-service's 401 special-case** — the global `withCredentialsInterceptor` handles 401 for non-`/api/me` paths (line 25 of `with-credentials-interceptor.ts`); `BooksService` just lets the error throw upward, which the interceptor catches and reroutes from.

**2. `spa/src/app/auth/auth-service.spec.ts`** — test scaffold. Note:
- `TestBed.configureTestingModule({ providers: [provideHttpClient(withFetch()), provideHttpClientTesting()] })`.
- `service = TestBed.inject(AuthService);` `httpTesting = TestBed.inject(HttpTestingController);`.
- `afterEach(() => { httpTesting.verify(); });` — guards against forgotten flushes.
- Pattern: kick the call (`const pending = service.loadMe();`), then `httpTesting.expectOne('/api/me').flush(me);`, then `await pending`, then assert signal.

**3. `spa/src/app/auth/auth.types.ts`** — types module style:
```ts
export interface Me {
  sub: string;
  preferred_username: string;
}
```
Plain TS, no decorators, no imports. `book.types.ts` matches this style.

**4. `spa/src/app/shared/http/with-credentials-interceptor.ts`** — already handles 401 globally:

```ts
if (err instanceof HttpErrorResponse && err.status === 401 && pathOf(authedReq.url) !== ME_PATH) {
  authService.clear();
  const returnTo = encodeURIComponent(router.url);
  router.navigateByUrl(`/login?return_to=${returnTo}`);
}
return throwError(() => err);
```

That means by the time a `BooksService` method's `firstValueFrom(...)` rejects with a 401, the interceptor has already:
- Cleared `me` signal.
- Triggered a navigation to `/login?return_to=...`.
- Rethrown the original `HttpErrorResponse`.

`BooksService` should **NOT** re-navigate, re-clear, or special-case the 401 — just `throw this.errors.parse(err)` and the consumer (`BookRow`, `BookForm`, etc.) won't render an inline error because the user is already mid-redirect.

### Signal exposure: `readonly signal()` vs. `asReadonly()` — small inconsistency, follow the epic

`AuthService` does:
```ts
private readonly _me = signal<Me | null>(null);
readonly me: Signal<Me | null> = this._me.asReadonly();
```

The epic's AC for `BooksService` (line 899) explicitly writes:
```ts
readonly books = signal<Book[]>([]);
readonly loading = signal<boolean>(false);
readonly loadError = signal<AppError | null>(null);
```

These are `WritableSignal<...>` exposed directly. The convention "service methods are the only write paths" is enforced by code review (architecture line 709), not by the type system. **Follow the epic verbatim** — direct signal exposure. Don't refactor `AuthService` to match (out of scope). If a future story tightens this, that's a deliberate change.

### `firstValueFrom` and 204 No Content

`DELETE /v1/books/{id}` returns 204 with no body. `firstValueFrom(this.http.delete('/v1/books/{id}'))` resolves with `null` (Angular parses an empty body as `null` by default). Just `await` the call — don't pass `{ observe: 'response' }` unless you need the headers. The promise resolution itself is the success signal.

### Optimistic update — the order matters

The AC8 sequence is **strictly**:

1. Snapshot prior status (before any signal mutation).
2. Skip-checks (`!exists`, `prev === next`).
3. Optimistic update (immediately visible to subscribers).
4. Fire PATCH.
5. Branch on resolve / reject.

If steps 3 and 4 swap, the UI doesn't appear optimistic — the optimism only matters because it's perceptually instant. If step 1 happens *after* step 3, the snapshot captures the new value and the revert becomes a no-op.

The Stories 2.6 (`BookRow` / `StatusControl`) and 2.7 (J2 Playwright spec) both test for synchronous optimism — Story 2.7's spec literally asserts the select's selected value updates "before any network round-trip resolves" (epics.md line 1098). The implementation must satisfy that ordering precisely.

### Immutability — the trap

Angular signals are reference-equal-checked. Doing `this.books().push(created)` (a) mutates the inner array in place and (b) does not trigger downstream `computed`/`effect` notifications (the reference didn't change). Every write to `books` MUST use `this.books.update(prev => /* new array */)` or `this.books.set(newArray)`. Spread, `map`, `filter`, `[...prev, x]` — never `.push`, `.splice`, `arr[i] = x`.

Anti-pattern explicitly flagged in architecture line 854:
> A component that mutates `this.booksService.books().push(newBook)` — mutating a signal's inner value.

The same rule applies inside the service. The architecture's example at line 838-847 is the good shape:

```ts
async load(): Promise<void> {
  const list = await firstValueFrom(this.http.get<Book[]>('/v1/books'));
  this.books.set(list);
}
```

### HTTP path conventions

All books-API paths are **unversioned-relative to the SPA's same-origin BFF**: `/v1/books` (collection) and `/v1/books/{id}` (resource). No prefix; the BFF static-serves the SPA at `/`, so a relative path works in production. In dev, `spa/proxy.conf.json` already forwards `/v1/*` to BFF on `:8000`. **Do not prepend `/api/v1/books` or `http://localhost:8000/v1/books` or anything else.**

Pattern (matches `auth-service.ts:15` exactly):

```ts
await firstValueFrom(this.http.get<Book[]>('/v1/books'));
await firstValueFrom(this.http.post<Book>('/v1/books', payload));
await firstValueFrom(this.http.patch<Book>(`/v1/books/${id}`, payload));
await firstValueFrom(this.http.delete(`/v1/books/${id}`));
```

### Interceptor interaction — already wired

`spa/src/app/app.config.ts` already registers `[withCredentialsInterceptor, csrfInterceptor]` globally. **You do NOT need to add `withCredentials: true` to individual requests** — the interceptor does it. You do NOT need to set the `X-CSRF-Token` header manually — `csrfInterceptor` reads the `csrf_token` cookie and sets the header on POST/PUT/PATCH/DELETE (csrf-interceptor.ts:25-34). Just call `this.http.post(...)` / `.patch(...)` / `.delete(...)` and the interceptors handle the rest.

This also means **the `BooksService` tests don't need to set up cookies or assert headers** — interceptors are not registered in the `HttpTestingController` configuration (we use `provideHttpClient(withFetch())` not the full interceptor chain). The `csrf-interceptor.spec.ts` already covers the interceptor itself.

### Pydantic detail array shape — what `invalid_input.detail` looks like

When the BFF rejects a `POST /v1/books` body (e.g., empty title), the envelope is:

```json
{
  "errorCode": "invalid_input",
  "message": "Request validation failed",
  "detail": [
    {"loc": ["body", "title"], "msg": "title must not be empty or whitespace-only", "type": "value_error"}
  ]
}
```

The `detail` field is an **array of pydantic error dicts** (with `input` stripped per BFF errors.py:62-69). `ErrorService.parse()` passes it through as `unknown` — Stories 2.5 / 2.6 will format it for the inline error display. For 2.4 just verify it's preserved end-to-end in `error-service.spec.ts`.

### Testing wisdom carried forward from Story 1.10

Patterns observed in `auth-service.spec.ts` (the closest-shape precedent):

- Use `expectOne('/v1/books')` not regex matchers — exact string is fine since the URL is fixed.
- For PATCH/DELETE on a path-parameterized URL, use a backtick template: `expectOne(`/v1/books/${id}`)`.
- Use `.flush(body)` for 2xx; for errors use `.flush(body, { status, statusText })`:

```ts
httpTesting.expectOne('/v1/books').flush(
  { errorCode: 'invalid_input', message: 'Request validation failed', detail: [] },
  { status: 422, statusText: 'Unprocessable Entity' },
);
```

- `httpTesting.expectNone(url)` is the right assertion for the no-op skip case in AC10.5.
- `service.books()` is the signal getter — call it as a function, not `service.books` (which returns the WritableSignal itself).
- Always `await pending` before asserting post-flush signal state.

### Files NOT to touch in this story

- `spa/src/app/app.routes.ts` — Story 2.5 replaces the `/books` route.
- `spa/src/app/books/books-page-placeholder.ts` — Story 2.5 deletes it.
- `spa/src/app/auth/auth-service.ts` — no refactor of `asReadonly()` to match BooksService.
- `spa/src/app/shared/http/csrf-interceptor.ts`, `with-credentials-interceptor.ts` — already correct.
- `spa/src/app/shared/ui/error-message.{ts,html,css}` — that's the existing **component**, not the new service.
- `spa/proxy.conf.json` — already forwards `/v1/*` to BFF.
- `spa/src/app/app.config.ts` — `ErrorService` is `@Injectable({ providedIn: 'root' })`, so it's auto-registered; no `providers:` array edit.
- `services/bff/...` — no backend changes in 2.4.
- `docker-compose.yml`, `compose/app.yml` — no infra changes.

### Project Structure Notes

New files for this story, all under `spa/src/app/`:

```
spa/src/app/
├── books/
│   ├── book.types.ts                              (NEW)
│   ├── books-service.ts                           (NEW)
│   ├── books-service.spec.ts                      (NEW)
│   └── books-page-placeholder.ts                  (untouched)
└── shared/
    └── errors/                                    (NEW folder)
        ├── app-error.types.ts                     (NEW)
        ├── error-service.ts                       (NEW)
        └── error-service.spec.ts                  (NEW)
```

Architecture's directory map (architecture.md line 1033-1062) shows `app-error.types.ts` and `error-service.{ts,spec.ts}` exactly at `shared/errors/` — follow it verbatim.

**No barrel files** (`index.ts`). Architecture line 637: "No barrel files unless a folder has 4+ external consumers." The new `shared/errors/` folder has two files; future consumers import the named exports directly.

**No CSS, no HTML** — services and types only. The architecture's filename pattern `error-service.{ts,spec.ts}` (no `.html` / `.css`) confirms.

### Previous Story Intelligence (Stories 1.9 / 1.10 / 1.11 / 1.14 — done, reviewed, merged)

- **Story 1.9** (`spa/src/app/auth/`) is the immediate template for service shape, test scaffolding, and interceptor behavior. Mimic it. (Skipped: it did not deliver `ErrorService` even though epic line 153 said it was Epic 1 scope — Story 2.4 picks up that gap.)
- **Story 1.10** delivered `LoginView`, `TopChrome`, and the route table at `app.routes.ts`. Coverage gates landed at 70%+ for the SPA per AR34. The 1.10 review found a few cosmetic issues but no architecture deviations — the test patterns observed there still apply.
- **Story 1.11–1.13** (Playwright) tests J1 + J5 against the running stack. They depend on the current `BooksPagePlaceholder` rendering at `/books`. **Do not break the placeholder route** — Stories 1.13's `j1-first-login` and `j5-logout` specs (`e2e/tests/`) navigate to `/books` after login and assert the page renders.
- **Story 1.14** (BFF multi-stage build) wired SPA same-origin serving with HTML5 history fallback. Relative paths like `/v1/books` resolve to the same origin in prod and to the BFF via `proxy.conf.json` in dev. No change required in 2.4.
- **Lint / coverage gates are non-negotiable.** Story 1.10's review caught a missed coverage threshold; budget time for `npm test -- --coverage` before declaring complete.

### Git intelligence (recent commits)

```
81ae50f story 2.1                                  (just-created BFF story file; no code yet)
060df66 feat: minor fixes to the CSFR token naming
ca02146 fix: BFF drops offline_access scope + realm declares profile scope
180b1e2 chore(1.14): code review — F1 path-traversal guard, F2 docstring fix, 5 defers; close epic-1
501a85a Merge story 1.14 — dev-story phase
96d6640 feat(1.14): BFF multi-stage build serves SPA bundle (closes D46, unblocks 5.4)
```

Epic 1 is closed. The only in-flight work is Story 2.1 (BFF book SQLModel) — a separate, parallel-safe stream. No SPA changes since Story 1.14's same-origin wiring. Branch `epic-2` is the working branch.

### Latest tech information (Angular v21 + signals)

- **Angular v21.2** (per `spa/package.json`) — zoneless, signals, `inject()` over constructor DI. All in use already in `AuthService`.
- **`signal()` / `WritableSignal`** is from `@angular/core`. `.set(...)`, `.update(prev => ...)`, `.asReadonly()` are the public API. **Avoid `.mutate(...)`** — it was removed in v17+. Use `.update(prev => ({ ...prev, ... }))` for object/array changes.
- **`HttpClient.get<T>(...)` returns `Observable<T>`**. Use `firstValueFrom` from `rxjs` to convert to a Promise. The `auth-service.ts:3` import is the canonical place.
- **`@Injectable({ providedIn: 'root' })`** is the only DI registration needed — no `providers:` edit in `app.config.ts`.
- **Test runner:** Vitest via `@angular/build:unit-test` (angular.json line ~67). Coverage via `@vitest/coverage-v8` (already a devDep). `npm test` runs the suite once with `--watch=false` semantics under `ng test`'s default; the package.json `test:coverage` script enables the coverage flag.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4: SPA — BooksService + types] (verbatim AC source)
- [Source: _bmad-output/planning-artifacts/epics.md#AR16] (snake_case wire / archetype envelope on failure)
- [Source: _bmad-output/planning-artifacts/epics.md#AR17] (ErrorCode wire values — `book_not_found`, `invalid_input`, `csrf_invalid`, `session_expired`, `auth_state_invalid`, `forbidden_scope`)
- [Source: _bmad-output/planning-artifacts/epics.md#AR21] (signals + per-feature service; `ErrorService` parses envelope to typed `AppError`)
- [Source: _bmad-output/planning-artifacts/epics.md#AR23] (functional router, `inject()` DI)
- [Source: _bmad-output/planning-artifacts/epics.md#AR34] (Vitest + TestBed + `HttpTestingController`; ≥70% coverage)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR7] (StatusControl is the only optimistic path)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR13] (optimistic vs pessimistic rule — only book-status PATCH is optimistic)
- [Source: _bmad-output/planning-artifacts/architecture.md#Frontend Architecture / F1] (`BooksService` (`books` signal + CRUD methods))
- [Source: _bmad-output/planning-artifacts/architecture.md#Communication Patterns] (immutable signal updates, service methods are only write paths)
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns] (HTTP status → ErrorCode mapping table)
- [Source: _bmad-output/planning-artifacts/architecture.md#Pattern Examples] (`books-service.ts` canonical shape, anti-patterns to reject)
- [Source: _bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure] (`shared/errors/` and `books/` folder layouts)
- [Source: _bmad-output/planning-artifacts/PRD.md#FR2 (FR-BOOK-01)] (book = title + pages + status; ownership keyed by `sub`)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#StatusControl / BookForm / BookList / BookRow] (component contracts the service supports)
- [Pattern: spa/src/app/auth/auth-service.ts] (service shape, `inject()` DI, `firstValueFrom` usage)
- [Pattern: spa/src/app/auth/auth-service.spec.ts] (TestBed scaffold, `HttpTestingController`, signal-getter assertions)
- [Pattern: spa/src/app/auth/auth.types.ts] (`.types.ts` module style — pure types, no decorators)
- [Pattern: spa/src/app/shared/http/with-credentials-interceptor.ts:25-31] (global 401 redirect — `BooksService` must NOT re-handle 401)
- [Pattern: spa/src/app/shared/http/csrf-interceptor.ts:25-34] (`X-CSRF-Token` is interceptor-managed)
- [Defer: _bmad-output/implementation-artifacts/deferred-work.md#D16] (404/405 envelope coverage — `ErrorService.parse()` covers it via the AC3 status-fallback path)
- [Gate: spa/package.json] (`test:coverage` script; Vitest + @vitest/coverage-v8; `ng lint`)

## Definition of Done

1. `book.types.ts` exists with the four documented exports and `snake_case` fields on `Book` (AC1).
2. `app-error.types.ts` exists with the AC2 discriminated union — and **does not** include `resource_server_unavailable` or `reading_speed_unset` (those land later).
3. `error-service.ts` exists, exports `@Injectable({providedIn:'root'}) ErrorService` with a total `parse(err: unknown): AppError` matching AC3.
4. `books-service.ts` exists, exposes `books`/`loading`/`loadError` signals and the five methods, all using `inject()` DI per AR4 / AR23 (AC4).
5. `load`/`create`/`update`/`setStatus`/`delete` behave per AC5–AC9, all writes are immutable, `setStatus` is optimistic with revert-on-failure and includes both skip-paths (AC8).
6. `books-service.spec.ts` covers happy + error + optimistic + revert + skip paths (AC10).
7. `error-service.spec.ts` covers every branch of the parse map (AC11).
8. `npm test` is green, Vitest coverage of the four new modules is ≥70%, suite count strictly increases (AC12).
9. `npm run lint` is clean (AC12).
10. No changes to `app.routes.ts`, `books-page-placeholder.ts`, or any other file outside the seven listed in §Scope.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) — via `bmad-dev-story` workflow.

### Debug Log References

- `npm test -- --watch=false` (worktree, post-impl): 11 files / 65 tests passed (baseline was 32; +33 new tests, AC12 requirement was ≥12).
- `npm run lint`: clean (1 finding fixed mid-implementation — `EnvelopeBody` switched from `type` alias to `interface` per `@typescript-eslint/consistent-type-definitions`).
- `npm run test:coverage`: `app/books/books-service.ts` 100% stmts / 85% branches / 100% funcs / 100% lines; `app/shared/errors/error-service.ts` 25/25 statements covered (text reporter elides 100%-coverage files; confirmed via `coverage/spa/coverage-final.json`). Both well above the AC12 ≥70% gate.

### Completion Notes List

- All 12 ACs satisfied. `book.types.ts` exposes the four named exports with `snake_case` on `Book.created_at` / `Book.updated_at` per AR16. `AppError` discriminated union in `shared/errors/app-error.types.ts` deliberately omits `resource_server_unavailable` (3.5) and `reading_speed_unset` (4.3).
- `ErrorService.parse()` is a pure, total mapping from `unknown` → `AppError`. Envelope-first branch (`isEnvelope` guard checks `typeof errorCode === 'string'`), then status fallback, then a catch-all `{ kind: 'unknown', status: 0 }` for non-`HttpErrorResponse` inputs.
- `BooksService` uses `inject(...)` DI per AR4 / AR23, mirrors `auth-service.ts`. Signals are exposed as `WritableSignal<...>` directly (per epic AC literal — not `asReadonly()` — code review enforces "service methods are the only write paths").
- `setStatus()` snapshot order is **strict**: `find row → guards (unknown id, prev===next) → optimistic update → fire PATCH → branch (success: replace with authoritative row; failure: revert + throw)`. Snapshot happens before any signal mutation so revert is correct.
- All `books.update(...)` callsites use immutable updates (spread, `map`, `filter`) — no `.push`, `.splice`, or index assignment. Tests assert `service.books() !== before` after every write method.
- `delete()` uses `firstValueFrom(http.delete(...))` and `await`s on the empty 204 body (Angular parses empty body as `null`; the resolve itself is success).
- No changes to `app.routes.ts`, `books-page-placeholder.ts`, `app.config.ts`, or interceptors. Story 2.5 will replace the route entry.

### File List

New files:

- `spa/src/app/books/book.types.ts`
- `spa/src/app/books/books-service.ts`
- `spa/src/app/books/books-service.spec.ts`
- `spa/src/app/shared/errors/app-error.types.ts`
- `spa/src/app/shared/errors/error-service.ts`
- `spa/src/app/shared/errors/error-service.spec.ts`

Modified files:

- `_bmad-output/implementation-artifacts/2-4-spa-booksservice-types.md` (status + tasks + Dev Agent Record)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (`2-4-spa-booksservice-types: ready-for-dev → in-progress → review`)

### Change Log

- 2026-05-16 — Implemented Story 2.4 per ACs 1–12. SPA `BooksService` + types + baseline `AppError`/`ErrorService` (first consumer). 33 new tests, lint clean, coverage ≥70% on all four new modules. Status moved to `review`.
- 2026-05-16 — Code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor lenses): 1 patch applied (P1 — missing-id `update()` test now asserts reference change), 3 defers logged (D54/D55/D56 — concurrency + phantom-write hardening, all out of scope per story §142). Status moved to `done`.

### Review Findings

- [x] [Review][Patch] P1 — `update()` missing-id test (`spa/src/app/books/books-service.spec.ts:174`) named "books reference still changes from map() but row is not present" but did not assert the reference change. Added pre-seed + `expect(service.books()).not.toBe(before)` to actually exercise the immutable-map path on no-match. **Applied.**
- [x] [Review][Defer] D54 — `setStatus()` concurrent-call snapshot races (`spa/src/app/books/books-service.ts:54-86`) — out of scope per story §142; logged in `deferred-work.md`.
- [x] [Review][Defer] D55 — `load()` concurrent-call last-wins (`spa/src/app/books/books-service.ts:20-29`) — no AC requires de-dup; single entry-point in practice; logged.
- [x] [Review][Defer] D56 — `update()` against unknown id triggers phantom signal write (`spa/src/app/books/books-service.ts:43-52`) — acceptable per story §152; future optimization; logged.

### Senior Developer Review (AI)

**Reviewer:** Claude Opus 4.7 (1M context) via `bmad-code-review` skill (Blind Hunter / Edge Case Hunter / Acceptance Auditor lenses).
**Date:** 2026-05-16.
**Outcome:** Approve with 1 patch applied, 3 defers logged.

**Lenses run:**

1. **Blind Hunter** (diff only) — surfaced 6 candidate findings, 5 dismissed as noise (story-acknowledged design choices, total-function guarantees, semantically-equivalent style). 1 actionable: P1 (test hygiene).
2. **Edge Case Hunter** (diff + project) — surfaced 5 candidate findings. 2 dismissed as out-of-domain (BFF concerns, server-controlled ids). 3 are real but out-of-scope per story line 142 / line 152 — logged as D54 / D55 / D56.
3. **Acceptance Auditor** (diff + spec + context) — all 12 ACs verified satisfied. No spec deviations.

**Test gates re-verified after patch:** 65/65 tests pass; lint clean; `books-service.ts` + `error-service.ts` 100% statement coverage.

**Action Items**

- [x] P1 (low) — `update()` missing-id test reference-change assertion added. AC10 immutability-assertion coverage. File: `spa/src/app/books/books-service.spec.ts:174-189`.
- [x] D54 (defer, low) — concurrent `setStatus` snapshot race. Out of scope per story §142. Logged in `deferred-work.md`.
- [x] D55 (defer, low) — concurrent `load()` last-wins. Out of scope. Logged.
- [x] D56 (defer, nit) — phantom signal write on unknown-id `update()`. Out of scope per story §152. Logged.
