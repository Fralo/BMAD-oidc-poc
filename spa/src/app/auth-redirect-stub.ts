import { ChangeDetectionStrategy, Component } from '@angular/core';

// Stub that lets the SSR auth guard navigate successfully via RedirectCommand.
// `/auth/login` is proxied to the BFF by server.ts before Angular SSR runs,
// so this component is never rendered in production.
@Component({
  selector: 'app-auth-redirect-stub',
  standalone: true,
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AuthRedirectStub {}
