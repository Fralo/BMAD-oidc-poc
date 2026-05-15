import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-books-page-placeholder',
  template: `<p>Books — coming in Epic 2</p>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BooksPagePlaceholder {}
