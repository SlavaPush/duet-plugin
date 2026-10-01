# Duet

A Claude Code plugin for developers who want OpenAI Codex to check Claude's work: small tasks, planned features, research and code reviews, with every Codex call journaled and limited.

**English** | [Русский](README.ru.md)

Duet is an independent project, not affiliated with Anthropic or OpenAI.

## What you get

| Command | Use it for | Changes files? |
| --- | --- | --- |
| `/duet:task` | A small change. The `implementer` subagent writes it, Codex reviews it, the main session reviews the stage. | Yes, in place. Never commits. |
| `/duet:feature` | A larger change. Optional research, a plan reviewed by Codex, implementation, Codex code review, a final stage review by the main session. | Yes, in place by default; in a git worktree on its own branch when you ask for one. Never commits or merges. |
| `/duet:research` | A question about the codebase. Claims with evidence, a Codex critique, an answer that keeps disagreements visible. | No. |
| `/duet:review` | A second opinion on a branch or the working tree. A Claude reviewer and Codex review the same state independently, then the main session writes a synthesis. | No. A branch review uses a temporary detached checkout inside the run directory. |

Every command also writes its run files under `.duet/runs/` in the project; see "How a run works" below.

## Requirements

- Claude Code (tested with 2.1.284).
- Codex CLI, signed in; check with `codex login status` (tested with 0.159.2; the adapter relies on `codex exec` features present since 0.154).
- Your Codex account must have access to the default model `gpt-6-astra`, or to another model set in the configuration.
- Python 3.9 or later (standard library only; nothing to install) and Git.
- macOS or Linux. Native Windows is not supported: the adapter uses `fcntl` and POSIX process groups. WSL is untested.
- The project you run Duet in must be a git repository with at least one commit.

Every run consumes both Claude and Codex usage, billed according to how each CLI is signed in: subscription limits or API billing.

## Install

In a Claude Code session:

```
/plugin marketplace add SlavaPush/duet-plugin
/plugin install duet@duet-plugin
```

Or from a shell:

```
claude plugin marketplace add SlavaPush/duet-plugin
claude plugin install duet@duet-plugin
```

Then restart Claude Code or start a new session. A first run that changes nothing in the project, started inside a git repository with at least one commit:

```
/duet:research How are the tests in this project organised?
```

To load a local checkout for one session: `claude --plugin-dir /path/to/duet-plugin`.

## Usage

### `/duet:task`

```
/duet:task Add a --version flag to the CLI with a test.
```

The main session writes the task, the acceptance criteria and the check commands to `task.md`; the checks come from `.duet.json`, or the session infers them and asks you to confirm. The `implementer` subagent changes the code in place, runs the checks, gets a Codex code review and fixes blocking findings, at most two fix rounds per dispatch. The main session then re-runs the checks, verifies every blocking finding and sends problems back to the implementer while code-review calls remain. At the end you get the change in your working tree and `report.md`, and you commit.

### `/duet:feature`

```
/duet:feature Add CSV export to the reports page, with tests.
```

If the task needs it, a research stage runs first. By default the work happens in place, in your working tree, like `/duet:task`. If you ask for a worktree in the request ("in a worktree", "on a separate branch") or set `"worktree": true` in `.duet.json`, the main session enters a git worktree named after the task instead; the run directory stays in the original checkout either way. The main session writes `plan.md`, Codex reviews the plan, and the plan is revised at most twice. Implementation, checks, code review and the stage review follow as in `/duet:task`, against the plan. At the end you get `report.md` and the change in your working tree, and you commit; with a worktree you also get its path and branch, and you merge.

### `/duet:research`

```
/duet:research Why does the importer parse dates twice?
/duet:research How could we move billing out of the core module, and what are the risks?
```

The main session reads code and documents and writes `research.md`: an answer and numbered claims `R-1`, `R-2`, ..., each typed as fact, inference or assumption; facts carry file and line references. Codex marks every claim confirmed, disputed or unverified and adds its own findings. `synthesis.md` holds the revised answer, a claims table with the final position on each claim, and the disagreements that remain. Project files are not changed.

### `/duet:review`

```
/duet:review --base main --head feature/login
/duet:review --base main
/duet:review --base main --head feature/login https://github.com/acme/app/pull/42
```

With `--head`, Duet reviews `main...feature/login` in a temporary detached checkout and removes the checkout afterwards. Without `--head`, it reviews the working tree, untracked files included, against the base; without `--base`, the base is the merge-base with the repository's main branch. A merge/pull request URL adds its title, description and discussion as context, fetched with the session's tools for that host; the changes always come from local git, so fetch the branch first. A fresh `reviewer` subagent and Codex review the same state without seeing each other's output, and `synthesis.md` lists the final findings with their sources, the disagreements, coverage and a verdict (`findings`, `no_findings` or `inconclusive`). Do not edit files while a review runs: a changed tree makes the review `stale`.

## How a run works

