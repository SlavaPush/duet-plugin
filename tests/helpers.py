import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))


class DuetCase(unittest.TestCase):
    """Temp git repo, fake codex first on PATH, isolated git config, XDG_CONFIG_HOME and environment."""

    def setUp(self):
        self.saved_environ = dict(os.environ)
        self.addCleanup(self.restore_environ)
        self.temp = Path(tempfile.mkdtemp(prefix="duet-plugin-"))
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.release = self.temp / "release"
        self.addCleanup(self.release_fake)
        (self.temp / "gitconfig").write_text(
            "[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n[commit]\n\tgpgsign = false\n",
            encoding="utf-8")
        fake_bin = self.temp / "bin"
        fake_bin.mkdir()
        fake = fake_bin / "codex"
        shutil.copy(ROOT / "tests/fake_codex.py", fake)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = self.temp / "codex-calls.jsonl"
        for key in [k for k in os.environ if k.startswith("GIT_") or k == "DUET_FAKE_SLEEP"]:
            os.environ.pop(key, None)
        os.environ.update({
            "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
            "XDG_CONFIG_HOME": str(self.temp / "config"),
            "GIT_CONFIG_GLOBAL": str(self.temp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "DUET_FAKE_LOG": str(self.log),
            "DUET_FAKE_MODE": "ok",
            "DUET_FAKE_RELEASE": str(self.release)})
        self.project = self.temp / "project"
        self.project.mkdir()
        self.git("init", "-q")
        (self.project / "a.py").write_text("answer = 1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    def restore_environ(self):
        os.environ.clear()
        os.environ.update(self.saved_environ)

    def release_fake(self):
        """Let any waiting fake call and detached worker finish before the temp directory disappears."""
        self.release.touch()
        from duet_codex import cli
        for process in cli.DETACHED:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        cli.DETACHED.clear()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=str(self.project), check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
