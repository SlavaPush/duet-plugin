"""One Codex call: reserve the attempt, run, keep the raw answer, validate, record the outcome."""
import json
from pathlib import Path

from . import journal as J
from .config import PLUGIN_ROOT, load_roles, stage_settings
from .errors import DuetError, LimitReached, ProcessLimitError
from .process import excerpt, run_process
from .schema import DEFAULT_SCHEMAS, load_schema, validate_schema

PROMPT_DIR = PLUGIN_ROOT / "prompts"


def build_prompt(role_prompt, sections):
    parts = [role_prompt.rstrip()]
    for title, text in sections:
        parts.append("\n\n## " + title + "\n\n" + text.rstrip())
    return "".join(parts) + "\n"


def effort_arg(effort):
    return 'model_reasoning_effort="%s"' % effort


def exec_argv(cwd, model, effort, schema_path, result_path):
    return ["codex", "exec", "-C", str(cwd), "-m", model, "-c", effort_arg(effort),
            "--sandbox", "read-only", "--json", "--output-schema", str(schema_path),
            "-o", str(result_path), "-"]


def resume_argv(session_id, model, effort, schema_path, result_path):
    return ["codex", "exec", "resume", session_id, "-m", model, "-c", effort_arg(effort),
            "-c", 'sandbox_mode="read-only"', "--json", "--output-schema", str(schema_path),
            "-o", str(result_path), "-"]


def parse_events(path):
    session_id, completed, failure = None, False, None
    with Path(path).open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if kind == "thread.started":
                session_id = event.get("thread_id")
            elif kind == "turn.completed":
                completed = True
            elif kind == "turn.failed":
                failure = str(event.get("error") or "turn.failed")
    return session_id, completed, failure


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DuetError("Cannot read %s: %s" % (path, exc)) from exc


def start_call(run, stage, cwd, prompt_file, context_files=(), schema=None, resume=None):
    """Reserve the attempt in the journal before anything runs; returns the journal event."""
    run = Path(run).resolve()
    cwd = Path(cwd).resolve()
    settings = stage_settings(load_roles(), stage)
    schema_name = schema or DEFAULT_SCHEMAS.get(stage)
    if schema_name is None:
        raise DuetError("No default schema for stage %s; pass --schema" % stage)
    load_schema(schema_name)
    role_prompt = read_text(PROMPT_DIR / (stage + ".md"))
    sections = [("Material", read_text(prompt_file))]
    sections += [("Context: " + Path(path).name, read_text(path)) for path in context_files]
    text = build_prompt(role_prompt, sections)
    tree = J.tree_state(cwd)

    def reserve(journal):
        limit = journal["limits"].get(stage, settings["limit"])
        attempt = J.attempts(journal, stage) + 1
        if attempt > limit:
            raise LimitReached("Limit reached for %s: %d calls per run. Only the user may raise it: "
                               "duet-codex limit --run %s --stage %s --set N" % (stage, limit, run, stage))
        prompt_name = "%s-%d.prompt.md" % (stage, attempt)
        (run / prompt_name).write_text(text, encoding="utf-8")
        entry = {
            "kind": "call", "stage": stage, "attempt": attempt, "provider": "codex",
            "model": settings["model"], "effort": settings["resume_effort"] if resume else settings["effort"],
            "schema": schema_name, "cwd": str(cwd), "prompt": prompt_name,
            "prompt_bytes": len(text.encode("utf-8")), "resume_of": resume, "session_id": None,
            "status": "running", "tree_before": tree, "tree_after": None, "tree_changed": None,
            "raw": "%s-%d.raw.md" % (stage, attempt), "result": None, "error": None, "returncode": None,
            "logs": None, "pid": None, "started_at": J.utc_now(), "finished_at": None,
            "n": len(journal["events"]) + 1, "at": J.utc_now()}
        journal["events"].append(entry)
        return entry
    return J.transact(run, reserve)


def perform_call(run, n):
    """Run the Codex call recorded as event n; always leaves a terminal status."""
    run = Path(run).resolve()
    event = J.load(run)["events"][n - 1]
    fields = {"status": "failed", "error": None, "session_id": None, "result": None, "returncode": None, "logs": None}
    try:
        roles = load_roles()
        schema = load_schema(event["schema"])
        schema_path = run / "logs" / (event["schema"] + ".schema.json")
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        raw_path = run / event["raw"]
        if event["resume_of"]:
            argv = resume_argv(event["resume_of"], event["model"], event["effort"], schema_path, raw_path)
        else:
            argv = exec_argv(event["cwd"], event["model"], event["effort"], schema_path, raw_path)
        prefix = run / "logs" / ("%s-%d" % (event["stage"], event["attempt"]))
        prompt = read_text(run / event["prompt"])
        try:
            outcome = run_process(argv, event["cwd"], prefix, roles["timeouts"]["call_seconds"], prompt,
                                  roles["limits"]["max_log_bytes"])
        except ProcessLimitError as exc:
            outcome = dict(exc.result, error=str(exc))
        fields["returncode"] = outcome["returncode"]
        fields["logs"] = {"stdout": outcome["stdout"], "stderr": outcome["stderr"]}
        session_id, completed, failure = parse_events(outcome["stdout"])
        fields["session_id"] = session_id or event["resume_of"]
        if outcome.get("error"):
            fields["error"] = outcome["error"]
        elif outcome["returncode"]:
            fields["error"] = "codex exited %s: %s" % (outcome["returncode"], excerpt(outcome["stderr"], 1500).strip())
        elif failure or not completed:
            fields["error"] = failure or "codex did not report a completed turn"
        elif not fields["session_id"]:
            fields["error"] = "codex did not report a session ID; this review could not be resumed"
        elif not raw_path.exists():
            fields["error"] = "codex produced no answer file"
        else:
            try:
                value = json.loads(raw_path.read_text(encoding="utf-8"))
                validate_schema(value, schema)
            except (ValueError, DuetError) as exc:
                fields.update(status="invalid", error="answer does not match schema %s: %s" % (event["schema"], exc))
            else:
                result = "%s-%d.json" % (event["stage"], event["attempt"])
                (run / result).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                fields.update(status="completed", result=result)
    except Exception as exc:  # any failure must still leave a terminal status in the journal
        fields.update(status="failed", error="%s: %s" % (type(exc).__name__, exc))
    try:
        tree_after = J.tree_state(event["cwd"])
    except DuetError as exc:
        tree_after = None
        fields["error"] = ((fields["error"] or "") + " | tree check failed: " + str(exc)).strip(" |")
    changed = tree_after != event["tree_before"]
    if fields["status"] == "completed" and changed:
        fields["status"] = "stale"
    return J.update(run, n, tree_after=tree_after, tree_changed=changed, finished_at=J.utc_now(), **fields)
