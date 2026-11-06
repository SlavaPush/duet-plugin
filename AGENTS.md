# Rules for agents working in this repository

## Release after every change that lands in `main`

This is a public plugin that users install by version number: a change that reaches `main` without a version bump is invisible to their installations. So every time changes to the plugin itself (`protocol.md`, `skills/`, `agents/`, `prompts/`, `schemas/`, `config/`, `bin/`, `lib/`, `README*.md`) land in `main`, in the same pass:

1. Raise the version in `.claude-plugin/plugin.json` and in `lib/duet_codex/__init__.py` (`test_manifests` requires them to match).
2. In `CHANGELOG.md`, rename the `Unreleased` section to `<version> - <YYYY-MM-DD>` and make sure it has one entry per change a plugin user can notice, in English.
3. Run `python3 -B -m unittest discover -s tests -v` and `claude plugin validate . --strict`.

Do not wait for a separate release request. Work that is still in a branch or uncommitted stays under `Unreleased`. Files that only serve this repository (`AGENTS.md`, `.claude/`, `.github/`, `tests/`, `docs/`) need no release on their own.
