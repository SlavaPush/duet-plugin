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
        code, _ = self.run_cli("mark", "--run", str(run), "--stage", "implement", "--status", "done", "--note", "3 files")
        self.assertEqual(code, 0)
        with self.assertRaises(SystemExit):
            self.run_cli("mark", "--run", str(run), "--stage", "implemnt", "--status", "done")
        code, out = self.run_cli("status", "--run", str(run))
        self.assertEqual(code, 0)
        self.assertEqual([e.get("stage") for e in out["events"]], ["code-review", "implement"])
        self.assertEqual(out["events"][1]["note"], "3 files")
        self.assertEqual(set(out["events"][0]["tree_after"]), {"head", "hash"})
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
