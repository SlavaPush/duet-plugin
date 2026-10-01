# Duet run protocol

Every Duet skill follows this protocol. The Claude session is the runtime: it orchestrates, talks to the user and writes research, plans, syntheses and reports. Source code is written only by the `implementer` subagent. Codex is reached only through `duet-codex`. Claude roles run at effort `high`: the skills and the subagents set `effort: high` in their frontmatter; the `CLAUDE_CODE_EFFORT_LEVEL` environment variable overrides it.

Adapter path: `${CLAUDE_PLUGIN_ROOT}/bin/duet-codex`. Call it as `duet-codex` from the main session; pass this absolute path to subagents, whose Bash may not have it on PATH.

## Run directory

`duet-codex init --scenario <task|feature|research|review> --cwd <project root>` creates `<repo>/.duet/runs/<scenario>-<timestamp>/` (excluded from git through `.git/info/exclude`) and prints `{"run": "<absolute path>"}`. Use that absolute path as `<run>` everywhere. Create the run before writing any material. Keep everything the run produces inside it:

- `task.md`: the task and acceptance criteria as understood, the base commit (`git rev-parse HEAD` at run start) and the check commands; `context/`: external material saved as files.
- `journal.json`: the timeline. `duet-codex` writes Codex calls; record Claude stages with `duet-codex mark --run <run> --stage <research|plan|worktree|freeze|implement|stage-review|synthesis|report> --status <started|done|needs_human> [--note TEXT]`. A `needs_human` mark may also name the Codex stage that stopped the run (`plan-review`, `code-review`, `critique`, `mr-review`).
- Stage artifacts by name and attempt: `plan.md`, `plan-review-N.json`, `implementation-N.md`, `checks-N.log`, `code-review-material-N.md`, `code-review-N.json`, `research.md`, `critique-N.json`, `review-claude.md`, `mr-review-N.json`, `synthesis.md`, `report.md`. Raw Codex answers are `<stage>-N.raw.md`, assembled prompts `<stage>-N.prompt.md`, CLI logs under `logs/`.

## Commands

```
duet-codex call --run <run> --stage <stage> --prompt <material.md> [--context FILE]... [--resume SESSION_ID] [--cwd DIR] [--background]
duet-codex wait --run <run> --event N [--timeout SECONDS]
duet-codex status --run <run>
duet-codex tree --cwd <dir>
duet-codex mark --run <run> --stage <stage> --status <status> [--note TEXT]
duet-codex limit --run <run> --stage <stage> --set N        # only when the user asks
```

Stages for `call`: `plan-review`, `code-review`, `critique`, `mr-review`. `--prompt` is the material file you write for this call; the role prompt and `<run>/task.md` (when it exists) are added automatically, so materials never repeat the task text. `--cwd` is the directory Codex reads and whose state is hashed: the project root, the feature worktree, or the head worktree of a branch review. `call` prints one JSON line with `n`, `stage`, `attempt`, `status`, `result`, `raw`, `session_id`, `error`, `tree_changed`, `tree_after`; exit codes: 0 completed, 1 failed, 2 invalid, 3 limit reached, 4 running, 5 stale. `result` and `raw` are absolute paths; read results from the printed `result` path, never from a guessed file name. For long calls pass `--background`, then `duet-codex wait --run <run> --event N --timeout 600`, repeating while it exits 4.

## Rules

1. **Explicit models.** Codex model and effort come from `config/roles.json` and the user's `~/.config/duet/roles.json`. Never pass a different model or effort; never edit those files during a run.
2. **Attempt before call.** `duet-codex` reserves every attempt before Codex starts and refuses calls over the stage limit (exit 3). Then stop, show `duet-codex status --run <run>`, and ask the user. Raise a limit only when the user explicitly asks, with `duet-codex limit`.
3. **Raw answers stay.** A call that exits 2 (`invalid`) kept the raw answer in `<stage>-N.raw.md`. If that call's `tree_changed` is false, you may spend one `--resume <session_id>` call asking the same session to return the same content in the required JSON shape; it counts against the limit. If `tree_changed` is true or the repair is still invalid, quote the raw answer in the report and ask the user.
4. **Results are not permission to advance.** Advance automatically only when the stage result is complete and consistent: a `pass` verdict, or `changes_requested` with findings you are about to act on. `needs_human`, exit 1, exhausted limits, stale results and contradictions stop the run: `duet-codex mark --run <run> --stage <stage> --status needs_human --note "<why>"`, write what is open into the report, ask the user. Never retry a failed call automatically.
5. **Reviewer independence.** Reviewers get fresh sessions: a new `Agent` call (never a fork) for the `reviewer` subagent, a new Codex session for the first round. Never paste one reviewer's output into another reviewer's input. Follow-up rounds `--resume` the same Codex session so earlier findings stay open until explicitly resolved.
6. **One reviewed state.** Nobody edits while a review runs. Before dispatching reviewers record `duet-codex tree --cwd <reviewed dir>` in a `freeze` mark; compare after. A Codex call whose tree changed is `stale` (exit 5) and is not approval. Before finishing a stage review, compare `duet-codex tree --cwd <reviewed dir>` with `tree_after` of the accepted `code-review` call; if they differ, the approval does not cover the current files and a new review is needed.
7. **Only the implementer writes code.** The main session never edits source files in these scenarios, not even a one-line fix: send it back to the implementer. Research, plans, syntheses and reports are written by the main session.
8. **Tools are native and optional.** The main session may use any tool, including MCP servers, to gather material; save what reviewers need as files under `context/` and pass them with `--context` or in the subagent prompt. Subagents have fixed tool lists. Codex has a read-only sandbox.

