import json

from helpers import ROOT, DuetCase
from duet_codex.config import load_roles
from duet_codex.schema import DEFAULT_SCHEMAS, load_schema


class PluginFileTests(DuetCase):
    def test_manifests(self):
        manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "duet")
        self.assertTrue(manifest["version"] and manifest["description"])
        marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual([p["name"] for p in marketplace["plugins"]], ["duet"])
        self.assertEqual(marketplace["plugins"][0]["source"], "./")

    def test_every_stage_has_prompt_and_schema(self):
        for stage in load_roles()["stages"]:
            prompt = ROOT / "prompts" / (stage + ".md")
            self.assertTrue(prompt.exists(), stage)
            self.assertGreater(len(prompt.read_text().splitlines()), 5, stage)
            load_schema(DEFAULT_SCHEMAS[stage])
