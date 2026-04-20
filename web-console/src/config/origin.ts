/**
 * App origin helpers for the `amprealize.ai` / `app.amprealize.ai` split.
 *
 * We ship a single `web-console` build to two Cloudflare Pages projects:
 *   - `amprealize-web`      → `amprealize.ai`       (marketing / wiki stopgap)
 *   - `amprealize-console`  → `app.amprealize.ai`   (authenticated SaaS shell)
 *
 * The two builds are identical code; only the `VITE_APP_ORIGIN` env var and
 * the `VITE_PUBLIC_PREVIEW` flag differ. See
 * `docs/runbooks/APP_ORIGIN_SPLIT.md` for the full deploy + rollback flow.
 *
 * Resolution order (most → least authoritative):
 *   1. Build-time `VITE_APP_ORIGIN` (`marketing` | `console`)
 *   2. Runtime hostname sniff — `app.amprealize.ai` → console, anything
 *      else → marketing. Covers local dev (`localhost`) and preview deploys
 *      where the env var may not be set.
 *   3. Default → `console` (matches local `npm run dev` behaviour, which
 *      develops the full product shell).
 */

export type AppOrigin = 'marketing' | 'console';

const CONSOLE_HOSTNAMES = new Set<string>([
  'app.amprealize.ai',
  'app.staging.amprealize.ai',
]);

function readBuildOrigin(): AppOrigin | null {
  const env = import.meta.env as Record<string, string | undefined>;
  const raw = env.VITE_APP_ORIGIN;
  if (raw === 'marketing' || raw === 'console') return raw;
  return null;
}

function readRuntimeOrigin(): AppOrigin | null {
  if (typeof window === 'undefined') return null;
  const host = window.location.hostname.toLowerCase();
  if (CONSOLE_HOSTNAMES.has(host)) return 'console';
  // Any `amprealize.ai` or `www.amprealize.ai` is the marketing / apex build.
  if (host === 'amprealize.ai' || host === 'www.amprealize.ai') return 'marketing';
  return null;
}

/**
 * Resolve the current app origin. Safe to call during render.
 *
 * Prefers the build-time flag so SSR / prerender paths behave consistently,
 * then falls back to hostname sniffing, then to `'console'` as the dev
 * default.
 */
export function getAppOrigin(): AppOrigin {
  return readBuildOrigin() ?? readRuntimeOrigin() ?? 'console';
}

export function isConsoleOrigin(): boolean {
  return getAppOrigin() === 'console';
}

export function isMarketingOrigin(): boolean {
  return getAppOrigin() === 'marketing';
}
