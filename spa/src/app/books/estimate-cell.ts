import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { AppError } from '../shared/errors/app-error.types';
import { ErrorMessage } from '../shared/ui/error-message';
import { BooksService } from './books-service';
import { EstimateOut } from './estimate.types';

/**
 * Failure copy strings — exported so the spec can import them without
 * depending on copy churn. Mirrors the `BOOK_ROW_DELETE_FAILURE_COPY`
 * precedent in `book-row.ts`.
 *
 * Punctuation notes (UX-DR — verbatim):
 *   - U+2014 EM DASH (—) between clauses in the J6 and generic copy.
 *   - U+2019 RIGHT SINGLE QUOTATION MARK (’) in "Couldn’t".
 *   - U+2026 HORIZONTAL ELLIPSIS (…) in "Estimating…".
 *   - U+2248 ALMOST EQUAL TO (≈) is in the formatted value from the wire,
 *     not in any copy string here.
 */
export const ESTIMATE_CELL_J6_COPY = 'Service unavailable — try again shortly';
export const ESTIMATE_CELL_GENERIC_COPY = 'Couldn’t get an estimate — try again';
/** Prefix shown before the `Settings` link when reading speed is unset. */
export const ESTIMATE_CELL_PRECONDITION_PREFIX = 'Set your reading speed in';
/** Suffix shown after the `Settings` link when reading speed is unset. */
export const ESTIMATE_CELL_PRECONDITION_SUFFIX = 'to enable estimates';
/** Button labels — exported for spec resilience. */
export const ESTIMATE_CELL_IDLE_LABEL = 'Estimate';
export const ESTIMATE_CELL_LOADING_LABEL = 'Estimating…';
export const ESTIMATE_CELL_REESTIMATE_LABEL = 'Re-estimate';

/**
 * Inline cell that requests a cross-service reading-time estimate for a book.
 *
 * State machine: `idle` → `loading` → (`success` | `error`).
 * `success` → `loading` (Re-estimate) → ... `error` → `idle` (button restored
 * beneath the inline error so the user can retry manually).
 *
 * Pessimistic UI: no spinner overlay, no skeleton, no animation — the button
 * is relabelled to `Estimating…` and disabled while a round-trip is in flight
 * (UX-DR11 / UX-DR13 + architecture §"Process Patterns / Loading state UI").
 *
 * No auto-retry / no polling on `resource_server_unavailable` (J6) — user
 * retries manually by clicking the restored `Estimate` button (UX §"Failure
 * recovery" + architecture §"Process Patterns / Retry & failure").
 *
 * Component state is component-local — the result is NOT stored on the
 * `BooksService` signal. Each `EstimateCell` instance is responsible for its
 * own `loading` / `result` / `error` triple.
 */
@Component({
  selector: 'app-estimate-cell',
  imports: [RouterLink, ErrorMessage],
  templateUrl: './estimate-cell.html',
  styleUrl: './estimate-cell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EstimateCell {
  readonly bookId = input.required<number>();
  // kept for BookRow binding stability; BFF reads pages from the server-side
  // books row, so the value is unused at runtime in this component.
  readonly pages = input.required<number>();

  private readonly booksService = inject(BooksService);

  readonly loading = signal<boolean>(false);
  readonly result = signal<EstimateOut | null>(null);
  readonly error = signal<AppError | null>(null);

  /**
   * User-visible copy for the current `error()` value (idle/loading/success
   * states return empty string). Used by the template's `<app-error-message>`
   * binding for the J6 + generic variants — the `reading_speed_unset` variant
   * is rendered via inline markup instead because `<app-error-message>` does
   * not support content projection (and we MUST NOT extend it — see AC9).
   */
  errorCopy(): string {
    const err = this.error();
    if (err === null) {
      return '';
    }
    return this.formatEstimateError(err);
  }

  async onEstimateClick(): Promise<void> {
    // One round-trip at a time. Clear any prior result/error so stale state
    // doesn't bleed through the loading view.
    this.loading.set(true);
    this.result.set(null);
    this.error.set(null);
    try {
      const out = await this.booksService.requestEstimate(this.bookId());
      this.result.set(out);
    } catch (err) {
      this.error.set(err as AppError);
    } finally {
      this.loading.set(false);
    }
  }

  /**
   * Map an `AppError` thrown by `BooksService.requestEstimate` to user-visible
   * copy.
   *
   * The `reading_speed_unset` branch returns the empty string because that
   * variant is rendered via inline markup in the template (it needs an
   * embedded `RouterLink` to `/settings` which `<app-error-message>` cannot
   * project). The `session_expired` branch is defensively mapped to the
   * generic copy — at runtime the global `withCredentialsInterceptor`
   * (Story 1.9) redirects to `/auth/login?return_to=...` before the rejection
   * reaches this component, so the branch is effectively dead, but typed
   * exhaustiveness requires it.
   *
   * The `default` branch is an exhaustiveness check: if a future `AppError`
   * variant is added without updating this switch, TypeScript fails to
   * assign the new kind to `never` and the build breaks (mirrors the
   * `book-row.ts` / `book-form.ts` / `status-control.ts` precedent).
   */
  private formatEstimateError(err: AppError): string {
    switch (err.kind) {
      case 'reading_speed_unset':
        // Rendered via inline link template — see template `@if e.kind === 'reading_speed_unset'`.
        return '';
      case 'resource_server_unavailable':
        return ESTIMATE_CELL_J6_COPY;
      case 'invalid_input':
      case 'forbidden_scope':
      case 'csrf_invalid':
      case 'book_not_found':
      case 'auth_state_invalid':
      case 'network':
      case 'unknown':
      case 'session_expired':
        return ESTIMATE_CELL_GENERIC_COPY;
      default: {
        const _exhaustive: never = err;
        return _exhaustive;
      }
    }
  }
}
