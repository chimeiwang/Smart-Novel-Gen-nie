---
name: novelwriter-agent-architecture
description: Use when modifying, reviewing, or designing NovelWriter's Agent system, LangGraph StateGraph workflow, agent nodes, tool calling, SSE streaming, writing chat APIs, conversation history, routing, or src/agents documentation.
---

# NovelWriter Agent Architecture

Use this skill for changes to NovelWriter's intelligent writing Agent system and chat orchestration.

## Required References

Read the relevant files before changing behavior:

```text
AGENTS.md
src/agents/AGENTS.md
src/agents/graph/state.ts
src/agents/graph/executor.ts
src/agents/graph/nodes/
src/agents/lib/llm-wrapper.ts
src/agents/lib/tools.ts
```

Load only the files needed for the task.

## Architecture Rules

- The core Agent IDs are `设定`, `剧情`, `写作`, `校验`.
- Agent orchestration uses LangGraph `StateGraph`.
- Agent output should remain structured JSON where applicable: `content`, `wantsToCall`, `insights`, `proactiveSuggestions`, and Agent-specific fields.
- Tool-capable Agents should use `callLLMWithTools`.
- Do not expose full tool results to the frontend by default. Frontend-visible events should show tool name and short argument summaries only.
- SSE should separate visible assistant content from status/tool telemetry.
- Frontend chat bubbles should receive only user-facing content, not tool result blobs or raw internal JSON.
- Preserve conversation history and call-chain depth protections.

## Documentation Rule

If Agent flow, routing, SSE event semantics, tool visibility, Agent IDs, or node responsibilities change, update:

```text
src/agents/AGENTS.md
```

If root-level developer guidance changes, update:

```text
AGENTS.md
```

## Validation

- Run `npm run typecheck` after code changes.
- Run targeted manual checks for SSE event order when changing streaming behavior.
- Verify that tool results remain hidden by default in frontend chat UI.

