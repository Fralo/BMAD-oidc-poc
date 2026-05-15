import {
  HttpClient,
  HttpHandlerFn,
  HttpRequest,
  provideHttpClient,
  withFetch,
  withInterceptors,
} from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { EMPTY } from 'rxjs';

import { csrfInterceptor } from './csrf-interceptor';

function setCsrfCookie(value: string | null): void {
  if (value === null) {
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    return;
  }
  document.cookie = `csrf_token=${value}; path=/`;
}

describe('csrfInterceptor', () => {
  let http: HttpClient;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([csrfInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpTesting = TestBed.inject(HttpTestingController);
    setCsrfCookie('abc123');
  });

  afterEach(() => {
    httpTesting.verify();
    setCsrfCookie(null);
  });

  it('does not add X-CSRF-Token on GET', () => {
    http.get('/v1/books').subscribe();
    const req = httpTesting.expectOne('/v1/books');
    expect(req.request.headers.has('X-CSRF-Token')).toBe(false);
    req.flush([]);
  });

  it('adds X-CSRF-Token on POST when cookie is present', () => {
    http.post('/v1/books', {}).subscribe();
    const req = httpTesting.expectOne('/v1/books');
    expect(req.request.headers.get('X-CSRF-Token')).toBe('abc123');
    req.flush({});
  });

  it('adds X-CSRF-Token on PUT, PATCH, DELETE when cookie is present', () => {
    http.put('/v1/reading-speed', {}).subscribe();
    const put = httpTesting.expectOne('/v1/reading-speed');
    expect(put.request.headers.get('X-CSRF-Token')).toBe('abc123');
    put.flush({});

    http.patch('/v1/books/1', {}).subscribe();
    const patch = httpTesting.expectOne('/v1/books/1');
    expect(patch.request.headers.get('X-CSRF-Token')).toBe('abc123');
    patch.flush({});

    http.delete('/v1/books/1').subscribe();
    const del = httpTesting.expectOne('/v1/books/1');
    expect(del.request.headers.get('X-CSRF-Token')).toBe('abc123');
    del.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('does not add X-CSRF-Token on POST when the cookie is missing', () => {
    setCsrfCookie(null);
    http.post('/v1/books', {}).subscribe();
    const req = httpTesting.expectOne('/v1/books');
    expect(req.request.headers.has('X-CSRF-Token')).toBe(false);
    req.flush({});
  });

  it('does not add X-CSRF-Token on HEAD or OPTIONS even when the cookie is present', () => {
    const captured: HttpRequest<unknown>[] = [];
    const next: HttpHandlerFn = (req) => {
      captured.push(req);
      return EMPTY;
    };
    TestBed.runInInjectionContext(() => {
      csrfInterceptor(new HttpRequest('HEAD', '/v1/books'), next).subscribe();
      csrfInterceptor(new HttpRequest('OPTIONS', '/v1/books'), next).subscribe();
    });
    expect(captured).toHaveLength(2);
    expect(captured[0].method).toBe('HEAD');
    expect(captured[0].headers.has('X-CSRF-Token')).toBe(false);
    expect(captured[1].method).toBe('OPTIONS');
    expect(captured[1].headers.has('X-CSRF-Token')).toBe(false);
  });
});
