import os
import subprocess
import sys
import time
from pathlib import Path

from helpers import DuetCase
from duet_codex.errors import DuetError, ProcessLimitError
from duet_codex.process import excerpt, run_process


class ProcessTests(DuetCase):
    def test_file_backed_stdio_and_exit_code(self):
        result = run_process([sys.executable, "-c", "import sys; print(sys.stdin.read().upper()); sys.exit(3)"],
                             self.project, self.temp / "logs/echo", 10, "hello")
        self.assertEqual(result["returncode"], 3)
        self.assertEqual(Path(result["stdout"]).read_text(), "HELLO\n")
        self.assertEqual(excerpt(result["stdout"]), "HELLO\n")

    def test_timeout_kills_the_whole_process_group(self):
        pid_file = self.temp / "child.pid"
        script = ("import subprocess, sys, time; child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                  "open(%r, 'w').write(str(child.pid)); time.sleep(60)" % str(pid_file))
        with self.assertRaises(ProcessLimitError) as raised:
            run_process([sys.executable, "-c", script], self.project, self.temp / "logs/slow", 1)
        self.assertEqual(raised.exception.result["returncode"], 124)
        child = int(pid_file.read_text())
        for _ in range(50):
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], stdout=subprocess.PIPE).stdout.decode().strip()
            if not state or state.startswith("Z"):
                break
            time.sleep(0.05)
        else:
            self.fail("grandchild survived the timeout: state %r" % state)

    def test_missing_executable_is_actionable(self):
        with self.assertRaises(DuetError):
            run_process(["definitely-not-a-command-xyz"], self.project, self.temp / "logs/missing", 5)

    def test_log_cap(self):
        with self.assertRaises(ProcessLimitError) as raised:
            run_process([sys.executable, "-c", "print('x' * 5000)"], self.project, self.temp / "logs/big", 5, max_log_bytes=100)
        self.assertEqual(raised.exception.result["returncode"], 125)
