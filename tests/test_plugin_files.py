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
import re

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


class SkillAndAgentFileTests(DuetCase):
    def test_all_skills_and_agents_exist_with_block_descriptions(self):
        expected = [ROOT / "skills" / name / "SKILL.md" for name in ("task", "feature", "research", "review")]
        expected += [ROOT / "agents" / (name + ".md") for name in ("implementer", "reviewer")]
        for path in expected:
            self.assertTrue(path.exists(), path)
            match = FRONTMATTER.match(path.read_text())
            self.assertIsNotNone(match, path)
            header = match.group(1)
            self.assertRegex(header, r"(?m)^name: [a-z]+$", path)
            self.assertRegex(header, r"(?m)^description: >-$", path)
            if "skills" in str(path):
                self.assertIn("protocol.md", path.read_text(), path)

    def test_agents_declare_model_and_tools(self):
        implementer = FRONTMATTER.match((ROOT / "agents/implementer.md").read_text()).group(1)
        reviewer = FRONTMATTER.match((ROOT / "agents/reviewer.md").read_text()).group(1)
        self.assertIn("tools: Read, Glob, Grep, Edit, Write, Bash", implementer)
        self.assertIn("tools: Read, Glob, Grep\n", reviewer + "\n")
        for header in (implementer, reviewer):
            self.assertIn("model: opus", header)
