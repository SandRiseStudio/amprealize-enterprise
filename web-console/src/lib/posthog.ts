/**
 * PostHog product analytics wrapper for amprealize web console.
 *
 * Mirrors the Raze opt-out pattern: never throws, fails open, honours
 * `localStorage['amprealize.posthog'] === 'off'` for user-level opt-out.
 *
 * Env vars (build-time, injected by Vite):
 *   VITE_POSTHOG_KEY          PostHog project API key (empty = disabled)
 *   VITE_POSTHOG_HOST         Ingest host (default: https://us.i.posthog.com)
 *   VITE_POSTHOG_ENABLED      Set to 'true' to force-enable in dev/local builds
 *   VITE_GIT_SHA              Injected by CI — attached as `git_sha` on every event
 */

import posthog from 'posthog-js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PostHogUserProps {
  id: string;
  email?: string;
  displayName?: string;
  tenantId?: string;
  edition?: string;
}

export interface PostHogEventProps {
  [key: string]: string | number | boolean | null | undefined;
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

function envStr(key: string): string | undefined {
  return (import.meta.env as Record<string, string | undefined>)[key];
}

function isLocalhost(): boolean {
  if (typeof window === 'undefined') return false;
  const { hostname } = window.location;
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
}

function isOptedOut(): boolean {
  try {
    if (typeof window === 'undefined') return false;
    return window.localStorage?.getItem('amprealize.posthog') === 'off';
  } catch {
    return false;
  }
}

let _initialized = false;

// Ambient properties attached to every capture() call.
const _ambient: PostHogEventProps = {};

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

export function initPostHog(): void {
  if (_initialized) return;

  const key = envStr('VITE_POSTHOG_KEY');
  if (!key) return;

  const forceEnabled = envStr('VITE_POSTHOG_ENABLED') === 'true';
  if (isLocalhost() && !forceEnabled) return;

  if (isOptedOut()) return;

  const host = envStr('VITE_POSTHOG_HOST') ?? 'https://us.i.posthog.com';
  const gitSha = envStr('VITE_GIT_SHA');

  posthog.init(key, {
    api_host: host,
    ui_host: 'https://us.posthog.com',

    // Autocapture and page-leave events are managed manually via the router
    // hook so we can sanitise route params before they hit the network.
    capture_pageview: false,
    capture_pageleave: false,

    // Session replay — aggressive masking per plan.
    session_recording: {
      maskAllInputs: true,
    },

    // PostHog JS v1.x replay config lives under session_recording; the maskAll*
    // surface-level props are also accepted at runtime by older bundles but
    // were dropped from the TS types. Cast through `unknown` to preserve the
    // defensive mask without angering the compiler.
    ...({ mask_all_text: true, block_all_media: true } as unknown as Record<string, unknown>),

    persistence: 'localStorage+cookie',

    loaded(ph) {
      if (gitSha) ph.register_once({ git_sha: gitSha });
    },
  });

  _initialized = true;

  if (gitSha) _ambient.git_sha = gitSha;
  _ambient.surface = 'web-console';
}

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export function identifyUser(user: PostHogUserProps): void {
  if (!_initialized) return;
  try {
    posthog.identify(user.id, {
      email: user.email,
      name: user.displayName,
      tenant_id: user.tenantId,
      edition: user.edition,
    });
    // Keep ambient props so every subsequent event carries them.
    if (user.tenantId) _ambient.tenant_id = user.tenantId;
    if (user.edition) _ambient.edition = user.edition;
  } catch {
    // Never crash the host app.
  }
}

export function resetUser(): void {
  if (!_initialized) return;
  try {
    posthog.reset();
    delete _ambient.tenant_id;
    delete _ambient.edition;
  } catch {
    // Never crash the host app.
  }
}

export function setPersonProperties(props: PostHogEventProps): void {
  if (!_initialized) return;
  try {
    posthog.setPersonProperties(props);
  } catch {
    // Never crash the host app.
  }
}

// ---------------------------------------------------------------------------
// Event capture
// ---------------------------------------------------------------------------

export function capture(event: string, props?: PostHogEventProps): void {
  if (!_initialized) return;
  if (isOptedOut()) return;
  try {
    posthog.capture(event, { ..._ambient, ...props });
  } catch {
    // Never crash the host app.
  }
}

// ---------------------------------------------------------------------------
// Opt-out helpers (for a settings UI)
// ---------------------------------------------------------------------------

export function optOut(): void {
  try {
    window.localStorage?.setItem('amprealize.posthog', 'off');
    if (_initialized) posthog.opt_out_capturing();
  } catch {
    // ignore
  }
}

export function optIn(): void {
  try {
    window.localStorage?.removeItem('amprealize.posthog');
    if (_initialized) posthog.opt_in_capturing();
  } catch {
    // ignore
  }
}

/** Expose the underlying instance for advanced use (feature flags, etc.). */
export { posthog as posthogClient };
