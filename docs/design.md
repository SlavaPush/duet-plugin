# Duet plugin — design

Status: implemented in 0.1.0

Duet becomes a Claude Code plugin: four scenario skills, two Claude subagents and one
adapter over `codex exec`. The Claude session is the runtime. No scenario continues on its
own after the session ends; a background Codex call that is already running may still finish
and record its result. Everything the run produced stays on disk and is readable by a human.

## 1. Scope

Four scenarios, all driven from a Claude Code session in the target project:

| Skill | Purpose |
| --- | --- |
| `/duet:task` | Small task: implement, Codex review, bounded fixes, main-session stage review |
| `/duet:feature` | Large task: optional research, plan, Codex plan review, implementation, checks, Codex code review, bounded fixes, main-session stage review |
| `/duet:research` | Answer questions about a project: claims with evidence, Codex critique, answer with visible disagreements |
| `/duet:review` | Review a branch, working tree or MR: independent Claude and Codex reviews on the same state, synthesis |

Not in scope: a background daemon, sealed checkpoints, frozen source snapshots, resume of a
run from another session, automatic commit/merge/push, file-deletion protocol, an installer,
the Workflow tool.

## 2. Principles

1. **Explicit models and effort.** Every model call names its model and effort. An unknown
   role, stage or settings key is an error, never a silent default.
2. **Attempt counted before the call.** The adapter appends the attempt to the journal
   before spawning Codex. Limits are per run and per stage; the adapter refuses calls over
   the limit. Claude stages follow the same limits by protocol. Only the user can raise a
   limit for a run, explicitly; the skills never do.
3. **Raw answers are kept.** The adapter saves the raw model output before parsing. An
   invalid answer becomes status `invalid` with the raw file next to it; nothing is lost.
4. **Results are separate from permission to advance.** A stage result is always saved.
   The skill advances automatically only when the result is complete and consistent;
   otherwise it stops and asks the user. No automatic repetition after an error.
5. **Reviewer independence.** A reviewer runs in a fresh session (a new subagent, not a
   fork; a new Codex session) and never receives another reviewer's output before writing
   its own. Follow-up rounds resume the same reviewer session so earlier findings stay
   open until explicitly closed.
6. **One reviewed state.** Edits stop while a review runs. The journal records HEAD and a
   hash of the working tree before and after the review; a mismatch marks a completed review
   `stale`, and stale reviews do not count as approval.
7. **Only the implementer writes code.** Research, plans, synthesis and reports are written
   by the main session. Source edits happen only in the `implementer` subagent (Opus by
   default), so the model that writes code is always explicit.
8. **Tools per stage are native and optional.** The main session has everything, including
   MCP servers (task tracker, GitHub or GitLab, browser). Subagents get a fixed read-only or
   write-capable tool list. Codex gets a read-only sandbox plus files passed to it.
   External materials are fetched by the main session and stored in the run directory.

## 3. Plugin layout

```
.claude-plugin/plugin.json      name "duet", version, description
.claude-plugin/marketplace.json single-plugin marketplace so /plugin marketplace add works
protocol.md                     run protocol shared by all skills; skills read it first
skills/task/SKILL.md
skills/feature/SKILL.md
skills/research/SKILL.md
skills/review/SKILL.md
agents/implementer.md           writes code; model opus; tools Read, Glob, Grep, Edit, Write, Bash
agents/reviewer.md              independent Claude review; model opus; tools Read, Glob, Grep
bin/duet-codex                  adapter over codex exec; Python 3.9+ stdlib; on PATH inside Bash
lib/duet_codex/                 the adapter's Python package
config/roles.json               default model/effort per Codex stage and per-run limits
schemas/review.json             Codex review output
schemas/critique.json           Codex research critique output
prompts/*.md                    role prompts sent to Codex (review, plan review, critique)
tests/                          fake codex executable and adapter tests (unittest)
README.md                       install, scenarios, configuration
README.ru.md                    Russian translation of README.md
CHANGELOG.md                    release notes
LICENSE                         MIT license
docs/design.md                  this document
docs/smoke.md                   manual checklist with the real CLIs
.github/workflows/tests.yml     offline test suite on Linux and macOS
```