1. **Explicit model and effort.** Every Codex call uses the model and effort from the configuration. Skills never pass others and never edit the configuration during a run.
2. **Reserved before the call.** `duet-codex` records every Codex call in the run journal before Codex starts and counts it against the limit of its stage.
3. **Raw answers are kept.** The raw Codex answer is saved even when it does not match the expected JSON schema.
4. **Stop and ask.** The run advances on its own only when a result is complete and consistent. A failed, stale or limit-reached call stops the run and asks you; nothing is retried automatically. If an answer does not match the schema and the tree did not change during that call, the same Codex session may get one repair request, which counts against the limit. Otherwise, or if the repaired answer is still invalid, the run stops and asks you.
5. **Independent reviewers.** Each reviewer starts in a fresh session: a new `reviewer` subagent, a new Codex session. Neither sees the other's output. Follow-up rounds resume the same Codex session, so earlier findings stay open until they are resolved.
6. **One reviewed state.** The adapter hashes the reviewed directory (HEAD, the diff against HEAD, untracked files) before and after every Codex call and records whether it changed. A completed call during which the tree changed is marked `stale` and does not count as approval.
7. **Only the implementer edits source files.** The main session writes research, plans, syntheses and reports, never code.
8. **No commits.** Duet never commits, pushes or merges.

Each run lives in `<repo>/.duet/runs/<scenario>-<timestamp>/`, excluded from git:

- `task.md`: the task as understood; `context/`: external material such as merge/pull request text and rule files.
- `journal.json`: the timeline of Claude stages and Codex calls.
- `report.md` (`task`, `feature`) or `synthesis.md` (`research`, `review`): the result.
- `<stage>-N.json`: parsed Codex answers; `<stage>-N.raw.md`: raw answers; `<stage>-N.prompt.md`: assembled prompts.
- `logs/`: Codex CLI logs.

`duet-codex status --run <dir>` prints the timeline as JSON.

## Cost and limits

Every run consumes Claude and Codex usage; how it is billed depends on how each CLI is signed in (subscription limits or API billing). On the Claude side: the main session (your session model) and the `implementer` and `reviewer` subagents (Opus), all at effort `high`. On the Codex side, every run has a call limit per stage:

| Stage | Used by | Calls per run, default |
| --- | --- | --- |
| Plan review, `plan-review` | `/duet:feature` | 3 |
| Code review, `code-review` | `/duet:task`, `/duet:feature` | 4 |
| Critique, `critique` | `/duet:research`, `/duet:feature` with research | 2 |
| Merge/pull request review, `mr-review` | `/duet:review` | 2 |

By default, a call that starts a new Codex session runs at effort `xhigh`, a resumed round runs at `high`, and every call times out after 1800 s.

`/duet:feature` is the most expensive scenario: up to 3 plan-review and 4 code-review calls, plus up to 2 critique calls when it includes research. An exhausted limit stops the run and asks you. To allow more calls in that run: `duet-codex limit --run <dir> --stage <stage> --set N`. Limits are copied into the journal when the run is created, so a changed `roles.json` limit applies to later runs.

## Data and permissions

