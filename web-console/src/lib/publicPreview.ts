/**
 * Public-preview mode helpers.
 *
 * When public-preview mode is on, the SaaS shell ships only the read-only
 * wiki surface: non-wiki sidebar entries are hidden and the root path (`/`)
 * redirects to the default wiki domain. This lets us keep `amprealize.ai`
 * wiki-only even after the authenticated product shell goes live at
 * `app.amprealize.ai` (GUIDEAI-5, M2 origin split).
 *
 * Precedence (most → least authoritative):
 *   1. `window.__AMPREALIZE_PUBLIC_PREVIEW__`  (runtime override — incident
 *      response / manual smoke testing)
 *   2. `VITE_PUBLIC_PREVIEW`                   (build-time env, injected by
 *      Vite; set per Pages project)
 *   3. App origin                              (`marketing` origin always
 *      forces preview mode — the apex must never expose auth routes)
 *   4. `false`                                 (full product shell)
 *
 * The origin-based step guarantees that even a misconfigured Pages project
 * that forgets to set `VITE_PUBLIC_PREVIEW=1` on the apex still behaves
 * correctly when served from `amprealize.ai` at runtime.
 */

import { isMarketingOrigin } from '../config/origin';

const TRUE_VALUES = new Set(['1', 'true', 'yes', 'on']);

declare global {
  interface Window {
    __AMPREALIZE_PUBLIC_PREVIEW__?: boolean | string;
  }
}

export const PREVIEW_REDIRECT_PATH = '/wiki/infra';

function readRuntimeOverride(): boolean | null {
  if (typeof window === 'undefined') return null;
  const raw = window.__AMPREALIZE_PUBLIC_PREVIEW__;
  if (raw === undefined) return null;
  if (typeof raw === 'boolean') return raw;
  return TRUE_VALUES.has(String(raw).toLowerCase());
}

function readBuildFlag(): boolean | null {
  const env = import.meta.env as Record<string, string | undefined>;
  const raw = env.VITE_PUBLIC_PREVIEW;
  if (raw === undefined || raw === null || raw === '') return null;
  return TRUE_VALUES.has(String(raw).toLowerCase());
}

/**
 * Whether the current build (or the active runtime override) is in
 * public-preview mode.
 *
 * Stable, synchronous read — safe to call during render and inside hooks.
 * It does not react to override changes; callers that need live updates
 * should wire up their own listener.
 */
export function isPublicPreview(): boolean {
  const override = readRuntimeOverride();
  if (override !== null) return override;

  const buildFlag = readBuildFlag();
  if (buildFlag !== null) return buildFlag;

  // Belt-and-suspenders: apex origin is always wiki-only even if the build
  // flag was never set. Prevents an unconfigured Pages deploy from ever
  // accidentally exposing the authenticated shell to anonymous visitors.
  if (isMarketingOrigin()) return true;

  return false;
}
