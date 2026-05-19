import {
  HttpClient,
  provideHttpClient,
  withFetch,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID, REQUEST } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ssrCookieForwardInterceptor } from './ssr-cookie-forward.interceptor';
import { SSR_API_TARGET } from './ssr-api-target.token';

const BFF_TARGET = 'http://bff:8000';

function makeServerRequest(headers: Record<string, string>): Request {
  return new Request('http://localhost/', { headers });
}

describe('ssrCookieForwardInterceptor', () => {
  it('attaches the inbound cookie header on the server when the URL targets the BFF and REQUEST has a cookie', () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([ssrCookieForwardInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: SSR_API_TARGET, useValue: BFF_TARGET },
        {
          provide: REQUEST,
          useValue: makeServerRequest({ cookie: 'bff_session=abc; csrf_token=xyz' }),
        },
      ],
    });
    const http = TestBed.inject(HttpClient);
    const ctrl = TestBed.inject(HttpTestingController);

    http.get(`${BFF_TARGET}/api/me`).subscribe();
    const req = ctrl.expectOne(`${BFF_TARGET}/api/me`);
    expect(req.request.headers.get('cookie')).toBe('bff_session=abc; csrf_token=xyz');
    req.flush({});
    ctrl.verify();
  });

  it('does NOT attach the cookie when the outbound URL targets a non-BFF origin (cookie leak guard)', () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([ssrCookieForwardInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: SSR_API_TARGET, useValue: BFF_TARGET },
        {
          provide: REQUEST,
          useValue: makeServerRequest({ cookie: 'bff_session=must-not-leak' }),
        },
      ],
    });
    const http = TestBed.inject(HttpClient);
    const ctrl = TestBed.inject(HttpTestingController);

    http.get('https://analytics.example.com/event').subscribe();
    const req = ctrl.expectOne('https://analytics.example.com/event');
    expect(req.request.headers.has('cookie')).toBe(false);
    req.flush({});
    ctrl.verify();
  });

  it('is a no-op on the server when REQUEST has no cookie header', () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([ssrCookieForwardInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: SSR_API_TARGET, useValue: BFF_TARGET },
        { provide: REQUEST, useValue: makeServerRequest({}) },
      ],
    });
    const http = TestBed.inject(HttpClient);
    const ctrl = TestBed.inject(HttpTestingController);

    http.get(`${BFF_TARGET}/api/me`).subscribe();
    const req = ctrl.expectOne(`${BFF_TARGET}/api/me`);
    expect(req.request.headers.has('cookie')).toBe(false);
    req.flush({});
    ctrl.verify();
  });

  it('is a no-op on the server when REQUEST itself is absent', () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([ssrCookieForwardInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: SSR_API_TARGET, useValue: BFF_TARGET },
        // REQUEST deliberately NOT provided.
      ],
    });
    const http = TestBed.inject(HttpClient);
    const ctrl = TestBed.inject(HttpTestingController);

    http.get(`${BFF_TARGET}/api/me`).subscribe();
    const req = ctrl.expectOne(`${BFF_TARGET}/api/me`);
    expect(req.request.headers.has('cookie')).toBe(false);
    req.flush({});
    ctrl.verify();
  });

  it('is a no-op on the server when SSR_API_TARGET is absent', () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([ssrCookieForwardInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        // SSR_API_TARGET deliberately NOT provided.
        {
          provide: REQUEST,
          useValue: makeServerRequest({ cookie: 'bff_session=should-not-attach' }),
        },
      ],
    });
    const http = TestBed.inject(HttpClient);
    const ctrl = TestBed.inject(HttpTestingController);

    http.get('/api/me').subscribe();
    const req = ctrl.expectOne('/api/me');
    expect(req.request.headers.has('cookie')).toBe(false);
    req.flush({});
    ctrl.verify();
  });

  it('is a no-op on the browser regardless of REQUEST state', () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([ssrCookieForwardInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: SSR_API_TARGET, useValue: BFF_TARGET },
        {
          provide: REQUEST,
          useValue: makeServerRequest({ cookie: 'bff_session=should-not-leak' }),
        },
      ],
    });
    const http = TestBed.inject(HttpClient);
    const ctrl = TestBed.inject(HttpTestingController);

    http.get(`${BFF_TARGET}/api/me`).subscribe();
    const req = ctrl.expectOne(`${BFF_TARGET}/api/me`);
    expect(req.request.headers.has('cookie')).toBe(false);
    req.flush({});
    ctrl.verify();
  });
});
