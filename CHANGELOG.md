# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.0 - 2026-10-01

Initial public release.

### Added

- Four skills: `/duet:task`, `/duet:feature`, `/duet:research` and `/duet:review`.
- The `duet-codex` adapter over `codex exec`: a run journal with every call reserved before it starts, per-stage call limits, raw Codex answers kept next to the parsed ones, and a tree-state check that marks a review `stale` when the reviewed files change.
- Two subagents: `implementer`, the only role that edits source files, and `reviewer`, an independent read-only Claude reviewer.
- An offline test suite that uses a fake `codex` executable.
