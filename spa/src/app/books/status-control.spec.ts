import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Book, BookStatus } from './book.types';
import { BooksService } from './books-service';
import { STATUS_CONTROL_FAILURE_COPY, StatusControl } from './status-control';

function mkBook(overrides: Partial<Book> = {}): Book {
  return {
    id: 1,
    title: 'Dune',
    pages: 688,
    status: 'to-read',
    created_at: '2026-05-16T00:00:00Z',
    updated_at: '2026-05-16T00:00:00Z',
    ...overrides,
  };
}

async function renderControl(
  initialStatus: BookStatus = 'to-read',
  bookId = 1,
): Promise<{
  fixture: ComponentFixture<StatusControl>;
  httpTesting: HttpTestingController;
  booksService: BooksService;
}> {
  await TestBed.configureTestingModule({
    imports: [StatusControl],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withFetch()),
      provideHttpClientTesting(),
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(StatusControl);
  fixture.componentRef.setInput('bookId', bookId);
  fixture.componentRef.setInput('status', initialStatus);
  fixture.detectChanges();
  await fixture.whenStable();

  const httpTesting = TestBed.inject(HttpTestingController);
  const booksService = TestBed.inject(BooksService);
  return { fixture, httpTesting, booksService };
}

function getSelect(fixture: ComponentFixture<StatusControl>): HTMLSelectElement {
  return (fixture.nativeElement as HTMLElement).querySelector(
    'select.status-control-select',
  ) as HTMLSelectElement;
}

function changeSelect(select: HTMLSelectElement, value: string): void {
  select.value = value;
  select.dispatchEvent(new Event('change'));
}

describe('StatusControl', () => {
  let httpTesting: HttpTestingController;

  afterEach(() => {
    httpTesting?.verify();
  });

  it('default state: renders an enabled <select> with three options in documented order and the current value selected', async () => {
    const r = await renderControl('to-read');
    httpTesting = r.httpTesting;
    r.booksService.books.set([mkBook({ id: 1, status: 'to-read' })]);

    const select = getSelect(r.fixture);
    expect(select).not.toBeNull();
    expect(select.disabled).toBe(false);
    expect(select.value).toBe('to-read');

    const options = Array.from(select.querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['to-read', 'reading', 'finished']);
  });

  it('disabled during in-flight PATCH: select disables, books() shows optimistic value, then re-enables after flush', async () => {
    const r = await renderControl('to-read');
    httpTesting = r.httpTesting;
    r.booksService.books.set([mkBook({ id: 1, status: 'to-read' })]);

    const pending = r.fixture.componentInstance.onChange('reading');
    r.fixture.detectChanges();

    // Optimistic write happened synchronously
    expect(r.booksService.books()[0].status).toBe('reading');

    // Select disabled before flush
    const select = getSelect(r.fixture);
    expect(select.disabled).toBe(true);

    const req = httpTesting.expectOne({ method: 'PATCH', url: '/v1/books/1' });
    expect(req.request.body).toEqual({ status: 'reading' });
    req.flush(mkBook({ id: 1, status: 'reading' }));
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    expect(getSelect(r.fixture).disabled).toBe(false);
  });

  it('optimistic-update happy path: books()[0].status flips synchronously then is replaced by the server row on success', async () => {
    const r = await renderControl('to-read');
    httpTesting = r.httpTesting;
    const initial = mkBook({ id: 1, status: 'to-read' });
    r.booksService.books.set([initial]);

    const pending = r.fixture.componentInstance.onChange('reading');
    r.fixture.detectChanges();

    expect(r.booksService.books()[0].status).toBe('reading');

    const serverRow = mkBook({
      id: 1,
      status: 'reading',
      updated_at: '2026-05-17T11:30:00Z',
    });
    httpTesting.expectOne('/v1/books/1').flush(serverRow);
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    expect(r.booksService.books()[0]).toEqual(serverRow);
  });

  it('optimistic-then-revert: 422 reverts books()[0].status to prior value and emits statusChangeFailed with documented copy', async () => {
    const r = await renderControl('to-read');
    httpTesting = r.httpTesting;
    r.booksService.books.set([mkBook({ id: 1, status: 'to-read' })]);

    const emitted: string[] = [];
    r.fixture.componentInstance.statusChangeFailed.subscribe((msg) => emitted.push(msg));

    const pending = r.fixture.componentInstance.onChange('reading');
    r.fixture.detectChanges();

    expect(r.booksService.books()[0].status).toBe('reading');

    httpTesting.expectOne('/v1/books/1').flush(
      { errorCode: 'invalid_input', message: 'bad input' },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    // Reverted by BooksService.setStatus
    expect(r.booksService.books()[0].status).toBe('to-read');
    expect(emitted).toEqual([STATUS_CONTROL_FAILURE_COPY]);
  });

  it('no-op skip: changing the select to the same value dispatches NO HTTP request and emits no failure', async () => {
    const r = await renderControl('to-read');
    httpTesting = r.httpTesting;
    r.booksService.books.set([mkBook({ id: 1, status: 'to-read' })]);

    const emitted: string[] = [];
    r.fixture.componentInstance.statusChangeFailed.subscribe((msg) => emitted.push(msg));

    const select = getSelect(r.fixture);
    changeSelect(select, 'to-read');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    httpTesting.expectNone('/v1/books/1');
    expect(emitted).toEqual([]);
  });
});
