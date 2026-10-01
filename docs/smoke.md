# Manual smoke checklist (real CLIs)

Run once per scenario on a small sample project before tagging a release. Each item is a real Claude Code session started with `claude --plugin-dir /path/to/duet-plugin`.

1. `duet-codex --version` and `codex login status` succeed inside the session's Bash; `claude plugin validate /path/to/duet-plugin --strict` reports no errors.
2. `/duet:task Add a --version flag to the CLI with a test.` → implementer runs, `code-review-1.json` exists, stage review happens, `report.md` written, working tree contains the change, nothing committed.
3. `/duet:feature` on a two-file change → `plan-review-1.json`, implementation in place in the working tree, no worktree created, report written. Repeat with "in a worktree" in the request → run dir in the original checkout, worktree entered, implementation in the worktree, report names the worktree path and branch.
4. `/duet:research Why does module X exist?` → `research.md` with `R-n` claims, `critique-1.json` classifying each of them once, `synthesis.md` with a claims table.
5. `/duet:review --base main --head <branch>` → `<run>/head` checkout created, `review-claude.md` and `mr-review-1.json` produced independently, `synthesis.md` with dispositions for every `C-n`/`X-n`, head checkout removed.
6. Force a limit: set `{"stages": {"code-review": {"limit": 1}}}` in `~/.config/duet/roles.json`, run `/duet:task` on a task that will get `changes_requested`; the run stops with exit 3 and asks; `duet-codex limit --run <run> --stage code-review --set 3` lets it continue.
7. Edit a file while a background `mr-review` runs → the call ends `stale` (exit 5) and the skill reports it instead of accepting the review.
8. Return path: in `/duet:task`, reject the implementer's result once in the stage review → the second dispatch resumes the previous Codex session (`resume_of` set in the journal) and the journal shows one more `code-review` call.
