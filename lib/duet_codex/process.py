"""Bounded subprocess with file-backed stdio; no shell expansion."""
import os
import signal
import subprocess
import time
from pathlib import Path

from .errors import DuetError, ProcessLimitError


def stop_group(process):
    deadline = time.monotonic() + 2

    def send(sig, until):
        while True:
            try:
                os.killpg(process.pid, sig)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                # Darwin can briefly report EPERM for an exiting process group.
                process.poll()
                if time.monotonic() >= until:
                    raise
                time.sleep(.01)
    if not send(signal.SIGTERM, deadline):
        return
    while time.monotonic() < deadline:
        process.poll()
        if not send(0, time.monotonic() + .2):
            break
        time.sleep(0.05)
    send(signal.SIGKILL, time.monotonic() + .2)
    process.wait()


def run_process(argv, cwd, prefix, timeout, input_text="", max_log_bytes=16777216, env=None):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {key: Path(str(prefix) + suffix) for key, suffix in
             (("stdin", ".stdin.txt"), ("stdout", ".stdout.log"), ("stderr", ".stderr.log"))}
    paths["stdin"].write_text(input_text, encoding="utf-8")
    started = time.monotonic()

    def limited(message, code):
        return ProcessLimitError(message, {"argv": argv, "returncode": code,
                                 "duration_seconds": round(time.monotonic() - started, 3),
                                 "stdout": str(paths["stdout"]), "stderr": str(paths["stderr"])})
    with paths["stdin"].open("rb") as src, paths["stdout"].open("wb") as out, paths["stderr"].open("wb") as err:
        try:
            process = subprocess.Popen(argv, cwd=str(cwd), stdin=src, stdout=out, stderr=err,
                                       start_new_session=True, env=env)
        except OSError as exc:
            raise DuetError("Cannot start %s: %s" % (argv[0], exc)) from exc
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise limited("Timeout after %ss; logs: %s" % (timeout, prefix), 124)
                if any(paths[key].stat().st_size > max_log_bytes for key in ("stdout", "stderr")):
                    raise limited("Process log size limit exceeded: %s" % prefix, 125)
                time.sleep(0.05)
        finally:
            stop_group(process)
    if any(paths[key].stat().st_size > max_log_bytes for key in ("stdout", "stderr")):
        raise limited("Process log size limit exceeded: %s" % prefix, 125)
    return {"argv": argv, "returncode": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": str(paths["stdout"]), "stderr": str(paths["stderr"])}


def excerpt(path, limit=6000):
    path = Path(path)
    with path.open("rb") as stream:
        size = path.stat().st_size
        if size <= limit:
            data = stream.read(limit)
        else:
            first = stream.read(limit // 2)
            stream.seek(-limit // 2, 2)
            data = first + b"\n[excerpt; full log at the supplied path]\n" + stream.read(limit // 2)
    return data.decode("utf-8", errors="replace")
