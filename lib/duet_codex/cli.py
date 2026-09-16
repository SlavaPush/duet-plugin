"""duet-codex: one journaled Codex call per invocation plus run bookkeeping."""
import argparse
import json
import sys
from pathlib import Path

from . import VERSION
from . import journal as J
from .codex import perform_call, start_call
from .config import load_roles
from .errors import DuetError, LimitReached

EXIT = {"completed": 0, "failed": 1, "invalid": 2, "running": 4, "stale": 5}
SCENARIOS = ("task", "feature", "research", "review")
CLAUDE_STAGES = ("research", "plan", "worktree", "freeze", "implement", "stage-review", "synthesis", "report")
SUMMARY_KEYS = ("n", "stage", "attempt", "status", "result", "raw", "session_id", "error", "tree_changed", "tree_after")


def emit(value):
    print(json.dumps(value, ensure_ascii=False))


def summary(event):
    return {key: event.get(key) for key in SUMMARY_KEYS}


def cmd_init(args):
    roles = load_roles()
    run = J.create_run(args.cwd, args.scenario, {stage: value["limit"] for stage, value in roles["stages"].items()})
    emit({"run": str(run)})
    return 0


def cmd_call(args):
    run = Path(args.run).resolve()
    event = start_call(run, args.stage, args.cwd, args.prompt, args.context, args.schema, args.resume)
    event = perform_call(run, event["n"])
    emit(summary(event))
    return EXIT[event["status"]]


def cmd_status(args):
    journal = J.load(args.run)
    events = [summary(event) if event["kind"] == "call" else
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
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("status", help="print the run journal")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("mark", help="record a Claude stage in the journal")
    p.add_argument("--run", required=True)
    p.add_argument("--stage", required=True, choices=CLAUDE_STAGES)
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
