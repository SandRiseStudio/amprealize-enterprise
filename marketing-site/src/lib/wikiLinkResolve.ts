/**
 * Wiki relative link resolution — matches web-console `wikiData.resolveWikiHref`
 * (see WikiArticle ReactMarkdown `components.a`).
 */

export type WikiDomain = 'infra' | 'platform' | 'ai-learning' | 'research';

const DOMAINS = new Set<string>(['infra', 'platform', 'ai-learning', 'research']);

export function isWikiDomain(value: string | undefined): value is WikiDomain {
  return value === 'infra' || value === 'platform' || value === 'ai-learning' || value === 'research';
}

export function normalizeWikiLink(link: string): string | null {
  const withoutAnchor = link.split('#')[0]?.trim();
  if (!withoutAnchor || !withoutAnchor.endsWith('.md')) return null;

  return withoutAnchor
    .replace(/^\.\//, '')
    .replace(/^\.\.\//, '')
    .replace(/^\.\.\/\.\.\//, '')
    .replace(/^\.\.\/\.\.\/\.\.\//, '')
    .replace(/^\/+/, '');
}

export function resolveWikiHref(
  currentDomain: WikiDomain,
  currentPath: string,
  href: string,
): { domain: WikiDomain; path: string } | null {
  const cleanHref = href.split('#')[0]?.trim();
  if (!cleanHref) return null;
  if (/^(https?:|mailto:|tel:)/i.test(cleanHref)) return null;

  const currentDir = currentPath.split('/').slice(0, -1);
  const seed = cleanHref.startsWith('/') ? [] : currentDir;
  const rawParts = [...seed, ...cleanHref.replace(/^\/+/, '').split('/')];
  const parts: string[] = [];

  for (const part of rawParts) {
    if (!part || part === '.') continue;
    if (part === '..') {
      parts.pop();
      continue;
    }
    parts.push(part);
  }

  if (!parts.length) return null;
  if (parts[0] === 'wiki') parts.shift();

  let domain = currentDomain;
  if (parts[0] && DOMAINS.has(parts[0])) {
    const next = parts.shift()!;
    domain = next as WikiDomain;
  }

  const path = parts.join('/');
  if (!path.endsWith('.md')) return null;
  return { domain, path };
}

/** Resolved marketing URL path including hash fragment (for in-page anchors). */
export function resolveWikiMarketingUrl(
  currentDomain: WikiDomain,
  currentPath: string,
  href: string,
): string | null {
  const hash = href.includes('#') ? href.slice(href.indexOf('#')) : '';
  const base = href.split('#')[0]?.trim() ?? '';
  const target = resolveWikiHref(currentDomain, currentPath, base);
  if (!target) return null;
  return `/wiki/${target.domain}/${target.path}${hash}`;
}
