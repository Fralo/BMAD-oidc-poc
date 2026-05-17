export type AppError =
  | { kind: 'session_expired' }
  | { kind: 'forbidden_scope' }
  | { kind: 'invalid_input'; detail?: unknown }
  | { kind: 'book_not_found' }
  | { kind: 'csrf_invalid' }
  | { kind: 'auth_state_invalid' }
  | { kind: 'network' }
  | { kind: 'unknown'; status: number };
