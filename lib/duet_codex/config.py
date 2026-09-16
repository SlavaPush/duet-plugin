"""Plugin defaults merged with the user's ~/.config/duet/roles.json; every leaf is validated."""
import json
import os
from pathlib import Path

from .errors import DuetError

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DuetError("Cannot read JSON %s: %s" % (path, exc)) from exc


def user_config_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "duet"


def merge(base, override, path="roles"):
    if not isinstance(override, dict):
        raise DuetError("Setting %s must be an object" % path)
    for key, value in override.items():
        if key not in base:
            raise DuetError("Unknown setting %s.%s" % (path, key))
        if isinstance(base[key], dict):
            merge(base[key], value, path + "." + key)
        else:
            base[key] = value
    return base


def positive_int(value, path):
    if type(value) is not int or value < 1:
        raise DuetError("%s must be a positive integer" % path)


def validate_roles(roles):
    model = roles["codex"].get("model")
    if not isinstance(model, str) or not model.strip():
        raise DuetError("roles.codex.model must be a non-empty string")
    for stage, value in roles["stages"].items():
        for key in ("effort", "resume_effort"):
            if value.get(key) not in EFFORTS:
                raise DuetError("roles.stages.%s.%s must be one of %s" % (stage, key, ", ".join(EFFORTS)))
        positive_int(value.get("limit"), "roles.stages.%s.limit" % stage)
    seconds = roles["timeouts"].get("call_seconds")
    if type(seconds) not in (int, float) or seconds <= 0:
        raise DuetError("roles.timeouts.call_seconds must be a positive number")
    positive_int(roles["limits"].get("max_log_bytes"), "roles.limits.max_log_bytes")
    return roles


def load_roles():
    roles = read_json(PLUGIN_ROOT / "config/roles.json")
    override = user_config_dir() / "roles.json"
    if override.exists():
        merge(roles, read_json(override))
    return validate_roles(roles)


def stage_settings(roles, stage):
    if stage not in roles["stages"]:
        raise DuetError("Unknown stage: " + stage)
    return dict(roles["stages"][stage], model=roles["codex"]["model"])
