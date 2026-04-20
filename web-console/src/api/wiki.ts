/**
 * Wiki API hooks
 *
 * React Query hooks for browsing wiki pages and searching.
 * All endpoints are read-only.
 */

import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import {
  fetchStaticPage,
  fetchStaticSearch,
  fetchStaticStatus,
  fetchStaticTree,
  isStaticWiki,
} from './staticWiki';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WikiPageNode {
  path: string;
  title: string;
  page_type: string;
  difficulty?: string;
  folder: string;
}

export interface WikiTreeResponse {
  domain: string;
  pages: WikiPageNode[];
  total: number;
}

export interface WikiPageDetail {
  domain: string;
  path: string;
  title: string;
  page_type: string;
  body: string;
  frontmatter: Record<string, unknown>;
}

export interface WikiStatusResponse {
  domain: string;
  total_pages: number;
  pages_by_type: Record<string, number>;
  last_updated?: string;
}

export interface WikiSearchResult {
  domain: string;
  page_path: string;
  title: string;
  page_type: string;
  score: number;
  snippet: string;
}

export interface WikiSearchResponse {
  query: string;
  results: WikiSearchResult[];
  total: number;
}

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const wikiKeys = {
  all: ['wiki'] as const,
  tree: (domain: string) => [...wikiKeys.all, 'tree', domain] as const,
  page: (domain: string, path: string) => [...wikiKeys.all, 'page', domain, path] as const,
  status: (domain: string) => [...wikiKeys.all, 'status', domain] as const,
  search: (query: string, domain?: string) => [...wikiKeys.all, 'search', query, domain] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

// In static-wiki mode (VITE_STATIC_WIKI=1) we read pre-rendered JSON shipped
// by the Pages build instead of hitting the FastAPI backend. Same hook names,
// same response shapes — the M1 amprealize.ai preview runs entirely without
// a server. See src/api/staticWiki.ts and scripts/build-static-wiki.mjs.

export function useWikiTree(domain: string) {
  return useQuery({
    queryKey: wikiKeys.tree(domain),
    queryFn: () =>
      isStaticWiki
        ? fetchStaticTree(domain)
        : apiClient.get<WikiTreeResponse>(`/v1/wiki/${encodeURIComponent(domain)}/pages`),
    staleTime: 5 * 60 * 1000,
    enabled: !!domain,
  });
}

export function useWikiPage(domain: string, path: string) {
  return useQuery({
    queryKey: wikiKeys.page(domain, path),
    queryFn: () =>
      isStaticWiki
        ? fetchStaticPage(domain, path)
        : apiClient.get<WikiPageDetail>(
            `/v1/wiki/${encodeURIComponent(domain)}/page?path=${encodeURIComponent(path)}`,
          ),
    staleTime: 5 * 60 * 1000,
    enabled: !!domain && !!path,
  });
}

export function useWikiStatus(domain: string) {
  return useQuery({
    queryKey: wikiKeys.status(domain),
    queryFn: () =>
      isStaticWiki
        ? fetchStaticStatus(domain)
        : apiClient.get<WikiStatusResponse>(`/v1/wiki/${encodeURIComponent(domain)}/status`),
    staleTime: 5 * 60 * 1000,
    enabled: !!domain,
  });
}

export function useWikiSearch(query: string, domain?: string) {
  return useQuery({
    queryKey: wikiKeys.search(query, domain),
    queryFn: () => {
      if (isStaticWiki) return fetchStaticSearch(query, domain);
      const params = new URLSearchParams({ q: query });
      if (domain) params.set('domain', domain);
      return apiClient.get<WikiSearchResponse>(`/v1/wiki/search?${params.toString()}`);
    },
    staleTime: 2 * 60 * 1000,
    enabled: query.length >= 2,
  });
}
