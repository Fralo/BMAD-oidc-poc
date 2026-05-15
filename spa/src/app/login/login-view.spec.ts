import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { BehaviorSubject } from 'rxjs';

import { LOGIN_AUTH_ERROR_COPY, LOGIN_AUTH_LOGIN_PATH, LoginView } from './login-view';

function buildRouteStub(queryParams: Record<string, string>) {
  const subject = new BehaviorSubject(convertToParamMap(queryParams));
  return {
    stub: {
      queryParamMap: subject.asObservable(),
      snapshot: { queryParamMap: convertToParamMap(queryParams) },
    },
    setParams(next: Record<string, string>) {
      subject.next(convertToParamMap(next));
    },
  };
}

describe('LoginView', () => {
  it('renders the default state (headline, copy, button) and no error message', async () => {
    const { stub } = buildRouteStub({});
    await TestBed.configureTestingModule({
      imports: [LoginView],
      providers: [
        provideZonelessChangeDetection(),
        { provide: ActivatedRoute, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(LoginView);
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h1')?.textContent?.trim()).toBe('Sign in to Reading Time Estimator');
    expect(el.querySelector('p.login-copy')?.textContent?.trim()).toBe(
      "You'll be redirected to authenticate, then returned here.",
    );
    expect(el.querySelector('button.login-button')?.textContent?.trim()).toBe('Log in');
    expect(el.querySelector('app-error-message')).toBeNull();
  });

  it('clicking "Log in" triggers a full-page redirect to /auth/login', async () => {
    const { stub } = buildRouteStub({});
    await TestBed.configureTestingModule({
      imports: [LoginView],
      providers: [
        provideZonelessChangeDetection(),
        { provide: ActivatedRoute, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(LoginView);
    fixture.detectChanges();
    await fixture.whenStable();

    const component = fixture.componentInstance;
    const spy = vi.spyOn(component, 'redirectToAuthLogin').mockImplementation(() => undefined);

    const button = (fixture.nativeElement as HTMLElement).querySelector(
      'button.login-button',
    ) as HTMLButtonElement;
    button.click();

    expect(spy).toHaveBeenCalledTimes(1);
    expect(LOGIN_AUTH_LOGIN_PATH).toBe('/auth/login');
  });

  it('redirectToAuthLogin() assigns window.location.href to LOGIN_AUTH_LOGIN_PATH', async () => {
    const { stub } = buildRouteStub({});
    await TestBed.configureTestingModule({
      imports: [LoginView],
      providers: [
        provideZonelessChangeDetection(),
        { provide: ActivatedRoute, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(LoginView);
    fixture.detectChanges();
    await fixture.whenStable();

    // Replace window.location with a stub that records href assignment,
    // then restore the original descriptor afterwards.
    const originalLocationDescriptor = Object.getOwnPropertyDescriptor(window, 'location');
    let assignedHref: string | null = null;
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

    try {
      fixture.componentInstance.redirectToAuthLogin();
      expect(assignedHref).toBe('/auth/login');
      expect(assignedHref).toBe(LOGIN_AUTH_LOGIN_PATH);
    } finally {
      if (originalLocationDescriptor) {
        Object.defineProperty(window, 'location', originalLocationDescriptor);
      }
    }
  });

  it('renders the inline ErrorMessage with UX-DR12 copy when ?error=auth is present', async () => {
    const { stub } = buildRouteStub({ error: 'auth' });
    await TestBed.configureTestingModule({
      imports: [LoginView],
      providers: [
        provideZonelessChangeDetection(),
        { provide: ActivatedRoute, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(LoginView);
    fixture.detectChanges();
    await fixture.whenStable();

    const errorEl = (fixture.nativeElement as HTMLElement).querySelector(
      'app-error-message p',
    );
    expect(errorEl?.textContent?.trim()).toBe(LOGIN_AUTH_ERROR_COPY);
    expect(LOGIN_AUTH_ERROR_COPY).toBe("Login didn't complete — try again.");
  });

  it('does NOT render the ErrorMessage when ?error has a non-auth value', async () => {
    const { stub } = buildRouteStub({ error: 'something-else' });
    await TestBed.configureTestingModule({
      imports: [LoginView],
      providers: [
        provideZonelessChangeDetection(),
        { provide: ActivatedRoute, useValue: stub },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(LoginView);
    fixture.detectChanges();
    await fixture.whenStable();

    expect((fixture.nativeElement as HTMLElement).querySelector('app-error-message')).toBeNull();
  });
});
