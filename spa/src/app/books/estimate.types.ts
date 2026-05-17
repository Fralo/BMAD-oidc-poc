/**
 * Wire shape returned by `POST /v1/books/{id}/estimate` (Story 4.2 / 4.1).
 *
 * `snake_case` per AR16 — the SPA does NOT case-convert between wire and
 * model. `minutes` is a non-negative integer (RS contract: `int ge=0`).
 * `formatted` is the verbatim duration string the RS produces via
 * `format_duration` (e.g., `"≈ 4 h 20 m"`, leading `≈` is U+2248 ALMOST
 * EQUAL TO). The SPA renders `formatted` directly — it MUST NOT reformat
 * `minutes` itself.
 */
export interface EstimateOut {
  minutes: number;
  formatted: string;
}
