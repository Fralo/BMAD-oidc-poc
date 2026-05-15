import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';
import { AuthService } from './auth/auth-service';
import { Me } from './auth/auth.types';

function makeAuthServiceStub(initial: Me | null) {
  const _me = signal<Me | null>(initial);
  return {
    me: _me.asReadonly(),
    setMe: (m: Me | null) => _me.set(m),
    clear: () => _me.set(null),
    loadMe: async () => undefined,
  };
}

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: makeAuthServiceStub(null) },
      ],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('renders <app-top-chrome /> and the router outlet at the root', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('app-top-chrome')).not.toBeNull();
    expect(compiled.querySelector('router-outlet')).not.toBeNull();
    // The 720px-wide content column wraps the router outlet.
    const main = compiled.querySelector('main.app-content');
    expect(main).not.toBeNull();
    expect(main?.querySelector('router-outlet')).not.toBeNull();
  });
});
