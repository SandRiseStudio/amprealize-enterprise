---
title: "LLM Routing in Amprealize"
type: in-practice
difficulty: advanced
prerequisites:
  - concepts/agents.md
  - concepts/prompt-engineering.md
  - in-practice/context-composition.md
tags:
  - amprealize
  - llm-routing
  - governance
  - byok
last_updated: "2026-04-26"
sources:
  - "amprealize/chat_action_router.py"
  - "amprealize/services/conversation_reply_service.py"
  - "amprealize/mcp/handlers/config_handlers.py"
  - "amprealize/web-console/src/api/conversations.ts"
  - "amprealize/llm/types.py"
  - "amprealize/work_item_execution_service.py"
amprealize_relevance: "Explains how Amprealize lets chat choose models while preserving governed action routing and permission recomputation."
visibility: internal
---

# LLM Routing in Amprealize

## What It Is

LLM routing lets Amprealize use a language model to classify a chat message into a governed action, while still treating the existing typed route contract as the safety boundary. The model can propose a route, but it cannot invent permissions or grant itself approval.

## The Flow

```
Chat composer selects model
    ↓
Message metadata records provider/model/credential scope
    ↓
ChatRouteGateway chooses deterministic, LLM, or hybrid routing
    ↓
LLMChatActionRouter returns strict JSON candidates
    ↓
Post-validation rebuilds ChatActionCandidate
    ↓
Permission scopes and approval flags are recomputed from the permission matrix
    ↓
Conversation replies store route metadata and emit governed audit records
```

## Safety Boundary

The LLM output is accepted only when it maps to known route categories, permission surfaces, permission actions, risk values, and action IDs. After parsing, Amprealize recomputes required scopes and approval flags with `get_chat_permission_requirement()` rather than trusting the model's text.

If the LLM returns invalid JSON, unknown actions, hallucinated enum values, or no candidates, routing falls back to the deterministic router and records the fallback reason in metadata.

## Model And Credential Selection

The web and VS Code chat composers pass `llm_model_id`, `llm_provider`, and `credential_scope` in message metadata. The backend validates that the selected model exists and that a user, project, org, or platform credential is available before persisting model metadata.

Global/personal chat intentionally defaults to the NVIDIA free/open model plan for now. The user model availability endpoint defaults to `provider_filter=nvidia` and `free_open_only=true`, and the web console passes those query params explicitly so frontier platform models do not appear in the global chat selector. The curated global chat list maps the short product names to NVIDIA NIM API model names: DeepSeek V4 Flash (`deepseek-ai/deepseek-v4-flash`), DeepSeek V4 Pro (`deepseek-ai/deepseek-v4-pro`), MiniMax M2.7 (`minimaxai/minimax-m2.7`), Kimi K2 Thinking (`moonshotai/kimi-k2-thinking`), Qwen3 Coder (`qwen/qwen3-coder-480b-a35b-instruct`), GPT-OSS 120B (`openai/gpt-oss-120b`), Mistral Large 3 (`mistralai/mistral-large-3-675b-instruct-2512`), GLM 5.1 (`z-ai/glm-5.1`), Llama 3.1 Nemotron Ultra (`nvidia/llama-3.1-nemotron-ultra-253b-v1`), and Llama 3.3 70B (`meta/llama-3.3-70b-instruct`).

BYOK resolution keeps the fail-closed invariant: when a scoped key exists but is invalid, Amprealize does not silently fall back to a platform key for that provider.

Users manage personal BYOK provider keys from the web console account settings page at `/settings`. The UI calls the user-scoped credential endpoints through authenticated requests, stores only encrypted keys server-side, displays masked key prefixes, and invalidates model availability after add/delete/re-enable so global chat picks up newly saved NVIDIA keys without a manual refresh.

## Key Files

- `amprealize/chat_action_router.py` — `ChatRouteGateway`, `LLMChatActionRouter`, and the deterministic fallback contract.
- `amprealize/services/conversation_reply_service.py` — live reply routing, selected model forwarding, route metadata, and governed audit records.
- `amprealize/services/conversation_api.py` — REST model metadata validation.
- `amprealize/services/conversation_events_api.py` — WebSocket model metadata transport and validation.
- `amprealize/mcp/handlers/config_handlers.py` — model availability filtering and serialization.
- `amprealize/llm/types.py` — provider/model catalog, including NVIDIA NIM defaults.
- `amprealize/work_item_execution_service.py` — BYOK credential precedence and model availability.
- `web-console/src/components/UserLLMCredentialsSection.tsx` — account settings UI for user-scoped BYOK keys.

## See Also

- [Agent Orchestration in Amprealize](agent-orchestration.md)
- [Context Composition in Amprealize](context-composition.md)
- [Prompt Engineering](../concepts/prompt-engineering.md)
