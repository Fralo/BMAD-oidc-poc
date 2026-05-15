import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map, startWith } from 'rxjs';
import { firstValueFrom } from 'rxjs';

import { AuthService } from '../../auth/auth-service';

interface ContextualLink {
  label: string;
  path: string;
}

@Component({
  selector: 'app-top-chrome',
  imports: [RouterLink],
  templateUrl: './top-chrome.html',
  styleUrl: './top-chrome.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TopChrome {
  private readonly authService = inject(AuthService);
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  readonly me = this.authService.me;

  private readonly currentUrl = toSignal(
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
      map((e) => e.urlAfterRedirects),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );

  readonly contextualLink = computed<ContextualLink | null>(() => {
    const url = this.currentUrl();
    const path = (url || '/').split('?')[0];
    if (path === '/books' || path.startsWith('/books/')) {
      return { label: 'Settings', path: '/settings' };
    }
    if (path === '/settings' || path.startsWith('/settings/')) {
      return { label: 'Books', path: '/books' };
    }
    return null;
  });

  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.http.post('/auth/logout', null));
    } catch {
      // J5: degrade open — local session is cleared regardless of remote outcome.
    }
    this.authService.clear();
    await this.router.navigateByUrl('/login');
  }
}
