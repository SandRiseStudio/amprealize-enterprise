import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function loadWikiRedirects() {
  const navPath = path.join(__dirname, 'src', 'generated', 'wiki-nav.json');
  if (!fs.existsSync(navPath)) return {};
  try {
    const nav = JSON.parse(fs.readFileSync(navPath, 'utf8'));
    const redirects = {};
    // `/wiki/{domain}` is a real static route (domain overview); do not 302 to first page.
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
