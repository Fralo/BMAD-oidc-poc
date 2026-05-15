import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-settings-page-placeholder',
  template: `<p>Settings — coming in Epic 3</p>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPagePlaceholder {}
