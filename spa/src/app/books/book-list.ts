import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ErrorMessage } from '../shared/ui/error-message';
import { BookRow } from './book-row';
import { BooksService } from './books-service';

export const BOOK_LIST_LOAD_ERROR_COPY = "Couldn't load books — refresh to try again.";
export const BOOK_LIST_EMPTY_COPY = 'No books yet. Add one above.';
export const BOOK_LIST_LOADING_COPY = 'Loading…';

@Component({
  selector: 'app-book-list',
  imports: [BookRow, ErrorMessage],
  templateUrl: './book-list.html',
  styleUrl: './book-list.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookList {
  private readonly booksService = inject(BooksService);

  readonly books = this.booksService.books;
  readonly loading = this.booksService.loading;
  readonly loadError = this.booksService.loadError;

  readonly loadErrorCopy = BOOK_LIST_LOAD_ERROR_COPY;
  readonly emptyCopy = BOOK_LIST_EMPTY_COPY;
  readonly loadingCopy = BOOK_LIST_LOADING_COPY;
}
