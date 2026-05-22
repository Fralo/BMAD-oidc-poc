/**
 * `AppError` discriminated union for the SPA.
 *
 * Each variant corresponds to a wire-level errorCode the BFF or RS emits
 * (architecture §C5). New variants are added as future stories surface
 * new domain errors.
 *
 * `session_expired` (401) is included as a variant for defense-in-depth:
 * the global `withCredentialsInterceptor` (Story 1.9) navigates the user
 * to `/auth/login?return_to=...` before any feature service observes the error,
 * but exposing the kind lets components reason about it when needed.
 *
 * Reference: architecture.md lines 714-731.
 */
export type AppError =
  | { kind: 'session_expired' }
  | { kind: 'network' }
  | { kind: 'reading_speed_unset' }
  | { kind: 'resource_server_unavailable' }
  | { kind: 'invalid_input'; detail?: unknown }
  | { kind: 'forbidden_scope' }
  | { kind: 'book_not_found' }
  | { kind: 'csrf_invalid' }
  | { kind: 'auth_state_invalid' }
  | {
      kind: 'unknown';
      status?: number;
      errorCode?: string;
      message?: string;
    };
