/**
 * Compose-CLI plumbing for the Playwright harness (Story 3.6).
 *
 * This module exists so `helpers.ts` can stay a thin facade over the
 * test-facing API (`logInAs`, `resetState`, `killRs`, `startRs`). The
 * host-process plumbing — `execFile`, `docker compose` invocations, JSON
 * parsing, healthcheck polling — lives here. Splitting the two makes the
 * harness easier to mock if anyone later writes a meta-spec for it
 * (mocking `child_process` from inside `helpers.ts` would be awkward).
 *
 * Used by the J4 spec (this story) and Epic 4's J6 spec (Story 4.4).
 *
 * Runtime contract:
 * - The runner must have the `docker` CLI + `compose` plugin installed
 *   (e2e/Dockerfile, Story 3.6) and `/var/run/docker.sock` bound from
 *   the host (compose/app.yml playwright service, Story 3.6).
 * - `COMPOSE_PROJECT_NAME` must match the host stack's project name
 *   (e.g., `bmad-books`) so `docker compose stop|start resource-server`
 *   targets the right container — `compose/app.yml` pins it.
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const RS_SERVICE = 'resource-server';

/**
 * Run a `docker` subcommand with `execFile` (no shell — args are passed
 * literally, injection-safe). Captures stdout + stderr; on rejection
 * re-throws with both streams in the message so failing CI runs have
 * the diagnostic inline.
 */
async function runDocker(args: readonly string[]): Promise<{ stdout: string; stderr: string }> {
  try {
    const { stdout, stderr } = await execFileAsync('docker', args, {
      encoding: 'utf8',
    });
    return { stdout, stderr };
  } catch (err) {
    // execFile rejects with an Error augmented with stdout/stderr/code.
    const e = err as Error & { stdout?: string; stderr?: string; code?: number };
    const msg = [
      `docker ${args.join(' ')} failed`,
      e.code !== undefined ? `(exit ${e.code})` : '',
      e.stdout ? `\nstdout: ${e.stdout}` : '',
      e.stderr ? `\nstderr: ${e.stderr}` : '',
      `\nerror: ${e.message}`,
    ]
      .filter(Boolean)
      .join(' ');
    throw new Error(msg);
  }
}

/**
 * Returns true if the resource-server container is in a state where it
 * would still respond to TCP/HTTP — `running`, `paused`, or `restarting`.
 * Returns false only for `exited`, `dead`, `created`, or `removing`.
 *
 * Why include `paused`: review patch P2. A paused container's TCP
 * sockets stay open (only its processes are frozen via SIGSTOP); from
 * `killRs`'s perspective, "is RS able to serve / do we still need to
 * stop it?" the answer is yes. Treating `paused` as not-running made
 * `killRs` a no-op while `/v1/reading-speed` could still be reached on
 * old in-flight requests, producing false-green J4 RS-down tests.
 *
 * Throws if `docker compose ps` finds no container at all — that means
 * either the service name doesn't exist in the project, or
 * `COMPOSE_PROJECT_NAME` is misaligned. Silent-false would mask both
 * misconfigs as "RS already stopped" and skip the kill (review P2).
 *
 * Uses `--all` so stopped containers still show up in stdout (without
 * `--all`, compose v2 omits non-running containers from `ps`, and we
 * couldn't distinguish "stopped" from "doesn't exist").
 *
 * Compose v2.20+ emits NDJSON from `docker compose ps --format json`
 * (one object per line). Older v2.x emits a single JSON array. Parse
 * both shapes defensively.
 */
const _ACTIVE_STATES = new Set(['running', 'paused', 'restarting']);