Skills, prompts, the protocol and the technical documentation are in English; the README is
available in English and Russian. Skills reference the adapter by name (`duet-codex`) because the
plugin's `bin/` is on PATH, and reference shared files via `${CLAUDE_PLUGIN_ROOT}`.

## 4. Roles

| Stage | Executor | Default model / effort | Tools |
| --- | --- | --- | --- |
| research, plan, synthesis, reports, stage review | main session | session model, effort high via skill frontmatter | all, including MCP |
| implement, checks, Codex code-review loop | `implementer` subagent | opus / high | Read, Glob, Grep, Edit, Write, Bash |
| independent Claude review | `reviewer` subagent; returns Markdown in its final message, the main session saves `review-claude.md` | opus / high | Read, Glob, Grep |
| plan-review, code-review, critique, mr-review | Codex via `duet-codex` | gpt-6-astra / xhigh | read-only sandbox, passed files |
| follow-up rounds (`--resume`) | Codex | gpt-6-astra / high | same |

Effort of Claude roles: the four skills and both subagents declare `effort: high` in their
frontmatter; the platform lets `CLAUDE_CODE_EFFORT_LEVEL` override frontmatter. Subagent models are fixed in the agent files and can be overridden per call.
Plugin subagents ignore `mcpServers` and `permissionMode`, so MCP data reaches subagents
only as files.

## 5. Run protocol

### Run directory

`<project>/.duet/runs/<scenario>-<YYYYMMDD-HHMMSS>/`, created by the skill. The adapter
adds `.duet/` to `<project>/.git/info/exclude` on first use so the project's `.gitignore`
stays untouched. For `feature`, the run directory lives in the original checkout; when the
user asks for a worktree, the code lives in that worktree and its path is recorded as a
`worktree` stage event.

Artifacts are plain files named by stage and attempt:

```
journal.json                  machine-readable timeline (adapter and skills append to it)
task.md                       task text and acceptance criteria as given by the user
context/*.md                  external materials saved by the main session (MR text, tracker card, logs)
research.md                   research scenario or optional feature step
critique-1.json / .raw.md     Codex critique
plan.md                       feature plan
plan-review-1.json / .raw.md  Codex plan review, attempt N
implementation-1.md           implementer's summary, attempt N
checks-1.log                  output of project checks, attempt N
code-review-1.json / .raw.md  Codex code review, attempt N
review-claude.md              reviewer subagent output (review scenario)
mr-review-1.json / .raw.md    Codex review (review scenario)
synthesis.md                  joint review or research answer
report.md                     final human-readable report
```

### Journal

`journal.json` is the single timeline. The adapter writes Codex calls; skills record Claude
stages with `duet-codex mark`. Journal writes are serialized with a file lock; the limit
check and the attempt reservation are one transaction. Every call event also records
`tree_changed`.

```json
{
  "version": 1,
  "scenario": "feature",
  "project": "/abs/project",
  "created_at": "2026-09-16T21:00:00Z",
  "limits": {"plan-review": 3, "code-review": 4, "critique": 2, "mr-review": 2},
  "events": [
    {"n": 1, "kind": "stage", "stage": "plan", "status": "done", "at": "..."},
    {"n": 2, "kind": "call", "stage": "plan-review", "attempt": 1, "provider": "codex",
     "model": "gpt-6-astra", "effort": "xhigh", "session_id": "…", "resume_of": null,
     "status": "completed", "result": "plan-review-1.json", "raw": "plan-review-1.raw.md",
     "tree_before": {"head": "sha", "hash": "sha256"}, "tree_after": {"head": "sha", "hash": "sha256"},
     "tree_changed": false, "pid": 12345, "returncode": 0, "started_at": "...", "finished_at": "..."}
  ]
}
```

Call statuses: `running`, `completed`, `invalid` (answer saved, schema not met),
`failed` (CLI error, timeout, cancelled), `stale` (a schema-valid answer, but the tree
changed during the call).

### Limits

Defaults per run, enforced by the adapter for Codex stages:

