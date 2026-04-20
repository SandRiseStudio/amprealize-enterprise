# Secrets Rotation — `amprealize.ai`

Quarterly (or on-demand after an incident) rotation of every secret the
SaaS depends on. Each entry names the secret, where it lives, who owns
rotation, and the exact command to rotate it without downtime.

Linked to GUIDEAI-5 Lane D. See `GUIDEAI_5_ROADMAP.md` for context.

## Ownership

| Secret | Store (of record) | Mirrored to | Owner | Cadence |
| --- | --- | --- | --- | --- |
| `FLY_API_TOKEN` | Fly dashboard | GitHub env `prod-saas` | platform | Quarterly |
| `CLOUDFLARE_API_TOKEN` | Cloudflare dashboard | GitHub env `prod-saas` | platform | Quarterly |
| `GHCR_TOKEN` (`packages:write`) | GitHub PAT vault | GitHub env `prod-saas` | platform | Quarterly |
| `AMPREALIZE_MAIN_DSN` password | Neon console | Fly secrets, 1P | platform | Biannual |
| `AMPREALIZE_TELEMETRY_DSN` password | Neon console | Fly secrets, 1P | platform | Biannual |
| `REDIS_URL` password | Upstash dashboard | Fly secrets, 1P | platform | Biannual |
| `AMPREALIZE_JWT_SECRET` | Fly secrets | — | platform | Quarterly |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard | Fly secrets, GitHub env | billing | On rotation |
| `WORKOS_API_KEY` | WorkOS dashboard | Fly secrets | platform | Biannual |
| `AUDIT_LOG_SIGNING_KEY` (Ed25519) | 1Password vault | Fly secrets | security | Annual |
| `VSCE_TOKEN` (OSS repo) | VS Code Marketplace | GitHub env `release` | platform | Annual |
| `NPM_TOKEN` (OSS repo) | npmjs.com | GitHub env `release` | platform | Annual |
| `PYPI_TRUSTED_PUBLISHER` | PyPI project | n/a (OIDC) | platform | n/a — managed by OIDC |
| `VITE_POSTHOG_KEY` | PostHog project settings | Fly secrets, GitHub env `prod-saas` | platform | Annual |

## Gating

Every secret rotation goes through the `prod-saas` GitHub Environment and
requires the **Required reviewers** check to merge. Two-person sign-off.

```text
GitHub Env prod-saas
  reviewers: @amprealize/platform-eng (at least 1)
  wait timer: 0 min (immediate; gated by reviewer approval)
```

## Rotation playbooks

### Fly API token

```bash
# 1. Mint new token
NEW_TOKEN=$(flyctl auth token)          # or use `flyctl tokens create`
# 2. Update GitHub env
gh secret set FLY_API_TOKEN --body "$NEW_TOKEN" --env prod-saas
# 3. Trigger a no-op deploy to confirm the new token works
gh workflow run deploy-prod.yml
# 4. Revoke the old token in the Fly dashboard after the deploy goes green
```

### Cloudflare API token

```bash
# 1. Dashboard → My Profile → API Tokens → Create (permissions:
#    Account.Cloudflare Pages:Edit, User.User Details:Read, Zone.Analytics:Read)
NEW_TOKEN="..."
gh secret set CLOUDFLARE_API_TOKEN --body "$NEW_TOKEN" --env prod-saas
gh workflow run deploy-prod.yml
# 2. Delete the old token from the dashboard after the deploy goes green
```

### Neon DSN password

```bash
# 1. Rotate role password in Neon
neonctl roles set-password --project-id "$NEON_PROJECT_ID_PROD" --role amprealize --password "$(openssl rand -base64 32)"
NEW_DSN=$(neonctl connection-string --project-id "$NEON_PROJECT_ID_PROD" --branch main --database amprealize --role amprealize)
# 2. Push to Fly without restart; new connections pick up the new password
flyctl secrets set -a amprealize-api-prod AMPREALIZE_MAIN_DSN="$NEW_DSN"
# 3. Verify: flyctl ssh console -a amprealize-api-prod --command "bash -lc 'psql \$AMPREALIZE_MAIN_DSN -c \"select 1\"'"
```

### Upstash Redis password

```bash
# 1. Dashboard → amprealize-prod → Reset Password
NEW_REDIS_URL="rediss://default:${NEW_PW}@${HOST}:${PORT}"
flyctl secrets set -a amprealize-api-prod REDIS_URL="$NEW_REDIS_URL"
# 2. Verify: redis-cli -u "$NEW_REDIS_URL" PING
```

### JWT signing secret

```bash
NEW_JWT=$(openssl rand -base64 48)
flyctl secrets set -a amprealize-api-prod AMPREALIZE_JWT_SECRET="$NEW_JWT"
# Forces re-issue of all user sessions at next request; documented in the
# user-facing incident post-mortem template.
```

### Ed25519 audit log signing key

```bash
# 1. Generate a new keypair
python -c "from nacl import signing; import base64; \
  k = signing.SigningKey.generate(); \
  print('private', base64.b64encode(bytes(k))); \
  print('public', base64.b64encode(bytes(k.verify_key)))"
# 2. Push private key to Fly; publish public key in a public GitHub gist
#    linked from docs/PUBLIC_KEYS.md so auditors can verify historical logs.
flyctl secrets set -a amprealize-api-prod AUDIT_LOG_SIGNING_KEY="..."
# 3. Rotate period boundary file in R2 so old logs can still be verified
#    against the previous public key. Never delete historical public keys.
```

### PostHog project API key (`VITE_POSTHOG_KEY`)

```bash
# 1. In PostHog → Project settings → Project API keys → rotate / create new
#    Write-protected key (no personal API key; use the Project API Key only).
# 2. Update Fly production secret (web-console build reads this at CI time)
flyctl secrets set -a amprealize-web-prod VITE_POSTHOG_KEY="phc_NEWKEY..."
# 3. Update GitHub Environment prod-saas VITE_POSTHOG_KEY so the next
#    CI build picks it up automatically.
# 4. Revoke the old key in PostHog after verifying events are flowing from
#    the new key (allow one full build + deploy cycle).
```

## Incident-triggered rotation

If an exposure is suspected, rotate every credential that touched the
compromised surface, in this order:

1. Revoke the leaked credential at the provider.
2. Rotate downstream secrets (Fly → Neon → Upstash → Stripe).
3. Invalidate any JWTs (bump `AMPREALIZE_JWT_SECRET`).
4. File a post-incident entry in `docs/INCIDENTS/` within 24 h.

## Automation

`scripts/rotate_secret.sh <SECRET_NAME>` wraps the above commands and is
the preferred call site; the runbook exists for fallback when the script
can't run (e.g. Fly API outage).
