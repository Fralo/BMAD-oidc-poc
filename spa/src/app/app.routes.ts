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
    loadComponent: () => import('./books/book-list-page').then((m) => m.BookListPage),
    canActivate: [authGuard],
  },
  {
    path: 'settings',
    loadComponent: () => import('./settings/settings-page').then((m) => m.SettingsPage),
    canActivate: [authGuard],
  },
  { path: '**', redirectTo: 'books' },
];
