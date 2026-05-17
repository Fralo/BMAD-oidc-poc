import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Story 4.3 stub.
 *
 * Renders a disabled `<button>Estimate</button>` with a tooltip explaining the
 * feature is not yet available. The two inputs are declared upfront so Story
 * 4.3 can replace this component wholesale without touching `BookRow`'s
 * template bindings (which already pass `[bookId]` and `[pages]`).
 */
@Component({
  selector: 'app-estimate-cell',
  imports: [],
  templateUrl: './estimate-cell.html',
  styleUrl: './estimate-cell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EstimateCell {
  readonly bookId = input.required<number>();
  readonly pages = input.required<number>();
}
