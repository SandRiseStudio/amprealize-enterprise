/**
 * Fires PostHog $pageview / $pageleave on every react-router location change.
 *
 * Route params that contain numeric IDs (e.g. /projects/42/boards/7) are
 * replaced with the path-parameter name from the route pattern so cardinality
 * stays low in PostHog dashboards:
 *   /projects/42/boards/7  →  /projects/:projectId/boards/:boardId
 *
 * Mount once in AnimatedRoutes (inside <BrowserRouter>) so the hook always
 * runs inside a router context.
 */

import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { capture } from '../lib/posthog';

const PARAM_PATTERNS: Array<[RegExp, string]> = [
  // Order matters — more specific patterns first.
  [/\/projects\/([a-zA-Z0-9_-]{5,})\//g, '/projects/:projectId/'],
  [/\/projects\/([a-zA-Z0-9_-]{5,})$/g, '/projects/:projectId'],
  [/\/boards\/([a-zA-Z0-9_-]{5,})\//g, '/boards/:boardId/'],
  [/\/boards\/([a-zA-Z0-9_-]{5,})$/g, '/boards/:boardId'],
  [/\/items\/([a-zA-Z0-9_-]{5,})\//g, '/items/:itemId/'],
  [/\/items\/([a-zA-Z0-9_-]{5,})$/g, '/items/:itemId'],
  [/\/agents\/([a-zA-Z0-9_-]{5,})\//g, '/agents/:agentId/'],
  [/\/agents\/([a-zA-Z0-9_-]{5,})$/g, '/agents/:agentId'],
  // Pure numeric segments anywhere in the path.
  [/\/\d+\//g, '/:id/'],
  [/\/\d+$/g, '/:id'],
];

function sanitisePath(raw: string): string {
  let path = raw;
  for (const [re, replacement] of PARAM_PATTERNS) {
    // Reset lastIndex before each global replace.
    re.lastIndex = 0;
    path = path.replace(re, replacement);
  }
  return path;
}

export function usePageviewTracking(): void {
  const location = useLocation();
  const prevPathRef = useRef<string | null>(null);

  useEffect(() => {
    const sanitised = sanitisePath(location.pathname);
    const url = `${window.location.origin}${sanitised}${location.search}`;

    // Fire pageleave for the previous route before recording the new pageview.
    if (prevPathRef.current !== null && prevPathRef.current !== sanitised) {
      capture('$pageleave', {
        $current_url: `${window.location.origin}${prevPathRef.current}`,
      });
    }

    capture('$pageview', {
      $current_url: url,
      path: sanitised,
    });

    prevPathRef.current = sanitised;
  }, [location.pathname, location.search]);
}
