# Amprealize marketing site (Astro)

Static marketing surface for **GUIDEAI-20** (apex marketing + wiki routing). This project is
deployed separately from the React `web-console` so `amprealize.ai` can ship a real landing,
`/pricing`, and SEO while `app.amprealize.ai` stays the authenticated console.

## Wiki paths

`npm run build` runs `scripts/gen-redirects.mjs`, which writes `public/_redirects` for
Cloudflare Pages:

- When `PUBLIC_LEGACY_WIKI_BASE` is set (CI default: `https://amprealize-web.pages.dev`):
  - `/wiki/*` → `302` to `${PUBLIC_LEGACY_WIKI_BASE}/wiki/:splat`
  - `/` → `302` to `${PUBLIC_LEGACY_WIKI_BASE}/wiki/infra` (smoke / M2 wiki-first apex)
- When it is **unset or empty**, no wiki rules are emitted (avoid self-redirect loops if the
  wiki SPA is not deployed elsewhere yet).

Never set the base to the **same hostname** as this Pages project’s apex (e.g. do not use
`https://amprealize.ai` while `amprealize.ai` already points here) — Cloudflare will loop
`/wiki/*` with `ERR_TOO_MANY_REDIRECTS`.

Set `PUBLIC_LEGACY_WIKI_REDIRECT_ROOT=0` to omit the `/` rule when shipping a real marketing
homepage on apex (M3+). Point `PUBLIC_LEGACY_WIKI_BASE` at `https://docs.amprealize.ai` or
remove passthrough once static wiki ships in this repo.

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
3. When ready for apex cutover, attach `amprealize.ai` / `www` custom domains to the marketing
   Pages project and remove them from the old wiki project. Update `PUBLIC_LEGACY_WIKI_BASE`
   for wiki redirects as above.

See also [docs/runbooks/GUIDEAI_5_ROADMAP.md](../docs/runbooks/GUIDEAI_5_ROADMAP.md).
