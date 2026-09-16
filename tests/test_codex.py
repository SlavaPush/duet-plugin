import json
import os
import subprocess
import threading

from helpers import DuetCase
from duet_codex import journal as J
from duet_codex import codex
from duet_codex.codex import build_prompt, exec_argv, parse_events, perform_call, resume_argv, start_call
from duet_codex.errors import DuetError, LimitReached


class CodexTests(DuetCase):
    def setUp(self):
        super().setUp()
        self.run = J.create_run(self.project, "task", {"code-review": 2})
        self.material = self.run / "material.md"
        self.material.write_text("Review the diff of a.py\n", encoding="utf-8")
        self.rules = self.run / "context" / "rules.md"
        self.rules.write_text("Prefer native elements.\n", encoding="utf-8")

    def test_prompt_and_argv_shapes(self):
        text = build_prompt("ROLE\n", [("Material", "M\n"), ("Context: rules.md", "R")])
        self.assertEqual(text, "ROLE\n\n## Material\n\nM\n\n## Context: rules.md\n\nR\n")
        argv = exec_argv("/p", "gpt-6-astra", "xhigh", "/s.json", "/r.md")
        self.assertEqual(argv[:4], ["codex", "exec", "-C", "/p"])
        self.assertIn('model_reasoning_effort="xhigh"', argv)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[argv.index("--output-schema") + 1], "/s.json")
        self.assertEqual(argv[argv.index("-o") + 1], "/r.md")
        self.assertEqual(argv[-1], "-")
        resumed = resume_argv("sid-1", "gpt-6-astra", "high", "/s.json", "/r.md")
        self.assertEqual(resumed[:4], ["codex", "exec", "resume", "sid-1"])
        self.assertIn('sandbox_mode="read-only"', resumed)
        self.assertIn('model_reasoning_effort="high"', resumed)
        self.assertNotIn("-C", resumed)
        self.assertNotIn("--sandbox", resumed)
        self.assertEqual(resumed[resumed.index("--output-schema") + 1], "/s.json")
        self.assertEqual(resumed[resumed.index("-o") + 1], "/r.md")
        self.assertEqual(resumed[-1], "-")

    def test_parse_events(self):
        path = self.temp / "events.jsonl"
        path.write_text('{"type":"thread.started","thread_id":"t1"}\nnot json\n[1]\n{"type":"turn.completed"}\n')
        self.assertEqual(parse_events(path), ("t1", True, None))
        path.write_text('{"type":"thread.started","thread_id":"t2"}\n{"type":"turn.failed","error":"boom"}\n')
        self.assertEqual(parse_events(path), ("t2", False, "boom"))

    def test_attempt_is_reserved_before_codex_runs(self):
        event = start_call(self.run, "code-review", self.project, self.material, [self.rules])
        self.assertEqual((event["n"], event["attempt"], event["status"], event["effort"]), (1, 1, "running", "xhigh"))
        self.assertEqual(J.load(self.run)["events"][0]["status"], "running")
        self.assertTrue((self.run / "code-review-1.prompt.md").exists())
        self.assertEqual(self.calls(), [])

    def test_completed_call_records_everything(self):
        event = start_call(self.run, "code-review", self.project, self.material, [self.rules])
        done = perform_call(self.run, event["n"])
        self.assertEqual(done["status"], "completed", done["error"])
        self.assertEqual(done["session_id"], "fake-session-1")
        self.assertEqual(done["returncode"], 0)
        self.assertTrue(done["logs"]["stdout"].endswith("code-review-1.stdout.log"))
        self.assertEqual(json.loads((self.run / done["result"]).read_text())["verdict"], "changes_requested")
        self.assertTrue((self.run / done["raw"]).exists())
        self.assertEqual((done["tree_after"], done["tree_changed"]), (done["tree_before"], False))
        call = self.calls()[0]
        self.assertIn("## Context: rules.md", call["prompt"])
        self.assertIn("Prefer native elements.", call["prompt"])
        self.assertEqual(call["argv"][call["argv"].index("-m") + 1], "gpt-6-astra")
        self.assertEqual(call["cwd"], str(self.project.resolve()))

    def test_resume_uses_session_resume_effort_and_cwd(self):
        first = perform_call(self.run, start_call(self.run, "code-review", self.project, self.material)["n"])
        event = start_call(self.run, "code-review", self.project, self.material, resume=first["session_id"])
        self.assertEqual((event["attempt"], event["effort"], event["resume_of"]), (2, "high", "fake-session-1"))
        done = perform_call(self.run, 2)
        self.assertEqual(done["status"], "completed")
        argv = self.calls()[1]["argv"]
        self.assertEqual(argv[:3], ["exec", "resume", "fake-session-1"])
        self.assertNotIn("-C", argv)
        self.assertNotIn("--sandbox", argv)
        self.assertIn('sandbox_mode="read-only"', argv)
        self.assertEqual(argv[-1], "-")
        self.assertEqual(self.calls()[1]["cwd"], str(self.project.resolve()))
        self.assertEqual(json.loads((self.run / done["result"]).read_text())["verdict"], "pass")

    def test_limit_is_enforced_before_spawn(self):
        for _ in range(2):
            perform_call(self.run, start_call(self.run, "code-review", self.project, self.material)["n"])
        with self.assertRaisesRegex(LimitReached, "code-review"):
            start_call(self.run, "code-review", self.project, self.material)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(len(J.load(self.run)["events"]), 2)

    def test_invalid_answer_keeps_raw(self):
        os.environ["DUET_FAKE_MODE"] = "invalid"
        done = perform_call(self.run, start_call(self.run, "code-review", self.project, self.material)["n"])
        self.assertEqual(done["status"], "invalid")
        self.assertIsNone(done["result"])
        self.assertIn('"verdict": "maybe"', (self.run / done["raw"]).read_text())
        self.assertIn("schema", done["error"])

    def test_failed_cli_is_recorded(self):
        os.environ["DUET_FAKE_MODE"] = "fail"
        done = perform_call(self.run, start_call(self.run, "code-review", self.project, self.material)["n"])
        self.assertEqual((done["status"], done["returncode"]), ("failed", 1))
        self.assertIn("exited 1", done["error"])

    def test_missing_prompt_file_still_ends_failed(self):
        event = start_call(self.run, "code-review", self.project, self.material)
        (self.run / event["prompt"]).unlink()
        done = perform_call(self.run, event["n"])
        self.assertEqual(done["status"], "failed")
        self.assertIn("Cannot read", done["error"])

    def test_edit_during_call_marks_stale_and_tree_changed(self):
        event = start_call(self.run, "code-review", self.project, self.material)
        (self.project / "a.py").write_text("answer = 3\n")
        done = perform_call(self.run, event["n"])
        self.assertEqual((done["status"], done["tree_changed"]), ("stale", True))
        self.assertIsNotNone(done["result"])
        os.environ["DUET_FAKE_MODE"] = "invalid"
        event = start_call(self.run, "code-review", self.project, self.material)
        (self.project / "a.py").write_text("answer = 4\n")
        done = perform_call(self.run, event["n"])
        self.assertEqual((done["status"], done["tree_changed"]), ("invalid", True))

    def test_task_file_is_a_prompt_section_and_schema_comes_from_the_plugin(self):
        (self.run / "task.md").write_text("Fix the average function\n", encoding="utf-8")
        done = perform_call(self.run, start_call(self.run, "code-review", self.project, self.material)["n"])
        prompt = self.calls()[0]["prompt"]
        self.assertLess(prompt.index("## Task"), prompt.index("## Material"))
        self.assertIn("Fix the average function", prompt)
        argv = self.calls()[0]["argv"]
        self.assertTrue(argv[argv.index("--output-schema") + 1].endswith("schemas/review.json"))
        self.assertFalse((self.run / "logs" / "review.schema.json").exists())
        self.assertEqual(done["pid"], os.getpid())

    def test_answer_problems_end_in_terminal_statuses(self):
        expected = {"no-answer": ("failed", "no answer file"), "no-session": ("failed", "session ID"),
                    "turn-failed": ("failed", "fake turn failure"), "garbage": ("invalid", "schema")}
        for mode, (status, message) in expected.items():
            with self.subTest(mode=mode):
                os.environ["DUET_FAKE_MODE"] = mode
                run = J.create_run(self.project, "task", {"code-review": 9})
                done = perform_call(run, start_call(run, "code-review", self.project, self.material)["n"])
                self.assertEqual(done["status"], status, done["error"])
                self.assertIn(message, done["error"])

    def test_tree_check_failure_after_the_call_is_not_approval(self):
        event = start_call(self.run, "code-review", self.project, self.material)
        original = codex.J.tree_state
        calls = []

        def flaky(cwd):
            calls.append(cwd)
            raise OSError("vanished")
        codex.J.tree_state = flaky
        try:
            done = perform_call(self.run, event["n"])
        finally:
            codex.J.tree_state = original
        self.assertEqual((done["status"], done["tree_after"], done["tree_changed"]), ("stale", None, True))
        self.assertIn("tree check failed", done["error"])

    def test_interrupt_leaves_a_terminal_status(self):
        event = start_call(self.run, "code-review", self.project, self.material)
        original = codex.run_process

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt
        codex.run_process = interrupted
        try:
            with self.assertRaises(KeyboardInterrupt):
                perform_call(self.run, event["n"])
        finally:
            codex.run_process = original
        recorded = J.load(self.run)["events"][0]
        self.assertEqual(recorded["status"], "failed")
        self.assertIn("interrupted", recorded["error"])

    def test_concurrent_reservations_respect_the_limit(self):
        run = J.create_run(self.project, "task", {"code-review": 1})
        outcomes = []

        def reserve():
            try:
                outcomes.append(start_call(run, "code-review", self.project, self.material)["attempt"])
            except LimitReached:
                outcomes.append("limit")
        threads = [threading.Thread(target=reserve) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes, key=str), [1, "limit", "limit", "limit"])

    def test_call_from_a_linked_worktree_keeps_the_run_in_the_checkout(self):
        worktree = self.temp / "wt"
        self.git("worktree", "add", "-q", "-b", "wt", str(worktree))
        (worktree / "a.py").write_text("answer = 42\n", encoding="utf-8")
        event = start_call(self.run, "code-review", worktree, self.material)
        done = perform_call(self.run, event["n"])
        self.assertEqual(done["status"], "completed", done["error"])
        self.assertEqual(done["cwd"], str(worktree.resolve()))
        self.assertEqual(done["tree_before"]["head"], self.git("rev-parse", "wt").decode().strip())
        self.assertEqual(self.calls()[0]["cwd"], str(worktree.resolve()))
        self.assertTrue((self.run / done["result"]).exists())
        self.assertEqual(self.git("status", "--porcelain"), b"")

    def test_perform_call_rejects_bad_event_numbers(self):
        J.append(self.run, {"kind": "stage", "stage": "freeze", "status": "done"})
        for bad in (0, 1, 2):
            with self.assertRaises(DuetError):
                perform_call(self.run, bad)
