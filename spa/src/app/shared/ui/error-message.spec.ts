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

  it('applies the .error-message class so the error-token CSS contract (small font + error color) is wired up', async () => {
    const fixture = TestBed.createComponent(ErrorMessage);
    fixture.componentRef.setInput('message', 'oops');
    fixture.detectChanges();
    await fixture.whenStable();

    const p = (fixture.nativeElement as HTMLElement).querySelector('p');
    expect(p?.classList.contains('error-message')).toBe(true);
  });
});
