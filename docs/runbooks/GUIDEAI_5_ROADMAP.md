# GUIDEAI-5 Rollout Roadmap (M2 → M4, Lanes B–D)

Companion to the M1 runbooks already in this directory
(`DNS_SETUP.md`, `NEON_UPSTASH_PROVISIONING.md`,
`CLOUDFLARE_PAGES_SETUP.md`, `OBSERVABILITY.md`). M1 ships the wiki-only
public preview of `amprealize.ai`. This file turns the remaining milestones
of the GUIDEAI-5 production plan into executable work streams: each section
has goals, scope, prerequisites, implementation steps, and exit criteria
sized so a single engineer can pick it up without additional planning.

Status summary (as of M1 ship):

| Track | State |
| --- | --- |
| M1 — wiki preview | **shipped** |
| M2 — authenticated product shell | scoped (below) |
| M3 — commercial v1 (Stripe + quotas) | scoped (below) |
| M4 — enterprise hardening (MCP, SSO, SOC2) | scoped (below) |
| Lane B — OSS distribution | scoped (below) |
| Lane C — self-hosted Enterprise | scoped (below) |
| Lane D — shared backbone ops | scoped (below) |
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
---

## M2 — Authenticated Product Shell + App Origin Split

Move the authenticated console to a new origin at `app.amprealize.ai` while
keeping `amprealize.ai` serving the wiki-only shell (M1 behaviour).
Everything ships behind the existing `VITE_PUBLIC_PREVIEW` kill switch so
we can revert the console to wiki-only in one Pages redeploy (< 10 min).

Origin split reference: [`APP_ORIGIN_SPLIT.md`](./APP_ORIGIN_SPLIT.md).

### Goals

- Same `web-console/` build deploys to **two** Cloudflare Pages projects:
  - `amprealize-web` → `amprealize.ai` (marketing / wiki stopgap,
    indexable, `VITE_APP_ORIGIN=marketing`).
  - `amprealize-console` → `app.amprealize.ai` (auth-gated SaaS shell,
    `noindex`, `VITE_APP_ORIGIN=console`).
- Users can run `amprealize auth login` → device-flow → sign in on
  `app.amprealize.ai`.
- Sidebar surfaces projects / boards / agents / work for authenticated
  users on the console origin; wiki remains available to everyone on the
  apex (and the console exposes `/wiki` too).
- Org + project context is selectable from a top-right picker and persisted
  in `localStorage` (already wired via `store/orgContextStore.ts`).

### Work items

