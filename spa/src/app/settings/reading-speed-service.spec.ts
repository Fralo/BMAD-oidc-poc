import { provideHttpClient, withFetch } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ReadingSpeedService } from './reading-speed-service';

describe('ReadingSpeedService', () => {
  let service: ReadingSpeedService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(withFetch()), provideHttpClientTesting()],
    });
    service = TestBed.inject(ReadingSpeedService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    vi.useRealTimers();
  });

  // ---------------------------------------------------------------------------
  // load()
  // ---------------------------------------------------------------------------

  it('load() happy 200 sets pagesPerHour', async () => {
    const pending = service.load();
    httpTesting.expectOne('/v1/reading-speed').flush({ pages_per_hour: 30 });
    await pending;
    expect(service.pagesPerHour()).toBe(30);
    expect(service.loadError()).toBeNull();
    expect(service.loading()).toBe(false);
  });

  it('load() 412 unset state sets pagesPerHour to null and clears loadError', async () => {
    const pending = service.load();
    httpTesting.expectOne('/v1/reading-speed').flush(
      { errorCode: 'reading_speed_unset', message: 'unset', detail: null },
      { status: 412, statusText: 'Precondition Failed' },
    );
    await pending;
    expect(service.pagesPerHour()).toBeNull();
    expect(service.loadError()).toBeNull();
    expect(service.loading()).toBe(false);
  });

  it('load() 503 sets loadError to resource_server_unavailable', async () => {
    const pending = service.load();
    httpTesting.expectOne('/v1/reading-speed').flush(
      { errorCode: 'resource_server_unavailable', message: 'down', detail: null },
      { status: 503, statusText: 'Service Unavailable' },
    );
    await pending;
    expect(service.loadError()).toEqual({ kind: 'resource_server_unavailable' });
    expect(service.pagesPerHour()).toBeNull();
    expect(service.loading()).toBe(false);
  });

  it('load() sets loading=true while pending', () => {
    void service.load();
    expect(service.loading()).toBe(true);
    expect(service.loadError()).toBeNull();
    httpTesting.expectOne('/v1/reading-speed').flush({ pages_per_hour: 30 });
  });

  it('load() 401 is swallowed silently (global handler navigates)', async () => {
    const pending = service.load();
    httpTesting
      .expectOne('/v1/reading-speed')
      .flush(null, { status: 401, statusText: 'Unauthorized' });
    await pending;
    expect(service.loading()).toBe(false);
    expect(service.loadError()).toBeNull();
  });

  it('load() GET method + relative URL', () => {
    void service.load();
    const req = httpTesting.expectOne('/v1/reading-speed');
    expect(req.request.method).toBe('GET');
    expect(req.request.url).toBe('/v1/reading-speed');
    req.flush({ pages_per_hour: 30 });
  });

  // ---------------------------------------------------------------------------
  // save()
  // ---------------------------------------------------------------------------

  it('save() happy 200 sets pagesPerHour and pulses justSaved', async () => {
    vi.useFakeTimers();
    const pending = service.save(45);
    const req = httpTesting.expectOne('/v1/reading-speed');
    req.flush({ pages_per_hour: 45 });
    await pending;
    expect(service.pagesPerHour()).toBe(45);
    expect(service.justSaved()).toBe(true);
    expect(service.saving()).toBe(false);
    vi.advanceTimersByTime(1100);
    expect(service.justSaved()).toBe(false);
  });

  it('save() 422 sets saveError to invalid_input', async () => {
    const pending = service.save(0);
    httpTesting.expectOne('/v1/reading-speed').flush(
      { errorCode: 'invalid_input', message: 'bad', detail: [{ loc: ['x'] }] },
      { status: 422, statusText: 'Unprocessable' },
    );
    await pending;
    const err = service.saveError();
    expect(err?.kind).toBe('invalid_input');
    expect(service.saving()).toBe(false);
  });

  it('save() 503 sets saveError to resource_server_unavailable', async () => {
    const pending = service.save(30);
    httpTesting.expectOne('/v1/reading-speed').flush(
      { errorCode: 'resource_server_unavailable', message: 'down', detail: null },
      { status: 503, statusText: 'Service Unavailable' },
    );
    await pending;
    expect(service.saveError()).toEqual({ kind: 'resource_server_unavailable' });
    expect(service.saving()).toBe(false);
  });

  it('save() 401 is swallowed silently', async () => {
    const pending = service.save(30);
    httpTesting
      .expectOne('/v1/reading-speed')
      .flush(null, { status: 401, statusText: 'Unauthorized' });
    await pending;
    expect(service.saving()).toBe(false);
    expect(service.saveError()).toBeNull();
  });

  it('save() body shape is { pages_per_hour: <value> }', () => {
    void service.save(42);
    const req = httpTesting.expectOne('/v1/reading-speed');
    expect(req.request.body).toEqual({ pages_per_hour: 42 });
    req.flush({ pages_per_hour: 42 });
  });

  it('save() PUT method', () => {
    void service.save(42);
    const req = httpTesting.expectOne('/v1/reading-speed');
    expect(req.request.method).toBe('PUT');
    req.flush({ pages_per_hour: 42 });
  });

  it('save() justSaved toggle window: true then false after 1s', async () => {
    vi.useFakeTimers();
    const pending = service.save(30);
    httpTesting.expectOne('/v1/reading-speed').flush({ pages_per_hour: 30 });
    await pending;
    expect(service.justSaved()).toBe(true);
    vi.advanceTimersByTime(500);
    expect(service.justSaved()).toBe(true);
    vi.advanceTimersByTime(600);
    expect(service.justSaved()).toBe(false);
  });

  it('save() success preserves previous pagesPerHour transition', async () => {
    // First a load gives us 20.
    const loadPromise = service.load();
    httpTesting.expectOne('/v1/reading-speed').flush({ pages_per_hour: 20 });
    await loadPromise;
    expect(service.pagesPerHour()).toBe(20);
    // Then a save replaces to 45.
    const savePromise = service.save(45);
    httpTesting.expectOne('/v1/reading-speed').flush({ pages_per_hour: 45 });
    await savePromise;
    expect(service.pagesPerHour()).toBe(45);
  });
});
