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
  let routerNavigate: ReturnType<typeof vi.fn>;
  let authClear: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    routerNavigate = vi.fn();
    authClear = vi.fn();

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([withCredentialsInterceptor])),
        provideHttpClientTesting(),
        {
          provide: Router,
          useValue: { url: '/books', navigateByUrl: routerNavigate },
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
  });

  it('sets withCredentials=true on every request', () => {
    http.get('/v1/books').subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/v1/books');
    expect(req.request.withCredentials).toBe(true);
    req.flush([]);
  });

  it('a non-/api/me 401 clears auth state and navigates to /login with return_to', () => {
    http.get('/v1/books').subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/v1/books');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(authClear).toHaveBeenCalledTimes(1);
    expect(routerNavigate).toHaveBeenCalledWith('/login?return_to=%2Fbooks');
  });

  it('a /api/me 401 does NOT trigger clear() or navigate()', () => {
    http.get('/api/me').subscribe({ error: () => undefined });
    const req = httpTesting.expectOne('/api/me');
    req.flush(null, { status: 401, statusText: 'Unauthorized' });
    expect(authClear).not.toHaveBeenCalled();
    expect(routerNavigate).not.toHaveBeenCalled();
  });

  it('a 5xx is propagated unchanged (no navigate, no clear)', () => {
    let observed: unknown = null;
    http.get('/v1/books').subscribe({ error: (err) => (observed = err) });
    const req = httpTesting.expectOne('/v1/books');
    req.flush(null, { status: 503, statusText: 'Service Unavailable' });
    expect(authClear).not.toHaveBeenCalled();
    expect(routerNavigate).not.toHaveBeenCalled();
    expect(observed).not.toBeNull();
  });

  it('on the server platform: 401 clears auth state but DOES NOT navigate', () => {
    httpTesting.verify();
    TestBed.resetTestingModule();
    const serverNavigate = vi.fn();
    const serverClear = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withFetch(), withInterceptors([withCredentialsInterceptor])),
        provideHttpClientTesting(),
        { provide: PLATFORM_ID, useValue: 'server' },
        {
          provide: Router,
          useValue: { url: '/books', navigateByUrl: serverNavigate },
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
    expect(serverNavigate).not.toHaveBeenCalled();
    ctrlServer.verify();
  });
});
