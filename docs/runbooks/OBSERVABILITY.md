# Observability — M1 (`amprealize.ai`)

Four layers of visibility power the initial public-preview launch. Each is
cheap, additive, and provisioned independently so one can be swapped later
without disturbing the others.

| Layer | Covers | Hosted at | Owner |
| --- | --- | --- | --- |
| Sentry | Frontend errors + perf | sentry.io | platform |
| Uptime Kuma | Synthetic health probes | Fly `amprealize-uptime` | platform |
| Cloudflare Analytics | RUM + edge metrics | Cloudflare dashboard | product |
| Raze JSONL sink | Backend structured logs | Fly volume + daily R2 copy | platform |

---

## 1. Sentry (frontend)

Code path: `web-console/src/lib/observability.ts` is called from `main.tsx`
before render. If `VITE_SENTRY_DSN` is unset (current M1 default) the module
no-ops and the `@sentry/react` bundle is never fetched.

### One-time setup

1. Create a Sentry project `amprealize-web` (React, environment = `production`).
2. Copy the DSN.
3. Install the SDK in `web-console/`:

   ```bash
   cd web-console
   npm install @sentry/react
   ```

4. Set `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`, and `VITE_GIT_SHA` in
   the Cloudflare Pages project (see `CLOUDFLARE_PAGES_SETUP.md` step 2).
5. Redeploy; confirm errors appear in Sentry by throwing from the console.

### Release correlation

`_reusable-release.yml` injects `VITE_GIT_SHA=${{ github.sha }}` into the
Pages build. Enable **Releases → Auto-associate commits** in Sentry and
Sentry will link stacktraces back to the exact deploy.

### Sampling

- `tracesSampleRate: 0.1` — 10 % of page views emit a transaction.
- `replaysOnErrorSampleRate: 1.0` — every errored session captures a replay.
- `replaysSessionSampleRate: 0` — no baseline replays (cost control).

Adjust in `observability.ts` once usage ramps.

---

## 2. Uptime Kuma (synthetics)

Fly app `amprealize-uptime` runs the official Kuma image at a single
`shared-cpu-1x` machine with a 1 GB persistent volume. Config:
`infra/uptime-kuma/fly.toml`.

### Deploy

```bash
flyctl volumes create kuma_data -a amprealize-uptime --size 1 --region iad
flyctl deploy -a amprealize-uptime --config infra/uptime-kuma/fly.toml
flyctl scale count 1 -a amprealize-uptime
```

### First-run configuration

Browse to `https://amprealize-uptime.fly.dev/`, create the admin user, then
add these monitors (all `Type: HTTP(s) - Keyword`, `Interval: 60s`,
`Retries: 2`, `Heartbeat Retry: 30s`):

| Name | URL | Expected keyword |
| --- | --- | --- |
| Web apex | `https://amprealize.ai` | `amprealize` |
| Web www  | `https://www.amprealize.ai` | `amprealize` |
| API health | `https://api.amprealize.ai/health` | `ok` |
| Wiki infra listing | `https://api.amprealize.ai/api/v1/wiki/infra` | `infra` |
| MCP readiness (M4 target) | `https://mcp.amprealize.ai/health` | `ok` |

Attach the PagerDuty webhook under **Settings → Notifications** so paging
routes to the on-call schedule. Alerts fire after two consecutive failures
(~2 min) which avoids flaps from Neon/Upstash blips.

### Public status page

Expose a read-only status page at `status.amprealize.ai`:

```bash
# Add CNAME status.amprealize.ai → amprealize-uptime.fly.dev (Cloudflare,
# proxied = ON, TLS mode Flexible for Kuma's self-managed cert).
flyctl certs create status.amprealize.ai -a amprealize-uptime
```

Toggle the status page to public inside Kuma's settings.

---

## 3. Cloudflare Analytics

No code change required. Cloudflare's built-in RUM + Workers Analytics are
free and enabled by default when the zone is proxied. From the dashboard:

1. `amprealize.ai` zone → **Analytics & Logs → Web Analytics** → confirm
   data is flowing once DNS is cut over.
2. Enable **Beacons → Core Web Vitals** to capture LCP/FID/CLS.
3. Create a dashboard filter **hostname = amprealize.ai** and share the link
   in `#amprealize-prod`.

For deeper frontend RUM later, plug Sentry's Browser Tracing integration (now
emitting transactions) or add Vercel Analytics' standalone script to the
Pages build. Not needed in M1.

---

## 4. Raze JSONL sink + daily rotation

The FastAPI app emits structured JSONL to stdout via Python's `logging`
module; Fly forwards stdout to the machine console and to
`/var/lib/fly/logs/app.log`. Raze is the internal tail process that
collects per-module JSONL files for auditability.

### Enabling the sink on Fly

Append to `fly.api.toml` (already tracked by `m1-dockerfile-api`):

```toml
[env]
  AMPREALIZE_RAZE_SINK = "jsonl"
  AMPREALIZE_RAZE_SINK_PATH = "/app/logs/raze.jsonl"
```

Mount a volume so logs survive restarts:

```bash
flyctl volumes create raze_logs -a amprealize-api-prod --size 1 --region iad
```

Add to `fly.api.toml`:

```toml
[[mounts]]
  source = "raze_logs"
  destination = "/app/logs"
```

### Daily rotation → R2

A nightly GitHub Actions job (see `laneD-shared-backbone`) runs:

```bash
flyctl ssh console -a amprealize-api-prod --command "bash -lc '\
  DATE=$(date -u +%Y%m%d); \
  gzip -c /app/logs/raze.jsonl > /tmp/raze-${DATE}.jsonl.gz'"
flyctl ssh sftp get -a amprealize-api-prod /tmp/raze-${DATE}.jsonl.gz
wrangler r2 object put amprealize-logs/raze/raze-${DATE}.jsonl.gz \
  --file raze-${DATE}.jsonl.gz
```

Retention: 30 days in R2 (`lifecycle` rule on the bucket).

---

## Verification

- [ ] Throw from browser console → Sentry event appears within 60 s.
- [ ] Kuma shows all M1 monitors green.
- [ ] Cloudflare Web Analytics shows pageviews for amprealize.ai.
- [ ] `/app/logs/raze.jsonl` grows over 5 min of API traffic.
- [ ] `status.amprealize.ai` loads the public status page.
