import { expect, test } from '@playwright/test';

// Smoke: asserts the public-preview (wiki-only) shell is what ships at
// amprealize.ai for M1. The SMOKE_BASE_URL env var is set by the deploy
// workflow (_reusable-release.yml). Locally it falls back to localhost:5173
// when running `npm run dev`.
const BASE_URL = process.env.SMOKE_BASE_URL ?? 'http://localhost:5173';
const API_URL = process.env.SMOKE_API_URL ?? 'https://api.amprealize.ai';

test.describe('amprealize.ai public preview (M1)', () => {
  test('root redirects to /wiki/infra', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForURL(/\/wiki\/infra/);
    expect(page.url()).toContain('/wiki/infra');
  });

  test('sidebar shows only the wiki surface (preview mode)', async ({ page }) => {
    await page.goto(`${BASE_URL}/wiki/infra`);
    await page.waitForLoadState('networkidle');

    // The wiki page ships its own sidebar (WikiSidebar). Confirm the main app
    // sidebar is *not* present — i.e. we're not showing Projects / Agents /
    // Boards while the product shell is still gated.
    const appSidebar = page.getByRole('navigation', { name: /app navigation/i });
    await expect(appSidebar).toHaveCount(0);

    // Wiki sidebar should be there
    const wikiSidebar = page.getByRole('navigation', { name: /wiki/i });
    await expect(wikiSidebar).toBeVisible();
  });

  test('renders an ai-learning article body', async ({ page }) => {
    await page.goto(`${BASE_URL}/wiki/ai-learning`);
    await page.waitForLoadState('networkidle');

    // Article should render real markdown — look for any heading.
    const heading = page.locator('main h1, main h2').first();
    await expect(heading).toBeVisible({ timeout: 10_000 });

    // Any text content beyond the navigation stubs
    const main = page.locator('main');
    const text = (await main.textContent()) ?? '';
    expect(text.length).toBeGreaterThan(200);
  });

  test('api /health responds 200', async ({ request }) => {
    const res = await request.get(`${API_URL}/health`);
    expect(res.status()).toBe(200);
  });

  test('api /api/v1/wiki/infra returns the infra domain', async ({ request }) => {
    // The wiki_api endpoint for a domain manifest / listing. Exact path is
    // `/api/v1/wiki/{domain}` (see amprealize/services/wiki_api.py).
    const res = await request.get(`${API_URL}/api/v1/wiki/infra`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toBeTruthy();
  });
});