export async function isRsRunning(): Promise<boolean> {
  const { stdout } = await runDocker(['compose', 'ps', '--all', '--format', 'json', RS_SERVICE]);
  const trimmed = stdout.trim();
  if (trimmed.length === 0) {
    throw new Error(
      `isRsRunning: no '${RS_SERVICE}' container found in this compose project. ` +
        `Check COMPOSE_PROJECT_NAME (currently '${process.env.COMPOSE_PROJECT_NAME ?? '<unset>'}') ` +
        `and that the service name is '${RS_SERVICE}'.`,
    );
  }

  const states: string[] = [];

  // Shape (A): single JSON array — older v2.x.
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (Array.isArray(parsed)) {
      for (const entry of parsed) {
        if (typeof entry === 'object' && entry !== null) {
          const s = (entry as { State?: string }).State;
          if (s) states.push(s);
        }
      }
    } else if (typeof parsed === 'object' && parsed !== null) {
      // Shape (C): single object (older v2.x for one-service queries).
      const s = (parsed as { State?: string }).State;
      if (s) states.push(s);
    }
  } catch {
    // Shape (B): NDJSON — one object per line, v2.20+.
    for (const line of trimmed.split('\n')) {
      const ln = line.trim();
      if (!ln) continue;
      try {
        const obj = JSON.parse(ln) as { State?: string };
        if (obj.State) states.push(obj.State);
      } catch {
        // Ignore non-JSON lines (defensive — shouldn't happen).
      }
    }
  }

  if (states.length === 0) {
    throw new Error(
      `isRsRunning: '${RS_SERVICE}' container present but produced no parseable State field. Raw output: ${trimmed.slice(0, 200)}`,
    );
  }
  return states.some((s) => _ACTIVE_STATES.has(s));
}

/**
 * Poll `docker inspect --format '{{.State.Health.Status}}' resource-server`
 * every 500ms until the trimmed stdout equals `healthy`. Throws on timeout
 * (default 30s) with the last observed status in the error message.
 *
 * The RS has a healthcheck declared in `compose/app.yml` (Story 3.1), so
 * `none` should never appear — the status will cycle `starting` → `healthy`
 * (or `starting` → `unhealthy` on a real failure).
 */
export async function waitForRsHealthy(timeoutMs = 30_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let last = '<no status yet>';
  while (Date.now() < deadline) {
    try {
      const { stdout } = await runDocker([
        'inspect',
        '--format',
        '{{.State.Health.Status}}',
        RS_SERVICE,
      ]);
      last = stdout.trim();
      if (last === 'healthy') return;
      // Review patch P3: `<no value>` is Go template's nil-deref output —
      // emitted when `.State.Health` is nil because no HEALTHCHECK is
      // declared (or the container was removed). Polling for 30s in that
      // case wastes a test budget on a config error. Fail fast with a
      // clearer signal than a generic timeout.
      if (last === '<no value>') {
        throw new Error(
          `waitForRsHealthy: '${RS_SERVICE}' has no healthcheck declared (docker inspect returned '<no value>'). ` +
            `Expected the Story 3.1 HEALTHCHECK on compose/app.yml:89-97 to be active.`,
        );
      }
    } catch (err) {
      // Re-throw the P3 fast-fail; absorb other inspect errors (container
      // may not exist yet during a fast stop/start cycle — transient).
      if (err instanceof Error && err.message.startsWith('waitForRsHealthy:')) {
        throw err;
      }
      last = `inspect-error: ${(err as Error).message}`;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`RS did not become healthy within ${timeoutMs}ms; last status: ${last}`);
}

/**
 * Stops the resource-server container. Does NOT wait for `exited` —
 * callers that care about state should follow up with `isRsRunning()`.
 */
export async function stopRs(): Promise<void> {
  await runDocker(['compose', 'stop', RS_SERVICE]);
}

/**
 * Starts the resource-server container. Does NOT wait for healthy —
 * the higher-level `startRs` in `helpers.ts` composes this with
 * `waitForRsHealthy` so callers always get a usable RS on return.
 */
export async function startRs(): Promise<void> {
  await runDocker(['compose', 'start', RS_SERVICE]);
}
