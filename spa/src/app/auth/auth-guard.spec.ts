import { provideHttpClient, withFetch } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { RedirectCommand, Route, Router, UrlSegment, provideRouter } from '@angular/router';

import { AuthService } from './auth-service';
import { authGuard } from './auth-guard';

function makeSegments(parts: string[]): UrlSegment[] {
  return parts.map((p) => new UrlSegment(p, {}));
}

describe('authGuard (CanMatch)', () => {
  describe('on the browser platform', () => {
    let httpTesting: HttpTestingController;
    let authService: AuthService;
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

      TestBed.configureTestingModule({
        providers: [
          provideRouter([]),
          provideHttpClient(withFetch()),
          provideHttpClientTesting(),
          { provide: PLATFORM_ID, useValue: 'browser' },
        ],
      });
      httpTesting = TestBed.inject(HttpTestingController);
      authService = TestBed.inject(AuthService);
    });

    afterEach(() => {
      httpTesting.verify();
      if (originalLocationDescriptor) {
        Object.defineProperty(window, 'location', originalLocationDescriptor);
      }
    });

    it('returns true on 200 and AuthService.me is populated', async () => {
      const segments = makeSegments(['books']);
      const pending = TestBed.runInInjectionContext(() =>
        authGuard({} as Route, segments),
      ) as Promise<boolean | RedirectCommand>;
      httpTesting.expectOne('/api/me').flush({ sub: 's1', preferred_username: 'alice' });
      const result = await pending;
      expect(result).toBe(true);
      expect(authService.me()).toEqual({ sub: 's1', preferred_username: 'alice' });
      expect(assignedHref).toBeNull();
    });

    it('on 401 returns false and assigns window.location.href with return_to', async () => {
      const segments = makeSegments(['books', '42']);
      const pending = TestBed.runInInjectionContext(() =>
        authGuard({} as Route, segments),
      ) as Promise<boolean | RedirectCommand>;
      httpTesting.expectOne('/api/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      const result = await pending;
      expect(result).toBe(false);
      expect(assignedHref).toMatch(/^\/auth\/login\?return_to=/);
      expect(authService.me()).toBeNull();
    });

    it('non-401 error from loadMe falls through to redirect (no throw)', async () => {
      const segments = makeSegments(['books']);
      const pending = TestBed.runInInjectionContext(() =>
        authGuard({} as Route, segments),
      ) as Promise<boolean | RedirectCommand>;
      httpTesting.expectOne('/api/me').flush(null, { status: 503, statusText: 'Service Unavailable' });
      const result = await pending;
      expect(result).toBe(false);
      expect(assignedHref).toMatch(/^\/auth\/login\?return_to=/);
    });

    it('short-circuits without calling /api/me when AuthService.me is already populated', async () => {
      authService.setMe({ sub: 's1', preferred_username: 'alice' });
      const segments = makeSegments(['settings']);
      const result = await TestBed.runInInjectionContext(() =>
        authGuard({} as Route, segments),
      );
      expect(result).toBe(true);
      // No HTTP call expected — httpTesting.verify() in afterEach would fail otherwise.
    });
  });

  describe('on the server platform', () => {
    let httpTesting: HttpTestingController;
    let router: Router;

    beforeEach(() => {
      TestBed.configureTestingModule({
        providers: [
          provideRouter([]),
          provideHttpClient(withFetch()),
          provideHttpClientTesting(),
          { provide: PLATFORM_ID, useValue: 'server' },
        ],
      });
      httpTesting = TestBed.inject(HttpTestingController);
      router = TestBed.inject(Router);
    });

    afterEach(() => {
      httpTesting.verify();
    });

    it('on 401 returns a RedirectCommand pointing at /auth/login with return_to', async () => {
      const segments = makeSegments(['books']);
      const pending = TestBed.runInInjectionContext(() =>
        authGuard({} as Route, segments),
      ) as Promise<boolean | RedirectCommand>;
      httpTesting.expectOne('/api/me').flush(null, { status: 401, statusText: 'Unauthorized' });
      const result = await pending;
      expect(result).toBeInstanceOf(RedirectCommand);
      const cmd = result as RedirectCommand;
      expect(router.serializeUrl(cmd.redirectTo)).toMatch(
        /^\/auth\/login\?return_to=/,
      );
    });

    it('on 200 SSR returns true', async () => {
      const segments = makeSegments(['books']);
      const pending = TestBed.runInInjectionContext(() =>
        authGuard({} as Route, segments),
      ) as Promise<boolean | RedirectCommand>;
      httpTesting.expectOne('/api/me').flush({ sub: 's1', preferred_username: 'alice' });
      const result = await pending;
      expect(result).toBe(true);
    });
  });
});
