# Chat Permission Matrix Contract

**Status:** Contract locked for `guideai-1051`; consumed by `guideai-1052` policy composition  
**Source of truth:** `amprealize/conversation_contracts.py`

This contract defines the permission model for Amprealize Chat. Runtime enforcement consumes the matrix through `PolicyCompositionEngine` so surfaces do not re-derive chat-specific rules.

## Actions

| Action | Meaning |
| --- | --- |
| `read` | View a conversation, resource link, thread, tool metadata, attachment, or platform-action result. |
| `create` | Create the surface or create content within it. |
| `update` | Edit metadata, content, membership settings, lifecycle state, or mutable configuration. |
| `delete` | Soft-delete, archive, remove, revoke, or otherwise make the surface unavailable. |
| `invite_share` | Invite participants, share links, expose resources to another conversation, or grant collaborative access. |
| `execute` | Start a run, invoke an agent, call a tool, transform an attachment, or trigger a platform mutation. |
| `publish` | Promote draft/private content to a broader project, organization, or public-facing channel. |
| `administer` | Manage ownership, policy, retention, lifecycle, grants, or surface-level settings. |

## Scope Types

| Scope | Boundary |
| --- | --- |
| `user` | A single authenticated user and their personal global chat settings. |
| `org` | Organization membership, grants, policy, compliance, and organization-wide admin controls. |
| `project` | Project membership, project settings, assigned agents, work items, runs, files, and tools. |
| `conversation` | Explicit conversation membership, participant role, thread membership, and message ownership. |
| `agent` | An agent identity, lifecycle state, assignment, tool grant, and current run authority. |

## Matrix

Cells list the scopes that may authorize the action. `approval` means the action is allowed only after an explicit confirmation, grant, or gate decision. `deny` means the action is not supported by default.

| Surface | Read | Create | Update | Delete | Invite/share | Execute | Publish | Administer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `global_chat` | `user` | `user` | `user` | `user` | deny | approval: `user` | deny | `user` |
| `project_space` | `project` | `project` | `project` | `project` | `project` | approval: `project` | `project` | `project` |
| `group_chat` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | approval: `conversation`, `project` | `conversation`, `project` | `conversation`, `project` |
| `work_item_thread` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | approval: `conversation`, `project` | `conversation`, `project` | `conversation`, `project` |
| `run_thread` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | `conversation`, `project` | approval: `conversation`, `project` | `conversation`, `project` | `conversation`, `project` |
| `agent_lifecycle` | `org`, `project`, `agent` | `org`, `project`, `agent` | `org`, `project`, `agent` | `org`, `project`, `agent` | `org`, `project`, `agent` | approval: `org`, `project`, `agent` | `org`, `project`, `agent` | `org`, `project`, `agent` |
| `mcp_tool` | `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` | approval: `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` |
| `attachment` | `user`, `conversation`, `project` | `user`, `conversation`, `project` | `user`, `conversation`, `project` | `user`, `conversation`, `project` | `user`, `conversation`, `project` | approval: `user`, `conversation`, `project` | `user`, `conversation`, `project` | `user`, `conversation`, `project` |
| `platform_action` | `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` | approval: `user`, `org`, `project` | `user`, `org`, `project` | `user`, `org`, `project` |

## Deny-By-Default

Any action/surface pair missing from `CHAT_PERMISSION_MATRIX`, any request with no recognized `user`, `org`, `project`, `conversation`, or `agent` scope, and any conflicting scope set that cannot be reconciled by most-restrictive-wins must be denied. Global chat never grants access to linked project resources; each linked work item, run, file, tool, attachment, or platform action must pass its own scope check.

## Runtime Consumption

- `PolicyCompositionEngine` maps `allow`, `require_approval`, and `deny` matrix effects to runtime `allow`, `review`, and `deny` decisions.
- The engine composes the matrix with user, org, project, conversation, agent, MCP/tool, attachment, and action-risk policies using most-restrictive-wins semantics.
- Deny overrides allow, review gates sensitive operations until `approved_by` is present, and evaluation failures fail closed with policy audit events.
- No migration changes are required for the contract itself.
- Runtime enforcement is tracked by `guideai-1052`.
