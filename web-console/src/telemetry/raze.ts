/**
 * Raze telemetry helper (web console)
 *
 * Following `behavior_use_raze_for_logging` (Student):
 * - Use structured logs
 * - Include actor_surface
 * - Fail open (never break UX on telemetry failures)
 */

import { apiClient, ApiError } from '../api/client';

export type RazeLogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

export interface RazeLogContext {
  [key: string]: unknown;
}

/**
 * Client-side perf breadcrumb. Records a `window.__perfMarks` entry and a
 * `performance.mark('perf:<name>')` so harnesses and DevTools can read
 * milestones without any server round-trip.
 */
interface PerfMarkEntry {
  name: string;
  t: number;
  epoch: number;
  context?: RazeLogContext;
}

declare global {
  interface Window {
    __perfMarks?: PerfMarkEntry[];
  }
}

export function perfMark(name: string, context: RazeLogContext = {}): void {
  try {
    if (typeof window === 'undefined') return;
    const t = typeof performance !== 'undefined' ? performance.now() : 0;
    const epoch = Date.now();
    if (!window.__perfMarks) {
      window.__perfMarks = [];
    }
    window.__perfMarks.push({ name, t, epoch, context });
    if (typeof performance !== 'undefined' && typeof performance.mark === 'function') {
      performance.mark(`perf:${name}`);
    }
  } catch {
    // Never let instrumentation break the page.
  }
}

let razeIngestDisabled = false;

export async function razeLog(
  level: RazeLogLevel,
  message: string,
  context: RazeLogContext = {}
): Promise<void> {
  if (razeIngestDisabled) return;

  try {
    await apiClient.post(
      '/v1/logs/ingest',
      {
        logs: [
          {
            level,
            message,
            service: 'web-console',
            actor_surface: 'web',
            context,
          },
        ],
      }
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      razeIngestDisabled = true;
      return;
    }
    if (import.meta.env.DEV) {
      // Keep local signal without spamming production console.
      console.debug('[Raze][ingest failed]', message, error);
    }
  }
}
