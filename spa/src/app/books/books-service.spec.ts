import { provideHttpClient, withFetch } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Book, BookCreate, BookUpdate } from './book.types';
import { BooksService } from './books-service';

function mkBook(overrides: Partial<Book> = {}): Book {
  return {
    id: 1,
    title: 'Test Title',
    pages: 100,
    status: 'to-read',
    created_at: '2026-05-16T00:00:00Z',
    updated_at: '2026-05-16T00:00:00Z',
    ...overrides,
  };
}

describe('BooksService', () => {
  let service: BooksService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withFetch()), provideHttpClientTesting()],
    });
    service = TestBed.inject(BooksService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  // -----------------------------------------------------------------------
  // Initial state
  // -----------------------------------------------------------------------
  it('initial signals: books=[], loading=false, loadError=null', () => {
    expect(service.books()).toEqual([]);
    expect(service.loading()).toBe(false);
    expect(service.loadError()).toBeNull();
  });

  // -----------------------------------------------------------------------
  // load()
  // -----------------------------------------------------------------------
  describe('load()', () => {
    it('happy path: sets loading=true synchronously, fires GET /v1/books, then sets books and loading=false on 200', async () => {
      const books = [mkBook({ id: 1 }), mkBook({ id: 2, title: 'Second' })];

      const pending = service.load();
      // Synchronous assertion BEFORE flushing — loading must already be true
      expect(service.loading()).toBe(true);
      expect(service.loadError()).toBeNull();

      httpTesting.expectOne({ method: 'GET', url: '/v1/books' }).flush(books);
      await pending;

      expect(service.books()).toEqual(books);
      expect(service.loading()).toBe(false);
      expect(service.loadError()).toBeNull();
    });

    it('error path: sets loadError to parsed AppError, leaves books unchanged, loading=false, does not reject', async () => {
      // pre-seed something so we can confirm books is not wiped
      service.books.set([mkBook({ id: 99 })]);
      const before = service.books();

      const pending = service.load();
      httpTesting.expectOne('/v1/books').flush(
        { errorCode: 'session_expired' },
        { status: 401, statusText: 'Unauthorized' },
      );
      await expect(pending).resolves.toBeUndefined();

      expect(service.loadError()).toEqual({ kind: 'session_expired' });
      expect(service.loading()).toBe(false);
      // books unchanged (same reference)
      expect(service.books()).toBe(before);
    });

    it('clears prior loadError when re-invoked', async () => {
      // First call errors
      const p1 = service.load();
      httpTesting.expectOne('/v1/books').flush(null, { status: 500, statusText: 'Server Error' });
      await p1;
      expect(service.loadError()).not.toBeNull();

      // Second call — loadError must be cleared synchronously before the request fires
      const p2 = service.load();
      expect(service.loadError()).toBeNull();
      httpTesting.expectOne('/v1/books').flush([]);
      await p2;
      expect(service.loadError()).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // create()
  // -----------------------------------------------------------------------
  describe('create()', () => {
    it('happy path: POSTs payload, prepends created book (newest first), returns the body', async () => {
      // Pre-seed with an existing book so we can verify "prepend"
      const existing = mkBook({ id: 1, title: 'Existing' });
      service.books.set([existing]);
      const before = service.books();

      const payload: BookCreate = { title: 'New', pages: 200, status: 'reading' };
      const created = mkBook({ id: 7, title: 'New', pages: 200, status: 'reading' });

      const pending = service.create(payload);
      const req = httpTesting.expectOne({ method: 'POST', url: '/v1/books' });
      expect(req.request.body).toEqual(payload);
      req.flush(created, { status: 201, statusText: 'Created' });

      const result = await pending;
      expect(result).toEqual(created);
      // Prepend: newest first
      expect(service.books()).toEqual([created, existing]);
      // Immutability: new reference
      expect(service.books()).not.toBe(before);
      // Loaderror is not touched
      expect(service.loadError()).toBeNull();
    });

    it('error path: rejects with parsed AppError, does not touch the books signal or loadError', async () => {
      const existing = mkBook({ id: 1 });
      service.books.set([existing]);
      const before = service.books();

      const payload: BookCreate = { title: '', pages: 0, status: 'to-read' };
      const pending = service.create(payload);
      httpTesting.expectOne('/v1/books').flush(
        { errorCode: 'invalid_input', detail: [{ loc: ['body', 'title'], msg: 'bad' }] },
        { status: 422, statusText: 'Unprocessable Entity' },
      );

      await expect(pending).rejects.toEqual({
        kind: 'invalid_input',
        detail: [{ loc: ['body', 'title'], msg: 'bad' }],
      });
      // books unchanged
      expect(service.books()).toBe(before);
      expect(service.loadError()).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // update()
  // -----------------------------------------------------------------------
  describe('update()', () => {
    it('happy path: PATCHes payload, replaces matching row immutably, returns the body', async () => {
      const a = mkBook({ id: 1, title: 'A' });
      const b = mkBook({ id: 2, title: 'B' });
      service.books.set([a, b]);
      const before = service.books();

      const payload: BookUpdate = { title: 'A-updated' };
      const updated = mkBook({ id: 1, title: 'A-updated', updated_at: '2026-05-17T00:00:00Z' });

      const pending = service.update(1, payload);
      const req = httpTesting.expectOne({ method: 'PATCH', url: '/v1/books/1' });
      expect(req.request.body).toEqual(payload);
      req.flush(updated);

      const result = await pending;
      expect(result).toEqual(updated);
      expect(service.books()).toEqual([updated, b]);
      // Immutability: new reference
      expect(service.books()).not.toBe(before);
    });

    it('happy path with missing id (race): books reference still changes from map() but row is not present', async () => {
      // Pre-seed a row that does NOT match the updated id, so we can capture and assert reference change
      const other = mkBook({ id: 1 });
      service.books.set([other]);
      const before = service.books();
      // No row with id=999 in the signal — update returns the body but signal map is a no-op for that id
      const updated = mkBook({ id: 999 });
      const pending = service.update(999, { title: 'X' });
      httpTesting.expectOne('/v1/books/999').flush(updated);
      const result = await pending;
      expect(result).toEqual(updated);
      // No row inserted — the missing id is not auto-added; existing rows unchanged in content
      expect(service.books()).toEqual([other]);
      // Signal reference changed (map() returns a new array even on no-match) — confirms immutable update path
      expect(service.books()).not.toBe(before);
    });

    it('error path: rejects with parsed AppError, does not touch the books signal', async () => {
      const a = mkBook({ id: 1 });
      service.books.set([a]);
      const before = service.books();

      const pending = service.update(1, { title: 'X' });
      httpTesting.expectOne('/v1/books/1').flush(
        { errorCode: 'book_not_found' },
        { status: 404, statusText: 'Not Found' },
      );

      await expect(pending).rejects.toEqual({ kind: 'book_not_found' });
      expect(service.books()).toBe(before);
    });
  });

  // -----------------------------------------------------------------------
  // setStatus()
  // -----------------------------------------------------------------------
  describe('setStatus()', () => {
    it('optimistic-then-success: optimistic update visible synchronously; replaced by server row after flush', async () => {
      const row = mkBook({ id: 1, status: 'to-read', updated_at: '2026-05-16T00:00:00Z' });
      service.books.set([row]);

      const pending = service.setStatus(1, 'reading');

      // Synchronous optimistic visibility
      expect(service.books()[0].status).toBe('reading');
      // optimistic row preserves old updated_at
      expect(service.books()[0].updated_at).toBe('2026-05-16T00:00:00Z');

      const serverRow = mkBook({
        id: 1,
        status: 'reading',
        updated_at: '2026-05-17T12:34:56Z',
      });
      const req = httpTesting.expectOne({ method: 'PATCH', url: '/v1/books/1' });
      expect(req.request.body).toEqual({ status: 'reading' });
      req.flush(serverRow);

      await pending;
      // Authoritative server row replaces optimistic
      expect(service.books()[0]).toEqual(serverRow);
      expect(service.books()[0].updated_at).toBe('2026-05-17T12:34:56Z');
    });

    it('optimistic-then-revert: optimistic update applied, then reverted on 422, rejects with parsed AppError', async () => {
      const row = mkBook({ id: 1, status: 'to-read' });
      service.books.set([row]);

      const pending = service.setStatus(1, 'reading');
      // Optimistic
      expect(service.books()[0].status).toBe('reading');

      httpTesting.expectOne('/v1/books/1').flush(
        { errorCode: 'invalid_input' },
        { status: 422, statusText: 'Unprocessable Entity' },
      );

      await expect(pending).rejects.toEqual({ kind: 'invalid_input', detail: undefined });
      // Reverted to original
      expect(service.books()[0].status).toBe('to-read');
    });

    it('no-op skip: prev === next does not fire HTTP and resolves to undefined', async () => {
      const row = mkBook({ id: 1, status: 'reading' });
      service.books.set([row]);
      const before = service.books();

      const result = await service.setStatus(1, 'reading');
      expect(result).toBeUndefined();
      httpTesting.expectNone('/v1/books/1');
      // signal untouched
      expect(service.books()).toBe(before);
    });

    it('unknown-id skip: no row with that id does not fire HTTP and resolves', async () => {
      // empty signal
      const before = service.books();
      const result = await service.setStatus(999, 'reading');
      expect(result).toBeUndefined();
      httpTesting.expectNone('/v1/books/999');
      expect(service.books()).toBe(before);
    });

    it('revert preserves immutability (new reference after revert)', async () => {
      const row = mkBook({ id: 1, status: 'to-read' });
      service.books.set([row]);
      const before = service.books();

      const pending = service.setStatus(1, 'finished');
      // optimistic reference changed
      expect(service.books()).not.toBe(before);
      const afterOptimistic = service.books();

      httpTesting.expectOne('/v1/books/1').flush(null, { status: 500, statusText: 'Server Error' });
      await expect(pending).rejects.toBeDefined();
      // reverted — new reference again
      expect(service.books()).not.toBe(afterOptimistic);
      expect(service.books()[0].status).toBe('to-read');
    });
  });

  // -----------------------------------------------------------------------
  // delete()
  // -----------------------------------------------------------------------
  describe('delete()', () => {
    it('happy path: DELETE /v1/books/{id} on 204 removes the row immutably', async () => {
      const a = mkBook({ id: 1 });
      const b = mkBook({ id: 2 });
      service.books.set([a, b]);
      const before = service.books();

      const pending = service.delete(1);
      httpTesting
        .expectOne({ method: 'DELETE', url: '/v1/books/1' })
        .flush(null, { status: 204, statusText: 'No Content' });

      await expect(pending).resolves.toBeUndefined();
      expect(service.books()).toEqual([b]);
      // Immutability: new reference
      expect(service.books()).not.toBe(before);
    });

    it('error path: rejects with parsed AppError, books signal untouched', async () => {
      const a = mkBook({ id: 1 });
      service.books.set([a]);
      const before = service.books();

      const pending = service.delete(1);
      httpTesting.expectOne('/v1/books/1').flush(
        { errorCode: 'book_not_found' },
        { status: 404, statusText: 'Not Found' },
      );

      await expect(pending).rejects.toEqual({ kind: 'book_not_found' });
      expect(service.books()).toBe(before);
    });
  });

  // -----------------------------------------------------------------------
  // requestEstimate() — Story 4.3
  // -----------------------------------------------------------------------
  describe('requestEstimate()', () => {
    it('happy path: POSTs {} to /v1/books/{id}/estimate, resolves with the body, does NOT mutate books signal', async () => {
      // Pre-seed the books signal so we can assert it's untouched.
      const existing = mkBook({ id: 1 });
      service.books.set([existing]);
      const before = service.books();

      const pending = service.requestEstimate(1);
      const req = httpTesting.expectOne({
        method: 'POST',
        url: '/v1/books/1/estimate',
      });
      // POST body MUST be the empty object — BFF reads pages from the local books row.
      expect(req.request.body).toEqual({});
      req.flush({ minutes: 260, formatted: '≈ 4 h 20 m' });

      const result = await pending;
      expect(result).toEqual({ minutes: 260, formatted: '≈ 4 h 20 m' });
      // Books signal untouched (same reference).
      expect(service.books()).toBe(before);
      expect(service.loadError()).toBeNull();
    });

    it('412 reading_speed_unset: rejects with the named AppError variant', async () => {
      const pending = service.requestEstimate(1);
      httpTesting.expectOne('/v1/books/1/estimate').flush(
        { errorCode: 'reading_speed_unset', message: 'unset', detail: null },
        { status: 412, statusText: 'Precondition Failed' },
      );
      await expect(pending).rejects.toEqual({ kind: 'reading_speed_unset' });
    });

    it('503: rejects with resource_server_unavailable (J6 marquee failure)', async () => {
      const pending = service.requestEstimate(7);
      httpTesting.expectOne('/v1/books/7/estimate').flush(
        { errorCode: 'resource_server_unavailable', message: 'down' },
        { status: 503, statusText: 'Service Unavailable' },
      );
      await expect(pending).rejects.toEqual({ kind: 'resource_server_unavailable' });
    });

    it('404 book_not_found: rejects with the named AppError variant', async () => {
      const pending = service.requestEstimate(42);
      httpTesting.expectOne('/v1/books/42/estimate').flush(
        { errorCode: 'book_not_found', message: 'gone' },
        { status: 404, statusText: 'Not Found' },
      );
      await expect(pending).rejects.toEqual({ kind: 'book_not_found' });
    });

    it('500 unknown: rejects with kind=unknown carrying status / errorCode / message', async () => {
      const pending = service.requestEstimate(3);
      httpTesting.expectOne('/v1/books/3/estimate').flush(
        { errorCode: 'unknown', message: 'boom' },
        { status: 500, statusText: 'Server Error' },
      );
      await expect(pending).rejects.toEqual({
        kind: 'unknown',
        status: 500,
        errorCode: 'unknown',
        message: 'boom',
      });
    });

    it('401 status-only fallback: rejects with session_expired', async () => {
      const pending = service.requestEstimate(9);
      // Non-envelope body — exercises the status-only fallback in ErrorService.
      httpTesting.expectOne('/v1/books/9/estimate').flush(
        null,
        { status: 401, statusText: 'Unauthorized' },
      );
      await expect(pending).rejects.toEqual({ kind: 'session_expired' });
    });
  });
});
