# PostHog — Web Console Operator Runbook

Product analytics for the amprealize web console SPA. Covers setup,
configuration, PII policy, event catalog, dashboards to build, and opt-out.

---

## 1. Quick start (production)

1. Create a **PostHog Cloud** project at [posthog.com](https://posthog.com)
   (US or EU region — choose per your DPA).
2. Copy the **Project API Key** (format: `phc_…`).
3. Inject it into the build as `VITE_POSTHOG_KEY`:
   ```bash
   flyctl secrets set -a amprealize-web-prod VITE_POSTHOG_KEY="phc_..."
   # Also set in GitHub Environment prod-saas for CI builds.
   ```
4. Optionally override the ingest host for EU:
   ```bash
   flyctl secrets set VITE_POSTHOG_HOST="https://eu.i.posthog.com"
   ```
5. Redeploy — events will begin flowing immediately on the next build.

---

## 2. Configuration reference

| Env var | Required | Default | Notes |
|---|---|---|---|
| `VITE_POSTHOG_KEY` | Yes (for analytics) | _(empty = disabled)_ | Project API Key from PostHog settings |
| `VITE_POSTHOG_HOST` | No | `https://us.i.posthog.com` | Change to `eu.i.posthog.com` for EU data residency |
| `VITE_POSTHOG_ENABLED` | No | `false` | Set `true` to enable on `localhost` for development testing |
| `VITE_GIT_SHA` | No | _(empty)_ | Injected by CI; attached to every event as `git_sha` |

All four are build-time Vite env vars (prefixed `VITE_`). They are inlined at
build time — changing them requires a redeploy.

---

## 3. Local development

PostHog is disabled by default on `localhost`. To verify instrumentation
during development:

```bash
# web-console/.env.local  (never committed)
VITE_POSTHOG_KEY=phc_your_dev_project_key
VITE_POSTHOG_ENABLED=true
```

Then run `npm run dev` and open the PostHog project — events land in
real-time in the **Activity** tab.

---

## 4. Event catalog (v1)

All events carry ambient properties automatically:

| Ambient prop | Value |
|---|---|
| `surface` | `"web-console"` |
| `git_sha` | Value of `VITE_GIT_SHA` at build time |
| `tenant_id` | Set after login via `identifyUser()` |
| `edition` | Set after login via `identifyUser()` |

### Session / Auth

| Event | Trigger |
|---|---|
| `$pageview` | Every react-router navigation |
| `$pageleave` | Before each non-first navigation |
| `user_signed_in` | Device flow or OAuth login completes |
| `user_signed_out` | Explicit logout |

### Behavior system

| Event | Trigger | Key props |
|---|---|---|
| `behavior_retrieved` | BCI search result returns | `behaviorSlug`, `topK`, `source` |
| `behavior_applied` | User applies a behavior to context | `behaviorSlug`, `context` |
| `plan_created` | New plan is created | `hasChecklist`, `behaviorCount` |
| `plan_opened` | Existing plan is opened | `planId` |

### Board / Work items

| Event | Trigger | Key props |
|---|---|---|
| `board_opened` | Board shell renders | `projectId`, `boardId`, `view` |
| `board_item_created` | Work item created | `projectId`, `boardId`, `itemType` |
| `board_item_moved` | Item moved between columns | `fromStatus`, `toStatus` |
| `board_view_toggled` | User switches board/outline/gantt | `view` |

### Wiki

| Event | Trigger | Key props |
|---|---|---|
| `wiki_page_viewed` | Article renders | `domain`, `path` |
| `wiki_search_submitted` | User navigates to a search result | `query` (email-redacted), `domain` |

### Workspace

| Event | Trigger | Key props |
|---|---|---|
| `workspace_switched` | Org context changes | `fromOrgId`, `toOrgId` |
| `edition_banner_cta_clicked` | Edition upgrade CTA clicked | `currentEdition`, `targetEdition`, `ctaLabel` |

---

## 5. Identity model

Persons are identified with `posthog.identify()` using:

- **Distinct ID**: `user.id` (UUID, never PII in the ID itself).
- **Person properties**: `email`, `name` (display name), `tenant_id`, `edition`.

`posthog.reset()` is called on logout — subsequent events are anonymous
until the next login.

---

## 6. Session replay

Session replay is enabled with aggressive masking:

- `maskAllText: true`
- `maskAllInputs: true`
- `blockAllMedia: true`

To mark a specific element as safe to display unmasked (e.g. a public label),
add the `ph-no-mask` CSS class. Use sparingly; never on form fields or
content typed by users.

---

## 7. PII policy

| Data | Where | Risk level | Mitigation |
|---|---|---|---|
| `email` | Person property on `identify` | Medium | Only stored as PostHog person property; not in event bodies |
| `query` (wiki search) | `wiki_search_submitted.query` | Low | `analyticsEvents.ts` redacts any string matching an email pattern to `[redacted:email]` |
| Page URLs | `$pageview.$current_url` | Low | Numeric path segments are normalised to `:id` by `usePageviewTracking` |
| Session replay content | Replay | Medium | All text and inputs masked globally |

Amprealize's DPA with PostHog covers the data flows above. If you change the
`identify` payload to include additional PII fields, update this document and
notify legal.

---

## 8. Opt-out

Users (or operators) can disable PostHog capture at runtime:

```js
// In browser console or from a Settings UI:
localStorage.setItem('amprealize.posthog', 'off');
location.reload(); // takes effect on next init
```

The wrapper also exports `optOut()` / `optIn()` from `src/lib/posthog.ts`
for integration into a settings page.

---

## 9. PostHog dashboards (live)

| Dashboard | URL | Insights |
|---|---|---|
| **Activation Funnel** | [open](https://us.posthog.com/project/316329/dashboard/1489249) | Sign-in → Board opened → Item created funnel; DAU trend |
| **Behavior Adoption** | [open](https://us.posthog.com/project/316329/dashboard/1489251) | Weekly unique users retrieving behaviors; top behavior slugs |
| **Wiki Engagement** | [open](https://us.posthog.com/project/316329/dashboard/1489253) | Page views by domain (weekly stacked bar); search volume over time |
| **Retention** | [open](https://us.posthog.com/project/316329/dashboard/1489254) | 8-week recurring retention table; WAU area chart |
| **Edition Upgrade Intent** | [open](https://us.posthog.com/project/316329/dashboard/1489255) | CTA clicks by current edition (bar); by target edition (pie) |

---

## 10. Secret rotation

See `docs/runbooks/SECRETS_ROTATION.md` → _PostHog project API key_ section.
Cadence: **annual** or immediately on suspected exposure.
