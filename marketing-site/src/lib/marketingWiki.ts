import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';
import { renderWikiMarkdownToHtml } from './wikiMarkdownRender';

/**
 * Monorepo root (`amprealize-enterprise/`). Prefer `process.cwd()` because Vite
 * may rewrite `import.meta.url` during Astro build, breaking depth-based paths.
 */
function monorepoRoot(): string {
  const cwd = process.cwd();
  if (path.basename(cwd) === 'marketing-site') {
    return path.resolve(cwd, '..');
  }
  return path.resolve(fileURLToPath(new URL('../../..', import.meta.url)));
}

const wikiMarkdownRoot = path.join(monorepoRoot(), 'wiki');

export type WikiNavPage = {
  path: string;
  title: string;
  pageType?: string;
  folder?: string;
};

export type WikiNavGroup = {
  folder: string;
  label: string;
  pages?: WikiNavPage[];
};

export type WikiNavDomain = {
  id: string;
  label: string;
  groups: WikiNavGroup[];
};

export type MarketingWikiNav = {
  domains: WikiNavDomain[];
  defaultDomain: string;
  defaultPath: string | null;
};

export function folderLabel(folder: string): string {
  if (!folder) return 'Pages';
  const last = folder.split('/').pop() ?? folder;
  return last.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function wikiMarkdownAbsPath(domain: string, pagePath: string): string {
  return path.join(wikiMarkdownRoot, domain, pagePath);
}

export function wikiMarkdownExists(domain: string, pagePath: string): boolean {
  try {
    return fs.statSync(wikiMarkdownAbsPath(domain, pagePath)).isFile();
  } catch {
    return false;
  }
}

/** Same ordering as web-console `groupWikiPages` + first page pick. */
export function pickFirstPagePathForDomain(nav: MarketingWikiNav, domainId: string): string | null {
  const d = nav.domains.find((x) => x.id === domainId);
  if (!d?.groups?.length) return null;
  const groups = [...d.groups].sort((a, b) => {
    if (!a.folder) return -1;
    if (!b.folder) return 1;
    return a.folder.localeCompare(b.folder);
  });
  const ordered = groups.flatMap((g) => [...(g.pages ?? [])].sort((a, b) => a.title.localeCompare(b.title)));
  return ordered[0]?.path ?? null;
}

export function getStaticWikiSlugParams(nav: MarketingWikiNav): { params: { slug: string } }[] {
  const out: { params: { slug: string } }[] = [];
  const seen = new Set<string>();
  for (const d of nav.domains) {
    for (const g of d.groups) {
      for (const p of g.pages ?? []) {
        const rel = (p.path ?? '').replace(/^\/+/, '');
        if (!rel || seen.has(`${d.id}/${rel}`)) continue;
        if (!wikiMarkdownExists(d.id, rel)) {
          console.warn(`[marketing-wiki] skip missing file: wiki/${d.id}/${rel}`);
          continue;
        }
        seen.add(`${d.id}/${rel}`);
        out.push({ params: { slug: `${d.id}/${rel}` } });
      }
    }
  }
  return out;
}

export type LoadedWikiPage = {
  domain: string;
  pagePath: string;
  title: string;
  html: string;
  folder: string;
  pageType: string;
};

export async function loadWikiPageFromSlug(
  slug: string,
  nav: MarketingWikiNav,
): Promise<LoadedWikiPage | null> {
  const normalized = slug.replace(/^\/+|\/+$/g, '');
  if (!normalized) return null;
  const slash = normalized.indexOf('/');
  if (slash < 0) return null;
  const domain = normalized.slice(0, slash);
  const pagePath = normalized.slice(slash + 1);
  if (!domain || !pagePath) return null;
  if (!nav.domains.some((d) => d.id === domain)) return null;
  if (!wikiMarkdownExists(domain, pagePath)) return null;

  const abs = wikiMarkdownAbsPath(domain, pagePath);
  const raw = fs.readFileSync(abs, 'utf8');
  const { data, content } = matter(raw);
  const pageMeta =
    nav.domains
      .find((d) => d.id === domain)
      ?.groups.flatMap((g) => g.pages ?? [])
      .find((p) => p.path === pagePath) ?? null;

  const title =
    (typeof data.title === 'string' && data.title.trim()) ||
    pageMeta?.title ||
    pagePath.replace(/\.md$/i, '');

  const html = await renderWikiMarkdownToHtml(domain, pagePath, content, title);

  const folder = pageMeta?.folder ?? (pagePath.includes('/') ? pagePath.slice(0, pagePath.lastIndexOf('/')) : '');
  const pageType = pageMeta?.pageType ?? (typeof data.type === 'string' ? data.type : 'reference');

  return {
    domain,
    pagePath,
    title,
    html,
    folder,
    pageType,
  };
}
