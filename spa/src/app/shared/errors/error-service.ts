import { HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';

import { AppError } from './app-error.types';

/**
 * The shape every BFF + RS error response shares: `{errorCode, message, detail}`.
 * Matches architecture §C5 / §"Format Patterns".
 */
interface ErrorEnvelope {
  errorCode?: string;
  message?: string;
  detail?: unknown;
}

/**
 * Parse an `HttpErrorResponse` (or any unknown error) into a typed
 * `AppError` discriminated union.
 *
 * The parser checks both the HTTP status AND the wire-level `errorCode`
 * field so a server that emits an unexpected envelope shape doesn't get
 * silently coerced into the "wrong" variant. Anything that doesn't match
 * a known (status, errorCode) tuple falls through to `{ kind: 'unknown' }`
 * with the status / errorCode / message attached so callers can render a
 * generic "Couldn't ... — try again" copy.
 *
 * Order of classification:
 *  1. Non-HttpErrorResponse                            → `unknown`
 *  2. status 0 (browser-side network failure)          → `network`
 *  3. status 502/503/504 (proxy/gateway/service)       → `resource_server_unavailable`
 *     CR7 (Story 3.5): a proxy / load balancer / cloud edge 503 will NOT
 *     carry the project envelope; classifying by status alone keeps the
 *     UX-DR12 copy consistent regardless of which hop emitted the failure.
 *  4. (status, errorCode) tuple match                  → the named variant
 *  5. Status-only fallback (for non-envelope bodies)   → the named variant
 *  6. Otherwise                                        → `unknown`
 */
@Injectable({ providedIn: 'root' })
export class ErrorService {
  parse(err: unknown): AppError {
    if (!(err instanceof HttpErrorResponse)) {
      return { kind: 'unknown' };
    }

    if (err.status === 0) {
      return { kind: 'network' };
    }

    if (err.status === 503 || err.status === 502 || err.status === 504) {
      return { kind: 'resource_server_unavailable' };
    }

    const body = (err.error ?? {}) as ErrorEnvelope;
    const code = body.errorCode;

    // (status, errorCode) tuple matches — most-specific path.
    if (err.status === 412 && code === 'reading_speed_unset') {
      return { kind: 'reading_speed_unset' };
    }
    if (err.status === 422 && code === 'invalid_input') {
      return { kind: 'invalid_input', detail: body.detail };
    }
    if (err.status === 403 && code === 'forbidden_scope') {
      return { kind: 'forbidden_scope' };
    }
    if (err.status === 403 && code === 'csrf_invalid') {
      return { kind: 'csrf_invalid' };
    }
    if (err.status === 404 && code === 'book_not_found') {
      return { kind: 'book_not_found' };
    }
    if (err.status === 400 && code === 'auth_state_invalid') {
      return { kind: 'auth_state_invalid' };
    }
    if (err.status === 401 && code === 'session_expired') {
      return { kind: 'session_expired' };
    }

    // errorCode-only (status didn't match the canonical pairing — defensive).
    switch (code) {
      case 'session_expired':
        return { kind: 'session_expired' };
      case 'forbidden_scope':
        return { kind: 'forbidden_scope' };
      case 'csrf_invalid':
        return { kind: 'csrf_invalid' };
      case 'auth_state_invalid':
        return { kind: 'auth_state_invalid' };
      case 'book_not_found':
        return { kind: 'book_not_found' };
      case 'invalid_input':
        return { kind: 'invalid_input', detail: body.detail };
      case 'reading_speed_unset':
        return { kind: 'reading_speed_unset' };
      case 'resource_server_unavailable':
        return { kind: 'resource_server_unavailable' };
    }

    // Status-only fallback (non-envelope body).
    switch (err.status) {
      case 401:
        return { kind: 'session_expired' };
      case 403:
        return { kind: 'csrf_invalid' };
      case 404:
        return { kind: 'book_not_found' };
      case 422:
        return { kind: 'invalid_input', detail: undefined };
      default:
        return {
          kind: 'unknown',
          status: err.status,
          errorCode: code,
          message: body.message,
        };
    }
  }
}
