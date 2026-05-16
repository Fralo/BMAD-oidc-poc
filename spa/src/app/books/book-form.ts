import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  ValidatorFn,
  Validators,
} from '@angular/forms';

import { AppError } from '../shared/errors/app-error.types';
import { ErrorMessage } from '../shared/ui/error-message';
import { BookCreate, BookStatus } from './book.types';
import { BooksService } from './books-service';

export const BOOK_FORM_ADD_BUTTON_IDLE = 'Add book';
export const BOOK_FORM_ADD_BUTTON_SUBMITTING = 'Adding…';

export const BOOK_FORM_VALIDATION_TITLE_REQUIRED = 'Title is required.';
export const BOOK_FORM_VALIDATION_PAGES_REQUIRED = 'Page count is required.';
export const BOOK_FORM_VALIDATION_PAGES_POSITIVE = 'Page count must be a positive number.';
export const BOOK_FORM_VALIDATION_MULTIPLE = 'Please correct the highlighted fields.';

export const BOOK_FORM_SERVER_INVALID_INPUT = 'The server rejected this book. Check the fields and try again.';
export const BOOK_FORM_SERVER_CSRF_INVALID = 'Your session is out of sync. Refresh the page and try again.';
export const BOOK_FORM_SERVER_SESSION_EXPIRED = 'Your session expired. Redirecting to sign in…';
export const BOOK_FORM_SERVER_NETWORK = "Couldn't reach the server. Check your connection and try again.";
export const BOOK_FORM_SERVER_GENERIC = 'Something went wrong. Try again.';

/**
 * Custom validator: rejects empty / whitespace-only strings.
 *
 * Angular's `Validators.required` accepts `"   "` (it only rejects `""`, `null`, `undefined`).
 * The story's AC explicitly lists "empty/whitespace-only title" as an invalid case.
 */
export const nonWhitespaceValidator: ValidatorFn = (
  control: AbstractControl,
): ValidationErrors | null => {
  const value = control.value as string | null | undefined;
  if (value === null || value === undefined || value.trim() === '') {
    return { nonWhitespace: true };
  }
  return null;
};

@Component({
  selector: 'app-book-form',
  imports: [ReactiveFormsModule, ErrorMessage],
  templateUrl: './book-form.html',
  styleUrl: './book-form.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BookForm {
  readonly variant = input.required<'add' | 'edit'>();

  private readonly booksService = inject(BooksService);
  private readonly fb = inject(NonNullableFormBuilder);

  readonly form = this.fb.group({
    title: this.fb.control('', {
      validators: [Validators.required, nonWhitespaceValidator],
    }),
    pages: this.fb.control<number | null>(null, {
      validators: [Validators.required, Validators.min(1)],
    }),
    // Status has a default valid value and the <select> exposes no empty
    // option — Validators.required would be unreachable, so it is omitted.
    status: this.fb.control<BookStatus>('to-read'),
  });

  readonly submitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);

  readonly idleButtonLabel = BOOK_FORM_ADD_BUTTON_IDLE;
  readonly submittingButtonLabel = BOOK_FORM_ADD_BUTTON_SUBMITTING;

  async onSubmit(): Promise<void> {
    if (this.form.invalid) {
      this.errorMessage.set(this.buildValidationMessage());
      return;
    }

    this.errorMessage.set(null);
    this.submitting.set(true);

    const payload: BookCreate = {
      title: this.form.controls.title.value.trim(),
      pages: this.form.controls.pages.value as number,
      status: this.form.controls.status.value,
    };

    try {
      await this.booksService.create(payload);
      // Success — reset to defaults; the books signal in BooksService has already prepended.
      this.form.reset({ title: '', pages: null, status: 'to-read' });
    } catch (err) {
      this.errorMessage.set(this.formatServerError(err as AppError));
      // Inputs preserve values on failure — we only reset on success.
    } finally {
      this.submitting.set(false);
    }
  }

  /** Build inline copy for client-side validation failures. */
  private buildValidationMessage(): string {
    const titleErrors = this.form.controls.title.errors;
    const pagesErrors = this.form.controls.pages.errors;
    const invalidFieldCount =
      (titleErrors ? 1 : 0) + (pagesErrors ? 1 : 0);

    if (invalidFieldCount > 1) {
      return BOOK_FORM_VALIDATION_MULTIPLE;
    }
    if (titleErrors) {
      // Both `required` and `nonWhitespace` map to "Title is required."
      return BOOK_FORM_VALIDATION_TITLE_REQUIRED;
    }
    if (pagesErrors) {
      if (pagesErrors['required']) {
        return BOOK_FORM_VALIDATION_PAGES_REQUIRED;
      }
      // `min` violation (pages <= 0) and any other pages error
      return BOOK_FORM_VALIDATION_PAGES_POSITIVE;
    }
    // Fallback (status invalid — unreachable today since status has a default valid value).
    return BOOK_FORM_VALIDATION_MULTIPLE;
  }

  /**
   * Map an `AppError` thrown by `BooksService.create` to user-visible copy.
   *
   * The `default` branch is an exhaustiveness check: if a future `AppError`
   * variant (e.g., Story 3.5's `resource_server_unavailable`) is added
   * without updating this switch, TypeScript will fail to assign the new
   * kind to `never` and the build breaks.
   */
  private formatServerError(err: AppError): string {
    switch (err.kind) {
      case 'invalid_input':
        return BOOK_FORM_SERVER_INVALID_INPUT;
      case 'csrf_invalid':
        return BOOK_FORM_SERVER_CSRF_INVALID;
      case 'session_expired':
        return BOOK_FORM_SERVER_SESSION_EXPIRED;
      case 'network':
        return BOOK_FORM_SERVER_NETWORK;
      case 'forbidden_scope':
      case 'book_not_found':
      case 'auth_state_invalid':
      case 'unknown':
        return BOOK_FORM_SERVER_GENERIC;
      default: {
        const _exhaustive: never = err;
        return _exhaustive;
      }
    }
  }
}
