import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  signal,
} from '@angular/core';

import { AppError } from '../shared/errors/app-error.types';
import { ErrorMessage } from '../shared/ui/error-message';
import { Book } from './book.types';
import { BookForm } from './book-form';
import { BooksService } from './books-service';
import { EstimateCell } from './estimate-cell';
import { StatusControl } from './status-control';

export const BOOK_ROW_DELETE_CONFIRM_MESSAGE = 'Delete this book?';
export const BOOK_ROW_DELETE_FAILURE_COPY = "Couldn't delete this book — try again.";

/**
 * Renders a single book as an interactive row.
 *
 * Display mode: title + page count + StatusControl + EstimateCell stub +
 * Edit/Delete text-buttons. Edit mode: swaps the row for an inline
 * `<app-book-form variant="edit">` controlled by the local `editing` signal.
 *
 * The component owns:
 *  - `editing` (local UI state — display vs edit)
 *  - `rowError` (row-level inline error copy for delete + status-change failures)
 *
 * It does NOT own the books signal (that's `BooksService`'s job) — `delete`,
 * `update`, and `setStatus` all mutate the books signal via the service, and
 * this row re-renders from the parent BookList's `@for track book.id`.
 */
@Component({
  selector: 'app-book-row',
  imports: [BookForm, StatusControl, EstimateCell, ErrorMessage],
  templateUrl: './book-row.html',
  styleUrl: './book-row.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookRow {
  readonly book = input.required<Book>();

  private readonly booksService = inject(BooksService);

  readonly editing = signal<boolean>(false);
  readonly rowError = signal<string | null>(null);

  onEditClick(): void {
    this.rowError.set(null);
    this.editing.set(true);
  }

  onEditSave(): void {
    // BooksService.update already replaced the row in the books signal; the
    // `book` input on this BookRow updates via signal flow.
    this.editing.set(false);
  }

  onEditCancel(): void {
    this.editing.set(false);
  }

  onStatusChangeFailed(msg: string): void {
    this.rowError.set(msg);
  }

  async onDeleteClick(): Promise<void> {
    this.rowError.set(null);
    if (!window.confirm(BOOK_ROW_DELETE_CONFIRM_MESSAGE)) {
      return; // user cancelled — no network call, no state change
    }
    try {
      await this.booksService.delete(this.book().id);
      // Success — BooksService.delete already filtered the row out of the
      // books signal; this component is unmounted by the parent BookList's
      // @for as a consequence. No further state mutation needed.
    } catch (err) {
      this.rowError.set(this.formatDeleteError(err as AppError));
    }
  }

  /**
   * Map an `AppError` thrown by `BooksService.delete` to user-visible copy.
   *
   * UX-DR12: single inline-error copy for delete failures — no per-kind
   * disambiguation. The `default` branch is an exhaustiveness check: future
   * `AppError` variants will fail the build until mapped here.
   */
  private formatDeleteError(err: AppError): string {
    switch (err.kind) {
      case 'invalid_input':
      case 'book_not_found':
      case 'csrf_invalid':
      case 'forbidden_scope':
      case 'auth_state_invalid':
      case 'network':
      case 'unknown':
      case 'session_expired':
        return BOOK_ROW_DELETE_FAILURE_COPY;
      default: {
        const _exhaustive: never = err;
        return _exhaustive;
      }
    }
  }
}
