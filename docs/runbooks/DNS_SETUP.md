# DNS Setup — `amprealize.ai` (GUIDEAI-17)

**Status: ✅ Complete (2026-04-20)** — all records live, zone settings applied.

Owner: platform team. Runs once, during M1 bring-up.

## 0. Prereqs

- Cloudflare account with a "Pro" or "Business" plan zone (required for origin lock
  + WAF managed ruleset).
- `wrangler` CLI authenticated (`wrangler login`) for Cloudflare Pages automation.
- GitHub org secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`,
  `CLOUDFLARE_ACCOUNT_ID` populated in the `prod-saas` GitHub Environment.
- `flyctl` CLI authenticated (`flyctl auth login`).

## 1. Register the apex

If `amprealize.ai` is not already owned, register it through Cloudflare Registrar
(cheapest at-cost pricing and avoids the DNS transfer step). Enable registrar
privacy + 2FA on the account.

If the domain is already registered elsewhere, transfer the NS records to
Cloudflare:

1. In the existing registrar, unlock the domain and obtain an auth code.
2. In Cloudflare → Websites → Add site → `amprealize.ai`, free plan initially.
3. Update NS at the old registrar to the two Cloudflare nameservers shown on
   the overview page.
4. Wait for `Status: Active` (typically 5–60 min).

## 2. Zone-level settings ✅

Applied automatically via `CF_API_TOKEN` (see `$REPO_ROOT/.env` for key storage).
Current state verified 2026-04-20:

| Setting | Applied value |
| --- | --- |
| SSL/TLS mode | `strict` (Full strict) |
| Always Use HTTPS | `on` |
| Min TLS version | `1.2` |
| TLS 1.3 + 0-RTT | `on` |
| Automatic HTTPS rewrites | `on` |
| Opportunistic encryption | `on` |
| Security level | `medium` |
| Browser integrity check | `on` |

To re-apply or verify:
```bash
export CF_API_TOKEN=$(grep CLOUDFLARE_API_TOKEN /path/to/.env | cut -d= -f2)
ZONE_ID=546497231d7ac194b21e2f846dc15bb1
for s in ssl always_use_https min_tls_version; do
  curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/$s" \
    -H "Authorization: Bearer $CF_API_TOKEN" | python3 -c "import sys,json;d=json.load(sys.stdin);print('$s:',d['result']['value'])"
done
```

To change settings the dashboard is still the easiest path. The table below lists the intended values:

### Original target table (Cloudflare Dashboard)

| Setting                      | Value                                           |
| ---------------------------- | ----------------------------------------------- |
| SSL/TLS → Encryption mode    | **Full (strict)**                               |
| SSL/TLS → Edge certificates  | Universal SSL **On**, Always Use HTTPS **On**   |
| SSL/TLS → Min TLS version    | **1.2**                                         |
| Security → WAF               | Managed rules ON (Cloudflare Managed Ruleset)   |
| Security → Bot Fight Mode    | **On** (free tier is fine for M1)               |
| Speed → Auto Minify          | HTML + JS + CSS **On**                          |
| Caching → Browser TTL        | Respect existing headers                        |
| Rules → Page Rules           | Add `*.amprealize.ai/api/*` → cache bypass      |

## 3. DNS records ✅

All records created 2026-04-20 via `flarectl`. To manage records:
```bash
export CF_API_TOKEN=$(grep CLOUDFLARE_API_TOKEN /path/to/.env | cut -d= -f2)
flarectl dns list --zone amprealize.ai        # list all
flarectl dns create --zone amprealize.ai ...  # create
flarectl dns update --zone amprealize.ai ...  # update (by ID)
flarectl dns delete --zone amprealize.ai ...  # delete (by ID)
```

Current records (all proxied, TTL auto):

```text
# Record ID                         TYPE   NAME               CONTENT                        STATUS
aa2d414e716d531cbd2e184dac06106a   CNAME  amprealize.ai      amprealize-web.pages.dev       ✅ live
e81658c64a64bf6e87479b2f5368832d   CNAME  www.amprealize.ai  amprealize-web.pages.dev       ✅ live
6c2cb883e7192ef39153184a3363150a   CNAME  app.amprealize.ai  amprealize-console.pages.dev   ✅ live
14c3e9c7bb5f0ed5508458b425454804   CNAME  api.amprealize.ai  amprealize-api-prod.fly.dev    ✅ live (origin pending Fly provision)
95429c15f55766ea516a05509d1d7679   CNAME  mcp.amprealize.ai  amprealize-mcp-prod.fly.dev    ✅ live (origin pending M4)
```

Note: all records are Cloudflare-proxied (orange cloud). `dig CNAME` will return Cloudflare anycast IPs, not the target — this is expected. Use `flarectl dns list --zone amprealize.ai` to see the real targets.

> The `api.` record MUST stay proxied (orange cloud) so Fly's origin sees
> Cloudflare IPs only. Configure Fly to accept the Cloudflare IP ranges with
> `flyctl ips allocate-v4 --shared` + origin-pull CA.

## 4. Verification checklist ✅ (2026-04-20)

```bash
# DNS resolves to Cloudflare anycast (proxied records don't expose CNAME target)
dig +short amprealize.ai           # → 104.26.x.x 172.67.x.x (CF anycast)
dig +short app.amprealize.ai       # → same CF anycast IPs

# HTTP/TLS
curl -I https://amprealize.ai      # ✅ HTTP/2 200
curl -I https://app.amprealize.ai  # ✅ HTTP/2 200 (noindex)
curl -I https://api.amprealize.ai/health  # 530 (expected — Fly origin not provisioned yet)

# Confirm records via flarectl (shows real targets)
export CF_API_TOKEN=$(grep CLOUDFLARE_API_TOKEN /path/to/.env | cut -d= -f2)
flarectl dns list --zone amprealize.ai
```

## 5. Roll-back

- In Cloudflare → Rules → Page Rules, disable the `*.amprealize.ai` rule.
- Delete the `CNAME api` record to pull API traffic offline.
- Set DNS → Proxy → **DNS only** to bypass Cloudflare if the WAF is blocking
  legitimate traffic (then re-enable once the rule is fixed).

## 6. Related plan items

- Work item: [GUIDEAI-17](https://amprealize.ai/work/GUIDEAI-17) (M1 DNS)
- Work item: [GUIDEAI-998](https://amprealize.ai/work/GUIDEAI-998) (M2 `app.` record)
- Dependent steps: Cloudflare Pages setup (`CLOUDFLARE_PAGES_SETUP.md`),
  origin split (`APP_ORIGIN_SPLIT.md`), Fly API deploy (`fly.api.toml`),
  smoke tests.