## Review subject

Both reviewers of a change must see the same complete subject. Define it once in the material file:

- **Working tree against a base commit** (task, feature, working-tree review): `git diff <base> --stat` and `git diff <base>` (includes staged and unstaged changes to tracked files), plus `git ls-files --others --exclude-standard` listed as "untracked files: read in full". Reviewers run in the project root (or the feature worktree).
- **Branch** (`--base <ref> --head <ref>`): resolve both once, `BASE=$(git rev-parse <base>)`, `HEAD_SHA=$(git rev-parse <head>)`; create a detached checkout `git worktree add --detach <run>/head $HEAD_SHA`; the subject is `git -C <run>/head diff $BASE...$HEAD_SHA --stat` and `git -C <run>/head diff $BASE...$HEAD_SHA`, saved to `<run>/context/diff.patch`. Reviewers run in `<run>/head` (Codex `--cwd <run>/head`; the reviewer subagent gets that path as its root). After synthesis, `git worktree remove <run>/head`; if removal fails, record the path in the report instead of forcing it.

Order matters: record `freeze` with `duet-codex tree --cwd <reviewed dir>` before preparing the diff and material, compare again right before dispatching (rebuild the material if it changed), and once more after both reviews. Submodule contents are not hashed recursively; only the recorded submodule commit and its dirty flag are. An untracked directory that is itself a git checkout (a linked worktree or an embedded repository) is hashed through its own tree state: its HEAD, its diff and its untracked files.

## Implementation stage

Used by `task` and `feature`.

1. `duet-codex mark --run <run> --stage implement --status started`.
2. Dispatch the `implementer` with the `Agent` tool, `subagent_type: "duet:implementer"`, a fresh agent, and wait for it to finish regardless of how it was launched. Its prompt must contain: the adapter path `${CLAUDE_PLUGIN_ROOT}/bin/duet-codex`; the protocol path `${CLAUDE_PLUGIN_ROOT}/protocol.md`; `<run>`; the path of `task.md` (and `plan.md` in feature); the base commit; the check commands; rule files; "work in the current directory"; the next artifact number N (1 for the first dispatch, otherwise one more than the highest existing `implementation-N.md`); the code-review calls left (from `duet-codex status`); and, for a return, the previous Codex `session_id`, the list of open finding IDs with their text, and the instruction that the first review call must `--resume` that session.
3. When it returns: `duet-codex mark --run <run> --stage implement --status done --note "<files changed>"`, then the stage review below.

### Stage review checklist (main session)

1. `duet-codex mark --run <run> --stage stage-review --status started`.
2. Read the diff of the review subject, the latest `implementation-N.md`, every `code-review-N.json` (paths from `duet-codex status --run <run>`), and the implementer's final message.
3. Re-run the check commands yourself; do not trust the summary alone.
4. For every `blocking` finding across rounds: it appears in a later `resolved_ids`, or the implementer disputed it with a reason you accept. Otherwise it is open.
5. Compare the diff with the acceptance criteria in `task.md` (and `plan.md`).
6. Compare `duet-codex tree --cwd <reviewed dir>` with `tree_after` of the last `completed` code-review call. Different means the approval does not cover the current files.
7. Problems and code-review calls left: dispatch the implementer again (step 2 above, as a return). Problems and no calls left, or a stale approval you cannot renew: `duet-codex mark --run <run> --stage stage-review --status needs_human --note "<what is open>"` and stop. Otherwise `--status done`.

## Research stage

Used by `research` and, optionally, `feature`.

1. `duet-codex mark --run <run> --stage research --status started`. Read code and documents with your own tools (MCP included; save fetched material under `context/`). Write `<run>/research.md`: `## Answer`; `## Claims` numbered `R-1`, `R-2`, ... each with type `fact`, `inference` or `assumption`, the statement, and evidence as file paths with line ranges (required for facts); `## Directions` with risks when the question asks for a way forward; `## Open questions`. Mark `--status done`.
2. `duet-codex call --run <run> --stage critique --prompt <run>/research.md [--context FILE]... --cwd <project root>`. Read the printed result. Check that every `R-n` in `research.md` appears exactly once in `claim_reviews`; a missing or duplicated ID is a contradiction (rule 4). One follow-up is allowed with `--resume <session_id>` when you answer a `disputed` note: write the reply as the material, listing the changed claims.
3. `duet-codex mark --run <run> --stage synthesis --status started`. Write `<run>/synthesis.md`: the answer revised in the light of the critique; a claims table with ID, type, critic result and your final position (agree, or keep with reason); Codex findings with your response; directions and open questions. Do not force consensus. Mark `--status done`. `synthesis.md` is the report of a research stage.

## Rule sets

If the user names rule sets, read `~/.config/duet/settings.json` (`$XDG_CONFIG_HOME/duet/settings.json` when set): `rules` maps a name to file paths relative to that directory. Copy the files into `<run>/context/` and pass them with `--context` and in subagent prompts. Do not apply rule sets the user did not name.

## Reports

`task` and `feature` write `<run>/report.md` with: Task; Result (done, needs_human, failed); Files changed; Checks (commands and results); Review rounds (per call: stage, attempt, verdict, each finding ID with state closed/open/disputed); Open items; How to continue. `research` and `review` use `synthesis.md` as the report. Then tell the user the same in a short message with the report path. The user commits and merges; Duet never does.
