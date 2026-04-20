import { expect, test } from '@playwright/test';

// Smoke: asserts the authenticated console shell at app.amprealize.ai (M2+).
//
// These tests run when deploy-prod-console.yml ships with VITE_PUBLIC_PREVIEW=0.
// They are intentionally skipped when SMOKE_ORIGIN is not 'console' so the same
// test suite can be run against both origins without false failures.
//
// Env vars (injected by _reusable-release.yml):
//   SMOKE_BASE_URL   – e.g. https://app.amprealize.ai   (set per origin)
//   SMOKE_API_URL    – e.g. https://api.amprealize.ai
//   SMOKE_ORIGIN     – 'console' | 'marketing' (optional; defaults from hostname)

const BASE_URL = process.env.SMOKE_BASE_URL ?? 'http://localhost:5173';
const API_URL = process.env.SMOKE_API_URL ?? 'https://api.amprealize.ai';

// Derive whether we are running against the console origin. Honour the
// explicit env var first; fall back to sniffing the hostname from BASE_URL.
function isConsoleOrigin(): boolean {
  if (process.env.SMOKE_ORIGIN) return process.env.SMOKE_ORIGIN === 'console';
  try {
    return new URL(BASE_URL).hostname.startsWith('app.');
  } catch {
    return false;
  }
}

const describeConsole = isConsoleOrigin() ? test.describe : test.describe.skip;

describeConsole('app.amprealize.ai authenticated console (M2)', () => {
  // ── Crawl hygiene ──────────────────────────────────────────────────────────

  test('robots.txt disallows all crawlers', async ({ request }) => {
    const res = await request.get(`${BASE_URL}/robots.txt`);
    expect(res.status()).toBe(200);
    const body = await res.text();
    expect(body).toContain('Disallow: /');
  });

  test('index.html carries noindex meta', async ({ request }) => {
    const res = await request.get(BASE_URL);
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toMatch(/name="robots"[^>]*content="noindex/i);
  });

  // ── Auth surface ───────────────────────────────────────────────────────────

  test('unauthenticated root redirects to /login', async ({ page }) => {
    // Navigate without any stored session; the ProtectedRoute should bounce to login.
    await page.goto(BASE_URL);
    await page.waitForURL(/\/login/, { timeout: 10_000 });
    expect(page.url()).toContain('/login');
  });

  test('login page renders the sign-in form', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');

    // Device-flow button or an OAuth "Continue with…" button — either proves
    // the login surface loaded, not a blank page or error screen.
    const loginCta = page.locator(
      'button:has-text("Sign in"), button:has-text("Continue with"), button:has-text("Log in")',
    ).first();
    await expect(loginCta).toBeVisible({ timeout: 10_000 });
  });

  test('unauthenticated /api/v1/capabilities returns route flags', async ({ request }) => {
    // capabilities endpoint is explicitly skip-authed; returns JSON with route flags.
    const res = await request.get(`${API_URL}/api/v1/capabilities`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('routes');
  });

  // ── No wiki-only redirect (console ≠ marketing apex) ──────────────────────

  test('root does NOT redirect to /wiki/infra', async ({ page }) => {
    await page.goto(BASE_URL);
    // Give any redirect time to settle — it should end up at /login, not /wiki/infra.
    await page.waitForLoadState('networkidle');
    expect(page.url()).not.toContain('/wiki/infra');
  });
});
