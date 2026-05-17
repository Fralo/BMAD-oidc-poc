import { provideHttpClient, withFetch } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import {
  ESTIMATE_CELL_GENERIC_COPY,
  ESTIMATE_CELL_IDLE_LABEL,
  ESTIMATE_CELL_J6_COPY,
  ESTIMATE_CELL_LOADING_LABEL,
  ESTIMATE_CELL_REESTIMATE_LABEL,
  EstimateCell,
} from './estimate-cell';

/**
 * Minimal stub component for the `/settings` route — exercised when the
 * `reading_speed_unset` variant renders its `<a routerLink="/settings">`.
 * We only need RouterLink resolution to succeed; we never navigate.
 */
@Component({ standalone: true, template: '' })
class SettingsRouteStub {}

const BOOK_ID = 1;

interface Harness {
  fixture: ComponentFixture<EstimateCell>;
  httpTesting: HttpTestingController;
  el: HTMLElement;
}

async function setup(bookId = BOOK_ID, pages = 100): Promise<Harness> {
  await TestBed.configureTestingModule({
    imports: [EstimateCell],
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withFetch()),
      provideHttpClientTesting(),
      provideRouter([{ path: 'settings', component: SettingsRouteStub }]),
    ],
  }).compileComponents();

  const fixture = TestBed.createComponent(EstimateCell);
  fixture.componentRef.setInput('bookId', bookId);
  fixture.componentRef.setInput('pages', pages);
  fixture.detectChanges();
  await fixture.whenStable();

  const httpTesting = TestBed.inject(HttpTestingController);
  return {
    fixture,
    httpTesting,
    el: fixture.nativeElement as HTMLElement,
  };
}

/**
 * Invoke the component's click handler directly so we can `await` the
 * returned Promise and assert post-resolve DOM. Mirrors the
 * `status-control.spec.ts` precedent of calling `componentInstance.onChange()`
 * — needed because raw `button.click()` doesn't surface the async pending
 * Promise that resolves with the HTTP round-trip.
 */
function click(fixture: ComponentFixture<EstimateCell>): Promise<void> {
  return fixture.componentInstance.onEstimateClick();
}

