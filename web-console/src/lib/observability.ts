/**
 * Frontend observability bootstrap for amprealize.ai.
 *
 * Wires Sentry for error/perf capture and PostHog for product analytics.
 * When the build was produced with `VITE_PUBLIC_PREVIEW=1`, product-shell-only
 * instrumentation is left out. The module is import-for-side-effect: call
 * `initObservability()` once from `main.tsx` before rendering.
 *
 * Env vars (build-time, injected by Vite):
 *   VITE_SENTRY_DSN         DSN for @sentry/react (empty = disabled)
 *   VITE_SENTRY_ENVIRONMENT prod | preview | dev
 *   VITE_APP_ENV            mirrored into Sentry release tag
 *   VITE_GIT_SHA            injected by CI for release correlation
 *   VITE_POSTHOG_KEY        PostHog project API key (empty = disabled)
 *   VITE_POSTHOG_HOST       Ingest host (default: https://us.i.posthog.com)
 *   VITE_POSTHOG_ENABLED    Set 'true' to force-enable in dev/local builds
 *
 * Sentry is loaded lazily to avoid pulling the vendor bundle on first paint
 * for users who hit the wiki-only preview. If the DSN is not configured at
 * build time, the import is skipped entirely.
 */

import { initPostHog } from './posthog';

interface SentryLike {
  init: (opts: Record<string, unknown>) => void;
  browserTracingIntegration?: () => unknown;
  replayIntegration?: (opts: Record<string, unknown>) => unknown;
}

function env(key: string): string | undefined {
  return (import.meta.env as Record<string, string | undefined>)[key];
}

let initialized = false;

export async function initObservability(): Promise<void> {
  if (initialized) return;
  initialized = true;

  // PostHog initialises synchronously and independently of Sentry.
  initPostHog();

  const dsn = env('VITE_SENTRY_DSN');
  if (!dsn) return;

  let Sentry: SentryLike;
  try {
    const mod: unknown = await (0, eval)("import('@sentry/react')");
    Sentry = mod as SentryLike;
  } catch {
    // Sentry not installed — skip silently. Intended for preview builds where
    // the team has not yet wired the DSN into CI.
    return;
  }

  const integrations: unknown[] = [];
  if (Sentry.browserTracingIntegration) {
    integrations.push(Sentry.browserTracingIntegration());
  }
  if (Sentry.replayIntegration) {
    integrations.push(Sentry.replayIntegration({ maskAllText: false, blockAllMedia: true }));
  }

  Sentry.init({
    dsn,
    environment: env('VITE_SENTRY_ENVIRONMENT') ?? env('VITE_APP_ENV') ?? 'production',
    release: env('VITE_GIT_SHA'),
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 1.0,
    integrations,
    beforeSend(event: { request?: { url?: string } }) {
      const crumb = event.request?.url ?? '';
      if (crumb.includes('localhost') || crumb.includes('127.0.0.1')) {
        return null;
      }
      return event;
    },
  });
}
