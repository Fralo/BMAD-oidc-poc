/**
 * `AppError` discriminated union for the SPA (Story 3.5).
 *
 * Each variant corresponds to a wire-level errorCode the BFF emits (see
 * architecture §C5). New variants are added as future stories surface new
 * domain errors. `session_expired` (401) is intentionally NOT a variant:
 * the global `withCredentialsInterceptor` (Story 1.9) navigates the user
 * to `/login?return_to=...` before any feature service observes the error.
 *
 * Reference: architecture.md lines 714-731.
 */
export type AppError =
  | { kind: 'reading_speed_unset' }
  | { kind: 'resource_server_unavailable' }
  | { kind: 'invalid_input'; detail?: unknown }
  | { kind: 'forbidden_scope' }
  | {
      kind: 'unknown';
      status?: number;
      errorCode?: string;
      message?: string;
    };
