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
 * `AppError` discriminated union (Story 3.5).
 *
 * The parser checks both the HTTP status AND the wire-level `errorCode`
 * field so a server that emits an unexpected envelope shape doesn't get
 * silently coerced into the "wrong" variant. Anything that doesn't match
 * a known (status, errorCode) tuple falls through to `{ kind: 'unknown' }`
 * with the status and message attached so callers can render a generic
 * "Couldn't ... — try again" copy.
 */
@Injectable({ providedIn: 'root' })
export class ErrorService {
  parse(err: unknown): AppError {
    if (!(err instanceof HttpErrorResponse)) {
      return { kind: 'unknown' };
    }
    const body = (err.error ?? {}) as ErrorEnvelope;
    const code = body.errorCode;
    // CR7: classify by status code alone for 503 — a 503 response from an
    // ingress / load balancer / cloud edge will NOT carry the project's
    // ``{errorCode: "resource_server_unavailable"}`` envelope (it's likely
    // HTML or a vendor-specific JSON shape). Falling through to
    // ``{ kind: 'unknown' }`` would render the generic "Couldn't ..." copy
    // for what is genuinely a service-unavailable condition. Map any 503
    // (or 502 / 504) to the named state so UX-DR12 copy is consistent
    // regardless of which proxy in the chain emitted the failure.
    if (err.status === 503 || err.status === 502 || err.status === 504) {
      return { kind: 'resource_server_unavailable' };
    }
    if (err.status === 412 && code === 'reading_speed_unset') {
      return { kind: 'reading_speed_unset' };
    }
    if (err.status === 422 && code === 'invalid_input') {
      return { kind: 'invalid_input', detail: body.detail };
    }
    if (err.status === 403 && code === 'forbidden_scope') {
      return { kind: 'forbidden_scope' };
    }
    return {
      kind: 'unknown',
      status: err.status,
      errorCode: code,
      message: body.message,
    };
  }
}
