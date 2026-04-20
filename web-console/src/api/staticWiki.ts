/**
 * Static-wiki mode.
 *
 * When the build sets `VITE_STATIC_WIKI=1`, `src/api/wiki.ts` dispatches to
 * the functions here instead of hitting the FastAPI backend. Content is
 * pre-rendered by `scripts/build-static-wiki.mjs` into
 * `public/_wiki/**` and served as static files by Cloudflare Pages.
 *
 * This is the M1 launch path for amprealize.ai — no backend required.
 * Once the Fly/Neon stack is provisioned we flip the flag off and the
 * same hooks go back to calling `/api/v1/wiki/*`.
 */

import type {
  WikiPageDetail,
  WikiSearchResponse,
  WikiSearchResult,
  WikiStatusResponse,
  WikiTreeResponse,
} from './wiki';

const STATIC_ROOT = '/_wiki';

function isStaticEnv(): boolean {
  const raw = (import.meta.env as Record<string, string | undefined>).VITE_STATIC_WIKI;
  if (!raw) return false;
  return ['1', 'true', 'yes', 'on'].includes(String(raw).toLowerCase());
}

export const isStaticWiki = isStaticEnv();

function pathToSlug(p: string): string {
  // base64url encoding — must match build-static-wiki.mjs. btoa expects
  // latin1, so UTF-8 chars are first encoded and then passed through
  // unescape to reduce to a byte string.
  const b64 = btoa(unescape(encodeURIComponent(p)));
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`Static wiki fetch failed: ${res.status} ${url}`);
  }
  return (await res.json()) as T;
}

export function fetchStaticTree(domain: string): Promise<WikiTreeResponse> {
  return fetchJson<WikiTreeResponse>(`${STATIC_ROOT}/${encodeURIComponent(domain)}/pages.json`);
}

export function fetchStaticStatus(domain: string): Promise<WikiStatusResponse> {
  return fetchJson<WikiStatusResponse>(`${STATIC_ROOT}/${encodeURIComponent(domain)}/status.json`);
}

export function fetchStaticPage(domain: string, path: string): Promise<WikiPageDetail> {
  const slug = pathToSlug(path);
  return fetchJson<WikiPageDetail>(
    `${STATIC_ROOT}/${encodeURIComponent(domain)}/pages/${slug}.json`,
  );
}

interface SearchIndexEntry {
  domain: string;
  page_path: string;
  title: string;
  page_type: string;
  body: string;
}

interface SearchIndex {
  entries: SearchIndexEntry[];
}

let _searchIndexPromise: Promise<SearchIndex> | null = null;

function loadSearchIndex(): Promise<SearchIndex> {
  _searchIndexPromise ??= fetchJson<SearchIndex>(`${STATIC_ROOT}/search-index.json`);
  return _searchIndexPromise;
}

export async function fetchStaticSearch(
  query: string,
  domain?: string,
  maxResults = 20,
): Promise<WikiSearchResponse> {
  const q = query.trim().toLowerCase();
  if (q.length < 2) {
    return { query, results: [], total: 0 };
  }

  const { entries } = await loadSearchIndex();
  const results: WikiSearchResult[] = [];

  for (const e of entries) {
    if (domain && e.domain !== domain) continue;
    const titleHits = countOccurrences(e.title.toLowerCase(), q);
    const bodyHits = countOccurrences(e.body.toLowerCase(), q);
    if (titleHits + bodyHits === 0) continue;

    const score = titleHits * 5 + bodyHits;
    const snippet = snippetAround(e.body, q);

    results.push({
      domain: e.domain,
      page_path: e.page_path,
      title: e.title,
      page_type: e.page_type,
      score,
      snippet,
    });
  }

  results.sort((a, b) => b.score - a.score);
  const limited = results.slice(0, maxResults);
  return { query, results: limited, total: limited.length };
}

function countOccurrences(haystack: string, needle: string): number {
  if (!needle) return 0;
  let count = 0;
  let idx = 0;
  while ((idx = haystack.indexOf(needle, idx)) !== -1) {
    count += 1;
    idx += needle.length;
  }
  return count;
}

function snippetAround(body: string, needle: string, radius = 120): string {
  const lower = body.toLowerCase();
  const idx = lower.indexOf(needle);
  if (idx === -1) {
    return body.slice(0, radius).trim();
  }
  const start = Math.max(0, idx - radius / 2);
  const end = Math.min(body.length, idx + needle.length + radius / 2);
  const prefix = start > 0 ? '…' : '';
  const suffix = end < body.length ? '…' : '';
  return `${prefix}${body.slice(start, end).replace(/\s+/g, ' ').trim()}${suffix}`.slice(0, 200);
}