| Stage | Calls | Meaning |
| --- | --- | --- |
| plan-review | 3 | initial review plus two plan fixes |
| code-review | 4 | initial review plus three fix rounds, shared by the implementer loop and the main session's returns |
| critique | 2 | initial critique plus one follow-up |
| mr-review | 2 | initial review plus one clarification |

Claude-side conventions: the implementer stops after a `pass` verdict or two fix rounds,
so the main session keeps budget for its own returns. Every return to the implementer is
a fix round and consumes at least one code-review call, because edits make the earlier
verdict stale; within the remaining limit the implementer may run further rounds. An
exhausted limit is not an error: the skill shows what remains open and asks the user, who
may raise the limit for this run with `duet-codex limit --run <dir> --stage code-review
--set N`. The skill never raises a limit on its own.

### State binding

Before and after every Codex call the adapter records `git rev-parse HEAD` and a sha256
over `git diff HEAD --binary` (external diff, textconv and submodule ignoring disabled)
plus the type, executable bit and contents of untracked, non-ignored files. Submodule
contents are not hashed recursively: only the recorded submodule commit and its dirty
flag enter the hash. An untracked directory that is itself a git checkout (a linked
worktree or an embedded repository) is hashed through its own tree state: its HEAD, its
diff and its untracked files. Skills
call `duet-codex tree` for the same value before dispatching the reviewer subagent and
after it returns. A
call whose answer is schema-valid but whose `tree_after` differs from `tree_before` is
`stale`; the skill reports it and asks whether to re-run. A `failed` or `invalid` call
keeps its status and records `tree_changed: true`.

### Invalid and failed results

`invalid`: if the call's `tree_changed` is false, the skill may spend one `--resume` call
asking the same Codex session to return the same content in the schema; that call counts
against the stage limit. If `tree_changed` is true or the repair is still invalid, the raw
answer is quoted in the report and the user decides.

`failed`: the skill shows the adapter's diagnostics (exit code, stderr excerpt, log paths)
and stops. Nothing is retried automatically.

Interruption of the session: the run directory and journal remain. A new session can read
them; the skills do not resume a run automatically.

## 6. Adapter `duet-codex`

One Codex call per invocation; no orchestration, no agent loop.

```
duet-codex init --scenario NAME --cwd DIR
duet-codex call --run DIR --stage STAGE --prompt FILE [--context FILE ...]
                [--schema NAME] [--resume SESSION_ID] [--background] [--cwd DIR]
duet-codex wait --run DIR --event N --timeout SECONDS
duet-codex status --run DIR
duet-codex mark --run DIR --stage STAGE --status started|done|needs_human [--note TEXT]
duet-codex limit --run DIR --stage STAGE --set N        only on the user's explicit request
duet-codex tree [--cwd DIR]
```

`call` resolves model and effort from `config/roles.json` merged with
`~/.config/duet/roles.json` (unknown keys are errors) and the stage limit from the run's
`journal.json`, where `init` copied the limits; it then appends the attempt to the journal,
records the tree, and runs:

```
codex exec -C CWD -m MODEL -c model_reasoning_effort='"EFFORT"' --sandbox read-only \
  --json --output-schema SCHEMA -o RESULT - < PROMPT > EVENTS 2> STDERR
```

The prompt file is the role prompt from `prompts/`, `<run>/task.md` when it exists, the
stage material and the listed context files, concatenated with headers; `result` and
`raw` in the printed summary are absolute paths. `--resume` runs `codex exec resume ID`
from the target directory (resume has no `-C`) with `-c sandbox_mode='"read-only"'`,
as the CLI requires. On completion the adapter checks the `turn.completed` event and the
session ID from `thread.started`, copies the raw answer to `<stage>-<n>.raw.md`, validates
JSON against the schema, records the tree again and sets the status. It prints one JSON
line: event number, status, result path, session ID.

`--background` detaches the Codex process (new session, stdio to files, pid recorded) and
returns immediately; `wait` polls the event until it leaves `running` or the timeout
passes, and can be called again. This keeps long reviews independent of the Bash tool's
timeout.

Exit codes: 0 completed, 1 failure, 2 invalid, 3 limit reached, 4 still running, 5 stale.
`wait` marks a dead worker's call `failed` only if it is still `running` under the lock.

