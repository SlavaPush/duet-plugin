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
