/**
 * Build `public/wiki-search-index.json` for client-side wiki search on the marketing site.
 * Shape matches web-console static wiki (`search-index.json`): { entries: [...] }.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');
const navPath = path.join(root, 'src', 'generated', 'wiki-nav.json');
const wikiRoot = path.join(root, '..', 'wiki');
const outFile = path.join(root, 'public', 'wiki-search-index.json');

function main() {
  if (!fs.existsSync(navPath)) {
    console.warn('[build-wiki-search-index] Missing wiki-nav.json — skip');
    return;
  }
  const nav = JSON.parse(fs.readFileSync(navPath, 'utf8'));
  const entries = [];

  for (const d of nav.domains ?? []) {
    for (const g of d.groups ?? []) {
      for (const p of g.pages ?? []) {
        const rel = (p.path ?? '').replace(/^\/+/, '');
        if (!rel) continue;
        const abs = path.join(wikiRoot, d.id, rel);
        if (!fs.existsSync(abs)) continue;
        const raw = fs.readFileSync(abs, 'utf8');
        const { content } = matter(raw);
        entries.push({
          domain: d.id,
          page_path: rel,
          title: p.title ?? rel,
          page_type: p.pageType ?? p.page_type ?? 'reference',
          body: content,
        });
      }
    }
  }

  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, JSON.stringify({ entries }), 'utf8');
  console.log(`[build-wiki-search-index] Wrote ${path.relative(root, outFile)} (${entries.length} pages)`);
}

main();
