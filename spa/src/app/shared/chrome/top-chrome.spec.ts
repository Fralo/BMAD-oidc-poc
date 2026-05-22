import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AuthService } from '../../auth/auth-service';
import { Me } from '../../auth/auth.types';

import { TopChrome } from './top-chrome';

function makeAuthServiceStub(initial: Me | null) {
  const _me = signal<Me | null>(initial);
  return {
    me: _me.asReadonly(),
    setMe: (m: Me | null) => _me.set(m),
    clear: vi.fn(() => _me.set(null)),
    loadMe: vi.fn(async () => undefined),
  };
}

async function setupHarness(initialMe: Me | null) {
  const authStub = makeAuthServiceStub(initialMe);
  TestBed.configureTestingModule({
    imports: [TopChrome],
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([
        { path: 'books', children: [] },
        { path: 'settings', children: [] },
      ]),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: authStub },
    ],
  });
  await TestBed.compileComponents();
  const router = TestBed.inject(Router);
  const http = TestBed.inject(HttpTestingController);
  return { authStub, router, http };
}

describe('TopChrome', () => {
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
  });

  afterEach(() => {
    if (originalLocationDescriptor) {
      Object.defineProperty(window, 'location', originalLocationDescriptor);
    }
  });

  it('unauthenticated variant renders product name only — no identity, no link', async () => {
    const { router } = await setupHarness(null);
    await router.navigateByUrl('/');

    const fixture = TestBed.createComponent(TopChrome);
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.top-chrome-brand')?.textContent?.trim()).toBe(
      'Reading Time Estimator',
    );
    expect(el.querySelector('.top-chrome-identity')).toBeNull();
    expect(el.querySelector('.top-chrome-link')).toBeNull();
  });

  it('authenticated variant on /books renders Settings link + identity block', async () => {
    const { router } = await setupHarness({ sub: 's1', preferred_username: 'alice' });
    await router.navigateByUrl('/books');

    const fixture = TestBed.createComponent(TopChrome);
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.top-chrome-brand')?.textContent?.trim()).toBe(
      'Reading Time Estimator',
    );
    const link = el.querySelector('.top-chrome-link');
    expect(link?.textContent?.trim()).toBe('Settings');
    expect(link?.getAttribute('href')).toBe('/settings');

    const identity = el.querySelector('.top-chrome-identity');
    expect(identity?.textContent).toContain('Signed in as ');
    expect(identity?.textContent).toContain('alice');
    expect(identity?.textContent).toContain('·');

    const logoutBtn = el.querySelector('.top-chrome-logout');
    expect(logoutBtn?.textContent?.trim()).toBe('Log out');
  });

  it('authenticated variant on /settings renders Books link instead of Settings', async () => {
    const { router } = await setupHarness({ sub: 's1', preferred_username: 'alice' });
    await router.navigateByUrl('/settings');

    const fixture = TestBed.createComponent(TopChrome);
    fixture.detectChanges();
    await fixture.whenStable();

    const link = (fixture.nativeElement as HTMLElement).querySelector('.top-chrome-link');
    expect(link?.textContent?.trim()).toBe('Books');
    expect(link?.getAttribute('href')).toBe('/books');
  });

  it('clicking Log out POSTs /auth/logout, clears auth state, and navigates to the front-channel logout URL', async () => {
    const { router, http, authStub } = await setupHarness({
      sub: 's1',
      preferred_username: 'alice',
    });
    await router.navigateByUrl('/books');

    const fixture = TestBed.createComponent(TopChrome);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance as TopChrome;
    const logoutSpy = vi.spyOn(component, 'logout');

    const logoutBtn = (fixture.nativeElement as HTMLElement).querySelector(
      '.top-chrome-logout',
    ) as HTMLButtonElement;
    logoutBtn.click();

    expect(logoutSpy).toHaveBeenCalledTimes(1);
    const clickPromise = logoutSpy.mock.results[0]!.value as Promise<void>;

    const req = http.expectOne('/auth/logout');
    expect(req.request.method).toBe('POST');
    const frontChannelUrl =
      'http://localhost:8080/realms/bmad-books/protocol/openid-connect/logout?id_token_hint=eyJ.fake.jwt&post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A4000%2F';
    req.flush({ logout_redirect_url: frontChannelUrl });

    await clickPromise;

    expect(authStub.clear).toHaveBeenCalledTimes(1);
    expect(assignedHref).toBe(frontChannelUrl);
  });

  it('logout still clears state + navigates to / when /auth/logout fails (degrade-open per J5)', async () => {
    const { router, http, authStub } = await setupHarness({
      sub: 's1',
      preferred_username: 'alice',
    });
    await router.navigateByUrl('/books');

    const fixture = TestBed.createComponent(TopChrome);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance as TopChrome;
    const logoutSpy = vi.spyOn(component, 'logout');

    const logoutBtn = (fixture.nativeElement as HTMLElement).querySelector(
      '.top-chrome-logout',
    ) as HTMLButtonElement;
    logoutBtn.click();

    expect(logoutSpy).toHaveBeenCalledTimes(1);
    const clickPromise = logoutSpy.mock.results[0]!.value as Promise<void>;

    const req = http.expectOne('/auth/logout');
    req.flush({ errorCode: 'oops', message: 'no' }, { status: 500, statusText: 'ISE' });

    await clickPromise;

    expect(authStub.clear).toHaveBeenCalledTimes(1);
    expect(assignedHref).toBe('/');
  });

  it('logout falls back to / when /auth/logout returns an empty body (defensive)', async () => {
    const { router, http, authStub } = await setupHarness({
      sub: 's1',
      preferred_username: 'alice',
    });
    await router.navigateByUrl('/books');

    const fixture = TestBed.createComponent(TopChrome);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance as TopChrome;
    const logoutSpy = vi.spyOn(component, 'logout');

    const logoutBtn = (fixture.nativeElement as HTMLElement).querySelector(
      '.top-chrome-logout',
    ) as HTMLButtonElement;
    logoutBtn.click();

    expect(logoutSpy).toHaveBeenCalledTimes(1);
    const clickPromise = logoutSpy.mock.results[0]!.value as Promise<void>;

    const req = http.expectOne('/auth/logout');
    req.flush({});

    await clickPromise;

    expect(authStub.clear).toHaveBeenCalledTimes(1);
    expect(assignedHref).toBe('/');
  });
});
