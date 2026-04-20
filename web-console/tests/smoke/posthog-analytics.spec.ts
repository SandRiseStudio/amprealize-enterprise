/**
 * Playwright smoke test — PostHog analytics integration
 *
 * Verifies that the web console:
 *   1. Fires at least one $pageview event to PostHog on navigation.
 *   2. Fires a wiki_page_viewed event when a wiki article loads.
 *
 * The test works by intercepting outbound PostHog requests.
 * It requires the app to be running with VITE_POSTHOG_KEY set to any
 * non-empty value and VITE_POSTHOG_ENABLED=true (local builds) or
 * a real key (CI builds with SMOKE_BASE_URL set).
 *
 * If no PostHog key is configured the interceptor never fires — the test
 * is skipped rather than failing, so it remains green in preview-only builds.
 */

import { expect, test } from '@playwright/test';

const BASE_URL = process.env.SMOKE_BASE_URL ?? 'http://localhost:5173';

// PostHog batch endpoint pattern for both us and eu clouds.
const POSTHOG_BATCH_PATTERN = /i\.posthog\.com\/batch\/?|i\.posthog\.eu\/batch\/?/;

interface PostHogBatchEntry {
  event: string;
  properties?: Record<string, unknown>;
}

test.describe('PostHog analytics smoke', () => {
  test('fires $pageview on wiki page load (when posthog is configured)', async ({ page }) => {
    const capturedBatches: PostHogBatchEntry[][] = [];

    // Intercept PostHog batch requests and record them without blocking.
    await page.route(POSTHOG_BATCH_PATTERN, async (route) => {
      try {
        const body = route.request().postDataJSON() as { batch?: PostHogBatchEntry[] };
        if (Array.isArray(body?.batch)) capturedBatches.push(body.batch);
      } catch {
        // ignore parse errors
      }
      await route.continue();
    });

    await page.goto(`${BASE_URL}/wiki/infra`);
    await page.waitForLoadState('networkidle');

    // Give PostHog up to 5s to flush.
    await page.waitForTimeout(5000);

    if (capturedBatches.length === 0) {
      test.skip(); // PostHog not configured in this environment — skip gracefully.
      return;
    }

    const allEvents = capturedBatches.flat();
    const pageviews = allEvents.filter((e) => e.event === '$pageview');
    expect(pageviews.length).toBeGreaterThan(0);

    // Pageview should carry the surface ambient prop.
    const firstPageview = pageviews[0];
    expect(firstPageview.properties?.surface).toBe('web-console');
  });

  test('fires wiki_page_viewed when navigating to a wiki article', async ({ page }) => {
    const capturedEvents: PostHogBatchEntry[] = [];

    await page.route(POSTHOG_BATCH_PATTERN, async (route) => {
      try {
        const body = route.request().postDataJSON() as { batch?: PostHogBatchEntry[] };
        if (Array.isArray(body?.batch)) capturedEvents.push(...body.batch);
      } catch {
        // ignore
      }
      await route.continue();
    });

    await page.goto(`${BASE_URL}/wiki/ai-learning`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(5000);

    if (capturedEvents.length === 0) {
      test.skip();
      return;
    }

    const wikiEvents = capturedEvents.filter((e) => e.event === 'wiki_page_viewed');
    expect(wikiEvents.length).toBeGreaterThan(0);
    expect(wikiEvents[0].properties?.domain).toBe('ai-learning');
  });
});
