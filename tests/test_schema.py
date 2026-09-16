import unittest

from helpers import ROOT  # noqa: F401  (puts lib on sys.path)
from duet_codex.errors import DuetError
from duet_codex.schema import DEFAULT_SCHEMAS, load_schema, validate_schema

FINDING = {"id": "X-1", "severity": "blocking", "file": "a.py", "start_line": 1, "end_line": 2,
           "description": "wrong", "suggestion": "fix"}
REVIEW = {"verdict": "changes_requested", "summary": "s", "findings": [FINDING], "resolved_ids": [], "questions": []}
CRITIQUE = {"summary": "s", "claim_reviews": [{"id": "R-1", "result": "disputed", "note": "why"}], "findings": [FINDING]}


class SchemaTests(unittest.TestCase):
    def test_valid_documents_pass(self):
        validate_schema(REVIEW, load_schema("review"))
        validate_schema(CRITIQUE, load_schema("critique"))

    def test_extra_missing_and_wrong_values_fail_with_path(self):
        with self.assertRaisesRegex(DuetError, "response.verdict"):
            validate_schema(dict(REVIEW, verdict="maybe"), load_schema("review"))
        with self.assertRaisesRegex(DuetError, "exactly the keys"):
            validate_schema(dict(REVIEW, extra=1), load_schema("review"))
        bad = dict(REVIEW, findings=[dict(FINDING, start_line="1")])
        with self.assertRaisesRegex(DuetError, r"findings\[\].start_line"):
            validate_schema(bad, load_schema("review"))
        with self.assertRaisesRegex(DuetError, "must be an object"):
            validate_schema([], load_schema("review"))

    def test_unknown_schema_and_defaults(self):
        with self.assertRaises(DuetError):
            load_schema("nope")
        self.assertEqual(set(DEFAULT_SCHEMAS), {"plan-review", "code-review", "mr-review", "critique"})
