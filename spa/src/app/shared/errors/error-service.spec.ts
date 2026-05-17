import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { ErrorService } from './error-service';

describe('ErrorService.parse', () => {
  let service: ErrorService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ErrorService);
  });

  it('returns resource_server_unavailable for 503 with the matching errorCode', () => {
    const err = new HttpErrorResponse({
      status: 503,
      error: { errorCode: 'resource_server_unavailable', message: 'down', detail: null },
    });
    expect(service.parse(err)).toEqual({ kind: 'resource_server_unavailable' });
  });

  it('returns reading_speed_unset for 412 with the matching errorCode', () => {
    const err = new HttpErrorResponse({
      status: 412,
      error: { errorCode: 'reading_speed_unset', message: 'unset', detail: null },
    });
    expect(service.parse(err)).toEqual({ kind: 'reading_speed_unset' });
  });

  it('returns invalid_input with detail for 422 with the matching errorCode', () => {
    const detail = [{ loc: ['body', 'pages_per_hour'], msg: 'ge' }];
    const err = new HttpErrorResponse({
      status: 422,
      error: { errorCode: 'invalid_input', message: 'bad', detail },
    });
    expect(service.parse(err)).toEqual({ kind: 'invalid_input', detail });
  });

  it('returns forbidden_scope for 403 with the matching errorCode', () => {
    const err = new HttpErrorResponse({
      status: 403,
      error: { errorCode: 'forbidden_scope', message: 'nope', detail: null },
    });
    expect(service.parse(err)).toEqual({ kind: 'forbidden_scope' });
  });

  it('falls through to unknown when 503 carries a different errorCode', () => {
    const err = new HttpErrorResponse({
      status: 503,
      error: { errorCode: 'service_unavailable', message: 'other', detail: null },
    });
    const result = service.parse(err);
    expect(result.kind).toBe('unknown');
    if (result.kind === 'unknown') {
      expect(result.status).toBe(503);
      expect(result.errorCode).toBe('service_unavailable');
      expect(result.message).toBe('other');
    }
  });

  it('falls through to unknown when 412 carries a different errorCode', () => {
    const err = new HttpErrorResponse({
      status: 412,
      error: { errorCode: 'something_else' },
    });
    const result = service.parse(err);
    expect(result.kind).toBe('unknown');
  });

  it('returns unknown for non-HttpErrorResponse input', () => {
    expect(service.parse(new Error('plain js error'))).toEqual({ kind: 'unknown' });
    expect(service.parse(undefined)).toEqual({ kind: 'unknown' });
    expect(service.parse(null)).toEqual({ kind: 'unknown' });
    expect(service.parse({ foo: 'bar' })).toEqual({ kind: 'unknown' });
  });

  it('handles HttpErrorResponse with missing body fields', () => {
    const err = new HttpErrorResponse({ status: 500 });
    const result = service.parse(err);
    expect(result.kind).toBe('unknown');
    if (result.kind === 'unknown') {
      expect(result.status).toBe(500);
    }
  });

  it('falls through to unknown for 500 (no matching status+code)', () => {
    const err = new HttpErrorResponse({
      status: 500,
      error: { errorCode: 'internal_error', message: 'boom' },
    });
    const result = service.parse(err);
    expect(result.kind).toBe('unknown');
    if (result.kind === 'unknown') {
      expect(result.status).toBe(500);
      expect(result.errorCode).toBe('internal_error');
    }
  });
});
