import {
  HttpClient,
  HttpHandlerFn,
  HttpRequest,
  provideHttpClient,
  withFetch,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { EMPTY } from 'rxjs';

import { ssrApiUrlInterceptor } from './ssr-api-url.interceptor';
import { SSR_API_TARGET } from './ssr-api-target.token';

describe('ssrApiUrlInterceptor', () => {
  describe('on the server platform', () => {
    let http: HttpClient;
    let httpTesting: HttpTestingController;

    beforeEach(() => {
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(withFetch(), withInterceptors([ssrApiUrlInterceptor])),
          provideHttpClientTesting(),
          { provide: PLATFORM_ID, useValue: 'server' },
          { provide: SSR_API_TARGET, useValue: 'http://bff:8000' },
        ],
      });
      http = TestBed.inject(HttpClient);
      httpTesting = TestBed.inject(HttpTestingController);
    });

    afterEach(() => httpTesting.verify());

    it('rewrites /api/* onto the configured SSR_API_TARGET', () => {
      http.get('/api/me').subscribe();
      const req = httpTesting.expectOne('http://bff:8000/api/me');
      expect(req.request.url).toBe('http://bff:8000/api/me');
      req.flush({});
    });

    it('rewrites /auth/* and /v1/* onto the target', () => {
      http.get('/auth/login').subscribe();
      const authReq = httpTesting.expectOne('http://bff:8000/auth/login');
      authReq.flush({});

      http.post('/v1/books/42/estimate', {}).subscribe();
      const v1Req = httpTesting.expectOne('http://bff:8000/v1/books/42/estimate');
      v1Req.flush({});
    });

    it('does not rewrite URLs whose paths fall outside the proxied prefixes', () => {
      http.get('https://example.com/anything').subscribe();
      const req = httpTesting.expectOne('https://example.com/anything');
      expect(req.request.url).toBe('https://example.com/anything');
      req.flush({});
    });

    it('is a no-op when SSR_API_TARGET is absent', () => {
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(withFetch(), withInterceptors([ssrApiUrlInterceptor])),
          provideHttpClientTesting(),
          { provide: PLATFORM_ID, useValue: 'server' },
          // SSR_API_TARGET deliberately NOT provided.
        ],
      });
      const httpFresh = TestBed.inject(HttpClient);
      const ctrl = TestBed.inject(HttpTestingController);

      httpFresh.get('/api/me').subscribe();
      const req = ctrl.expectOne('/api/me');
      expect(req.request.url).toBe('/api/me');
      req.flush({});
      ctrl.verify();
    });
  });

  describe('on the browser platform', () => {
    it('never rewrites — even when SSR_API_TARGET is somehow provided', () => {
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(withFetch(), withInterceptors([ssrApiUrlInterceptor])),
          provideHttpClientTesting(),
          { provide: PLATFORM_ID, useValue: 'browser' },
          { provide: SSR_API_TARGET, useValue: 'http://bff:8000' },
        ],
      });
      const http = TestBed.inject(HttpClient);
      const ctrl = TestBed.inject(HttpTestingController);

      http.get('/api/me').subscribe();
      const req = ctrl.expectOne('/api/me');
      expect(req.request.url).toBe('/api/me');
      req.flush({});
      ctrl.verify();
    });
  });

  it('directly: passes the request through unchanged when called without server platform', () => {
    const captured: HttpRequest<unknown>[] = [];
    const next: HttpHandlerFn = (req) => {
      captured.push(req);
      return EMPTY;
    };
    TestBed.configureTestingModule({
      providers: [{ provide: PLATFORM_ID, useValue: 'browser' }],
    });
    TestBed.runInInjectionContext(() => {
      ssrApiUrlInterceptor(new HttpRequest('GET', '/api/me'), next).subscribe();
    });
    expect(captured).toHaveLength(1);
    expect(captured[0].url).toBe('/api/me');
  });
});
