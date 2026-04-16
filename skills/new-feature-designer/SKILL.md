# Skill: New Feature Designer

**Slug**: `new-feature-designer`
**Version**: 1.0
**Role**: Teacher (facilitates structured feature design)

## Purpose

Conducts a thorough, structured feature intake interview to produce a **Feature Definition** document for Amprealize. This skill is a **designer/interviewer only** — it does not implement features, create work items, or write code. It ensures every feature is fully fleshed out before implementation starts.

## When to Apply

### Must Use
- A new product feature is being considered (not a bug fix or chore)
- A significant enhancement to an existing feature needs scoping
- A feature needs cross-surface planning (MCP, API, CLI, Web, Extension)
- Enterprise vs. OSS distribution decisions need to be made

### Recommended
- Refactoring that will change user-facing behavior
- Adding a new service or package to the platform
- Feature flag rollout planning

### Skip
- Simple bug fixes with obvious scope
- Documentation-only changes
- Direct work item creation (use `work-item-planner` skill instead)
- Implementation (use Plan agent or implement directly)

## Input Contract

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `feature_idea` | string | yes | — | Natural-language description of the feature |
| `project_id` | string | no | session context | Target project for the feature |
| `edition` | enum | no | discovered | `oss` \| `enterprise_starter` \| `enterprise_premium` |
| `surfaces` | list | no | all | Surfaces to evaluate: `mcp`, `api`, `cli`, `web`, `vscode` |

## Output Contract

Returns a structured Feature Definition document:

```json
{
  "version": "1.0",
  "feature_name": "Behavior Versioning Diff View",
  "summary": "...",
  "distribution": {
    "edition": "oss",
    "feature_flag": "ENABLE_BEHAVIOR_DIFF_VIEW",
    "rollout_strategy": "percentage",
    "starter_cap": null,
    "oss_stub_pattern": null
  },
  "surface_coverage": [
    {
      "surface": "web",
      "day_one": true,
      "follow_up": false,
      "notes": "React component in behavior detail panel"
    }
  ],
  "services_impacted": [
    {
      "service": "BehaviorService",
      "impact_type": "modified",
      "description": "Add versioning diff endpoint"
    }
  ],
  "data_model_changes": [],
  "behavioral_context": {
    "existing_behaviors": ["behavior_curate_behavior_handbook"],
    "new_behaviors": [],
    "primary_role": "Student"
  },
  "security": {
    "auth_level": "authenticated",
    "new_permissions": [],
    "audit_logging": ["behavior.diff.viewed"],
    "data_sensitivity": "internal"
  },
  "acceptance_criteria": [
    "Given two behavior versions, when a user views the diff, then additions are highlighted green and deletions red",
    "Given a behavior with only one version, when a user opens diff view, then a message indicates no previous version exists"
  ],
  "testing_requirements": {
    "parity_surfaces": ["web", "api"],
    "unit_coverage_target": 90,
    "integration_tests": ["BehaviorService.get_diff()"]
  },
  "open_questions": []
}
```

## Interview Phases

The interview always covers these 7 phases in order:

1. **Identity & Distribution** — Name, pitch, edition, feature flag, caps
2. **Surface Coverage** — Day-one vs. follow-up per surface, UX considerations
3. **Architecture & Integration** — Services, data model, config, migration
4. **Behavioral Context** — Existing/new behaviors, role, AGENTS.md updates
5. **Feature Interactions** — Dependencies, impacts, compatibility, migration
6. **Security & Compliance** — Auth, permissions, audit, data sensitivity
7. **Success & Testing** — Acceptance criteria, metrics, test strategy, docs

## Usage

### As Agent (primary mode)
Invoke `@NewFeature` in VS Code Copilot Chat:
```
@NewFeature Add a behavior versioning diff view that shows changes between behavior versions
```

### As Playbook Reference
The full interview framework is documented in:
`amprealize/agents/playbooks/AGENT_NEW_FEATURE.md`

### Programmatic (future)
```python
from amprealize.agents.feature_designer.models import FeatureDefinition

definition = FeatureDefinition(
    feature_name="Behavior Versioning Diff View",
    summary="Shows side-by-side diff of behavior version changes",
    edition=Edition.OSS,
    ...
)
```

## Handoff Targets

After producing a Feature Definition, the output can be handed to:

| Target | Purpose |
|--------|---------|
| **Plan agent** | Create a phased implementation plan |
| **WorkItemPlanner** | Generate GWS-compliant work items |
| **Markdown file** | Save as standalone document for team review |

## Related Behaviors

- `behavior_define_feature_scope` — Primary behavior for this skill
- `behavior_validate_cross_surface_parity` — Surface coverage validation
- `behavior_design_api_contract` — API contract design (Phase 3)
- `behavior_lock_down_security_surface` — Security review (Phase 6)
- `behavior_design_test_strategy` — Test strategy (Phase 7)
