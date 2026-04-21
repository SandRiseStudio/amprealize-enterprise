import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function pickFirstPagePathForDomain(nav, domainId) {
  const d = nav.domains?.find((x) => x.id === domainId);
  if (!d?.groups?.length) return null;
  const groups = [...d.groups].sort((a, b) => {
    if (!a.folder) return -1;
    if (!b.folder) return 1;
    return a.folder.localeCompare(b.folder);
  });
  const ordered = groups.flatMap((g) =>
    [...(g.pages ?? [])].sort((a, b) => a.title.localeCompare(b.title)),
  );
  return ordered[0]?.path ?? null;
}

function loadWikiRedirects() {
  const navPath = path.join(__dirname, 'src', 'generated', 'wiki-nav.json');
  if (!fs.existsSync(navPath)) return {};
  try {
    const nav = JSON.parse(fs.readFileSync(navPath, 'utf8'));
    const redirects = {};
    for (const d of nav.domains ?? []) {
      const first = pickFirstPagePathForDomain(nav, d.id);
      if (first) redirects[`/wiki/${d.id}`] = `/wiki/${d.id}/${first}`;
    }
    if (nav.defaultDomain && nav.defaultPath) {
      redirects['/wiki'] = `/wiki/${nav.defaultDomain}/${nav.defaultPath}`;
    }
    return redirects;
  } catch {
    return {};
  }
}

// Production hostname after DNS points the apex here (GUIDEAI-20).
export default defineConfig({
  site: 'https://amprealize.ai',
  compressHTML: true,
  integrations: [sitemap()],
  redirects: loadWikiRedirects(),
});
