import { Routes } from '@angular/router';

import { authGuard } from './auth/auth-guard';
import { redirectIfAuthedGuard } from './auth/redirect-if-authed-guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'books' },
  {
    path: 'login',
    loadComponent: () => import('./login/login-view').then((m) => m.LoginView),
    canActivate: [redirectIfAuthedGuard],
  },
  {
    path: 'books',
    loadComponent: () =>
      import('./books/books-page-placeholder').then((m) => m.BooksPagePlaceholder),
    canActivate: [authGuard],
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./settings/settings-page-placeholder').then((m) => m.SettingsPagePlaceholder),
    canActivate: [authGuard],
  },
  { path: '**', redirectTo: 'books' },
];