describe('EstimateCell', () => {
  let harness: Harness;

  afterEach(() => {
    harness?.httpTesting.verify();
  });

  // --- 1. Idle state ----------------------------------------------------
  it('idle: renders a single enabled "Estimate" primary button, no error, no result', async () => {
    harness = await setup();
    const { el } = harness;

    const buttons = el.querySelectorAll('button');
    expect(buttons.length).toBe(1);
    const btn = buttons[0] as HTMLButtonElement;
    expect(btn.textContent?.trim()).toBe(ESTIMATE_CELL_IDLE_LABEL);
    expect(btn.disabled).toBe(false);
    expect(btn.classList.contains('estimate-cell-button--primary')).toBe(true);
    // No error visible
    expect(el.querySelector('app-error-message')).toBeNull();
    expect(el.querySelector('.estimate-cell-error')).toBeNull();
    // No result rendered
    expect(el.querySelector('.estimate-cell-result')).toBeNull();
    // No fabricated ≈ on idle
    expect(el.textContent ?? '').not.toContain('≈');
  });

  // --- 2. Loading state -------------------------------------------------
  it('loading: clicking Estimate immediately disables the button, relabels to "Estimating…", and fires POST /v1/books/1/estimate with body {}', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    const pending = click(fixture);
    fixture.detectChanges();

    // Loading-state DOM assertions BEFORE flushing.
    const btn = el.querySelector('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.textContent?.trim()).toBe(ESTIMATE_CELL_LOADING_LABEL);

    const req = httpTesting.expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` });
    expect(req.request.body).toEqual({});
    // Flush something terminal so afterEach's verify() doesn't trip.
    req.flush({ minutes: 1, formatted: '≈ 1 m' });
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();
  });

  // --- 3. Success state -------------------------------------------------
  it('success: replaces the button with the formatted text (verbatim) and a Re-estimate button', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    const pending = click(fixture);
    fixture.detectChanges();

    httpTesting
      .expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` })
      .flush({ minutes: 260, formatted: '≈ 4 h 20 m' });
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();

    // Formatted text rendered verbatim (verbatim including U+2248 ≈).
    const result = el.querySelector('.estimate-cell-result');
    expect(result).not.toBeNull();
    expect(result?.textContent?.trim()).toBe('≈ 4 h 20 m');

    // Re-estimate button present, primary Estimate button gone.
    const reestimate = el.querySelector('button.estimate-cell-reestimate') as HTMLButtonElement | null;
    expect(reestimate).not.toBeNull();
    expect(reestimate?.textContent?.trim()).toBe(ESTIMATE_CELL_REESTIMATE_LABEL);
    expect(el.querySelector('button.estimate-cell-button--primary')).toBeNull();

    // No error rendered in success state.
    expect(el.querySelector('app-error-message')).toBeNull();
    expect(el.querySelector('.estimate-cell-error')).toBeNull();
  });

  // --- 4. Re-estimate replaces value in place ---------------------------
  it('re-estimate: clicking Re-estimate fires a second POST and replaces the formatted text in place', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    // First round-trip → success.
    let pending = click(fixture);
    fixture.detectChanges();
    httpTesting
      .expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` })
      .flush({ minutes: 260, formatted: '≈ 4 h 20 m' });
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();
    expect(el.querySelector('.estimate-cell-result')?.textContent?.trim()).toBe('≈ 4 h 20 m');

    // Click Re-estimate via the same handler.
    pending = click(fixture);
    fixture.detectChanges();
    // Second request fires.
    const req = httpTesting.expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` });
    expect(req.request.body).toEqual({});
    req.flush({ minutes: 130, formatted: '≈ 2 h 10 m' });
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();

    // New value in place, old value gone.
    expect(el.querySelector('.estimate-cell-result')?.textContent?.trim()).toBe('≈ 2 h 10 m');
    expect(el.textContent ?? '').not.toContain('≈ 4 h 20 m');
    // Re-estimate button still present.
    expect(el.querySelector('button.estimate-cell-reestimate')).not.toBeNull();
  });

  // --- 5. reading_speed_unset (J3 freshuser precondition) ---------------
  it('reading_speed_unset (412): renders the link copy with RouterLink to /settings and restores the Estimate button', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    const pending = click(fixture);
    fixture.detectChanges();
    httpTesting
      .expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` })
      .flush(
        { errorCode: 'reading_speed_unset', message: 'unset', detail: null },
        { status: 412, statusText: 'Precondition Failed' },
      );
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();

    // Literal copy present.
    const errorP = el.querySelector('p.estimate-cell-error');
    expect(errorP).not.toBeNull();
    const normalized = (errorP?.textContent ?? '').replace(/\s+/g, ' ').trim();
    expect(normalized).toBe('Set your reading speed in Settings to enable estimates');

    // `Settings` is a link to /settings.
    const link = errorP?.querySelector('a') as HTMLAnchorElement | null;
    expect(link).not.toBeNull();
    expect(link?.textContent?.trim()).toBe('Settings');
    // Either the RouterLink-set href or the routerLink attribute is sufficient.
    const href = link?.getAttribute('href');
    const routerLinkAttr = link?.getAttribute('ng-reflect-router-link') ?? link?.getAttribute('routerLink');
    const settingsResolved = (href ?? '').endsWith('/settings') || routerLinkAttr === '/settings';
    expect(settingsResolved).toBe(true);

    // Estimate button restored.
    const btn = el.querySelector('button.estimate-cell-button--primary') as HTMLButtonElement | null;
    expect(btn).not.toBeNull();
    expect(btn?.textContent?.trim()).toBe(ESTIMATE_CELL_IDLE_LABEL);
    expect(btn?.disabled).toBe(false);

    // No shared <app-error-message> in this variant (inline markup only).
    expect(el.querySelector('app-error-message')).toBeNull();
    // No fabricated ≈ in failure state.
    expect(el.textContent ?? '').not.toContain('≈');
  });

  // --- 6. resource_server_unavailable (J6) ------------------------------
  it('resource_server_unavailable (503): renders the J6 copy via <app-error-message>, restores the Estimate button, NO fabricated duration', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    const pending = click(fixture);
    fixture.detectChanges();
    httpTesting
      .expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` })
      .flush(
        { errorCode: 'resource_server_unavailable', message: 'rs down' },
        { status: 503, statusText: 'Service Unavailable' },
      );
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();

    const errorEl = el.querySelector('app-error-message');
    expect(errorEl).not.toBeNull();
    expect(errorEl?.textContent?.trim()).toBe(ESTIMATE_CELL_J6_COPY);

    // Estimate button restored.
    const btn = el.querySelector('button.estimate-cell-button--primary') as HTMLButtonElement | null;
    expect(btn).not.toBeNull();
    expect(btn?.textContent?.trim()).toBe(ESTIMATE_CELL_IDLE_LABEL);

    // No fabricated ≈ duration anywhere in the DOM — J6 must NEVER show a value.
    expect(el.textContent ?? '').not.toContain('≈');
    expect(el.querySelector('.estimate-cell-result')).toBeNull();
  });

  // --- 7. Generic error -------------------------------------------------
  it('generic error (500 unknown): renders the generic copy via <app-error-message> and restores the Estimate button', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    const pending = click(fixture);
    fixture.detectChanges();
    httpTesting
      .expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` })
      .flush(
        { errorCode: 'unknown', message: 'boom' },
        { status: 500, statusText: 'Server Error' },
      );
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();

    const errorEl = el.querySelector('app-error-message');
    expect(errorEl).not.toBeNull();
    expect(errorEl?.textContent?.trim()).toBe(ESTIMATE_CELL_GENERIC_COPY);

    // Estimate button restored.
    const btn = el.querySelector('button.estimate-cell-button--primary') as HTMLButtonElement | null;
    expect(btn).not.toBeNull();
    expect(btn?.textContent?.trim()).toBe(ESTIMATE_CELL_IDLE_LABEL);
  });

  // --- 8. 404 book_not_found — generic copy (pins the J6 copy reservation)
  it('book_not_found (404): renders the GENERIC copy (NOT the J6 copy) and restores the Estimate button', async () => {
    harness = await setup();
    const { el, fixture, httpTesting } = harness;

    const pending = click(fixture);
    fixture.detectChanges();
    httpTesting
      .expectOne({ method: 'POST', url: `/v1/books/${BOOK_ID}/estimate` })
      .flush(
        { errorCode: 'book_not_found', message: 'gone' },
        { status: 404, statusText: 'Not Found' },
      );
    await pending;
    fixture.detectChanges();
    await fixture.whenStable();

    const errorEl = el.querySelector('app-error-message');
    expect(errorEl).not.toBeNull();
    // Generic, not J6 — pins that J6 copy is reserved for resource_server_unavailable.
    expect(errorEl?.textContent?.trim()).toBe(ESTIMATE_CELL_GENERIC_COPY);
    expect(errorEl?.textContent?.trim()).not.toBe(ESTIMATE_CELL_J6_COPY);

    // Estimate button restored.
    expect(el.querySelector('button.estimate-cell-button--primary')).not.toBeNull();
  });
});
