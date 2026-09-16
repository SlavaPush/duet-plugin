# Duet

Claude Code plugin where Claude and Codex work together in four scenarios, with every Codex call journaled and bounded.

| Command | What happens |
| --- | --- |
| `/duet:task` | Implementer subagent (Opus) implements in place, Codex reviews, bounded fixes, main-session stage review |
| `/duet:feature` | Optional research, plan reviewed by Codex, implementation in a worktree, checks, Codex code review, stage review |
| `/duet:research` | Claims with evidence, Codex critique, answer with visible disagreements |
| `/duet:review` | Fresh Claude reviewer and Codex review the same state independently, then a synthesis |

## Requirements

Claude Code, Codex CLI signed in (`codex login status`), Python 3.9+, Git. macOS or Linux.

## Install

From this repository as a marketplace:

```
/plugin marketplace add <github-user>/duet-plugin
/plugin install duet@duet-plugin
```

For a local checkout: `claude --plugin-dir /path/to/duet-plugin`.

## Configuration

- `~/.config/duet/roles.json` overrides any subset of `config/roles.json` (Codex model, per-stage effort, resume effort, per-run call limits, timeouts). Unknown keys and invalid values are errors.
- `~/.config/duet/settings.json` may define `rules`: named lists of Markdown files (paths relative to that directory) that skills pass to reviewers and the implementer when you name them.
- Optional `.duet.json` in a project: `{"checks": ["npm test", "npm run lint"]}`.

## Runs

Each run lives in `<repo>/.duet/runs/<scenario>-<timestamp>/` (excluded from git): `journal.json` is the timeline, `report.md` or `synthesis.md` the result, `<stage>-N.json` the parsed Codex answers, `<stage>-N.raw.md` the raw ones, `logs/` the CLI logs. `duet-codex status --run <dir>` prints the timeline.

Limits per run: plan review 3 calls, code review 4, critique 2, MR review 2. An exhausted limit stops the run and asks you; raise it with `duet-codex limit --run <dir> --stage <stage> --set N`.

## Adapter

`bin/duet-codex` makes one `codex exec` call per invocation: read-only sandbox, explicit model and effort, structured output validated against `schemas/`, raw answer kept, attempt reserved in the journal before the call, tree state recorded before and after. See `protocol.md` for the rules every skill follows.

## Tests

`python3 -B -m unittest discover -s tests -v` (offline, uses a fake `codex`). Real runs use your account limits; see `docs/smoke.md`.
