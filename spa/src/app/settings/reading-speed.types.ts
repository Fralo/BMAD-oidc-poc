/**
 * Wire shape emitted by GET / PUT `/v1/reading-speed` (Story 3.5).
 *
 * `snake_case` per AR16 — the SPA does NOT case-convert between wire and
 * model. The `pagesPerHour` signal on `ReadingSpeedService` is the SPA's
 * idiomatic camelCase name; the wire field stays `pages_per_hour`.
 */
export interface ReadingSpeedOut {
  pages_per_hour: number;
}
