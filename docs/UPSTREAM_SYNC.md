# Upstream OSS Sync Guide

This document describes how the enterprise repository stays in sync with the
open-source (OSS) upstream and how to resolve conflicts when they arise.

## How sync works

A GitHub Actions workflow (`.github/workflows/upstream-sync.yml`) runs daily:

1. Fetches the latest `main` from the OSS repo
2. Checks if there are new commits
3. Attempts a merge
4. **No conflicts** → creates a PR automatically
5. **Conflicts detected** → creates a GitHub issue listing the conflicted files

You can also trigger it manually from **Actions → Upstream OSS Sync → Run workflow**.

## Setup (one-time)

Add the OSS repo as a remote on your local machine:

```bash
cd amprealize-enterprise
git remote add upstream https://github.com/amprealize/amprealize.git
git fetch upstream
```

## Resolving conflicts manually

When the automated sync reports conflicts:

```bash
# 1. Fetch latest upstream
git fetch upstream main

# 2. Create a sync branch
git checkout main
git pull origin main
git checkout -b sync/upstream-manual

# 3. Merge upstream (this will show conflicts)
git merge upstream/main

# 4. Resolve conflicts
# Open each conflicted file and resolve. Common patterns:
#   - Enterprise overrides (edition.py, caps_enforcer.py) → keep enterprise version
#   - Shared code (api.py, services) → merge both changes carefully
#   - New OSS files → accept as-is unless they conflict with enterprise features

# 5. Mark resolved and commit
git add .
git commit  # The merge commit message is pre-filled

# 6. Push and create PR
git push origin sync/upstream-manual
# Then create a PR: sync/upstream-manual → main
```

## Common conflict patterns

### 1. `amprealize/edition.py`

The enterprise fork overrides `detect_edition()` to resolve Starter/Premium.
The OSS version always returns `Edition.OSS`.

**Resolution**: Keep the enterprise version. If OSS added new fields to
`EditionCapabilities` or new entries to `_VALID_TRANSITIONS`, merge those
additions into the enterprise file.

### 2. `amprealize/caps_enforcer.py`

Enterprise extends the caps enforcer with org-level enforcement.

**Resolution**: Keep the enterprise version, but if OSS added new cap fields,
add them to the enterprise enforcer too.

### 3. `amprealize/cli.py`

Both repos modify the CLI. The OSS version has upgrade hooks that import
`amprealize_enterprise` conditionally.

**Resolution**: Accept both changes. If OSS added a new subcommand, it should
merge cleanly. If both repos modified the same function, review line-by-line.

### 4. New migration files

If both repos added Alembic migrations, you'll get a branch (two heads).

**Resolution**:
```bash
# After merge, check for multiple heads
alembic heads

# If multiple heads, create a merge migration
alembic merge -m "merge_oss_enterprise_migrations" <head1> <head2>
```

### 5. `pyproject.toml`

Version bumps or dependency changes on both sides.

**Resolution**: Take the higher version for each dependency. For the project
version, use the enterprise version (it tracks its own version separately).

### 6. CI workflows (`.github/workflows/`)

These are typically independent per repo. The enterprise repo has its own CI.

**Resolution**: Keep the enterprise version. If OSS added a new workflow file,
accept it and adjust if it references OSS-only infrastructure.

## Files the enterprise repo owns

These files are **always** resolved in favor of the enterprise version:

- `amprealize/edition.py` — enterprise edition detection
- `amprealize/caps_enforcer.py` — enterprise caps enforcement
- `src/` — enterprise-only source modules
- `.github/workflows/ci.yml` — enterprise CI pipeline
- `pyproject.toml` — enterprise version and deps

## Files the OSS repo owns

These files should typically accept the OSS version:

- `amprealize/` (most files) — shared business logic
- `tests/` — shared test suite
- `scripts/check_enterprise_guard.py` — OSS-side guard
- `docs/MIGRATION_GUIDE.md` — shared migration docs
- `schema/` — shared schema definitions

## Verifying a sync

After merging upstream changes:

```bash
# 1. Run the enterprise guard (should pass — enterprise repo is allowed)
python scripts/check_enterprise_guard.py || true

# 2. Run tests
./scripts/run_tests.sh --breakeramp

# 3. Verify edition detection still works
python -c "from amprealize.edition import detect_edition; print(detect_edition())"

# 4. Check for Alembic migration branch conflicts
alembic heads  # Should show exactly 1 head
```

## Workflow schedule

| Trigger | Frequency | What happens |
|---------|-----------|-------------|
| Cron | Daily 06:00 UTC | Auto-sync, PR or issue |
| Manual | On demand | Same, with optional branch override |
| Dry run | On demand | Preview only, no merge/PR |
