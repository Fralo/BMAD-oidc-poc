import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { AppError } from '../shared/errors/app-error.types';
import { ErrorService } from '../shared/errors/error-service';
import { Book, BookCreate, BookStatus, BookUpdate } from './book.types';

@Injectable({ providedIn: 'root' })
export class BooksService {
  private readonly http = inject(HttpClient);
  private readonly errors = inject(ErrorService);

  readonly books = signal<Book[]>([]);
  readonly loading = signal<boolean>(false);
  readonly loadError = signal<AppError | null>(null);

  async load(): Promise<void> {
    this.loading.set(true);
    this.loadError.set(null);
    try {
      const list = await firstValueFrom(this.http.get<Book[]>('/v1/books'));
      this.books.set(list);
    } catch (err) {
      this.loadError.set(this.errors.parse(err));
    } finally {
      this.loading.set(false);
    }
  }

  async create(payload: BookCreate): Promise<Book> {
    let created: Book;
    try {
      created = await firstValueFrom(this.http.post<Book>('/v1/books', payload));
    } catch (err) {
      throw this.errors.parse(err);
    }
    this.books.update((prev) => [created, ...prev]);
    return created;
  }

  async update(id: number, payload: BookUpdate): Promise<Book> {
    let updated: Book;
    try {
      updated = await firstValueFrom(this.http.patch<Book>(`/v1/books/${id}`, payload));
    } catch (err) {
      throw this.errors.parse(err);
    }
    this.books.update((prev) => prev.map((b) => (b.id === id ? updated : b)));
    return updated;
  }

  async setStatus(id: number, next: BookStatus): Promise<void> {
    const target = this.books().find((b) => b.id === id);
    if (!target) {
      // unknown id — caller has a stale id; skip
      return;
    }
    const prev = target.status;
    if (prev === next) {
      // no-op — skip network round-trip
      return;
    }

    // Optimistic update — immutable spread
    this.books.update((rows) =>
      rows.map((b) => (b.id === id ? { ...b, status: next } : b)),
    );

    let updated: Book;
    try {
      updated = await firstValueFrom(
        this.http.patch<Book>(`/v1/books/${id}`, { status: next }),
      );
    } catch (err) {
      // Revert to prior status
      this.books.update((rows) =>
        rows.map((b) => (b.id === id ? { ...b, status: prev } : b)),
      );
      throw this.errors.parse(err);
    }

    // Replace optimistic row with authoritative server row
    this.books.update((rows) => rows.map((b) => (b.id === id ? updated : b)));
  }

  async delete(id: number): Promise<void> {
    try {
      await firstValueFrom(this.http.delete(`/v1/books/${id}`));
    } catch (err) {
      throw this.errors.parse(err);
    }
    this.books.update((rows) => rows.filter((b) => b.id !== id));
  }
}
