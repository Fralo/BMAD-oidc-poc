import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { AppError } from '../shared/errors/app-error.types';
import { BookStatus } from './book.types';
import { BooksService } from './books-service';

export const STATUS_CONTROL_FAILURE_COPY = "Couldn't change status — try again.";

/**
 * Native `<select>` adapter over `BooksService.setStatus`.
 *
 * This component is a dumb adapter — the optimistic update + revert lives in
 * `BooksService.setStatus`. Here we only own:
 *  - the `busy` signal disabling the `<select>` during in-flight PATCH
 *  - the AppError → user-visible copy translation
 *  - the emission of that copy upward so the parent BookRow can surface it
 */
@Component({
  selector: 'app-status-control',
  imports: [],
  templateUrl: './status-control.html',
  styleUrl: './status-control.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusControl {
  readonly bookId = input.required<number>();
  readonly status = input.required<BookStatus>();
  readonly statusChangeFailed = output<string>();

  private readonly booksService = inject(BooksService);

  readonly busy = signal<boolean>(false);

  async onChange(next: BookStatus): Promise<void> {
    if (next === this.status() || this.busy()) {
      return;
    }
    this.busy.set(true);
    try {
      await this.booksService.setStatus(this.bookId(), next);
    } catch (err) {
      // setStatus has already reverted the books signal; surface inline copy upward.
      this.statusChangeFailed.emit(this.formatStatusError(err as AppError));
    } finally {
      this.busy.set(false);
    }
  }

  /**
   * Map an `AppError` thrown by `BooksService.setStatus` to user-visible copy.
   *
   * UX-DR12: single inline-error copy for the binary control — no need to
   * disambiguate by kind. The `default` branch is an exhaustiveness check: if
   * a future `AppError` variant is added without updating this switch,
   * TypeScript will fail to assign the new kind to `never` and the build
   * breaks.
   */
  private formatStatusError(err: AppError): string {
    switch (err.kind) {
      case 'invalid_input':
      case 'book_not_found':
      case 'csrf_invalid':
      case 'forbidden_scope':
      case 'auth_state_invalid':
      case 'network':
      case 'unknown':
      case 'session_expired':
        return STATUS_CONTROL_FAILURE_COPY;
      default: {
        const _exhaustive: never = err;
        return _exhaustive;
      }
    }
  }
}
