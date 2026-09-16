---
name: feature
description: >-
  Large task with planning. Optional research, a plan reviewed by Codex,
  implementation by the implementer subagent (Opus) in a worktree, project checks,
  Codex code review with bounded fixes, and a main-session stage review. Use when
  the user asks for a feature with Duet or wants plan review before implementation.
---

Read `${CLAUDE_PLUGIN_ROOT}/protocol.md` first and follow it throughout.

1. **Run.** In the original checkout: `duet-codex init --scenario feature --cwd .`; note `<run>` (absolute; it stays in the original checkout). Write `<run>/task.md` with the task, acceptance criteria and the check commands (from `.duet.json` `checks` if present; otherwise inferred and confirmed with the user). Save external material under `<run>/context/`. Resolve rule sets if named.
2. **Research (optional).** If the task needs understanding of how the code works first, follow the protocol's Research stage inside this run.
3. **Worktree.** Enter a worktree with the `EnterWorktree` tool, named after the task. Then `duet-codex mark --run <run> --stage worktree --status done --note "<worktree path>"` and record the worktree's base commit (`git rev-parse HEAD` inside it) in `task.md`. From here every `duet-codex call` uses `--cwd .` (the worktree) and the implementer works in the worktree.
4. **Plan.** `duet-codex mark --run <run> --stage plan --status started`. Write `<run>/plan.md`: decisions, affected files and areas, risks, how each acceptance criterion will be verified. No line-by-line pseudocode. Mark `--status done`.
5. **Plan review.** Write `<run>/plan-review-material-1.md` (task, acceptance criteria, the plan) and run `duet-codex call --run <run> --stage plan-review --prompt <run>/plan-review-material-1.md --cwd . [--context <rules>]`. On `changes_requested`: revise `plan.md`, write `plan-review-material-2.md` with what changed per finding ID, and call again with `--resume <session_id>`. At most two revisions; then `needs_human`. On `needs_human`: show the questions to the user and wait. Read results from the printed `result` path.
6. **Implement.** Follow the protocol's Implementation stage with N = 1, the task file and `plan.md`; the implementer works in the worktree.
7. **Stage review.** Follow the Stage review checklist, comparing the diff against `plan.md` as well. The code-review budget is shared between the implementer's rounds and your returns.
8. **Report.** `<run>/report.md` with the plan, review history, checks and open items. Tell the user the worktree path and branch, what to look at, the report path. The user merges; do not leave the worktree with `ExitWorktree` unless the user asks.
