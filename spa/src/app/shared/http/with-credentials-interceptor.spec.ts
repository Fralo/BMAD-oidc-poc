import { HttpClient, provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';

import { AuthService } from '../../auth/auth-service';
import { withCredentialsInterceptor } from './with-credentials-interceptor';

describe('withCredentialsInterceptor', () => {
  let http: HttpClient;
  let httpTesting: HttpTestingController;
  let authClear: ReturnType<typeof vi.fn>;
  let originalLocationDescriptor: PropertyDescriptor | undefined;
  let assignedHref: string | null;

  beforeEach(() => {
    assignedHref = null;
    originalLocationDescriptor = Object.getOwnPropertyDescriptor(window, 'location');
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        set href(value: string) {
          assignedHref = value;
        },
        get href(): string {
          return assignedHref ?? '';
        },
      },
    });

    authClear = vi.fn();

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([withCredentialsInterceptor])),
        provideHttpClientTesting(),
        {
          provide: Router,
          useValue: { url: '/books' },
        },
        {
          provide: AuthService,
          useValue: { clear: authClear, setMe: vi.fn(), me: () => null },
        },
      ],
    });
    http = TestBed.inject(HttpClient);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    if (originalLocationDescriptor) {
      Object.defineProperty(window, 'location', originalLocationDescriptor);
    }
  });

  it('sets withCredentials=true on every request', () => {
    http.get('/v1/books').subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/v1/books');
    expect(req.request.withCredentials).toBe(true);
    req.flush([]);
  });

  it('a non-/api/me 401 clears auth state and assigns window.location.href to /auth/login with return_to', () => {
    http.get('/v1/books').subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/v1/books');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(authClear).toHaveBeenCalledTimes(1);
    expect(assignedHref).toBe('/auth/login?return_to=%2Fbooks');
  });

  it('a /api/me 401 does NOT trigger clear() or navigate()', () => {
    http.get('/api/me').subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/api/me');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(authClear).not.toHaveBeenCalled();
    expect(assignedHref).toBeNull();
  });

  it('a /auth/logout 401 does NOT trigger clear() or navigate() (top-chrome owns the redirect)', () => {
    http.post('/auth/logout', null).subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/auth/logout');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(authClear).not.toHaveBeenCalled();
    expect(assignedHref).toBeNull();
  });

  it('a 5xx is propagated unchanged (no navigate, no clear)', () => {
    let observed: unknown = null;
    http.get('/v1/books').subscribe({ error: (err) => (observed = err) });
    const req = httpTesting.expectOne('/v1/books');
    req.flush(null, { status: 503, statusText: 'Service Unavailable' });
    expect(authClear).not.toHaveBeenCalled();
    expect(assignedHref).toBeNull();
    expect(observed).not.toBeNull();
  });

  it('on the server platform: 401 clears auth state but DOES NOT navigate', () => {
    httpTesting.verify();
    TestBed.resetTestingModule();
    const serverClear = vi.fn();
    let serverAssignedHref: string | null = null;
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        set href(value: string) {
          serverAssignedHref = value;
        },
        get href(): string {
          return serverAssignedHref ?? '';
        },
      },
    });
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([withCredentialsInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        {
          provide: Router,
          useValue: { url: '/books' },
        },
        {
          provide: AuthService,
          useValue: { clear: serverClear, setMe: vi.fn(), me: () => null },
        },
      ],
    });
    const httpServer = TestBed.inject(HttpClient);
    const ctrlServer = TestBed.inject(HttpTestingController);

    httpServer.get('/v1/books').subscribe({ error: () => undefined });
    const req = ctrlServer.expectOne('/v1/books');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(serverClear).toHaveBeenCalledTimes(1);
    expect(serverAssignedHref).toBeNull();
    ctrlServer.verify();
  });
});
