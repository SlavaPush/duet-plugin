import argparse
import sys

from . import VERSION
from .errors import DuetError, LimitReached


def build_parser():
    parser = argparse.ArgumentParser(prog="duet-codex", description="One journaled Codex call per invocation for Duet runs")
    parser.add_argument("--version", action="version", version="duet-codex " + VERSION)
    parser.add_subparsers(dest="command")
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
