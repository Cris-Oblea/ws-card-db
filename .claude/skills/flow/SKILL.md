---
name: flow
description: Lightweight orchestrator for ws-card-db. The MAIN LOOP runs it to coordinate a NON-TRIVIAL change through architect → 🚦 your approval → the right dev-agent → reviewer. No GitHub issue, no PR ceremony, no board — this is a personal repo. SKIP it for small/obvious edits and read-only tasks (just answer or run the step inline). Invoke at the start of a multi-step feature.
---

# flow — lightweight orchestrator (ws-card-db)

The **main loop** runs this skill as orchestrator: it does not write code or design itself — it delegates to the project's sub-agents in order and carries context between them.

> **Why a skill, not an agent.** The orchestrator must spawn sub-agents, and in Claude Code a sub-agent cannot spawn other sub-agents (one-level nesting) — only the main loop has the `Agent` tool. So orchestration runs in the main loop via this skill. Never invoke it *as* a sub-agent.

## When to use it (and when NOT)

- **Use it** for a non-trivial, multi-step change (new pipeline stage, cost-model change, web feature) where a plan + review add value.
- **Skip it** for small/obvious edits, one-file fixes, or read-only tasks (querying, searching, reading). This is a personal repo — `CLAUDE.md` says "skip steps when the task is small/obvious." Do not add ceremony where it doesn't pay off.

## The flow

```
request → architect (plan + trade-offs + which dev-agent) → 🚦 you approve → dev-agent → reviewer (empirical validation)
```

1. **architect** — reads `CLAUDE.md`, inspects the real code, proposes *how* to solve it (plan, trade-offs, which files) and **which dev-agent** takes each part. Does not code.
2. **🚦 Human gate** — you approve the plan before any code is written. Do not proceed on your own.
3. **dev-agent** — the specialist implements the approved plan:
   - **`pipeline-dev`** — extraction / cleaning / build pipeline.
   - **`cost-analyst`** — the cost model, validation, accuracy.
   - **`web-maintainer`** — the static lookup website.
4. **reviewer** — validates the result. **This is a data/research project: there are no classic unit tests.** The reviewer validates **empirically**: % accuracy vs the official list, audits (`cardlist_audit.json`), counts and suspects — not assertions. Iterate back to the dev-agent if it doesn't hold up.

## Acceptance check (the yardstick)

In the plan, the architect states a short **"done" list** — the concrete, checkable outcomes (e.g. "≥98% accuracy preserved", "costs stay multiples of 500", "audit counts unchanged"). The reviewer validates against that list. Keep it to a few bullet points, not a formal spec.

## Optional paper trail (only for bigger features)

For a sizeable feature, keep a minimal trail under `documentation/imp/{feature-name}/`:
- `plan.md` — architect's plan + the "done" list + which dev-agent.
- `review.md` — reviewer's verdict against the "done" list.

Skip the trail for small changes. (If you want it ephemeral rather than versioned, add `documentation/imp/` to `.gitignore`.) Do **not** use `site/` — that is the deployed web app.

## Closing

When the review holds up and you approve: commit (English, conventional commits) and push to `main` directly — or a lightweight self-PR only if you want to eyeball the diff. **No mandatory issue, no external review** (personal repo). Keep `CLAUDE.md` + `documentation/` up to date as part of finishing the change.
