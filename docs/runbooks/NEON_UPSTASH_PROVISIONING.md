# Neon + Upstash Provisioning — `amprealize.ai` (M1)

Owner: platform team. Runs once per environment (prod, preview). Outputs the
DSN/secrets required by `fly.api.toml`.

## 0. Prereqs

- Neon account with the org billing set up.
- Upstash account.
- `neonctl` CLI (`npm i -g neonctl`) authenticated via `neonctl auth`.
- `flyctl` CLI authenticated.
- GitHub Environment `prod-saas` ready to receive secrets.

## 1. Neon project

```bash
# Create project in us-east-2 (closest to Fly iad region)
neonctl projects create \
  --name amprealize-prod \
  --region-id aws-us-east-2

# Capture the project id — save in 1Password as NEON_PROJECT_ID_PROD
PROJECT_ID="$(neonctl projects list --output json | jq -r '.[] | select(.name=="amprealize-prod") | .id')"

# Two databases: main (RLS + pgvector) and telemetry (TimescaleDB)
neonctl databases create --project-id "$PROJECT_ID" --name amprealize
neonctl databases create --project-id "$PROJECT_ID" --name amprealize_telemetry

# Two branches so we can point the API and a telemetry worker at isolated compute
neonctl branches create --project-id "$PROJECT_ID" --name main
neonctl branches create --project-id "$PROJECT_ID" --name telemetry
```

### 1.1 Extensions

Connect as the Neon `postgres` role in each database and enable the extensions
the application bootstrap already expects. Neon auto-installs extensions from
an allowlist — no restart needed.

```sql
-- amprealize (main)
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- amprealize_telemetry
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

If `timescaledb` is not yet available on the current Neon tier, open a support
ticket or defer the telemetry DSN until M2. Wiki preview does not need it.

### 1.2 Capture DSNs

```bash
MAIN_DSN=$(neonctl connection-string --project-id "$PROJECT_ID" --branch main --database amprealize --role amprealize)
TELEMETRY_DSN=$(neonctl connection-string --project-id "$PROJECT_ID" --branch telemetry --database amprealize_telemetry --role amprealize)
AUTH_DSN=$MAIN_DSN   # auth/tenant tables share the main DB in M1
```

Store these in GitHub Environment `prod-saas` as secrets:

- `AMPREALIZE_MAIN_DSN`
- `AMPREALIZE_TELEMETRY_DSN`
- `AMPREALIZE_AUTH_PG_DSN`

Also mirror into 1Password vault `amprealize-prod`.

## 2. Run migrations

Two `alembic.ini`s ship with the enterprise repo (`alembic.ini` and
`alembic.telemetry.ini`). Run both from a one-off Fly machine so the IP is
allow-listed in Neon's edge.

```bash
flyctl ssh console -a amprealize-api-prod --command "bash -lc '\
  DATABASE_URL=$AMPREALIZE_MAIN_DSN      alembic -c alembic.ini          upgrade head && \
  DATABASE_URL=$AMPREALIZE_TELEMETRY_DSN alembic -c alembic.telemetry.ini upgrade head'"
```

If the Fly machine does not yet exist (first deploy), run locally instead:

```bash
uv venv && source .venv/bin/activate
uv pip install -e '.[postgres,telemetry]'
DATABASE_URL=$AMPREALIZE_MAIN_DSN alembic -c alembic.ini upgrade head
DATABASE_URL=$AMPREALIZE_TELEMETRY_DSN alembic -c alembic.telemetry.ini upgrade head
```

## 3. Upstash Redis

Provision via dashboard (Upstash CLI is unreliable on macOS). Steps:

1. <https://console.upstash.com/redis> → **Create Database**.
2. Name `amprealize-prod`, region `us-east-1` (shared with Fly iad).
3. Type **Regional**, Eviction **allkeys-lru**, TLS **enabled**.
4. Capture the Redis URL: `rediss://default:<password>@<host>:<port>`.
5. Store as `REDIS_URL` in GitHub Environment `prod-saas`.

## 4. Fly secrets

```bash
flyctl secrets set -a amprealize-api-prod \
  AMPREALIZE_MAIN_DSN="$AMPREALIZE_MAIN_DSN" \
  AMPREALIZE_TELEMETRY_DSN="$AMPREALIZE_TELEMETRY_DSN" \
  AMPREALIZE_AUTH_PG_DSN="$AMPREALIZE_AUTH_PG_DSN" \
  REDIS_URL="$REDIS_URL" \
  AMPREALIZE_JWT_SECRET="$(openssl rand -base64 48)"
```

## 5. Verification

```bash
psql "$AMPREALIZE_MAIN_DSN"      -c "SELECT extname FROM pg_extension;"
psql "$AMPREALIZE_TELEMETRY_DSN" -c "SELECT extname FROM pg_extension;"
redis-cli -u "$REDIS_URL" PING   # → PONG
curl -fsS https://api.amprealize.ai/health
```

## 6. Cost sanity check

Neon `scale` plan (~$19/mo + usage) and Upstash pay-as-you-go stay under $50/mo
for the M1 wiki-only preview. Nothing in the wiki path hits Postgres except the
admin/auth checks which are skipped in public-preview mode.

## 7. Related

- Work items: [GUIDEAI-19](https://amprealize.ai/work/GUIDEAI-19)
  (API deployment) and [GUIDEAI-17](https://amprealize.ai/work/GUIDEAI-17) (DNS).
- Secrets playbook: [SECRETS_MANAGEMENT_PLAN](../SECRETS_MANAGEMENT_PLAN.md).
- Disaster recovery: [DISASTER_RECOVERY_POLICY](../DISASTER_RECOVERY_POLICY.md).
