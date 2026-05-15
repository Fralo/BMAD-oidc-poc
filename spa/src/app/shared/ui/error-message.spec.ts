import { TestBed } from '@angular/core/testing';
import { ErrorMessage } from './error-message';

describe('ErrorMessage', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ErrorMessage],
    }).compileComponents();
  });

  it('renders the message input verbatim', async () => {
    const fixture = TestBed.createComponent(ErrorMessage);
    fixture.componentRef.setInput('message', 'Something went wrong');
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    const p = el.querySelector('p');
    expect(p?.textContent?.trim()).toBe('Something went wrong');
  });

  it('uses the error token utility classes', async () => {
    const fixture = TestBed.createComponent(ErrorMessage);
    fixture.componentRef.setInput('message', 'oops');
    fixture.detectChanges();
    await fixture.whenStable();

    const p = (fixture.nativeElement as HTMLElement).querySelector('p');
    expect(p?.classList.contains('text-small')).toBe(true);
    expect(p?.classList.contains('text-error')).toBe(true);
  });
});
