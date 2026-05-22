import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, Signal, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { AppError } from '../shared/errors/app-error.types';
import { ErrorService } from '../shared/errors/error-service';
import { ReadingSpeedOut } from './reading-speed.types';

/**
 * SPA service for the J4 reading-speed feature (Story 3.5).
 *
 * Reactive state via Angular signals:
 *  - `pagesPerHour` — `null` is the legitimate "unset" state (412 from the RS).
 *  - `loading` / `loadError` — GET cycle.
 *  - `saving` / `saveError` / `justSaved` — PUT cycle. `justSaved` pulses
 *    `true` for ~1s after a successful save (UX-DR9 / UX-DR11 — the only
 *    success acknowledgement permitted anywhere in the SPA).
 *
 * 401 handling is delegated to the global `withCredentialsInterceptor`
 * (Story 1.9) — this service's catch blocks for 401 just reset
 * `loading` / `saving` and return silently while the interceptor navigates
 * to `/auth/login?return_to=...`.
 */
const READING_SPEED_URL = '/v1/reading-speed';
const JUST_SAVED_PULSE_MS = 1000;

@Injectable({ providedIn: 'root' })
export class ReadingSpeedService {
  private readonly http = inject(HttpClient);
  private readonly errorService = inject(ErrorService);

  private readonly _pagesPerHour = signal<number | null>(null);
  private readonly _loading = signal<boolean>(false);
  private readonly _loadError = signal<AppError | null>(null);
  private readonly _saving = signal<boolean>(false);
  private readonly _saveError = signal<AppError | null>(null);
  private readonly _justSaved = signal<boolean>(false);

  // CR6: outstanding `_justSaved` pulse timer. Cancelled before scheduling
  // a new one so two saves within 1s don't overlap (the first timer's
  // `set(false)` would otherwise clobber the second save's pulse).
  private _justSavedTimer: ReturnType<typeof setTimeout> | null = null;

  readonly pagesPerHour: Signal<number | null> = this._pagesPerHour.asReadonly();
  readonly loading: Signal<boolean> = this._loading.asReadonly();
  readonly loadError: Signal<AppError | null> = this._loadError.asReadonly();
  readonly saving: Signal<boolean> = this._saving.asReadonly();
  readonly saveError: Signal<AppError | null> = this._saveError.asReadonly();
  readonly justSaved: Signal<boolean> = this._justSaved.asReadonly();

  async load(): Promise<void> {
    this._loading.set(true);
    this._loadError.set(null);
    try {
      const response = await firstValueFrom(
        this.http.get<ReadingSpeedOut>(READING_SPEED_URL),
      );
      this._pagesPerHour.set(response.pages_per_hour);
    } catch (err) {
      if (err instanceof HttpErrorResponse && err.status === 412) {
        // 412 unset is the first-time-user happy-path; not a load error.
        this._pagesPerHour.set(null);
        this._loadError.set(null);
        return;
      }
      if (err instanceof HttpErrorResponse && err.status === 401) {
        // Global handler owns the /login navigation.
        return;
      }
      this._pagesPerHour.set(null);
      this._loadError.set(this.errorService.parse(err));
    } finally {
      this._loading.set(false);
    }
  }

  async save(value: number): Promise<void> {
    this._saving.set(true);
    this._saveError.set(null);
    try {
      const response = await firstValueFrom(
        this.http.put<ReadingSpeedOut>(READING_SPEED_URL, { pages_per_hour: value }),
      );
      this._pagesPerHour.set(response.pages_per_hour);
      this._justSaved.set(true);
      if (this._justSavedTimer !== null) {
        clearTimeout(this._justSavedTimer);
      }
      this._justSavedTimer = setTimeout(() => {
        this._justSaved.set(false);
        this._justSavedTimer = null;
      }, JUST_SAVED_PULSE_MS);
    } catch (err) {
      if (err instanceof HttpErrorResponse && err.status === 401) {
        return;
      }
      this._saveError.set(this.errorService.parse(err));
    } finally {
      this._saving.set(false);
    }
  }
}
