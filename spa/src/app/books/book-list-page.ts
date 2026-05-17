import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';

import { BookForm } from './book-form';
import { BookList } from './book-list';
import { BooksService } from './books-service';

@Component({
  selector: 'app-book-list-page',
  imports: [BookForm, BookList],
  templateUrl: './book-list-page.html',
  styleUrl: './book-list-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookListPage implements OnInit {
  private readonly booksService = inject(BooksService);

  ngOnInit(): void {
    void this.booksService.load();
  }
}
