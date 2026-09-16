"""duet-codex: one journaled Codex call per invocation plus run bookkeeping."""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from . import VERSION
from . import journal as J
from .codex import perform_call, start_call
from .config import load_roles
from .errors import DuetError, LimitReached

EXIT = {"completed": 0, "failed": 1, "invalid": 2, "running": 4, "stale": 5}
SCENARIOS = ("task", "feature", "research", "review")
CLAUDE_STAGES = ("research", "plan", "worktree", "freeze", "implement", "stage-review", "synthesis", "report")
CODEX_STAGES = ("plan-review", "code-review", "critique", "mr-review")
BIN = Path(__file__).resolve().parents[2] / "bin" / "duet-codex"
PYTHON = sys.executable
DETACHED = []  # background workers are never waited for; keeping the handles avoids finalizer noise
SUMMARY_KEYS = ("n", "stage", "attempt", "status", "result", "raw", "session_id", "error", "tree_changed", "tree_after")


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def summary(event, run):
    value = {key: event.get(key) for key in SUMMARY_KEYS}
    for key in ("result", "raw"):
        if value.get(key):
            value[key] = str(Path(run).resolve() / value[key])
    return value


def cmd_init(args):
    roles = load_roles()
    run = J.create_run(args.cwd, args.scenario, {stage: value["limit"] for stage, value in roles["stages"].items()})
    emit({"run": str(run)})
    return 0


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cmd_call(args):
    run = Path(args.run).resolve()
    event = start_call(run, args.stage, args.cwd, args.prompt, args.context, args.schema, args.resume)
    if args.background:
        log = run / "logs" / ("%s-%d.worker.log" % (event["stage"], event["attempt"]))
        try:
            with log.open("ab") as stream:
                process = subprocess.Popen([PYTHON, str(BIN), "_worker", "--run", str(run), "--event", str(event["n"])],
                                           stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, start_new_session=True)
                DETACHED.append(process)
        except OSError as exc:
            event = J.update(run, event["n"], status="failed", finished_at=J.utc_now(),
                             error="cannot start the background worker: %s" % exc)
        else:
            event = J.update(run, event["n"], pid=process.pid)
    else:
        event = perform_call(run, event["n"])
    emit(summary(event, run))
    return EXIT[event["status"]]


def cmd_worker(args):
    perform_call(args.run, args.event)
    return 0


def cmd_wait(args):
    if not math.isfinite(args.timeout) or args.timeout < 0:
        raise DuetError("--timeout must be a finite, non-negative number of seconds")
    deadline = time.monotonic() + args.timeout
    while True:
        event = J.call_event(J.load(args.run), args.event)
        if event["status"] != "running":
            break
        if event.get("pid") and not alive(event["pid"]):
            def settle(journal):
                entry = journal["events"][args.event - 1]
                if entry["status"] == "running":
                    entry.update(status="failed", finished_at=J.utc_now(),
                                 error="worker process exited without recording an outcome; see logs/")
                return entry
            event = J.transact(args.run, settle)
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0.05, deadline - time.monotonic())))
    emit(summary(event, args.run))
    return EXIT[event["status"]]


def cmd_status(args):
    journal = J.load(args.run)
    events = [summary(event, args.run) if event["kind"] == "call" else
              {key: event.get(key) for key in ("n", "kind", "stage", "status", "note")}
              for event in journal["events"]]
    emit({"scenario": journal["scenario"], "project": journal["project"], "limits": journal["limits"], "events": events})
    return 0


def cmd_mark(args):
    J.append(args.run, {"kind": "stage", "stage": args.stage, "status": args.status, "note": args.note})
    return 0


def cmd_tree(args):
    emit(J.tree_state(args.cwd))
    return 0


def cmd_limit(args):
    if args.set < 1:
        raise DuetError("A limit must be a positive integer")

    def change(journal):
        if args.stage not in journal["limits"]:
            raise DuetError("Unknown stage: " + args.stage)
        journal["limits"][args.stage] = args.set
        journal["events"].append({"kind": "limit", "stage": args.stage, "status": "set",
                                  "note": "user set the limit to %d" % args.set,
                                  "n": len(journal["events"]) + 1, "at": J.utc_now()})
    J.transact(args.run, change)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="duet-codex", description="One journaled Codex call per invocation for Duet runs")
    parser.add_argument("--version", action="version", version="duet-codex " + VERSION)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="create a run directory under <repo>/.duet/runs")
    p.add_argument("--scenario", required=True, choices=SCENARIOS)
    p.add_argument("--cwd", default=".")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("call", help="make one Codex call for a stage")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--prompt", required=True, help="stage material file written by the skill")
    p.add_argument("--context", action="append", default=[], help="extra file appended as a context section")
    p.add_argument("--schema", help="schema name; defaults by stage")
    p.add_argument("--resume", metavar="SESSION_ID", help="continue this Codex session instead of starting a new one")
    p.add_argument("--cwd", default=".", help="directory Codex reads; the reviewed state is hashed here")
    p.add_argument("--background", action="store_true", help="detach the call; poll it with wait")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("_worker")
    p.add_argument("--run", required=True)
    p.add_argument("--event", type=int, required=True)
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("wait", help="wait for a background call")
    p.add_argument("--run", required=True)
    p.add_argument("--event", type=int, required=True)
    p.add_argument("--timeout", type=float, default=600)
    p.set_defaults(func=cmd_wait)

    p = sub.add_parser("status", help="print the run journal")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("mark", help="record a Claude stage in the journal")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", required=True, choices=CLAUDE_STAGES + CODEX_STAGES)
    p.add_argument("--status", required=True, choices=("started", "done", "needs_human"))
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("tree", help="print HEAD and the working-tree hash")
    p.add_argument("--cwd", default=".")
    p.set_defaults(func=cmd_tree)

    p = sub.add_parser("limit", help="set a stage limit for this run (user request only)")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", required=True)
    p.add_argument("--set", type=int, required=True)
    p.set_defaults(func=cmd_limit)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except LimitReached as exc:
        print("duet-codex: " + str(exc), file=sys.stderr)
        return 3
    except DuetError as exc:
        print("duet-codex: " + str(exc), file=sys.stderr)
        return 1
