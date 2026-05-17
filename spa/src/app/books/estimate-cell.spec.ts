import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { EstimateCell } from './estimate-cell';

describe('EstimateCell', () => {
  it('renders a disabled "Estimate" button with the documented title attribute', async () => {
    await TestBed.configureTestingModule({
      imports: [EstimateCell],
      providers: [provideZonelessChangeDetection()],
    }).compileComponents();

    const fixture = TestBed.createComponent(EstimateCell);
    fixture.componentRef.setInput('bookId', 1);
    fixture.componentRef.setInput('pages', 100);
    fixture.detectChanges();
    await fixture.whenStable();

    const button = (fixture.nativeElement as HTMLElement).querySelector(
      'button.estimate-cell-button',
    ) as HTMLButtonElement;

    expect(button).not.toBeNull();
    expect(button.textContent?.trim()).toBe('Estimate');
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('title')).toBe('Available in Epic 4');
  });
});
