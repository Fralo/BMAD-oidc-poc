import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the Reading Time Estimator E2E harness (Story 1.11).
 *
 * `workers: 1` is LOAD-BEARING: every spec calls `resetState(request, { resetToken })`
 * in a `beforeEach` (per Story 1.13 onward). Parallel workers would have two specs
 * simultaneously truncating + re-seeding the BFF's sessions/auth_states tables,
 * producing nondeterministic interleavings. Do NOT raise this without first
 * redesigning the test-reset contract.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
