---
name: research
description: >-
  Research a project with Codex as critic. The main session gathers evidence and
  writes typed claims, Codex classifies every claim and adds findings, and the
  answer keeps disagreements visible. Use for questions like why something works
  this way, how to change the architecture, or any codebase question that needs a
  verified answer.
effort: high
---

Read `${CLAUDE_PLUGIN_ROOT}/protocol.md` first and follow it throughout.

1. **Run.** In the project root: `duet-codex init --scenario research --cwd .`; write `<run>/task.md` with the question, the decision it supports and any constraints. Save external material under `<run>/context/`. Resolve rule sets if named.
2. **Research, critique, synthesis.** Follow the protocol's Research stage.
3. **Report.** Show the user the answer, the disagreements and the path of `<run>/synthesis.md`.
