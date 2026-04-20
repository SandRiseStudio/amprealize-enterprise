#!/usr/bin/env node
// Generate static wiki JSON for Cloudflare Pages.
//
// Reads wiki/<domain>/**/*.md from the enterprise repo root and writes
// pre-rendered API-shaped JSON into web-console/public/_wiki/**. The
// frontend (src/api/wiki.ts) reads these when VITE_STATIC_WIKI=1.
//
// Emits:
//   public/_wiki/<domain>/pages.json       — WikiTreeResponse
//   public/_wiki/<domain>/status.json      — WikiStatusResponse
//   public/_wiki/<domain>/pages/<b64>.json — WikiPageDetail (path base64url)
//   public/_wiki/search-index.json         — compact list for client search
//
// Intentionally minimal: no external dependencies beyond Node 20 built-ins.

import { mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_CONSOLE_ROOT = resolve(__dirname, '..');
const REPO_ROOT = resolve(WEB_CONSOLE_ROOT, '..');
const WIKI_SRC = resolve(REPO_ROOT, 'wiki');
const OUT_ROOT = resolve(WEB_CONSOLE_ROOT, 'public', '_wiki');

// All wiki domains shipped on the public preview build (amprealize.ai). Kept
// in sync with `PUBLIC_WIKI_DOMAIN_IDS` in src/components/wiki/wikiData.ts.
const PUBLIC_DOMAINS = ['research', 'infra', 'ai-learning', 'platform'];

// File names hidden from the tree (match amprealize/services/wiki_api.py).
const SKIP_FILES = new Set(['index.md', 'log.md', 'overview.md', 'SCHEMA.md']);

function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const full = join(dir, e.name);
    if (e.isDirectory()) {
      out.push(...walk(full));
    } else if (e.isFile() && e.name.endsWith('.md')) {
      out.push(full);
    }
  }
  return out;
}

// Tiny YAML frontmatter parser (keys: string/number/bool only). Mirrors
// amprealize.wiki_service._parse_frontmatter just enough for page titles and
// types — we don't need list/dict semantics here.
function parseFrontmatter(text) {
  if (!text.startsWith('---')) return { fm: {}, body: text };
  const end = text.indexOf('\n---', 3);
  if (end === -1) return { fm: {}, body: text };
  const header = text.slice(3, end).trim();
  const body = text.slice(end + 4).replace(/^\r?\n/, '');
  const fm = {};
  for (const raw of header.split(/\r?\n/)) {
    const line = raw.trimEnd();
    if (!line || line.startsWith('#')) continue;
    const m = /^([A-Za-z0-9_-]+)\s*:\s*(.*)$/.exec(line);
    if (!m) continue;
    let [, key, value] = m;
    value = value.trim();
    if (value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1);
    } else if (value.startsWith("'") && value.endsWith("'")) {
      value = value.slice(1, -1);
    } else if (value === 'true') {
      value = true;
    } else if (value === 'false') {
      value = false;
    } else if (value !== '' && !Number.isNaN(Number(value))) {
      value = Number(value);
    }
    fm[key] = value;
  }
  return { fm, body };
}

function titleFromStem(stem) {
  return stem
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Base64url for path → filename. Avoids URL-encoding collisions on subpaths
// while staying decodable for debugging.
function pathToSlug(p) {
  return Buffer.from(p, 'utf-8')
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function ensureDir(dir) {
  mkdirSync(dir, { recursive: true });
}

function writeJson(filePath, data) {
  ensureDir(dirname(filePath));
  writeFileSync(filePath, JSON.stringify(data));
}

function mtimeIso(filePath) {
  try {
    return statSync(filePath).mtime.toISOString();
  } catch {
    return null;
  }
}

function processDomain(domain) {
  const domainDir = join(WIKI_SRC, domain);
  let files;
  try {
    files = walk(domainDir);
  } catch {
    console.warn(`[static-wiki] skipping missing domain: ${domain}`);
    return { pages: [], searchEntries: [] };
  }

  const pages = [];
  const pagesByType = {};
  const searchEntries = [];
  let latestMtime = null;

  for (const md of files.sort()) {
    const rel = relative(domainDir, md).split(sep).join('/');
    const name = rel.split('/').pop();
    if (SKIP_FILES.has(name)) continue;

    let raw;
    try {
      raw = readFileSync(md, 'utf-8');
    } catch {
      continue;
    }
    const { fm, body } = parseFrontmatter(raw);
    const title = String(fm.title ?? titleFromStem(name.replace(/\.md$/, '')));
    const pageType = String(fm.type ?? 'unknown');
    const folder = rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/')) : '';
    const difficulty = fm.difficulty ? String(fm.difficulty) : undefined;

    pages.push({
      path: rel,
      title,
      page_type: pageType,
      ...(difficulty ? { difficulty } : {}),
      folder,
    });

    pagesByType[pageType] = (pagesByType[pageType] || 0) + 1;

    const mt = mtimeIso(md);
    if (mt && (!latestMtime || mt > latestMtime)) latestMtime = mt;

    // Per-page JSON
    const slug = pathToSlug(rel);
    writeJson(join(OUT_ROOT, domain, 'pages', `${slug}.json`), {
      domain,
      path: rel,
      title,
      page_type: pageType,
      body,
      frontmatter: fm,
    });

    // Search entry (full body, scored client-side)
    searchEntries.push({
      domain,
      page_path: rel,
      title,
      page_type: pageType,
      body,
    });
  }

  writeJson(join(OUT_ROOT, domain, 'pages.json'), {
    domain,
    pages,
    total: pages.length,
  });

  writeJson(join(OUT_ROOT, domain, 'status.json'), {
    domain,
    total_pages: pages.length,
    pages_by_type: pagesByType,
    ...(latestMtime ? { last_updated: latestMtime } : {}),
  });

  console.log(`[static-wiki] ${domain}: ${pages.length} pages`);
  return { pages, searchEntries };
}

function main() {
  rmSync(OUT_ROOT, { recursive: true, force: true });
  ensureDir(OUT_ROOT);

  const allSearch = [];
  for (const domain of PUBLIC_DOMAINS) {
    const { searchEntries } = processDomain(domain);
    allSearch.push(...searchEntries);
  }

  writeJson(join(OUT_ROOT, 'search-index.json'), { entries: allSearch });
  writeJson(join(OUT_ROOT, 'manifest.json'), {
    generated_at: new Date().toISOString(),
    domains: PUBLIC_DOMAINS,
    total_pages: allSearch.length,
  });

  console.log(`[static-wiki] ok — ${allSearch.length} pages across ${PUBLIC_DOMAINS.length} domains`);
}

main();
