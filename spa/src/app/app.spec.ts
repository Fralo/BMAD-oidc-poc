import { TestBed } from '@angular/core/testing';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render the AC7 smoke fragment with token-derived utility classes', async () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    const smoke = compiled.querySelector('main > div');
    expect(smoke?.textContent?.trim()).toBe('SPA scaffold is alive');
    expect(smoke?.classList.contains('bg-surface-muted')).toBe(true);
    expect(smoke?.classList.contains('text-accent')).toBe(true);
    expect(smoke?.classList.contains('p-3')).toBe(true);
  });
});
