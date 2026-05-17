import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal, WritableSignal } from '@angular/core';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppError } from '../shared/errors/app-error.types';
import { ReadingSpeedService } from './reading-speed-service';
import { SettingsPage } from './settings-page';

/**
 * Minimal mock surface of ReadingSpeedService — exposes the same signals
 * (writable inside the test) and method spies the component consumes.
 */
interface MockSpeedService {
  pagesPerHour: WritableSignal<number | null>;
  loading: WritableSignal<boolean>;
  loadError: WritableSignal<AppError | null>;
  saving: WritableSignal<boolean>;
  saveError: WritableSignal<AppError | null>;
  justSaved: WritableSignal<boolean>;
  load: ReturnType<typeof vi.fn>;
  save: ReturnType<typeof vi.fn>;
}

function buildMockService(): MockSpeedService {
  return {
    pagesPerHour: signal<number | null>(null),
    loading: signal<boolean>(false),
    loadError: signal<AppError | null>(null),
    saving: signal<boolean>(false),
    saveError: signal<AppError | null>(null),
    justSaved: signal<boolean>(false),
    load: vi.fn().mockResolvedValue(undefined),
    save: vi.fn().mockResolvedValue(undefined),
  };
}

async function flush(fixture: ComponentFixture<SettingsPage>): Promise<void> {
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('SettingsPage', () => {
  let mock: MockSpeedService;
  let fixture: ComponentFixture<SettingsPage>;

  function setupComponent(): ComponentFixture<SettingsPage> {
    TestBed.configureTestingModule({
      imports: [SettingsPage],
      providers: [{ provide: ReadingSpeedService, useValue: mock }],
    });
    return TestBed.createComponent(SettingsPage);
  }

  beforeEach(() => {
    mock = buildMockService();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ---------------------------------------------------------------------------
  // Render states
  // ---------------------------------------------------------------------------

  it('Loading state — input + button disabled, button label "Save"', async () => {
    mock.loading.set(true);
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    const btn = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(input.disabled).toBe(true);
    expect(btn.disabled).toBe(true);
    expect(btn.textContent?.trim()).toBe('Save');
  });

  it('Loaded with value — input populated, helper visible, no ErrorMessage', async () => {
    mock.pagesPerHour.set(30);
    mock.loadError.set(null);
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.value).toBe('30');
    const helper = fixture.nativeElement.querySelector('.settings-helper');
    expect(helper?.textContent).toContain('e.g., 30');
    expect(fixture.nativeElement.querySelector('app-error-message')).toBeNull();
  });

  it('Unset (412) — input empty, helper visible, NO ErrorMessage', async () => {
    mock.pagesPerHour.set(null);
    mock.loadError.set(null);
    mock.loading.set(false);
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(input.value).toBe('');
    expect(fixture.nativeElement.querySelector('app-error-message')).toBeNull();
  });

  it('Load-error 503 — inline ErrorMessage with the UX-DR12 copy', async () => {
    mock.loadError.set({ kind: 'resource_server_unavailable' });
    fixture = setupComponent();
    await flush(fixture);
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg).not.toBeNull();
    expect(msg?.textContent).toContain('Service unavailable — try again shortly');
  });

  // ---------------------------------------------------------------------------
  // Validation
  // ---------------------------------------------------------------------------

  it('Validation: empty input on submit — inline error, save NOT called', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg?.textContent).toContain('Enter a positive number');
    expect(mock.save).not.toHaveBeenCalled();
  });

  it('Validation: zero — inline error, save NOT called', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '0';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg?.textContent).toContain('Enter a positive number');
    expect(mock.save).not.toHaveBeenCalled();
  });

  it('Validation: negative — inline error, save NOT called', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '-5';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg?.textContent).toContain('Enter a positive number');
    expect(mock.save).not.toHaveBeenCalled();
  });

  it('Validation: non-numeric — inline error, save NOT called', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = 'abc';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg?.textContent).toContain('Enter a positive number');
    expect(mock.save).not.toHaveBeenCalled();
  });

  it('Validation runs on submit only (not on blur, per UX-DR15)', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '0';
    input.dispatchEvent(new Event('input'));
    input.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    // No submit → no validation error rendered.
    expect(fixture.nativeElement.querySelector('app-error-message')).toBeNull();
  });

  // ---------------------------------------------------------------------------
  // Save success / error paths
  // ---------------------------------------------------------------------------

  it('Submit valid value calls save(value) with parsed integer', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '30';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    expect(mock.save).toHaveBeenCalledTimes(1);
    expect(mock.save).toHaveBeenCalledWith(30);
  });

  it('Save success: button progresses Save → Saving… → Saved → Save', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const btn = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(btn.textContent?.trim()).toBe('Save');
    // Simulate the service mid-save.
    mock.saving.set(true);
    fixture.detectChanges();
    expect(btn.textContent?.trim()).toBe('Saving…');
    // Simulate the save completing.
    mock.saving.set(false);
    mock.justSaved.set(true);
    mock.pagesPerHour.set(45);
    fixture.detectChanges();
    expect(btn.textContent?.trim()).toBe('Saved');
    // After the 1s pulse.
    mock.justSaved.set(false);
    fixture.detectChanges();
    expect(btn.textContent?.trim()).toBe('Save');
  });

  it('Save error 503: ErrorMessage with UX-DR12 copy, button restored', async () => {
    fixture = setupComponent();
    await flush(fixture);
    mock.saveError.set({ kind: 'resource_server_unavailable' });
    fixture.detectChanges();
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg?.textContent).toContain('Service unavailable — try again shortly');
    const btn = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(btn.textContent?.trim()).toBe('Save');
  });

  it('Save error 422: ErrorMessage "Enter a positive number"', async () => {
    fixture = setupComponent();
    await flush(fixture);
    mock.saveError.set({ kind: 'invalid_input' });
    fixture.detectChanges();
    const msg = fixture.nativeElement.querySelector('app-error-message');
    expect(msg?.textContent).toContain('Enter a positive number');
  });

  // ---------------------------------------------------------------------------
  // ngOnInit calls load()
  // ---------------------------------------------------------------------------

  it('Component invokes load() exactly once on init', async () => {
    fixture = setupComponent();
    await flush(fixture);
    expect(mock.load).toHaveBeenCalledTimes(1);
  });

  it('Submit via Enter key dispatches the same submit handler', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '30';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    // Native form submit (Enter key triggers this in browsers).
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    expect(mock.save).toHaveBeenCalledWith(30);
  });

  it('Input preserves entered value on validation failure', async () => {
    fixture = setupComponent();
    await flush(fixture);
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '0';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', { cancelable: true }));
    await flush(fixture);
    // Re-read the input — entered value preserved.
    const inputAfter = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    expect(inputAfter.value).toBe('0');
  });
});
