"""Run directory, locked machine-readable timeline and the reviewed-state hash."""
import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from .config import read_json
from .errors import DuetError


def atomic_json(path, value):
    path = Path(path)
    if path.is_symlink():
        raise DuetError("Refusing a symlink in run storage: " + str(path))
    temporary = path.with_name("%s.tmp-%d" % (path.name, os.getpid()))
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def git(cwd, *args):
    try:
        result = subprocess.run(["git", *args], cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise DuetError("Cannot run git: %s" % exc) from exc
    if result.returncode:
        raise DuetError("git %s failed in %s: %s" % (args[0], cwd, result.stderr.decode(errors="replace").strip()))
    return result.stdout


def repo_root(cwd):
    return Path(git(cwd, "rev-parse", "--show-toplevel").decode().strip())


def tree_state(cwd):
    """HEAD plus a digest of the diff against HEAD and of every untracked, non-ignored file."""
    root = repo_root(cwd)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    diff = git(root, "diff", "HEAD", "--binary", "--no-ext-diff", "--no-textconv", "--no-color",
               "--ignore-submodules=none")
    digest = hashlib.sha256(b"diff %d\n" % len(diff) + diff)
    for name in git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
        if not name:
            continue
        path = root / os.fsdecode(name)
        if path.is_symlink():
            kind, data = b"link", os.fsencode(os.readlink(path))
        else:
            kind = b"exec" if path.stat().st_mode & 0o111 else b"file"
            data = path.read_bytes()
        digest.update(b"%s %d %d\n" % (kind, len(name), len(data)) + name + data)
    return {"head": head, "hash": digest.hexdigest()}


def exclude_runs(root):
    common = Path(git(root, "rev-parse", "--git-common-dir").decode().strip())
    if not common.is_absolute():
        common = root / common
    exclude = common / "info" / "exclude"
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if ".duet/" not in existing.splitlines():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as stream:
            stream.write(("" if not existing or existing.endswith("\n") else "\n") + ".duet/\n")


def create_run(cwd, scenario, limits):
    root = repo_root(cwd)
    exclude_runs(root)
    base = root / ".duet" / "runs"
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run = base / (scenario + "-" + stamp)
    suffix = 1
    while run.exists():
        suffix += 1
        run = base / ("%s-%s-%d" % (scenario, stamp, suffix))
    (run / "context").mkdir(parents=True)
    (run / "logs").mkdir()
    atomic_json(run / "journal.json", {"version": 1, "scenario": scenario, "project": str(root),
                                       "created_at": utc_now(), "limits": limits, "events": []})
    return run


def load(run):
    return read_json(Path(run) / "journal.json")


def save(run, journal):
    atomic_json(Path(run) / "journal.json", journal)


@contextlib.contextmanager
def locked(run):
    """Exclusive lock for read-modify-write of journal.json; never held during a Codex call."""
    with (Path(run) / "journal.lock").open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def transact(run, change):
    with locked(run):
        journal = load(run)
        result = change(journal)
        save(run, journal)
        return result


def append(run, event):
    def change(journal):
        entry = dict(event, n=len(journal["events"]) + 1, at=utc_now())
        journal["events"].append(entry)
        return entry
    return transact(run, change)


def update(run, n, **fields):
    def change(journal):
        if not 1 <= n <= len(journal["events"]):
            raise DuetError("No journal event %d in %s" % (n, run))
        entry = journal["events"][n - 1]
        entry.update(fields)
        return entry
    return transact(run, change)


def attempts(journal, stage):
    return sum(1 for event in journal["events"] if event["kind"] == "call" and event["stage"] == stage)


def call_event(journal, n):
    """The Codex call recorded as event n, or a DuetError naming the problem."""
    if type(n) is not int or not 1 <= n <= len(journal["events"]):
        raise DuetError("No journal event %r" % (n,))
    event = journal["events"][n - 1]
    if event.get("kind") != "call":
        raise DuetError("Journal event %d is not a Codex call" % n)
    return event
