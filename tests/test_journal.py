import hashlib
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
        os.symlink("elsewhere", self.project / "other.lnk")
        with_second_link = J.tree_state(self.project)
        (self.project / "other.lnk").unlink()
        (self.project / "other.lnk").write_text("x")
        (self.project / "other.lnk").chmod(0o644)
        plain = J.tree_state(self.project)
        self.assertNotEqual(with_second_link["hash"], plain["hash"])
        (self.project / "other.lnk").chmod(0o755)
        self.assertNotEqual(plain["hash"], J.tree_state(self.project)["hash"])
        (self.project / "ignored.log").write_text("noise")
        (self.project / ".gitignore").write_text("*.log\n")
        with_ignore = J.tree_state(self.project)
        (self.project / "ignored.log").write_text("more noise")
        self.assertEqual(with_ignore["hash"], J.tree_state(self.project)["hash"])
        self.git("add", "-A")
        self.git("commit", "-qm", "edit")
        self.assertNotEqual(J.tree_state(self.project)["head"], clean["head"])

    def test_tree_state_hash_format_for_an_untracked_file_is_stable(self):
        (self.project / "note.txt").write_bytes(b"hello\n")
        (self.project / "note.txt").chmod(0o644)
        expected = hashlib.sha256(b"diff 0\n" + b"file 8 6\n" + b"note.txt" + b"hello\n").hexdigest()
        self.assertEqual(J.tree_state(self.project)["hash"], expected)

    def test_tree_state_hashes_a_linked_worktree_inside_the_project(self):
        before = J.tree_state(self.project)
        self.git("worktree", "add", "-q", ".claude/worktrees/demo", "-b", "demo")
        added = J.tree_state(self.project)
        self.assertNotEqual(added["hash"], before["hash"])
        (self.project / ".claude/worktrees/demo/a.py").write_text("answer = 3\n")
        self.assertNotEqual(J.tree_state(self.project)["hash"], added["hash"])

    def test_tree_state_tracks_edits_commits_and_untracked_files_of_an_embedded_repository(self):
        (self.project / "vendor").mkdir()
        (self.project / "vendor" / "lib.py").write_text("value = 1\n")
        self.git("-C", "vendor", "init", "-q")
        self.git("-C", "vendor", "add", "-A")
        self.git("-C", "vendor", "commit", "-qm", "base")
        base = J.tree_state(self.project)
        (self.project / "vendor" / "lib.py").write_text("value = 2\n")
        edited = J.tree_state(self.project)
        self.assertNotEqual(base["hash"], edited["hash"])
        self.git("-C", "vendor", "commit", "-qam", "edit")
        committed = J.tree_state(self.project)
        self.assertNotEqual(edited["hash"], committed["hash"])
        (self.project / "vendor" / "new.txt").write_text("new")
        with_untracked = J.tree_state(self.project)
        self.assertNotEqual(committed["hash"], with_untracked["hash"])
        nested = J.tree_state(self.project / "vendor")
        self.git("-C", "vendor", "commit", "--allow-empty", "-qm", "empty")
        self.assertEqual(J.tree_state(self.project / "vendor")["hash"], nested["hash"])
        self.assertNotEqual(J.tree_state(self.project)["hash"], with_untracked["hash"])

    def test_tree_state_hashes_an_untracked_link_to_a_directory_as_a_link(self):
        os.symlink("../bin", self.project / "tools")
        self.assertTrue((self.project / "tools").is_dir())
        expected = hashlib.sha256(b"diff 0\n" + b"link 5 6\n" + b"tools" + b"../bin").hexdigest()
        self.assertEqual(J.tree_state(self.project)["hash"], expected)

    def test_tree_state_rejects_an_embedded_repository_without_commits(self):
        (self.project / "vendor").mkdir()
        (self.project / "vendor" / "lib.py").write_text("value = 1\n")
        self.git("-C", "vendor", "init", "-q")
        with self.assertRaises(DuetError):
            J.tree_state(self.project)

    def test_git_errors_are_actionable(self):
        with self.assertRaisesRegex(DuetError, "git"):
            J.tree_state(self.temp)

    def test_call_event_validates_number_and_kind(self):
        run = J.create_run(self.project, "review", {})
        J.append(run, {"kind": "stage", "stage": "freeze", "status": "done"})
        J.append(run, {"kind": "call", "stage": "mr-review", "status": "running"})
        self.assertEqual(J.call_event(J.load(run), 2)["stage"], "mr-review")
        for bad in (0, 3, -1, 1):
            with self.assertRaises(DuetError):
                J.call_event(J.load(run), bad)
