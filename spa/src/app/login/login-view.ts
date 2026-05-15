import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { map } from 'rxjs';

import { ErrorMessage } from '../shared/ui/error-message';

export const LOGIN_AUTH_LOGIN_PATH = '/auth/login';
export const LOGIN_AUTH_ERROR_COPY = "Login didn't complete — try again.";

@Component({
  selector: 'app-login-view',
  imports: [ErrorMessage],
  templateUrl: './login-view.html',
  styleUrl: './login-view.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginView {
  private readonly route = inject(ActivatedRoute);

  private readonly errorParam = toSignal(
    this.route.queryParamMap.pipe(map((p) => p.get('error'))),
    { initialValue: this.route.snapshot.queryParamMap.get('error') },
  );

  readonly showAuthError = computed(() => this.errorParam() === 'auth');
  readonly authErrorCopy = LOGIN_AUTH_ERROR_COPY;

  onLogin(): void {
    this.redirectToAuthLogin();
  }

  /** Indirection seam: tests spy on this method to avoid touching real `window.location`. */
  redirectToAuthLogin(): void {
    window.location.href = LOGIN_AUTH_LOGIN_PATH;
  }
}
