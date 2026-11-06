#!/usr/bin/env python3
"""Fake Codex CLI for offline tests.

DUET_FAKE_MODE: ok | invalid (wrong shape) | garbage (not JSON) | fail (exit 1) | no-answer | no-session |
turn-failed | slow (waits for DUET_FAKE_RELEASE) | wrong-claims (critique repeats the first claim and adds R-9).

A critique answer reviews the claim IDs found in the prompt: `### R-n` headings and the lines of a
`## Changed claims` section; R-1 when there are none.
"""
import json
import os
import re
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
elif mode == "garbage":
    body = "not json {"
elif "claim_reviews" in schema["properties"]:
    ids = re.findall(r"^### (R-\d+)\b", prompt, re.M)
    changed = re.search(r"^## Changed claims[ \t]*$", prompt, re.M)
    if changed:
        section = re.split(r"^#", prompt[changed.end():], maxsplit=1, flags=re.M)[0]
        ids += re.findall(r"^[ \t]*(?:- )?`?(R-\d+)\b", section, re.M)
    ids = list(dict.fromkeys(ids)) or ["R-1"]
    if mode == "wrong-claims":
        ids = [ids[0], ids[0], "R-9"]
    body = json.dumps({"summary": "fake critique",
                       "claim_reviews": [{"id": i, "result": "confirmed", "note": "checked"} for i in ids],
                       "findings": []})
else:
    verdict = "pass" if "resume" in args else "changes_requested"
    body = json.dumps({"verdict": verdict, "summary": "fake review",
                       "findings": [] if verdict == "pass" else [finding],
                       "resolved_ids": ["X-1"] if verdict == "pass" else [], "questions": []})
if mode != "no-answer":
    with open(out, "w", encoding="utf-8") as stream:
        stream.write(body)
session = args[args.index("resume") + 1] if "resume" in args else "fake-session-1"
if mode != "no-session":
    print(json.dumps({"type": "thread.started", "thread_id": session}))
if mode == "turn-failed":
    print(json.dumps({"type": "turn.failed", "error": "fake turn failure"}))
else:
    print(json.dumps({"type": "turn.completed", "usage": {}}))
