# Amprealize marketing site (Astro)

Static marketing surface for **GUIDEAI-20** (apex marketing + wiki routing). This project is
deployed separately from the React `web-console` so `amprealize.ai` can ship a real landing,
`/pricing`, and SEO while `app.amprealize.ai` stays the authenticated console.

## Wiki paths

`npm run build` runs `scripts/gen-redirects.mjs`, which writes `public/_redirects` for
Cloudflare Pages:

- `/wiki/*` → `302` to `${PUBLIC_LEGACY_WIKI_BASE}/wiki/:splat` (default `https://amprealize.ai`)

Use that default **only while the apex still points at the legacy wiki Pages project**. After
DNS cuts over to this deployment, set `PUBLIC_LEGACY_WIKI_BASE=https://docs.amprealize.ai` (or
bundle static wiki content into this repo and delete the redirect rule).

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
