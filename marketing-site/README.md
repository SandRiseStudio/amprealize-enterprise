# Amprealize marketing site (Astro)

Static marketing surface for **GUIDEAI-20**: **landing, pricing, and SEO at `amprealize.ai`**
while `app.amprealize.ai` stays the authenticated console. The public wiki ships from the
separate Cloudflare Pages project **`amprealize-web`** (e.g. `https://amprealize-web.pages.dev`).

## Wiki passthrough (optional)

`npm run build` runs `scripts/gen-redirects.mjs`, which may write `public/_redirects`:

- **Default (CI / local):** `PUBLIC_LEGACY_WIKI_BASE` unset or empty → **no** wiki redirect rules.
  Apex traffic stays on the marketing pages only.
- **If `PUBLIC_LEGACY_WIKI_BASE` is set** (e.g. `https://amprealize-web.pages.dev`):
  - `/wiki/*` → `302` to `${PUBLIC_LEGACY_WIKI_BASE}/wiki/:splat`
  - Unless `PUBLIC_LEGACY_WIKI_REDIRECT_ROOT=0`, also `/` → `302` to `${PUBLIC_LEGACY_WIKI_BASE}/wiki/infra`

Never set the base to the **same hostname** as this Pages project’s apex while that host
serves this project — `/wiki/*` would redirect to itself (`ERR_TOO_MANY_REDIRECTS`).

Use **Deploy marketing site (Astro)** workflow input `legacy_wiki_base` only when you
intentionally want the marketing project to forward wiki paths.

## Public wiki (static, no iframe)

**`/wiki/*`** is generated at build time from the monorepo **`../wiki/`** Markdown (same
sources the console static wiki uses). Pages use the marketing **app shell** (console-style
sidebar) plus an in-page wiki chrome (domain tabs, local TOC, article body). There is **no
iframe** and no dependency on the wiki SPA for HTML.

`functions/_middleware.js` still **reverse-proxies** **`/_wiki/*`**, **`/assets/*`**, and
**`/favicon.png`** to **`WIKI_UPSTREAM`** when those URLs hit the marketing origin (optional
for bookmarks or other clients). Wiki **HTML** at `/wiki/*` is served entirely from Astro
`dist/`.

Configure **`WIKI_UPSTREAM`** on the Cloudflare Pages project if you rely on that proxy
(defaults to `https://amprealize-web.pages.dev`).

The GitHub Action runs `wrangler pages deploy dist` with **`workingDirectory: marketing-site`**
so **`functions/`** next to `dist/` is included in the deployment (Wrangler 3.x does not support
`--cwd` on `pages deploy`).

**`npm run dev`:** wiki routes work locally without extra env vars (Markdown is read from
`../wiki/` when the dev server cwd is `marketing-site`).

## Local dev

```bash
cd marketing-site
npm ci
npm run dev
```

## Production deploy

1. Create a Cloudflare Pages project (e.g. `amprealize-marketing`) if it does not exist.
2. Run the GitHub workflow **Deploy marketing site (Astro)** (push to `main` under
   `marketing-site/**` or manual dispatch).
3. Attach `amprealize.ai` / `www` to the marketing Pages project when ready. Keep wiki on
   `amprealize-web` (or another origin); do not enable wiki passthrough unless you want redirects.

See also [docs/runbooks/GUIDEAI_5_ROADMAP.md](../docs/runbooks/GUIDEAI_5_ROADMAP.md).
