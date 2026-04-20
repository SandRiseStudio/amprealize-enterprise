# Origin Split Runbook — `amprealize.ai` vs `app.amprealize.ai`

Work item: [GUIDEAI-998](../../README.md) ("Authenticated Product Shell + App Origin Split"), M2 of [GUIDEAI-5](./GUIDEAI_5_ROADMAP.md).

Starting M2, the `web-console` ships to two Cloudflare Pages projects from
the same codebase. This runbook is the single source of truth for how the
split is configured, deployed, rolled out, and rolled back.

## Why two origins

| Concern                        | Apex (`amprealize.ai`)            | Console (`app.amprealize.ai`)         |
| ------------------------------ | --------------------------------- | ------------------------------------- |
| Audience                       | Anonymous visitors (SEO)          | Authenticated users                   |
| Rendering                      | Static, indexable                 | SPA, `noindex`                        |
| Auth cookies                   | Never issued                      | Host-only on `app.`                   |
| Bundle weight                  | Minimal (wiki-only)               | Full SaaS shell                       |
| Release cadence                | Marketing copy                    | Product ships                         |
| Pages project                  | `amprealize-web`                  | `amprealize-console`                  |
| Deploy workflow                | `deploy-prod.yml`                 | `deploy-prod-console.yml`             |
| `VITE_APP_ORIGIN`              | `marketing`                       | `console`                             |
| `VITE_PUBLIC_PREVIEW` (M2)     | `1` (wiki-only stopgap)           | `0` after week-1 smoke; `1` initially |
| `VITE_PUBLIC_PREVIEW` (M3+)    | `0` (real marketing site)         | `0`                                   |
| Kill switch                    | n/a (always wiki-only until M3)   | Dispatch console workflow w/ preview  |

Both projects build from `web-console/`; the `VITE_APP_ORIGIN` env var and
a small Vite plugin (`vite.config.ts` → `appOriginPlugin`) decide whether
to inject a `<meta name="robots" content="noindex, nofollow">` tag and emit
`robots.txt` with a disallow-all rule.

## One-time provisioning

### 1. DNS

Add the `app` record in Cloudflare (zone `amprealize.ai`):

| Type  | Name | Content                                          | Proxy | TTL   |
| ----- | ---- | ------------------------------------------------ | ----- | ----- |
| CNAME | app  | `amprealize-console.pages.dev`                   | Proxy | Auto  |

See [`DNS_SETUP.md`](./DNS_SETUP.md) for the full zone configuration.

### 2. Cloudflare Pages project

```sh
# Create the second Pages project. Pages dashboard: Create project →
# "Direct upload" (we deploy via wrangler in CI).
wrangler pages project create amprealize-console \
  --production-branch main

# Bind custom domain. Requires Cloudflare for SaaS or the zone hosted in
# the same Cloudflare account.
wrangler pages domain add amprealize-console app.amprealize.ai

# Set the required environment variables on the project. These are
# consumed by the Vite build in CI (inputs flow from
# `deploy-prod-console.yml` → `_reusable-release.yml`).
#
# NOTE: `wrangler pages secret put` stores secrets at runtime for Pages
# Functions. For build-time Vite env vars, set them on the project's
# *Build environment variables* via the dashboard or the `--env-file` flag
# on `wrangler pages deploy`. CI already passes them at build time.
```

Verify: `curl -I https://app.amprealize.ai` returns `200 OK` with TLS.
Expect a `404` body served by Pages until the first deploy lands.

### 3. Backend CORS

Already done in this commit: `fly.api.toml` now lists
`https://app.amprealize.ai` in `AMPREALIZE_CORS_ORIGINS`. The next API
deploy picks it up. You can also set the env var directly without a code
deploy:

```sh
flyctl secrets set \
  AMPREALIZE_CORS_ORIGINS='https://amprealize.ai,https://www.amprealize.ai,https://app.amprealize.ai' \
  -a amprealize-api-prod
```

## Deploy flow

### Normal flow (both origins on `main` push)

1. Push to `main` triggers `deploy-prod.yml` (marketing) **and**
   `deploy-prod-console.yml` (console) in parallel.
2. Marketing deploy owns the API rollout (Fly + GHCR). Console deploy skips
   Fly / GHCR and only pushes Pages.
3. Each workflow runs its own Playwright smoke against its own origin
   (`SMOKE_BASE_URL` wired via the `smoke_base_url` input).

### Console-only hotfix

Dispatch `deploy-prod-console.yml` manually from GitHub Actions. Leave
`public_preview` unchecked to ship the authenticated shell.

### API-only hotfix alongside console deploy

Rare — temporarily set `fly_app: amprealize-api-prod` in
`deploy-prod-console.yml` and `fly_app: ""` in `deploy-prod.yml` for the
duration of the fix. Revert once landed.

## Week-1 smoke plan (M2 rollout)

The console origin ships with `VITE_PUBLIC_PREVIEW=1` for its first deploy
so the flow is:

1. **T+0 — Create Pages project, first deploy (preview=1).** Confirms
   DNS, TLS, CSP, `robots.txt`, `_headers` all work. Site shows wiki-only
   even at `app.amprealize.ai`.
2. **T+24h — Flip preview=0.** Manually dispatch `deploy-prod-console.yml`
   with `public_preview=false` (default), or merge a commit. Authenticated
   shell now exposed at `app.amprealize.ai`. Apex stays wiki-only.
3. **T+48h — Monitor.** Watch Sentry auth routes, Kuma uptime, PostHog
   sign-in funnel. If anything is wrong, flip back (see §Rollback).

## Rollback

### Fast rollback (< 10 min) — revert console to wiki-only

GitHub Actions → **Deploy prod (app.amprealize.ai)** → **Run workflow** →
set **public_preview = true** → Run. On completion, `app.amprealize.ai`
serves the wiki-only shell identical to M1. No DNS change, no API change.

### Nuclear rollback — take `app.` offline entirely

Cloudflare dashboard → Pages → `amprealize-console` → Settings → Custom
domains → Remove `app.amprealize.ai`. Users hitting `app.amprealize.ai`
see a Cloudflare 522. Apex is unaffected.

## Verification checklist

Run after every deploy that changes the origin split:

```sh
# Apex serves indexable wiki content
curl -sS https://amprealize.ai/robots.txt | grep -q 'Disallow: $' \
  || echo "FAIL: apex robots.txt is too restrictive"
curl -sS -I https://amprealize.ai | grep -i 'content-type: text/html'

# Console disallows indexing
curl -sS https://app.amprealize.ai/robots.txt | grep -q 'Disallow: /' \
  || echo "FAIL: console robots.txt missing disallow-all"
curl -sS https://app.amprealize.ai/ | grep -q 'name="robots"' \
  || echo "FAIL: console index.html missing noindex meta"

# CORS allows the console origin
curl -sS -I \
  -H 'Origin: https://app.amprealize.ai' \
  -H 'Access-Control-Request-Method: GET' \
  -X OPTIONS \
  https://api.amprealize.ai/api/v1/auth/me \
  | grep -i 'access-control-allow-origin: https://app.amprealize.ai'
```

## Related files

- `web-console/src/config/origin.ts` — origin resolution (build flag + hostname fallback)
- `web-console/src/lib/publicPreview.ts` — layered preview flag
- `web-console/vite.config.ts` — `appOriginPlugin` (noindex meta + robots.txt)
- `.github/workflows/deploy-prod.yml` — marketing apex deploy
- `.github/workflows/deploy-prod-console.yml` — console deploy
- `.github/workflows/_reusable-release.yml` — shared pipeline
- `fly.api.toml` — CORS allowlist
