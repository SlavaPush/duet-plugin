# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added

- An optional `auto` list in `~/.config/duet/settings.json` selects a rule set when the request names none: the first entry whose `when` condition holds for the request applies.

### Changed

- The `implementer` subagent runs at effort `medium`; the `reviewer` subagent runs on Fable.

- `/duet:feature` now works in place by default, like `/duet:task`. A git worktree is used only when the request asks for one or `.duet.json` sets `"worktree": true`.

## 0.1.0 - 2026-10-01

Initial public release.

### Added

- Four skills: `/duet:task`, `/duet:feature`, `/duet:research` and `/duet:review`.
- The `duet-codex` adapter over `codex exec`: a run journal with every call reserved before it starts, per-stage call limits, raw Codex answers kept next to the parsed ones, and a tree-state check that marks a review `stale` when the reviewed files change.
- Two subagents: `implementer`, the only role that edits source files, and `reviewer`, an independent read-only Claude reviewer.
- An offline test suite that uses a fake `codex` executable.
