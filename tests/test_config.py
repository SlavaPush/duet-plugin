import json

from helpers import DuetCase
from duet_codex.config import EFFORTS, load_roles, stage_settings, user_config_dir
from duet_codex.errors import DuetError


class ConfigTests(DuetCase):
    def write_user(self, value):
        path = user_config_dir() / "roles.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_defaults(self):
        roles = load_roles()
        settings = stage_settings(roles, "code-review")
        self.assertEqual((settings["model"], settings["effort"], settings["resume_effort"], settings["limit"]),
                         ("gpt-6-astra", "xhigh", "high", 4))
        self.assertEqual([stage_settings(roles, s)["limit"] for s in ("plan-review", "critique", "mr-review")], [3, 2, 2])
        self.assertEqual(roles["timeouts"]["call_seconds"], 1800)
        self.assertIn("xhigh", EFFORTS)

    def test_user_override_merges_a_subset(self):
        self.write_user({"codex": {"model": "gpt-6-astra-mini"}, "stages": {"code-review": {"limit": 25}}})
        settings = stage_settings(load_roles(), "code-review")
        self.assertEqual((settings["model"], settings["limit"], settings["effort"]), ("gpt-6-astra-mini", 25, "xhigh"))

    def test_unknown_keys_and_bad_leaves_are_errors(self):
        cases = [
            ({"stages": {"code-review": {"efort": "high"}}}, "Unknown setting roles.stages.code-review.efort"),
            ({"stages": {"code-review": {"effort": "ultra"}}}, "roles.stages.code-review.effort"),
            ({"stages": {"code-review": {"limit": 0}}}, "roles.stages.code-review.limit"),
            ({"stages": {"code-review": {"limit": True}}}, "roles.stages.code-review.limit"),
            ({"codex": {"model": {"typo": 1}}}, "roles.codex.model"),
            ({"codex": {"model": " "}}, "roles.codex.model"),
            ({"timeouts": {"call_seconds": "oops"}}, "roles.timeouts.call_seconds"),
            ({"limits": {"max_log_bytes": False}}, "roles.limits.max_log_bytes"),
            ({"stages": "nope"}, "roles.stages must be an object"),
        ]
        for value, message in cases:
            with self.subTest(value=value):
                self.write_user(value)
                with self.assertRaisesRegex(DuetError, message):
                    load_roles()
        self.write_user({})
        with self.assertRaisesRegex(DuetError, "Unknown stage"):
            stage_settings(load_roles(), "deploy")
