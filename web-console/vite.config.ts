/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * App-origin plugin (GUIDEAI-5 / M2).
 *
 * The same web-console build ships to two Cloudflare Pages projects:
 *   - marketing (`amprealize.ai`)       — indexable, wiki-only stopgap
 *   - console  (`app.amprealize.ai`)    — auth-gated SaaS shell, noindex
 *
 * When `VITE_APP_ORIGIN=console` at build time we:
 *   - inject a `<meta name="robots" content="noindex, nofollow">` tag into
 *     `index.html` so accidental indexing never happens
 *   - emit a `robots.txt` disallowing all crawlers
 *
 * For `marketing` (or unset), the existing `/robots.txt` (if any) and the
 * default indexable behaviour are preserved.
 */
function appOriginPlugin(): Plugin {
  const origin = process.env.VITE_APP_ORIGIN ?? 'console';
  const isConsole = origin === 'console';
  return {
    name: 'amprealize:app-origin',
    transformIndexHtml(html) {
      if (!isConsole) return html;
      if (html.includes('name="robots"')) return html;
      return html.replace(
        /<head>/i,
        '<head>\n    <meta name="robots" content="noindex, nofollow" />',
      );
    },
    generateBundle() {
      if (!isConsole) return;
      this.emitFile({
        type: 'asset',
        fileName: 'robots.txt',
        source: '# app.amprealize.ai is the authenticated console — do not index.\nUser-agent: *\nDisallow: /\n',
      });
    },
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), appOriginPlugin()],
  resolve: {
    alias: ((): Record<string, string> => {
      const localFallback = resolve(__dirname, 'src/vendor/collab-client-dist/index.js');
      const candidates = [
        process.env.AMPREALIZE_REPO_ROOT,
        resolve(__dirname, '..'),
        resolve(__dirname),
      ].filter(Boolean) as string[];

      for (const base of candidates) {
        const srcEntry = resolve(base, 'packages/collab-client/src/index.ts');
        const distEntry = resolve(base, 'packages/collab-client/dist/index.js');
        if (existsSync(srcEntry)) {
          return {
            '@amprealize/collab-client': srcEntry,
          };
        }
        if (existsSync(distEntry)) {
          return {
            '@amprealize/collab-client': distEntry,
          };
        }
      }

      if (existsSync(localFallback)) {
        return {
          '@amprealize/collab-client': localFallback,
        };
      }

      return {};
    })(),
    // Ensure collab-client's optional peer dep on react resolves to
    // the web-console copy rather than a Vite optional-peer-dep stub.
    dedupe: ['react', 'react-dom'],
  },
  server: {
    fs: {
      allow: [
        ...(process.env.AMPREALIZE_REPO_ROOT ? [resolve(process.env.AMPREALIZE_REPO_ROOT)] : []),
        resolve(__dirname, '..'),
        resolve(__dirname),
      ],
    },
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
