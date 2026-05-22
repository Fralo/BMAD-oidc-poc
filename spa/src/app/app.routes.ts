import { Routes } from '@angular/router';

import { authGuard } from './auth/auth-guard';
import { AuthRedirectStub } from './auth-redirect-stub';

export const routes: Routes = [
  // Stub for the SSR auth guard's RedirectCommand target. Production traffic
  // to /auth/login is intercepted by server.ts's proxy and never reaches
  // Angular; this entry only exists so the in-process router can navigate
  // to it successfully, which is what triggers Angular SSR's 302 emission.
  { path: 'auth/login', component: AuthRedirectStub },
  {
    path: '',
    canMatch: [authGuard],
    children: [
      {
        path: 'books',
        loadComponent: () => import('./books/book-list-page').then((m) => m.BookListPage),
      },
      {
        path: 'settings',
        loadComponent: () => import('./settings/settings-page').then((m) => m.SettingsPage),
      },
    ],
  },
  { path: '**', redirectTo: 'books' },
];
