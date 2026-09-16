import io
import subprocess
import sys
from contextlib import redirect_stdout

from helpers import ROOT, DuetCase
from duet_codex import VERSION
from duet_codex.cli import main


class CliTests(DuetCase):
    def test_version_from_launcher_and_main(self):
        result = subprocess.run([sys.executable, str(ROOT / "bin/duet-codex"), "--version"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(VERSION.encode(), result.stdout + result.stderr)
        with self.assertRaises(SystemExit) as raised:
            with redirect_stdout(io.StringIO()):
                main(["--version"])
        self.assertEqual(raised.exception.code, 0)
import json
import os
import time
from pathlib import Path

from duet_codex import journal as J


class CommandTests(DuetCase):
    def run_cli(self, *argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(argv))
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        return code, (json.loads(lines[-1]) if lines else None)

    def init(self):
        code, out = self.run_cli("init", "--scenario", "task", "--cwd", str(self.project))
        self.assertEqual(code, 0)
        run = Path(out["run"])
        (run / "material.md").write_text("review a.py\n")
        return run

    def call(self, run, *extra):
        return self.run_cli("call", "--run", str(run), "--stage", "code-review", "--prompt",
                            str(run / "material.md"), "--cwd", str(self.project), *extra)

    def test_init_uses_role_limits(self):
        run = self.init()
        self.assertEqual(J.load(run)["limits"], {"plan-review": 3, "code-review": 4, "critique": 2, "mr-review": 2})

    def test_call_mark_status_and_exit_codes(self):
        run = self.init()
        code, out = self.call(run)
        self.assertEqual((code, out["status"], out["n"], out["tree_changed"]), (0, "completed", 1, False))
        self.assertEqual(out["result"], str(run / "code-review-1.json"))
        self.assertEqual(out["raw"], str(run / "code-review-1.raw.md"))
        code, _ = self.run_cli("mark", "--run", str(run), "--stage", "implement", "--status", "done", "--note", "3 files")
        self.assertEqual(code, 0)
        code, _ = self.run_cli("mark", "--run", str(run), "--stage", "code-review", "--status", "needs_human", "--note", "limit")
        self.assertEqual(code, 0)
        with self.assertRaises(SystemExit):
            self.run_cli("mark", "--run", str(run), "--stage", "implemnt", "--status", "done")
        code, out = self.run_cli("status", "--run", str(run))
        self.assertEqual(code, 0)
        self.assertEqual([e.get("stage") for e in out["events"]], ["code-review", "implement", "code-review"])
        self.assertEqual(out["events"][1]["note"], "3 files")
        self.assertEqual(set(out["events"][0]["tree_after"]), {"head", "hash"})
        self.assertEqual(out["events"][0]["result"], str(run / "code-review-1.json"))
        os.environ["DUET_FAKE_MODE"] = "invalid"
        code, out = self.call(run)
        self.assertEqual((code, out["status"]), (2, "invalid"))
        os.environ["DUET_FAKE_MODE"] = "fail"
        code, out = self.call(run)
        self.assertEqual((code, out["status"]), (1, "failed"))

    def test_limit_refusal_and_user_raise(self):
        run = self.init()
        for _ in range(4):
            self.assertEqual(self.call(run)[0], 0)
        self.assertEqual(self.call(run)[0], 3)
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(self.run_cli("limit", "--run", str(run), "--stage", "code-review", "--set", "0")[0], 1)
        self.assertEqual(self.run_cli("limit", "--run", str(run), "--stage", "code-review", "--set", "5")[0], 0)
        code, out = self.call(run)
        self.assertEqual((code, out["attempt"]), (0, 5))
        self.assertEqual(J.load(run)["events"][-2]["kind"], "limit")

    def test_tree_prints_state(self):
        code, out = self.run_cli("tree", "--cwd", str(self.project))
        self.assertEqual(code, 0)
        self.assertEqual(set(out), {"head", "hash"})

    def test_background_call_and_wait(self):
        run = self.init()
        os.environ["DUET_FAKE_MODE"] = "slow"
        code, out = self.call(run, "--background")
        self.assertEqual((code, out["status"]), (4, "running"))
        self.assertTrue(J.load(run)["events"][0]["pid"])
        code, out = self.run_cli("wait", "--run", str(run), "--event", "1", "--timeout", "0.3")
        self.assertEqual((code, out["status"]), (4, "running"))
        self.release.touch()
        code, out = self.run_cli("wait", "--run", str(run), "--event", "1", "--timeout", "20")
        self.assertEqual((code, out["status"]), (0, "completed"))
        self.assertTrue((run / "code-review-1.json").exists())

    def test_wait_detects_a_dead_worker_but_keeps_a_finished_result(self):
        run = self.init()
        event = J.append(run, {"kind": "call", "stage": "code-review", "attempt": 1, "status": "running", "pid": 2147483000})
        code, out = self.run_cli("wait", "--run", str(run), "--event", str(event["n"]), "--timeout", "5")
        self.assertEqual((code, out["status"]), (1, "failed"))
        self.assertIn("worker", out["error"])
        done = J.append(run, {"kind": "call", "stage": "code-review", "attempt": 2, "status": "completed", "pid": 2147483000})
        code, out = self.run_cli("wait", "--run", str(run), "--event", str(done["n"]), "--timeout", "5")
        self.assertEqual((code, out["status"]), (0, "completed"))

    def test_background_spawn_failure_ends_failed(self):
        run = self.init()
        from duet_codex import cli
        original = cli.PYTHON
        cli.PYTHON = "/nonexistent/python3"
        try:
            code, out = self.call(run, "--background")
        finally:
            cli.PYTHON = original
        self.assertEqual((code, out["status"]), (1, "failed"))
        self.assertIn("worker", out["error"])

    def test_wait_validates_event_and_timeout(self):
        run = self.init()
        J.append(run, {"kind": "stage", "stage": "freeze", "status": "done"})
        self.assertEqual(self.run_cli("wait", "--run", str(run), "--event", "0", "--timeout", "1")[0], 1)
        self.assertEqual(self.run_cli("wait", "--run", str(run), "--event", "1", "--timeout", "1")[0], 1)
        self.assertEqual(self.run_cli("wait", "--run", str(run), "--event", "5", "--timeout", "1")[0], 1)
        self.call(run)
        self.assertEqual(self.run_cli("wait", "--run", str(run), "--event", "2", "--timeout", "inf")[0], 1)
        self.assertEqual(self.run_cli("wait", "--run", str(run), "--event", "2", "--timeout", "-1")[0], 1)
        code, out = self.run_cli("wait", "--run", str(run), "--event", "2", "--timeout", "1")
        self.assertEqual((code, out["status"], out["result"]), (0, "completed", str(run / "code-review-1.json")))

    def test_sigterm_cancels_the_worker_and_its_codex(self):
        import signal
        run = self.init()
        os.environ["DUET_FAKE_MODE"] = "slow"
        code, out = self.call(run, "--background")
        self.assertEqual(code, 4)
        pid = J.load(run)["events"][0]["pid"]
        pattern = str(run / "code-review-1.raw.md")  # only the fake codex has the answer path in its argv
        for _ in range(200):
            found = subprocess.run(["pgrep", "-f", pattern], stdout=subprocess.PIPE).stdout.split()
            if found:
                break
            time.sleep(0.05)
        else:
            self.fail("the fake codex did not start")
        codex_pid = int(found[0])
        os.kill(pid, signal.SIGTERM)
        code, out = self.run_cli("wait", "--run", str(run), "--event", "1", "--timeout", "20")
        self.assertEqual((code, out["status"]), (1, "failed"))
        self.assertIn("interrupted", out["error"])
        for _ in range(100):
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(codex_pid)], stdout=subprocess.PIPE).stdout.decode().strip()
            if not state or state.startswith("Z"):
                break
            time.sleep(0.05)
        else:
            self.fail("the fake codex survived SIGTERM to the worker: state %r" % state)
