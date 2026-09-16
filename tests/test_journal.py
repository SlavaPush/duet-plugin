import os
import threading

from helpers import DuetCase
from duet_codex import journal as J
from duet_codex.errors import DuetError


class JournalTests(DuetCase):
    def test_create_run_is_excluded_from_git_and_has_a_journal(self):
        run = J.create_run(self.project, "task", {"code-review": 4})
        self.assertTrue(run.is_dir() and (run / "context").is_dir() and (run / "logs").is_dir())
        self.assertRegex(run.name, r"^task-\d{8}-\d{6}$")
        journal = J.load(run)
        self.assertEqual((journal["version"], journal["scenario"], journal["limits"], journal["events"]),
                         (1, "task", {"code-review": 4}, []))
        self.assertEqual(journal["project"], str(self.project.resolve()))
        self.assertEqual(self.git("status", "--porcelain"), b"")
        self.assertIn(".duet/", (self.project / ".git/info/exclude").read_text())
        second = J.create_run(self.project, "task", {})
        self.assertNotEqual(run, second)

    def test_append_update_attempts_and_failed_transaction(self):
        run = J.create_run(self.project, "review", {})
        first = J.append(run, {"kind": "call", "stage": "mr-review", "status": "running"})
        J.append(run, {"kind": "stage", "stage": "synthesis", "status": "done"})
        self.assertEqual((first["n"], J.load(run)["events"][1]["n"]), (1, 2))
        self.assertIn("at", first)
        updated = J.update(run, 1, status="completed", result="mr-review-1.json")
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(J.load(run)["events"][0]["result"], "mr-review-1.json")
        self.assertEqual(J.attempts(J.load(run), "mr-review"), 1)
        self.assertEqual(J.attempts(J.load(run), "code-review"), 0)
        with self.assertRaises(DuetError):
            J.update(run, 9, status="x")

        def broken(journal):
            journal["events"].append({"kind": "stage"})
            raise DuetError("stop")
        with self.assertRaises(DuetError):
            J.transact(run, broken)
        self.assertEqual(len(J.load(run)["events"]), 2)

    def test_concurrent_updates_do_not_lose_writes(self):
        run = J.create_run(self.project, "review", {})
        for n in range(3):
            J.append(run, {"kind": "stage", "stage": "s%d" % n, "status": "started"})

        def worker(index):
            for _ in range(20):
                J.append(run, {"kind": "stage", "stage": "t%d" % index, "status": "done"})
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        events = J.load(run)["events"]
        self.assertEqual(len(events), 83)
        self.assertEqual([e["n"] for e in events], list(range(1, 84)))

    def test_tree_state_tracks_edits_untracked_files_links_and_commits(self):
        clean = J.tree_state(self.project)
        self.assertEqual(clean["head"], self.git("rev-parse", "HEAD").decode().strip())
        (self.project / "a.py").write_text("answer = 2\n")
        edited = J.tree_state(self.project)
        self.assertNotEqual(clean["hash"], edited["hash"])
        (self.project / "new.txt").write_text("target")
        with_file = J.tree_state(self.project)
        self.assertNotEqual(edited["hash"], with_file["hash"])
        (self.project / "new.txt").unlink()
        os.symlink("target", self.project / "new.txt")
        self.assertNotEqual(with_file["hash"], J.tree_state(self.project)["hash"])
        (self.project / "ignored.log").write_text("noise")
        (self.project / ".gitignore").write_text("*.log\n")
        with_ignore = J.tree_state(self.project)
        (self.project / "ignored.log").write_text("more noise")
        self.assertEqual(with_ignore["hash"], J.tree_state(self.project)["hash"])
        self.git("add", "-A")
        self.git("commit", "-qm", "edit")
        self.assertNotEqual(J.tree_state(self.project)["head"], clean["head"])

    def test_git_errors_are_actionable(self):
        with self.assertRaisesRegex(DuetError, "git"):
            J.tree_state(self.temp)
