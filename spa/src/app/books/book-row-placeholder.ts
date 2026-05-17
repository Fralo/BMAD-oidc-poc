import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { Book } from './book.types';

@Component({
  selector: 'app-book-row-placeholder',
  templateUrl: './book-row-placeholder.html',
  styleUrl: './book-row-placeholder.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookRowPlaceholder {
  readonly book = input.required<Book>();
}
