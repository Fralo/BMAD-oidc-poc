import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { AppError } from '../shared/errors/app-error.types';
import {
  BOOK_LIST_EMPTY_COPY,
  BOOK_LIST_LOADING_COPY,
  BOOK_LIST_LOAD_ERROR_COPY,
  BookList,
} from './book-list';
import { BooksService } from './books-service';
import { Book } from './book.types';

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

interface BooksServiceStub {
  books: ReturnType<typeof signal<Book[]>>;
  loading: ReturnType<typeof signal<boolean>>;
  loadError: ReturnType<typeof signal<AppError | null>>;
}

function makeBooksServiceStub(): BooksServiceStub {
  return {
    books: signal<Book[]>([]),
    loading: signal<boolean>(false),
    loadError: signal<AppError | null>(null),
  };
}

async function renderBookList(stub: BooksServiceStub) {
  await TestBed.configureTestingModule({
    imports: [BookList],
    providers: [
      provideZonelessChangeDetection(),
      { provide: BooksService, useValue: stub },
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(BookList);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture;
}

describe('BookList', () => {
  it('loading state: renders "Loading…" and nothing else when loading=true and books is empty', async () => {
    const stub = makeBooksServiceStub();
    stub.loading.set(true);

    const fixture = await renderBookList(stub);
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('.book-list-loading')?.textContent?.trim()).toBe(
      BOOK_LIST_LOADING_COPY,
    );
    expect(el.querySelector('.book-list-empty')).toBeNull();
    expect(el.querySelector('.book-list-rows')).toBeNull();
    expect(el.querySelector('app-error-message')).toBeNull();
  });

  it('empty state: renders "No books yet. Add one above." when loading=false and books is empty', async () => {
    const stub = makeBooksServiceStub();

    const fixture = await renderBookList(stub);
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('.book-list-empty')?.textContent?.trim()).toBe(
      BOOK_LIST_EMPTY_COPY,
    );
    expect(el.querySelector('.book-list-loading')).toBeNull();
    expect(el.querySelector('.book-list-rows')).toBeNull();
    expect(el.querySelector('app-error-message')).toBeNull();
  });

  it('populated state: renders one row per book and exposes the title', async () => {
    const stub = makeBooksServiceStub();
    stub.books.set([
      mkBook({ id: 1, title: 'Dune' }),
      mkBook({ id: 2, title: 'Foundation' }),
    ]);

    const fixture = await renderBookList(stub);
    const el = fixture.nativeElement as HTMLElement;

    const items = el.querySelectorAll('.book-list-rows > li');
    expect(items.length).toBe(2);

    const titles = Array.from(el.querySelectorAll('app-book-row .book-row-title')).map(
      (n) => n.textContent?.trim(),
    );
    expect(titles).toEqual(['Dune', 'Foundation']);

    // No competing states rendered
    expect(el.querySelector('.book-list-loading')).toBeNull();
    expect(el.querySelector('.book-list-empty')).toBeNull();
    expect(el.querySelector('app-error-message')).toBeNull();
  });

  it('load-error state: renders ErrorMessage with the documented copy when loadError is non-null', async () => {
    const stub = makeBooksServiceStub();
    stub.loadError.set({ kind: 'network' });

    const fixture = await renderBookList(stub);
    const el = fixture.nativeElement as HTMLElement;

    const msgEl = el.querySelector('app-error-message p');
    expect(msgEl?.textContent?.trim()).toBe(BOOK_LIST_LOAD_ERROR_COPY);
    expect(BOOK_LIST_LOAD_ERROR_COPY).toBe("Couldn't load books — refresh to try again.");

    expect(el.querySelector('.book-list-loading')).toBeNull();
    expect(el.querySelector('.book-list-empty')).toBeNull();
    expect(el.querySelector('.book-list-rows')).toBeNull();
  });

  it('load-error takes precedence over a populated books list', async () => {
    const stub = makeBooksServiceStub();
    stub.books.set([mkBook()]);
    stub.loadError.set({ kind: 'unknown', status: 500 });

    const fixture = await renderBookList(stub);
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('app-error-message p')?.textContent?.trim()).toBe(
      BOOK_LIST_LOAD_ERROR_COPY,
    );
    expect(el.querySelector('.book-list-rows')).toBeNull();
  });
});
