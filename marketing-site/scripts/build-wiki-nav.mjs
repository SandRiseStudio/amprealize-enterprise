/**
 * Build wiki navigation JSON for the marketing Astro shell from web-console
 * static wiki data (scripts/build-static-wiki.mjs output).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');
const wikiRoot = path.join(root, '..', 'web-console', 'public', '_wiki');
const outDir = path.join(root, 'src', 'generated');
const outFile = path.join(outDir, 'wiki-nav.json');

const DOMAIN_LABELS = {
  infra: 'Infrastructure',
  platform: 'Platform',
  'ai-learning': 'AI Learning',
  research: 'Research',
};

function folderLabel(folder) {
  if (!folder) return 'Pages';
  const last = folder.split('/').pop() ?? folder;
  return last.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function groupPages(pages) {
  const map = new Map();
  for (const p of pages) {
    const folder = p.folder ?? '';
    if (!map.has(folder)) map.set(folder, []);
    map.get(folder).push({
      path: p.path,
      title: p.title,
      pageType: p.page_type ?? p.pageType ?? 'reference',
      folder: p.folder ?? '',
    });
  }
  const groups = [];
  for (const [folder, folderPages] of map) {
    groups.push({
      folder,
      label: folderLabel(folder),
      pages: folderPages.sort((a, b) => a.title.localeCompare(b.title)),
    });
  }
  return groups.sort((a, b) => {
    if (!a.folder) return -1;
    if (!b.folder) return 1;
    return a.folder.localeCompare(b.folder);
  });
}

function pickDomainRootPath(pages) {
  if (!pages.length) return null;
  const ordered = groupPages(pages).flatMap((g) => g.pages);
  return ordered[0]?.path ?? null;
}

function main() {
  if (!fs.existsSync(wikiRoot)) {
    console.warn(`[build-wiki-nav] Missing ${wikiRoot} — writing empty wiki-nav.json`);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(
      outFile,
      `${JSON.stringify({ domains: [], defaultDomain: 'infra', defaultPath: null }, null, 2)}\n`,
      'utf8',
    );
    return;
  }

  const manifestPath = path.join(wikiRoot, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const domainIds = manifest.domains ?? [];

  const domains = [];
  for (const id of domainIds) {
    const pagesPath = path.join(wikiRoot, id, 'pages.json');
    if (!fs.existsSync(pagesPath)) continue;
    const { pages = [] } = JSON.parse(fs.readFileSync(pagesPath, 'utf8'));
    const groups = groupPages(pages);
    domains.push({
      id,
      label: DOMAIN_LABELS[id] ?? id,
      groups,
    });
  }

  const defaultDomain = domains.find((d) => d.id === 'infra')?.id ?? domains[0]?.id ?? 'infra';
  const firstPagesPath = path.join(wikiRoot, defaultDomain, 'pages.json');
  const firstDomainPages = fs.existsSync(firstPagesPath)
    ? JSON.parse(fs.readFileSync(firstPagesPath, 'utf8')).pages ?? []
    : [];
  const defaultPath = pickDomainRootPath(firstDomainPages);

  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    outFile,
    `${JSON.stringify({ domains, defaultDomain, defaultPath }, null, 2)}\n`,
    'utf8',
  );
  console.log(`[build-wiki-nav] Wrote ${path.relative(root, outFile)} (${domains.length} domains)`);
}

main();
