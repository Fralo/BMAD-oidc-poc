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

import { redirectIfAuthedGuard } from './redirect-if-authed-guard';

describe('redirectIfAuthedGuard', () => {
  let httpTesting: HttpTestingController;
  let router: Router;

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
  });

  afterEach(() => {
    httpTesting.verify();
  });

  it('returns a UrlTree to /books on 200', async () => {
    const route = {} as ActivatedRouteSnapshot;
    const state = { url: '/login' } as RouterStateSnapshot;
    const pending = TestBed.runInInjectionContext(() => redirectIfAuthedGuard(route, state)) as Promise<
      boolean | UrlTree
    >;
    httpTesting.expectOne('/api/me').flush({ sub: 's1', preferred_username: 'alice' });
    const result = await pending;
    expect(result).not.toBe(true);
    expect(router.serializeUrl(result as UrlTree)).toBe('/books');
  });

  it('returns true on 401', async () => {
    const route = {} as ActivatedRouteSnapshot;
    const state = { url: '/login' } as RouterStateSnapshot;
    const pending = TestBed.runInInjectionContext(() => redirectIfAuthedGuard(route, state)) as Promise<
      boolean | UrlTree
    >;
    httpTesting.expectOne('/api/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    const result = await pending;
    expect(result).toBe(true);
  });
});
