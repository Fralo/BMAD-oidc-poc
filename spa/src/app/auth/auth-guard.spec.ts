import { provideHttpClient, withFetch } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';

import { AuthService } from './auth-service';
import { authGuard } from './auth-guard';

describe('authGuard', () => {
  let httpTesting: HttpTestingController;
  let router: Router;
  let authService: AuthService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withFetch()),
        provideHttpClientTesting(),
      ],
    });
    httpTesting = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    authService = TestBed.inject(AuthService);
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('returns true on 200 and updates AuthService.me', async () => {
    const route = {} as ActivatedRouteSnapshot;
    const state = { url: '/books' } as RouterStateSnapshot;
    const pending = TestBed.runInInjectionContext(() => authGuard(route, state)) as Promise<boolean | UrlTree>;
    httpTesting.expectOne('/api/me').flush({ sub: 's1', preferred_username: 'alice' });
    const result = await pending;
    expect(result).toBe(true);
    expect(authService.me()).toEqual({ sub: 's1', preferred_username: 'alice' });
  });

  it('returns a UrlTree to /login with encoded return_to on 401', async () => {
    const route = {} as ActivatedRouteSnapshot;
    const state = { url: '/books?foo=bar' } as RouterStateSnapshot;
    const pending = TestBed.runInInjectionContext(() => authGuard(route, state)) as Promise<boolean | UrlTree>;
    httpTesting.expectOne('/api/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    const result = await pending;
    expect(result).not.toBe(true);
    expect(router.serializeUrl(result as UrlTree)).toBe('/login?return_to=%2Fbooks%3Ffoo%3Dbar');
  });
});
