import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  OnInit,
  signal,
} from '@angular/core';

import { ErrorMessage } from '../shared/ui/error-message';
import { ReadingSpeedService } from './reading-speed-service';

/**
 * J4 SettingsView (Story 3.5).
 *
 * Replaces the Story 1.10 placeholder. Renders the reading-speed editor per
 * UX-DR9 / UX-DR11 / UX-DR15:
 *  - Section heading + labelled native number input + helper text + Save button.
 *  - Validation runs on submit only (UX-DR15 — never on blur).
 *  - Success briefly relabels the button to "Saved" (~1s pulse — the only
 *    success acknowledgement permitted anywhere in the SPA, per UX-DR11).
 *  - Inline ErrorMessage for 503 / 422 / validation failures (UX-DR12 copy).
 *  - 412 (no value yet) is NOT an error from the user's POV — the helper
 *    text is the cue.
 */
@Component({
  selector: 'app-settings-page',
  imports: [ErrorMessage],
  templateUrl: './settings-page.html',
  styleUrl: './settings-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPage implements OnInit {
  private readonly speedService = inject(ReadingSpeedService);

  readonly loading = this.speedService.loading;
  readonly saving = this.speedService.saving;
  readonly loadError = this.speedService.loadError;
  readonly saveError = this.speedService.saveError;
  readonly justSaved = this.speedService.justSaved;

  private readonly _inputValue = signal<string>('');
  readonly inputValue = this._inputValue.asReadonly();

  private readonly _validationError = signal<string | null>(null);
  readonly validationError = this._validationError.asReadonly();

  readonly saveButtonLabel = computed(() => {
    if (this.justSaved()) return 'Saved';
    if (this.saving()) return 'Saving…';
    return 'Save';
  });

  /**
   * Surface the load-error message string for the template (only the
   * resource_server_unavailable kind has a literal copy per UX-DR12 here;
   * other AppError kinds fall back to a generic copy).
   */
  readonly loadErrorMessage = computed<string | null>(() => {
    const err = this.loadError();
    if (!err) return null;
    if (err.kind === 'resource_server_unavailable') {
      return 'Service unavailable — try again shortly';
    }
    return null; // Other load-error kinds are not currently surfaced here.
  });

  /**
   * Surface the save-error message string for the template.
   * - resource_server_unavailable → "Service unavailable — try again shortly"
   * - invalid_input → "Enter a positive number" (the only ge=1 violation
   *   the RS can return on this endpoint per Story 3.3)
   * - anything else → generic "Couldn't save — try again"
   */
  readonly saveErrorMessage = computed<string | null>(() => {
    const err = this.saveError();
    if (!err) return null;
    if (err.kind === 'resource_server_unavailable') {
      return 'Service unavailable — try again shortly';
    }
    if (err.kind === 'invalid_input') {
      return 'Enter a positive number';
    }
    return "Couldn't save — try again";
  });

  // Tracks whether the user has typed into the input. While false, the
  // effect below synchronizes the input value from `pagesPerHour()` (so
  // the loaded value populates the field on first paint). Once the user
  // edits, the effect stops clobbering their input.
  private _userEdited = false;

  constructor() {
    effect(() => {
      const current = this.speedService.pagesPerHour();
      if (this._userEdited) return;
      this._inputValue.set(current === null ? '' : String(current));
    });
  }

  async ngOnInit(): Promise<void> {
    await this.speedService.load();
  }

  onInput(event: Event): void {
    const target = event.target as HTMLInputElement;
    this._inputValue.set(target.value);
    this._userEdited = true;
    this._validationError.set(null);
  }

  async onSubmit(event: Event): Promise<void> {
    event.preventDefault();
    const raw = this._inputValue().trim();
    if (!/^[1-9]\d*$/.test(raw)) {
      this._validationError.set('Enter a positive number');
      return;
    }
    this._validationError.set(null);
    const value = Number.parseInt(raw, 10);
    await this.speedService.save(value);
  }
}
