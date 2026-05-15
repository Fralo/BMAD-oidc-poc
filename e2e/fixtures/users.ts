export interface SeededUser {
  readonly username: string;
  readonly password: string;
  readonly subPattern: RegExp;
}

/**
 * The two users seeded by `keycloak/realm-bmad-books.json` (Story 1.2).
 *
 * `subPattern` is a regex (not a literal string) because Keycloak generates
 * the user `sub` UUIDs at realm import time — they are not stable across
 * `docker compose down -v` + re-import cycles. Specs that need to assert
 * something about `sub` should use `subPattern.test(observedSub)`.
 */
export const testuser: SeededUser = {
  username: 'testuser',
  password: 'testpassword',
  subPattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
};

export const freshuser: SeededUser = {
  username: 'freshuser',
  password: 'freshpassword',
  subPattern: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
};