- **Sent to OpenAI** through the Codex CLI: the assembled prompt (the role prompt, the run's `task.md`, the stage material such as a plan, a diff, check output or research, and any context files such as named rule sets or merge/pull request text), plus whatever Codex reads in the reviewed directory. Codex runs in a read-only sandbox (`codex exec --sandbox read-only`) and cannot edit files.
- **Sent to Anthropic**: the normal Claude Code session.
- **Stored on disk** in plain text under `.duet/runs/`: assembled prompts, raw and parsed answers, and CLI logs, which include another copy of the prompt. On first use the adapter adds `.duet/` to `.git/info/exclude`; your `.gitignore` is not touched. Run directories are never deleted automatically; remove them yourself. Do not put secrets in task text.
- **Permissions**: like any Claude Code plugin, Duet runs with your user's permissions. The `implementer` subagent has the `Bash`, `Edit` and `Write` tools.

## Configuration

Defaults, from `config/roles.json`:

```json
{
  "codex": {"model": "gpt-6-astra"},
  "stages": {
    "plan-review": {"effort": "xhigh", "resume_effort": "high", "limit": 3},
    "code-review": {"effort": "xhigh", "resume_effort": "high", "limit": 4},
    "critique": {"effort": "xhigh", "resume_effort": "high", "limit": 2},
    "mr-review": {"effort": "xhigh", "resume_effort": "high", "limit": 2}
  },
  "timeouts": {"call_seconds": 1800},
  "limits": {"max_log_bytes": 16777216}
}
```

To override any subset, create `~/.config/duet/roles.json` (`$XDG_CONFIG_HOME/duet/roles.json` when `XDG_CONFIG_HOME` is set):

```json
{"codex": {"model": "<your-model>"}, "stages": {"code-review": {"effort": "high", "limit": 3}}}
```

- `codex.model`: the model of every Codex call.
- `stages.<stage>.effort`: effort of a call that starts a new Codex session; `resume_effort`: effort of a resumed round; `limit`: calls per run. Allowed efforts: `minimal`, `low`, `medium`, `high`, `xhigh`.
- `timeouts.call_seconds`: the timeout of one Codex call.
- `limits.max_log_bytes`: the maximum size of a call's stdout or stderr log; a larger log fails the call.

Unknown keys and invalid values are errors.

`~/.config/duet/settings.json` may define `rules`: named lists of Markdown files, with paths relative to that directory, for example `{"rules": {"python": ["rules/python.md", "rules/tests.md"]}}`. A rule set applies only when you name it in your request.

An optional `.duet.json` in a project lists the check commands for `/duet:task` and `/duet:feature`, and can make `/duet:feature` use a worktree by default in that project: `{"checks": ["npm test", "npm run lint"], "worktree": true}`.

Claude roles run at effort `high`, set in the skill and agent frontmatter; the `CLAUDE_CODE_EFFORT_LEVEL` environment variable overrides it.

## Troubleshooting

`duet-codex` is `bin/duet-codex` in the plugin directory; in a Claude Code session with Duet enabled, the session runs it by name. `duet-codex call` and `duet-codex wait` normally print one JSON line with an `error` field. Errors before a call starts, such as an exhausted limit or an invalid `roles.json`, go to stderr with the prefix `duet-codex:`.

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 0 | `completed`: the answer matches the schema and is saved. This is not approval. | Read the result at the printed `result` path and check its verdict: `pass`, `changes_requested` or `needs_human`. A `critique` result has claim reviews instead of a verdict. |
| 1 | `failed`: a Codex CLI error, a timeout, or an adapter error. | Read `error` and the logs in `<run>/logs/`, fix the cause, then ask for the call again. |
| 2 | `invalid`: the answer does not match the schema. | Read `<stage>-N.raw.md`. |
| 3 | The stage limit is reached. | Check `duet-codex status --run <dir>`; raise the limit with `duet-codex limit` if you want more calls. |
| 4 | `running`: a `--background` call has not finished yet. | Run `duet-codex wait --run <dir> --event N` again. |
| 5 | `stale`: the reviewed files changed during the call. | Stop editing and run the review again. |

- Codex is not signed in: run `codex login`; `codex login status` shows the state.
- The model is not available to your account: set `codex.model` in `~/.config/duet/roles.json`.
- `Timeout after 1800s`: raise `timeouts.call_seconds`.
- `Process log size limit exceeded`: raise `limits.max_log_bytes`.
- `Cannot start codex`: install the Codex CLI and make sure `codex` is on `PATH`.
- An interrupted call (Ctrl+C or `SIGTERM`) still gets a final status in the journal: normally `failed`, or `stale` when the interrupt hits the final tree check after a valid answer. A call without `--background` then ends without a JSON line. Read the recorded status with `duet-codex status --run <dir>`, or with `duet-codex wait` for a background call.
- Logs of call N of a stage: `<run>/logs/<stage>-N.stdin.txt` (the prompt as sent), `<stage>-N.stdout.log` (Codex JSON events), `<stage>-N.stderr.log`, and `<stage>-N.worker.log` for a background call.
- `duet-codex status --run <dir>` prints every stage and call with its status, result paths and error.

## Update and uninstall

- Update: `claude plugin marketplace update duet-plugin`, then `claude plugin update duet@duet-plugin`; restart Claude Code to apply the update.
- Uninstall: `claude plugin uninstall duet@duet-plugin`, then `claude plugin marketplace remove duet-plugin`.

What stays behind: `.duet/` directories in your projects and the `.duet/` line in their `.git/info/exclude`, `~/.config/duet/` if you created it, and the worktrees and branches created by `/duet:feature` when you asked for a worktree (`git worktree list` shows them).

## Development

Run the tests with `python3 -B -m unittest discover -s tests -v`; they run offline and use a fake `codex` executable. Validate the manifests with `claude plugin validate . --strict`. The manual checklist with the real CLIs is in [docs/smoke.md](docs/smoke.md), architecture and decisions are in [docs/design.md](docs/design.md), and the rules every skill follows are in [protocol.md](protocol.md).

```
.claude-plugin/        plugin.json, marketplace.json
.github/workflows/     tests.yml
agents/                implementer.md, reviewer.md
bin/                   duet-codex
config/                roles.json
docs/                  design.md, smoke.md
lib/duet_codex/        the adapter's Python package
prompts/               role prompts sent to Codex, one per stage
schemas/               review.json, critique.json
skills/                task/, feature/, research/, review/
tests/                 unittest suite and fake_codex.py
```

The repository root holds `protocol.md`, `README.md`, `README.ru.md`, `CHANGELOG.md` and `LICENSE`.

## License

MIT. See [LICENSE](LICENSE).
