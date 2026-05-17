import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';

import { ErrorService } from './error-service';

function makeHttpError(opts: {
  status: number;
  body?: unknown;
  statusText?: string;
}): HttpErrorResponse {
  return new HttpErrorResponse({
    status: opts.status,
    statusText: opts.statusText ?? 'Error',
    error: opts.body,
    url: 'http://test/v1/books',
  });
}

describe('ErrorService', () => {
  let service: ErrorService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ErrorService);
  });

  it('maps status-0 transport error to network', () => {
    const err = makeHttpError({ status: 0, body: null, statusText: 'Unknown Error' });
    expect(service.parse(err)).toEqual({ kind: 'network' });
  });

  it('maps envelope session_expired (401) to session_expired', () => {
    const err = makeHttpError({
      status: 401,
      body: { errorCode: 'session_expired', message: 'Session expired' },
    });
    expect(service.parse(err)).toEqual({ kind: 'session_expired' });
  });

  it('maps envelope forbidden_scope (403) to forbidden_scope', () => {
    const err = makeHttpError({
      status: 403,
      body: { errorCode: 'forbidden_scope' },
    });
    expect(service.parse(err)).toEqual({ kind: 'forbidden_scope' });
  });

  it('maps envelope invalid_input (422) to invalid_input passing the detail through exactly', () => {
    const detailArray = [
      { loc: ['body', 'title'], msg: 'title must not be empty or whitespace-only', type: 'value_error' },
    ];
    const err = makeHttpError({
      status: 422,
      body: { errorCode: 'invalid_input', message: 'Request validation failed', detail: detailArray },
    });
    const parsed = service.parse(err);
    expect(parsed).toEqual({ kind: 'invalid_input', detail: detailArray });
    if (parsed.kind === 'invalid_input') {
      // exact reference preservation — pass-through, not a clone
      expect(parsed.detail).toBe(detailArray);
    }
  });

  it('maps envelope book_not_found (404) to book_not_found', () => {
    const err = makeHttpError({
      status: 404,
      body: { errorCode: 'book_not_found' },
    });
    expect(service.parse(err)).toEqual({ kind: 'book_not_found' });
  });

  it('maps envelope csrf_invalid (403) to csrf_invalid', () => {
    const err = makeHttpError({
      status: 403,
      body: { errorCode: 'csrf_invalid' },
    });
    expect(service.parse(err)).toEqual({ kind: 'csrf_invalid' });
  });

  it('maps envelope auth_state_invalid (400) to auth_state_invalid', () => {
    const err = makeHttpError({
      status: 400,
      body: { errorCode: 'auth_state_invalid' },
    });
    expect(service.parse(err)).toEqual({ kind: 'auth_state_invalid' });
  });

  it('maps envelope with unknown errorCode (500) to unknown with the status', () => {
    const err = makeHttpError({
      status: 500,
      body: { errorCode: 'totally_unknown_code' },
    });
    expect(service.parse(err)).toEqual({ kind: 'unknown', status: 500 });
  });

  it('falls back to status when body is non-envelope: 404 -> book_not_found', () => {
    const err = makeHttpError({
      status: 404,
      body: { detail: 'Not Found' },
    });
    expect(service.parse(err)).toEqual({ kind: 'book_not_found' });
  });

  it('falls back to status when body is non-envelope: 401 -> session_expired', () => {
    const err = makeHttpError({
      status: 401,
      body: null,
    });
    expect(service.parse(err)).toEqual({ kind: 'session_expired' });
  });

  it('falls back to status when body is non-envelope: 403 -> csrf_invalid', () => {
    const err = makeHttpError({
      status: 403,
      body: { detail: 'Forbidden' },
    });
    expect(service.parse(err)).toEqual({ kind: 'csrf_invalid' });
  });

  it('falls back to status when body is non-envelope: 422 -> invalid_input with undefined detail', () => {
    const err = makeHttpError({
      status: 422,
      body: { detail: [{ loc: ['body'], msg: 'bad' }] },
    });
    expect(service.parse(err)).toEqual({ kind: 'invalid_input', detail: undefined });
  });

  it('falls back to status when body is non-envelope: unmapped 599 -> unknown', () => {
    const err = makeHttpError({
      status: 599,
      body: { whatever: true },
    });
    expect(service.parse(err)).toEqual({ kind: 'unknown', status: 599 });
  });

  it('treats errorCode that is not a string as non-envelope (falls back to status)', () => {
    const err = makeHttpError({
      status: 404,
      body: { errorCode: 42 },
    });
    expect(service.parse(err)).toEqual({ kind: 'book_not_found' });
  });

  it('returns unknown/status=0 when err is not an HttpErrorResponse (raw Error)', () => {
    expect(service.parse(new Error('boom'))).toEqual({ kind: 'unknown', status: 0 });
  });

  it('returns unknown/status=0 when err is null/undefined/primitive', () => {
    expect(service.parse(null)).toEqual({ kind: 'unknown', status: 0 });
    expect(service.parse(undefined)).toEqual({ kind: 'unknown', status: 0 });
    expect(service.parse('plain string')).toEqual({ kind: 'unknown', status: 0 });
  });

  it('never throws on weird input', () => {
    expect(() => service.parse({ random: 'object' })).not.toThrow();
    expect(() => service.parse(0)).not.toThrow();
  });
});
