import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, Signal, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Me } from './auth.types';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly _me = signal<Me | null>(null);
  readonly me: Signal<Me | null> = this._me.asReadonly();

  async loadMe(): Promise<void> {
    try {
      const result = await firstValueFrom(this.http.get<Me>('/api/me'));
      this._me.set(result);
    } catch (err) {
      this._me.set(null);
      if (err instanceof HttpErrorResponse && err.status === 401) {
        return;
      }
      throw err;
    }
  }

  /** Internal writer for guards and the auth-callback handler — feature code should call loadMe(). */
  setMe(me: Me | null): void {
    this._me.set(me);
  }

  clear(): void {
    this._me.set(null);
  }
}
