# Cloudflare Pages Setup — `amprealize-web` + `amprealize-console`

The SaaS frontend (`web-console/`) is deployed to Cloudflare Pages. Starting
M2 (GUIDEAI-5), the same codebase ships to **two separate Pages projects**
— one per origin — so marketing and the authenticated console can evolve
independently:

| Project               | Domain                  | Purpose                      | Workflow                      |
| --------------------- | ----------------------- | ---------------------------- | ----------------------------- |
| `amprealize-web`      | `amprealize.ai` + `www` | Marketing / wiki (M1 → M3)   | `deploy-prod.yml`             |
| `amprealize-console`  | `app.amprealize.ai`     | Authenticated SaaS (M2+)     | `deploy-prod-console.yml`     |

Both bundles build from `web-console/` but with different `VITE_APP_ORIGIN`
/ `VITE_PUBLIC_PREVIEW` values. See
[`APP_ORIGIN_SPLIT.md`](./APP_ORIGIN_SPLIT.md) for the origin-split
deploy + rollback procedure.

This runbook covers the **one-time provisioning** of both projects. Day-2
deploys are automated.

## 1. Create the Pages project

Via Cloudflare dashboard (`Workers & Pages → Pages → Create application →
Connect to Git`):

| Field | Value |
| --- | --- |
| Project name | `amprealize-web` |
| Production branch | `main` |
| Framework preset | `Vite` |
| Build command | `npm ci && npm run build` |
| Build output directory | `web-console/dist` |
| Root directory (advanced) | `web-console` |
| Node version | `20` (set via `NODE_VERSION` env var) |

Or via `wrangler`:

```bash
wrangler pages project create amprealize-web \
  --production-branch main \
  --compatibility-date $(date -u +%Y-%m-%d)
```

## 2. Environment variables

Set on the Pages project (Production and Preview scopes both). `NODE_VERSION`
is Pages-specific; the rest are consumed by Vite at build time.

### `amprealize-web` (marketing apex)

| Name | Production value | Preview value |
| --- | --- | --- |
| `NODE_VERSION` | `20` | `20` |
| `VITE_API_BASE_URL` | `https://api.amprealize.ai` | `https://api-staging.amprealize.ai` |
| `VITE_PUBLIC_PREVIEW` | `1` | `1` |
| `VITE_APP_ORIGIN` | `marketing` | `marketing` |
| `VITE_SENTRY_DSN` | *(from 1Password, wired in m1-observability)* | same |
| `VITE_APP_ENV` | `production` | `preview` |

`VITE_PUBLIC_PREVIEW=1` activates the wiki-only shell on the apex; this
stays `1` until M3 swaps in the real marketing site (GUIDEAI-20).
`VITE_APP_ORIGIN=marketing` keeps the apex indexable and forces the
wiki-only branch at runtime regardless of the flag.

### `amprealize-console` (authenticated app at `app.amprealize.ai`)

| Name | Production value | Preview value |
| --- | --- | --- |
| `NODE_VERSION` | `20` | `20` |
| `VITE_API_BASE_URL` | `https://api.amprealize.ai` | `https://api-staging.amprealize.ai` |
| `VITE_PUBLIC_PREVIEW` | `0` (after week-1 smoke; start at `1`) | `1` |
| `VITE_APP_ORIGIN` | `console` | `console` |
| `VITE_SENTRY_DSN` | *(from 1Password)* | same |
| `VITE_APP_ENV` | `production` | `preview` |

`VITE_APP_ORIGIN=console` activates the Vite `appOriginPlugin` which
injects `<meta name="robots" content="noindex, nofollow">` into
`index.html` and emits `robots.txt` with a disallow-all rule. The flag is
belt-and-suspenders — the runtime origin sniff in `src/config/origin.ts`
also catches a missing env var.

## 3. Custom domains

In the Pages project → **Custom domains**:

1. Add `amprealize.ai` (apex). Cloudflare auto-creates an AAAA record
   pointing to the Pages project.
2. Add `www.amprealize.ai`. Confirm Cloudflare creates a CNAME to
   `amprealize-web.pages.dev`.

Cross-reference `docs/runbooks/DNS_SETUP.md` — the apex A/AAAA records from
the DNS runbook should be removed when Pages is attached so the Pages managed
records take over. Keep the MX, TXT, `api`, and `mcp` records untouched.

Verify:

```bash
dig +short amprealize.ai
dig +short www.amprealize.ai
curl -sI https://amprealize.ai | head -n 1     # HTTP/2 200
curl -sI https://www.amprealize.ai | head -n 1 # HTTP/2 301 → amprealize.ai
```

## 4. Branch deploys

- `main` → `amprealize.ai`.
- Any other branch → `<branch>.amprealize-web.pages.dev` (preview URL).

Disable auto-deploy for dependabot/PR branches by setting **Preview
deployments → Only branch alias** to `preview/*` (optional; safer defaults).

## 5. Redirects, headers, SPA routing

The repo ships `web-console/public/_redirects` and
`web-console/public/_headers`. Pages copies these into the deploy output
automatically. Confirm after the first deploy:

```bash
curl -sI https://amprealize.ai/wiki/infra | head    # expect 200 + HSTS header
curl -sI https://amprealize.ai/totally-bogus-path   # expect 200 (SPA fallback)
```

## 6. Integration with GitHub Actions

The reusable CI workflow (`m1-reusable-cicd`) calls
`cloudflare/pages-action@v1` for preview deploys and `wrangler pages deploy`
for production, using `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` stored
in the `prod-saas` GitHub Environment.

```yaml
- uses: cloudflare/wrangler-action@v3
  with:
    apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
    command: pages deploy web-console/dist --project-name amprealize-web --branch main
```

The API token must scope to
`Account.Cloudflare Pages:Edit` + `User Details:Read`.

## 7. Verification checklist (M1)

- [ ] `https://amprealize.ai/` 200 and redirects client-side to `/wiki/infra`.
- [ ] Sidebar shows only the Wiki entry.
- [ ] Clicking a research/infra/ai-learning link renders its markdown body.
- [ ] No uncaught console errors.
- [ ] Network tab shows XHR to `api.amprealize.ai/api/v1/wiki/...`.
- [ ] Lighthouse perf score ≥ 90 on mobile.

## 8. Rollback

Cloudflare Pages keeps every deployment. To revert:

```bash
wrangler pages deployment list --project-name amprealize-web
wrangler pages deployment tail amprealize-web <DEPLOYMENT_ID>   # inspect
# Promote a known-good deploy:
wrangler pages deployment promote <DEPLOYMENT_ID> --project-name amprealize-web
```

Or via dashboard → `amprealize-web → Deployments → ⋯ → Rollback to this
deployment`.