Codex CLI facts the adapter relies on (checked against codex-cli 0.154.0): prompt through
stdin with `-`, `--json` event stream, `-o` final answer, `--output-schema`, resume by
explicit ID only, never `--last`.

Carried over from an earlier standalone prototype: `process.py` (bounded subprocess with
file stdio and process-group stop), `atomic_json`, the finding schema. Everything else is
new and small.

## 7. Scenarios

Every skill starts by reading `protocol.md`, creating the run directory, saving `task.md`
and any external materials into `context/`, and applying the user's rule sets from
`~/.config/duet/settings.json` as context files when the user names them.

### `/duet:task`

1. Main session clarifies the task only if it cannot be understood; writes `task.md`.
2. Determines project checks: from `.duet.json` `{"checks": [...]}` if present, else
   inferred from the project and confirmed with the user.
3. Dispatches `implementer` (in place, no worktree) with the task, checks and rules.
   The implementer: implements; runs checks; calls `duet-codex call --stage code-review`;
   fixes blocking findings; re-runs checks; calls `--resume` re-review; at most two fix
   rounds; writes `implementation-N.md` with what changed, which findings are closed,
   open or disputed, and check results.
4. Main session stage review: reads the diff, the plan of the task, Codex findings and the
   journal; re-runs checks; verifies every blocking finding is closed or explicitly
   disputed with a reason. Problems go back to the implementer while the code-review
   budget lasts; a return resumes the previous Codex session and consumes at least one call
   within the remaining budget; when the budget is exhausted the skill asks the user.
5. Writes `report.md`; shows the user the diff summary, open items and the report path.
   The user commits.

### `/duet:feature`

1. Optional research step identical to `/duet:research`, when the task needs it.
2. Main session enters a worktree (native isolation) for the task branch only when the
   user asks for one in the request or `.duet.json` sets `"worktree": true`; otherwise
   the work happens in place, in the project root, as in `/duet:task`.
3. Plan in `plan.md`: decisions, affected areas, risks, how acceptance criteria are checked.
   No line-by-line pseudocode.
4. `duet-codex call --stage plan-review`; the main session fixes the plan and resumes the
   review, at most two fixes. `needs_human` when the reviewer asks for a human decision.
5. Implementation as in `/duet:task` steps 3–4, in the project root or in the worktree
   when one was entered, with the plan as input. The code-review limit is shared across the implementer loop and the main
   session's returns.
6. `report.md` with plan, review history, checks and open items. The user commits, or
   merges when a worktree was used.

### `/duet:research`

1. Main session gathers evidence: code, documents, external materials via MCP saved to
   `context/`.
2. Writes `research.md`: answer body, numbered claims typed fact / inference / assumption
   with file references, candidate directions with risks, open questions.
3. `duet-codex call --stage critique`: Codex classifies every claim confirmed / disputed /
   unverified with a note and adds its own findings.
4. Main session writes `synthesis.md`: the answer with every claim's fate visible,
   disagreements kept, no forced consensus. One follow-up critique round is allowed.
5. Shows the answer and the path of `synthesis.md`, which is the report of this scenario.

### `/duet:review`

1. Inputs: `--base` and either `--head` (branch review) or the working tree; optional MR
   URL, whose description and discussion the main session fetches with the session's
   tools for that host into `context/`. The source of changes is always local git.
2. Records the reviewed state with `duet-codex tree` and asks the user not to edit until
   the reviews finish.
3. In parallel and independently: `reviewer` subagent (fresh, read-only, does not see the
   Codex output) returns findings `C-n` as Markdown that the main session saves as
   `review-claude.md`; `duet-codex call --stage mr-review --background` writes
   `mr-review-1.json` with findings `X-n`. Both receive the same task text and context
   files and read the same directory: for a branch review a detached checkout of head
   under `<run>/head`, removed after synthesis; for the working tree, the project root.
4. Main session synthesis in `synthesis.md`: every original finding gets a disposition
   (confirmed / disputed / merged) with a reason; a finding may be listed as a source of
   several final findings; fresh synthesis findings are marked as not independently
   confirmed; coverage is reported per reviewer honestly.
