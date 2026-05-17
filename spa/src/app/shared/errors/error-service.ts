import { HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';

import { AppError } from './app-error.types';

interface EnvelopeBody {
  errorCode: string;
  message?: string;
  detail?: unknown;
}

function isEnvelope(body: unknown): body is EnvelopeBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    'errorCode' in body &&
    typeof (body as { errorCode: unknown }).errorCode === 'string'
  );
}

@Injectable({ providedIn: 'root' })
export class ErrorService {
  parse(err: unknown): AppError {
    if (!(err instanceof HttpErrorResponse)) {
      return { kind: 'unknown', status: 0 };
    }

    if (err.status === 0) {
      return { kind: 'network' };
    }

    const body: unknown = err.error;

    if (isEnvelope(body)) {
      switch (body.errorCode) {
        case 'session_expired':
          return { kind: 'session_expired' };
        case 'forbidden_scope':
          return { kind: 'forbidden_scope' };
        case 'invalid_input':
          return { kind: 'invalid_input', detail: body.detail };
        case 'book_not_found':
          return { kind: 'book_not_found' };
        case 'csrf_invalid':
          return { kind: 'csrf_invalid' };
        case 'auth_state_invalid':
          return { kind: 'auth_state_invalid' };
        default:
          return { kind: 'unknown', status: err.status };
      }
    }

    // Status-fallback path (non-envelope body)
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
        return { kind: 'unknown', status: err.status };
    }
  }
}
