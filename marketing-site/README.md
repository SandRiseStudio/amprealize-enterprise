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
