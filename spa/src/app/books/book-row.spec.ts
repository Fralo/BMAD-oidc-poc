import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { BookForm } from './book-form';
import { Book } from './book.types';
import { BookRow, BOOK_ROW_DELETE_FAILURE_COPY } from './book-row';
import { BooksService } from './books-service';
import { StatusControl } from './status-control';

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

async function renderRow(book: Book): Promise<{
  fixture: ComponentFixture<BookRow>;
  httpTesting: HttpTestingController;
  booksService: BooksService;
}> {
  await TestBed.configureTestingModule({
    imports: [BookRow],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withFetch()),
      provideHttpClientTesting(),
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(BookRow);
  fixture.componentRef.setInput('book', book);
  fixture.detectChanges();
  await fixture.whenStable();

  const httpTesting = TestBed.inject(HttpTestingController);
  const booksService = TestBed.inject(BooksService);
  // Seed the books signal so optimistic / delete paths find the row.
  booksService.books.set([book]);
  fixture.detectChanges();
  await fixture.whenStable();

  return { fixture, httpTesting, booksService };
}

function getEl(fixture: ComponentFixture<BookRow>): HTMLElement {
  return fixture.nativeElement as HTMLElement;
}

function getActionButton(
  fixture: ComponentFixture<BookRow>,
  label: 'Edit' | 'Delete',
): HTMLButtonElement | null {
  const buttons = Array.from(
    getEl(fixture).querySelectorAll('button.book-row-action'),
  ) as HTMLButtonElement[];
  return buttons.find((b) => b.textContent?.trim() === label) ?? null;
}

describe('BookRow', () => {
  let httpTesting: HttpTestingController;
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    confirmSpy = vi.spyOn(window, 'confirm');
  });

  afterEach(() => {
    confirmSpy?.mockRestore();
    httpTesting?.verify();
  });

  it('display mode renders title, "<n> pages", status-control, estimate-cell, Edit and Delete buttons, no error', async () => {
    const r = await renderRow(mkBook({ title: 'Dune', pages: 688, status: 'to-read' }));
    httpTesting = r.httpTesting;
    const el = getEl(r.fixture);

    expect(el.querySelector('.book-row-title')?.textContent?.trim()).toBe('Dune');
    expect(el.querySelector('.book-row-pages')?.textContent?.trim()).toBe('688 pages');
    expect(el.querySelector('app-status-control')).not.toBeNull();
    expect(el.querySelector('app-estimate-cell')).not.toBeNull();

    const editBtn = getActionButton(r.fixture, 'Edit');
    const deleteBtn = getActionButton(r.fixture, 'Delete');
    expect(editBtn).not.toBeNull();
    expect(deleteBtn).not.toBeNull();

    expect(el.querySelector('app-error-message')).toBeNull();
    expect(el.querySelector('app-book-form')).toBeNull();
  });

  it('Edit toggles to edit mode: app-book-form is mounted, display row is hidden', async () => {
    const r = await renderRow(mkBook({ title: 'Dune', pages: 688 }));
    httpTesting = r.httpTesting;

    getActionButton(r.fixture, 'Edit')?.click();
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const el = getEl(r.fixture);
    expect(el.querySelector('app-book-form')).not.toBeNull();
    expect(el.querySelector('.book-row')).toBeNull();
    expect(r.fixture.componentInstance.editing()).toBe(true);
  });

  it('Cancel from edit returns to display mode', async () => {
    const r = await renderRow(mkBook({ title: 'Dune' }));
    httpTesting = r.httpTesting;

    getActionButton(r.fixture, 'Edit')?.click();
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    // Invoke the form's cancel handler programmatically (via the BookRow handler)
    r.fixture.componentInstance.onEditCancel();
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    expect(r.fixture.componentInstance.editing()).toBe(false);
    expect(getEl(r.fixture).querySelector('.book-row')).not.toBeNull();
    expect(getEl(r.fixture).querySelector('app-book-form')).toBeNull();
  });

  it('Save flow calls BooksService.update and returns to display mode with the new title', async () => {
    const r = await renderRow(mkBook({ id: 7, title: 'Dune', pages: 688, status: 'to-read' }));
    httpTesting = r.httpTesting;

    getActionButton(r.fixture, 'Edit')?.click();
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    // Modify the title via the inline form's input
    const titleInput = getEl(r.fixture).querySelector(
      'app-book-form input[formcontrolname="title"]',
    ) as HTMLInputElement;
    titleInput.value = 'Dune (revised)';
    titleInput.dispatchEvent(new Event('input'));
    titleInput.dispatchEvent(new Event('change'));
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    // Submit via the form component directly so we can await the Promise
    const formDebug = r.fixture.debugElement.query(By.directive(BookForm));
    expect(formDebug).not.toBeNull();
    const formInstance = formDebug.componentInstance as BookForm;

    const pending = formInstance.onSubmit();
    r.fixture.detectChanges();

    const req = httpTesting.expectOne({ method: 'PATCH', url: '/v1/books/7' });
    expect(req.request.body).toEqual({
      title: 'Dune (revised)',
      pages: 688,
      status: 'to-read',
    });
    const updated = mkBook({
      id: 7,
      title: 'Dune (revised)',
      pages: 688,
      status: 'to-read',
    });
    req.flush(updated);
    await pending;

    // Push the updated book in via the parent input (simulates BookList's signal flow).
    r.fixture.componentRef.setInput('book', updated);
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    expect(r.fixture.componentInstance.editing()).toBe(false);
    expect(getEl(r.fixture).querySelector('.book-row-title')?.textContent?.trim()).toBe(
      'Dune (revised)',
    );
    expect(r.booksService.books()[0].title).toBe('Dune (revised)');
  });

  it('statusChangeFailed from StatusControl populates rowError and renders below the row', async () => {
    const r = await renderRow(mkBook({ id: 1 }));
    httpTesting = r.httpTesting;

    const statusEl = r.fixture.debugElement.query(By.directive(StatusControl));
    expect(statusEl).not.toBeNull();
    (statusEl.componentInstance as StatusControl).statusChangeFailed.emit('boom');
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const el = getEl(r.fixture);
    const errEl = el.querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe('boom');
    expect(r.fixture.componentInstance.rowError()).toBe('boom');
  });

  it('Delete confirm-cancel: no network call, row preserved', async () => {
    const r = await renderRow(mkBook({ id: 9 }));
    httpTesting = r.httpTesting;
    confirmSpy.mockReturnValue(false);

    await r.fixture.componentInstance.onDeleteClick();
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    httpTesting.expectNone('/v1/books/9');
    expect(r.booksService.books().length).toBe(1);
    expect(getEl(r.fixture).querySelector('.book-row')).not.toBeNull();
  });

  it('Delete confirm-OK happy path: BooksService.delete filters the row out on 204', async () => {
    const book = mkBook({ id: 9 });
    const r = await renderRow(book);
    httpTesting = r.httpTesting;
    confirmSpy.mockReturnValue(true);

    const pending = r.fixture.componentInstance.onDeleteClick();
    r.fixture.detectChanges();

    const req = httpTesting.expectOne({ method: 'DELETE', url: '/v1/books/9' });
    req.flush(null, { status: 204, statusText: 'No Content' });
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    expect(r.booksService.books()).toEqual([]);
    expect(confirmSpy).toHaveBeenCalledWith('Delete this book?');
  });

  it('Delete confirm-OK error path: 404 renders rowError with documented copy, row preserved', async () => {
    const r = await renderRow(mkBook({ id: 9 }));
    httpTesting = r.httpTesting;
    confirmSpy.mockReturnValue(true);

    const pending = r.fixture.componentInstance.onDeleteClick();
    r.fixture.detectChanges();

    const req = httpTesting.expectOne('/v1/books/9');
    req.flush(
      { errorCode: 'book_not_found', message: 'not found' },
      { status: 404, statusText: 'Not Found' },
    );
    await pending;
    r.fixture.detectChanges();
    await r.fixture.whenStable();

    const errEl = getEl(r.fixture).querySelector('app-error-message p');
    expect(errEl?.textContent?.trim()).toBe(BOOK_ROW_DELETE_FAILURE_COPY);
    expect(r.fixture.componentInstance.rowError()).toBe(BOOK_ROW_DELETE_FAILURE_COPY);
    // Row not filtered (delete threw)
    expect(r.booksService.books().length).toBe(1);
    expect(getEl(r.fixture).querySelector('.book-row')).not.toBeNull();
  });
});