1. **Origin split — infra**
   - Provision new Pages project `amprealize-console` bound to
     `app.amprealize.ai` (see `APP_ORIGIN_SPLIT.md` §"One-time
     provisioning" for commands).
   - Add `app` CNAME in Cloudflare (see `DNS_SETUP.md`).
   - Add `https://app.amprealize.ai` to `AMPREALIZE_CORS_ORIGINS` in
     `fly.api.toml` (done in this commit) and on Fly secrets.
   - Auth cookies stay host-only on `app.amprealize.ai` — no `Domain=`
     attribute so the apex can never read them.
2. **Frontend origin awareness** (done in this commit)
   - `web-console/src/config/origin.ts` resolves `AppOrigin` from
     `VITE_APP_ORIGIN` with a runtime hostname fallback.
   - `web-console/src/lib/publicPreview.ts` forces wiki-only mode when the
     origin is `marketing`, even if the build flag is missing.
   - `web-console/vite.config.ts` injects `<meta name="robots">` and emits
     `robots.txt` disallow-all when `VITE_APP_ORIGIN=console`.
3. **Backend** — confirm `/api/v1/auth/device/*` endpoints work against
   Neon prod; add an integration test against the staging Neon branch.
   (Device flow is already in `amprealize/api.py`; this task is just
   verification + test.)
4. **Auth shell** — already in place: `AuthProvider`, `useAuth`,
   `ProtectedRoute`, `orgContextStore`, and `App.tsx` route tree all
   landed pre-M2. No new wiring required beyond the origin split.
5. **CI / deploy pipeline** (done in this commit)
   - `_reusable-release.yml` accepts new `vite_app_origin` +
     `smoke_base_url` inputs.
   - `deploy-prod.yml` targets the marketing apex
     (`pages_project: amprealize-web`, `vite_app_origin: marketing`,
     `vite_public_preview: 1`).
   - `deploy-prod-console.yml` targets the console
     (`pages_project: amprealize-console`, `vite_app_origin: console`,
     `vite_public_preview: 0` with a kill-switch dispatch input).
6. **Kill switch** — dispatch `deploy-prod-console.yml` with
   `public_preview=true` to revert `app.amprealize.ai` to wiki-only inside
   one Pages deploy. Apex always stays wiki-only in M2; no switch needed
   there until M3.

### Prereqs

- M1 shipped (auth middleware already present, just disabled).
- Neon migrations up to `amprealize/auth/` head on the prod branch.
- Sentry DSN wired so auth flows show up in release reports.

### Exit criteria

- [ ] `amprealize auth login` succeeds end-to-end against prod, landing on
      `app.amprealize.ai`.
- [ ] `curl -sS https://app.amprealize.ai/robots.txt` returns a
      disallow-all rule; `curl -sS https://amprealize.ai/robots.txt` does
      not.
- [ ] `curl -sS https://app.amprealize.ai/` HTML contains
      `name="robots"` with `noindex`.
- [ ] Sidebar shows Projects, Boards, Agents, Work, Wiki, Settings for
      signed-in users on `app.`; apex stays wiki-only.
- [ ] Org picker in `WorkspaceShell` persists and switches tenants without
      a page reload.
- [ ] Dispatch `deploy-prod-console.yml` with `public_preview=true`
      returns `app.amprealize.ai` to wiki-only within one Pages deploy
      (< 10 min).

### Out of scope (deferred to M3)

- Paid plans, quota enforcement, billing UI.
- Invitations / SSO.

---

## M3 — Commercial v1 (Stripe + Quotas)

Wire Stripe Products + the `QuotaEnforcer` from
[GUIDEAI-369](https://amprealize.ai/work/GUIDEAI-369) T3.10.1 at
`ExecutionGateway` so Starter/Pro/Team tiers hit hard and soft quota
boundaries. Expose billing UI in the web-console and surface usage metrics
in the dashboard.

### Goals

- Three public plans (Starter / Pro / Team) visible on `amprealize.ai/pricing`.
- Checkout via Stripe Billing Portal; subscriptions update the tenant's
  plan atomically.
- Every gated API call (chat completions, tool execution, embedding) is
  accounted and rate-limited by `QuotaEnforcer`.
- Usage meters visible in the web-console under `/settings/billing`.

### Work items

1. **Stripe products** — create the three products + monthly/annual prices
   via `scripts/stripe_bootstrap.py`; pin IDs in `config/stripe.yml`.
2. **Webhook endpoint** — `amprealize/api_billing.py` already has a stub;
   harden it with signature verification, idempotency (Redis key
   `stripe:event:<id>`), and transactional writes to `tenant_subscription`.
3. **QuotaEnforcer wiring** — `amprealize/services/execution_gateway.py`
   calls `QuotaEnforcer.check(tenant_id, quota_key)` before every
   downstream provider call. Already implemented behind a feature flag;
   flip the flag on in prod.
4. **Frontend billing** — `web-console/src/pages/settings/Billing.tsx`
   (port from OSS; enterprise adds the "Contact sales" path for Enterprise
   tier).
5. **Usage metering** — nightly job `scripts/usage_rollup.py` rolls the
   telemetry branch's `agent_call_events` into `tenant_usage_daily` and
   publishes to the Stripe metered subscription item.
6. **Alerts** — Grafana board fed by the telemetry Neon branch; page when
   > 2× daily usage jump.

### Prereqs

- M2 shipped (users can sign in and have an org context).
- Neon telemetry branch has the `tenant_usage_daily` hypertable.
- Stripe account transferred from sandbox to live mode.

### Exit criteria

- [ ] Paid user exceeding Starter quota receives HTTP 429 with a checkout
      link header.
- [ ] Stripe webhook → DB update round trip < 1 s p95.
- [ ] Billing dashboard shows current-cycle usage within ±2 % of Stripe's
      invoice.
- [ ] Revenue metrics flowing into Cloudflare Analytics dashboard.

---

## M4 — Enterprise Hardening (MCP GA, SSO, SOC2, License Keys)

Graduate the MCP WebSocket proxy to `mcp.amprealize.ai`
(see [GUIDEAI-21](https://amprealize.ai/work/GUIDEAI-21)), land SSO/SAML,
emit SOC2-compliant signed audit logs, and ship a license-key activation
flow for self-hosted Enterprise installs.

### Goals

- `mcp.amprealize.ai` GA with 99.9 % uptime SLA.
- SAML SSO supported via WorkOS (or Okta fallback); JIT org provisioning.
- Every mutating API call emits an immutable, Ed25519-signed JSONL log
  entry to the SOC2 evidence sink.
- Self-hosted Enterprise operators enter a license key on first run and
  the in-process license daemon phones home weekly.

### Work items

1. **MCP proxy** — promote the existing `amprealize/mcp_ws_proxy/`
   prototype to a Fly app `amprealize-mcp-prod` fronted by
   `mcp.amprealize.ai` (CNAME already in place from M1 DNS runbook).
2. **SSO** — adopt WorkOS SDK; wire `/auth/saml/callback`; add
   `saml_identity_provider` table on the main Neon branch.
3. **Audit log signing** — `amprealize/audit/signed_log.py` already exists;
   generate a key per environment, store in GitHub env secrets, rotate
   yearly per Lane D runbook.
4. **License daemon** — `amprealize/enterprise/license.py` generates and
   validates license keys; phones home to
   `https://api.amprealize.ai/enterprise/license/report`.
5. **SOC2 artifacts** — wire `scripts/soc2_artifact_dump.py` into the
   nightly R2 cron from Lane D so auditors have continuous evidence.

### Prereqs

- M3 shipped (billing + quotas fund the SSO/enterprise price tier).
- WorkOS account provisioned; callback URL registered.
- Fly IAM for a second app (`amprealize-mcp-prod`).

### Exit criteria

- [ ] A customer-owned IdP signs a user in through SAML and lands on the
      right org.
- [ ] `signed_log_verify.py` replays one day of audit logs with zero
      signature failures.
- [ ] License activation round-trip succeeds in < 2 s on
      `docker run amprealize/enterprise:latest`.
- [ ] SOC2 Type I audit has machine-generated evidence bundles.

---

## Lane B — OSS Distribution

Own the public surface (`github.com/amprealize/amprealize`, PyPI, VS Code
Marketplace, GHCR public image). Independent of the SaaS rollout so an OSS
release does not need SaaS deploy approval.

### Work items

1. **`publish-pypi.yml`** — confirm it targets the OSS repo on tag push,
   uses OIDC trusted publisher, and runs on
   `workflow_run: completed(ci.yml)`.
2. **VS Code Marketplace** — set `VSCE_TOKEN` in the OSS repo's
   `release` environment; call `vsce publish --pre-release` from the
   existing `publish-vscode.yml` path in `ci.yml`.
3. **GHCR public image** — new workflow `publish-oss-docker.yml` builds
   `amprealize/amprealize-oss` tagged `latest` and the git SHA, pushed to
   `ghcr.io` with package visibility `public`.
4. **Install docs** — refresh `docs/ONBOARDING_QUICKSTARTS.md` with the
   three-surface install story.

### Exit criteria

- [ ] Tagging `v0.x.y` on the OSS repo publishes to PyPI, VS Code
      Marketplace, and GHCR in one pipeline.
- [ ] Fresh laptop can `pip install amprealize`, install the VS Code
      extension, and run `docker run ghcr.io/amprealize/amprealize-oss`
      without additional steps.

---

## Lane C — Self-Hosted Enterprise

Ship an installable Enterprise bundle that runs on the customer's own
infra. Reuses the `infra/Dockerfile.api` image but swaps the OSS core for
the enterprise one.

### Work items

1. **GHCR private image** — `publish-enterprise-docker.yml` builds from
   `infra/Dockerfile.api`, tags `ghcr.io/amprealize/amprealize-enterprise:
   <sha>`, visibility `private`.
2. **`docker-compose.enterprise.yml`** — ships Postgres 16, Redis 7, the
   API image, and a reverse proxy (caddy) with sane defaults.
3. **Helm chart skeleton** — `charts/amprealize/` with values for API
   image tag, license key, ingress, persistence, and optional Postgres
   operator reference.
4. **Install guide** — new `docs/ENTERPRISE_INSTALL.md` covering
   single-node Docker and Kubernetes paths.
5. **License activation** — reuse the daemon from M4; include activation
   docs.

### Exit criteria

- [ ] `docker compose -f docker-compose.enterprise.yml up` produces a
      working stack with a single env file edit.
- [ ] `helm install amprealize charts/amprealize -f values.yaml` succeeds
      on kind + a real EKS cluster.
- [ ] Auditor can replay the install from docs alone.

---

## Lane D — Shared Backbone Ops

Cross-cutting operations that protect both the SaaS and self-hosted lanes.

### Work items

1. **Secrets rotation runbook** — new `docs/runbooks/SECRETS_ROTATION.md`
   that documents quarterly rotation for Fly tokens, Cloudflare tokens,
   Neon roles, Upstash passwords, Stripe webhook secrets, WorkOS API keys,
   and the audit-log signing keypair. Each tied to a GitHub Environment
   approval gate.
2. **Nightly `pg_dump` → R2** — GitHub Actions cron runs
   `flyctl ssh console -a amprealize-api-prod --command "pg_dump $AMPREALIZE_MAIN_DSN | gzip > /tmp/pg.sql.gz"`,
   then `wrangler r2 object put amprealize-backups/pg/...`. 30-day
   retention.
3. **Disaster Recovery dry run** — quarterly restore from R2 into a
   scratch Neon branch and run the smoke suite from `m1-smoke-tests`.
4. **Alerting on-call** — PagerDuty schedule, Kuma + Sentry + Stripe
   webhook failures all route to `#amprealize-oncall`.

### Exit criteria

- [ ] All secrets have a documented rotation date + owner.
- [ ] `scripts/dr_drill.sh` restores prod to a fresh environment in under
      30 minutes.
- [ ] DR drill passes quarterly; postmortems filed for any miss.

---

## Cross-links

- Active work items: [GUIDEAI-5](https://amprealize.ai/work/GUIDEAI-5) (SaaS
  launch), GUIDEAI-17 (DNS), GUIDEAI-19 (API deploy), GUIDEAI-21 (MCP GA),
  GUIDEAI-369 (quota enforcement).
- Feature flags used: `AMPREALIZE_PUBLIC_PREVIEW`, `VITE_PUBLIC_PREVIEW`.
- CI entry points: `.github/workflows/deploy-prod.yml` →
  `.github/workflows/_reusable-release.yml`.
- Core parity checks: `scripts/core_parity_check.sh`,
  `scripts/sync_wiki_from_oss.sh`.
