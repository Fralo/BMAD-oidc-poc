import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { AppError } from '../shared/errors/app-error.types';
import { BookListPage } from './book-list-page';
import { BooksService } from './books-service';
import { Book } from './book.types';

function makeBooksServiceStub() {
  const books = signal<Book[]>([]);
  const loading = signal<boolean>(false);
  const loadError = signal<AppError | null>(null);
  const load = vi.fn().mockResolvedValue(undefined);
  return { books, loading, loadError, load };
}

describe('BookListPage', () => {
  it('calls BooksService.load() once on init', async () => {
    const stub = makeBooksServiceStub();
    await TestBed.configureTestingModule({
      imports: [BookListPage],
      providers: [
        provideZonelessChangeDetection(),
        { provide: BooksService, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(BookListPage);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(stub.load).toHaveBeenCalledTimes(1);
  });

  it('renders the heading, the add form, and the book list', async () => {
    const stub = makeBooksServiceStub();
    await TestBed.configureTestingModule({
      imports: [BookListPage],
      providers: [
        provideZonelessChangeDetection(),
        { provide: BooksService, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(BookListPage);
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h1')?.textContent?.trim()).toBe('Books');

    const form = el.querySelector('app-book-form');
    expect(form).not.toBeNull();
    expect(form?.getAttribute('variant')).toBe('add');

    expect(el.querySelector('app-book-list')).not.toBeNull();
  });
});
