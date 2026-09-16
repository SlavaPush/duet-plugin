"""Minimal JSON-schema checks for the shapes Duet asks Codex to return."""
import json
from pathlib import Path

from .errors import DuetError

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
DEFAULT_SCHEMAS = {"plan-review": "review", "code-review": "review", "mr-review": "review", "critique": "critique"}


def load_schema(name):
    path = SCHEMA_DIR / (name + ".json")
    if not path.exists():
        raise DuetError("Unknown schema: " + name)
    return json.loads(path.read_text(encoding="utf-8"))


def validate_schema(value, schema, path="response"):
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict):
            raise DuetError(path + " must be an object")
        expected = set(schema["properties"])
        if set(value) != expected:
            raise DuetError("%s must have exactly the keys %s" % (path, sorted(expected)))
        for key, child in schema["properties"].items():
            validate_schema(value[key], child, path + "." + key)
    elif kind == "array":
        if not isinstance(value, list):
            raise DuetError(path + " must be an array")
        for item in value:
            validate_schema(item, schema["items"], path + "[]")
    elif kind == "string":
        if not isinstance(value, str):
            raise DuetError(path + " must be a string")
        if "enum" in schema and value not in schema["enum"]:
            raise DuetError(path + " has an unsupported value: " + value)
    elif kind == "integer":
        if type(value) is not int or value < schema.get("minimum", value):
            raise DuetError(path + " must be a valid integer")
    else:
        raise DuetError("Unsupported schema type: " + kind)
