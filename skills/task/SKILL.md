---
name: task
description: >-
  Small coding task with Codex review. The implementer subagent (Opus) implements
  in place, Codex reviews through duet-codex, bounded fixes follow, then the main
  session reviews the stage. Use when the user asks for a small change with Duet
  or with a Codex review.
---

Read `${CLAUDE_PLUGIN_ROOT}/protocol.md` first and follow it throughout.

1. **Run.** In the project root: `duet-codex init --scenario task --cwd .`; note `<run>`. Write `<run>/task.md`: the task as understood, concrete acceptance criteria, the base commit from `git rev-parse HEAD`, and the check commands (from `.duet.json` `checks` if present; otherwise inferred from the project and confirmed with the user). Ask one clarifying question only if the request cannot be understood from the message and the code. Save external material under `<run>/context/`. Resolve rule sets if named (protocol, Rule sets).
2. **Implement.** Follow the protocol's Implementation stage with N = 1 and the task file; the implementer works in the project root.
3. **Stage review.** Follow the Stage review checklist. Return work to the implementer while code-review calls remain; otherwise stop with `needs_human`.
4. **Report.** Write `<run>/report.md` as the protocol's Reports section describes and tell the user: what changed, check results, open items, the report path. The user commits.