5. Verdict: `findings`, `no_findings`, or `inconclusive`. Incomplete coverage or open
   disagreement downgrades only `no_findings` to `inconclusive`; with findings present the
   verdict stays `findings`.
6. `synthesis.md` is the report; the summary for the user: blocking items first,
   disagreements, coverage.

## 8. Schemas

`review.json` (plan-review, code-review, mr-review): `verdict` pass / changes_requested /
needs_human; `summary`; `findings[]` with `id`, `severity` blocking / advisory, `file`,
`start_line`, `end_line`, `description`, `suggestion`; `resolved_ids[]` for resumed rounds;
`questions[]`. Every object has `additionalProperties: false` and all fields required, as
Codex's structured output expects.

`critique.json`: `summary`; `claim_reviews[]` with `id`, `result` confirmed / disputed /
unverified, `note`; `findings[]` as above.

The reviewer subagent writes Markdown with the same finding fields and `C-n` IDs; the
main session reads it as text.

## 9. Configuration

`config/roles.json` (plugin defaults):

```json
{
  "codex": {"model": "gpt-6-astra"},
  "stages": {
    "plan-review": {"effort": "xhigh", "resume_effort": "high", "limit": 3},
    "code-review": {"effort": "xhigh", "resume_effort": "high", "limit": 4},
    "critique":    {"effort": "xhigh", "resume_effort": "high", "limit": 2},
    "mr-review":   {"effort": "xhigh", "resume_effort": "high", "limit": 2}
  },
  "timeouts": {"call_seconds": 1800},
  "limits": {"max_log_bytes": 16777216}
}
```

`~/.config/duet/roles.json` overrides any subset; unknown keys and invalid values are
errors; limits are positive integers without an upper cap. Rule sets keep
their current home in `~/.config/duet/settings.json` and are passed as context files.
`.duet.json` in a project is optional and has two fields: `checks`, and `worktree`
(boolean, default `false`) which makes `/duet:feature` use a worktree in that project.

## 10. Installation

From the GitHub repository, which is also a single-plugin marketplace:

```
/plugin marketplace add SlavaPush/duet-plugin
/plugin install duet@duet-plugin
```

For local development: `claude --plugin-dir /path/to/duet-plugin`. Requirements: Claude Code,
Codex CLI signed in, Python 3.9+, Git. No installer, no symlinks, no per-project setup
beyond the optional `.duet.json`.

## 11. Testing

Adapter tests with a fake `codex` executable on PATH (unittest, stdlib): attempt recorded
before spawn; limit refusal with exit 3; raw answer kept and status `invalid` on bad JSON;
resume passes the session ID and sandbox through `-c`; background call plus `wait`; tree
hash changes on edit and marks the call `stale`; unknown roles.json key is an error.

Skills are checked by hand on a sample project with the real CLIs: one run per scenario,
inspecting the run directory and the report. Real runs use account limits and are not part
of the automated suite.

## 12. Size

Target: 400–700 lines of Markdown (protocol, four skills, two agents, prompts), 300–400
lines of Python (adapter), about 250 lines of tests, a short README.

## 13. Decisions recorded during review

- **Worktree is opt-in in `feature`.** By default `feature` works in place like `task`:
  a worktree costs a separate checkout and a merge, which most features do not need. The
  user asks for one per request, or per project through `.duet.json`.
- **Worktree ownership in `feature`.** When used, the main session enters the worktree
  with the native EnterWorktree tool. Its working directory, and therefore the working directory of
  every subagent it spawns, becomes the worktree. The implementer does not get its own
  `isolation: worktree`, because the main session must review the same files afterwards.
  This follows from the platform's tool semantics; the first real `/duet:feature` run
  confirms it.
- **No built-in Claude second opinion in `feature`.** After the Codex code review the code
  is already checked twice: by Codex and by the main session's stage review. A fresh
  `reviewer` pass on every feature would add time and cost by default. When a second
  independent opinion is wanted, run `/duet:review --base main --head <branch>` on the
  finished branch; that is the same dual review without a new flag.
