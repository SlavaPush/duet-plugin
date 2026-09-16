#!/usr/bin/env python3
"""Fake Codex CLI for offline tests. DUET_FAKE_MODE: ok | invalid | fail | slow (waits for DUET_FAKE_RELEASE)."""
import json
import os
import sys
import time

args = sys.argv[1:]
prompt = sys.stdin.read() if args and args[-1] == "-" else ""
log = os.environ.get("DUET_FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"argv": args, "prompt": prompt, "cwd": os.getcwd()}) + "\n")
if "--version" in args:
    print("codex-cli fake 0.154.0")
    sys.exit(0)
mode = os.environ.get("DUET_FAKE_MODE", "ok")
if mode == "fail":
    sys.stderr.write("fake codex failure\n")
    sys.exit(1)
if mode == "slow":
    release = os.environ.get("DUET_FAKE_RELEASE", "")
    deadline = time.monotonic() + 30
    while not os.path.exists(release) and time.monotonic() < deadline:
        time.sleep(0.05)
out = args[args.index("-o") + 1]
with open(args[args.index("--output-schema") + 1], encoding="utf-8") as stream:
    schema = json.load(stream)
finding = {"id": "X-1", "severity": "blocking", "file": "a.py", "start_line": 1, "end_line": 1,
           "description": "fake finding", "suggestion": "fix it"}
if mode == "invalid":
    body = '{"verdict": "maybe"}'
elif "claim_reviews" in schema["properties"]:
    body = json.dumps({"summary": "fake critique",
                       "claim_reviews": [{"id": "R-1", "result": "confirmed", "note": "checked"}],
                       "findings": []})
else:
    verdict = "pass" if "resume" in args else "changes_requested"
    body = json.dumps({"verdict": verdict, "summary": "fake review",
                       "findings": [] if verdict == "pass" else [finding],
                       "resolved_ids": ["X-1"] if verdict == "pass" else [], "questions": []})
with open(out, "w", encoding="utf-8") as stream:
    stream.write(body)
session = args[args.index("resume") + 1] if "resume" in args else "fake-session-1"
print(json.dumps({"type": "thread.started", "thread_id": session}))
print(json.dumps({"type": "turn.completed", "usage": {}}))
