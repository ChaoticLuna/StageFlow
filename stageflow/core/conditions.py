"""Pluggable condition system. Each condition type is a callable that receives
params and returns (passed: bool, message: str).

Register custom conditions via:
    from stageflow.core.conditions import register, Condition

    @register("my_check")
    def my_check(params: dict) -> tuple[bool, str]:
        ...

Caching:
    Conditions are cached with a TTL (default 30s). The cache is keyed by
    (hash of conditions, base_path). This prevents re-evaluating the same
    expensive conditions (shell_test, http_status, etc.) in rapid succession.
    Pass cache_ttl=0 to disable caching.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

# Registry of condition evaluators: name -> callable(params) -> (bool, message)
_CONDITION_REGISTRY: Dict[str, Callable[[dict], Tuple[bool, str]]] = {}

# Condition cache: key -> (result, timestamp)
_CONDITION_CACHE: Dict[str, Tuple[Tuple[bool, list[str]], float]] = {}
_CACHE_TTL = 30.0  # seconds


def set_cache_ttl(ttl: float):
    """Set the condition cache TTL in seconds. 0 = disable caching."""
    global _CACHE_TTL
    _CACHE_TTL = max(0, ttl)


def clear_cache():
    """Clear the condition evaluation cache."""
    global _CONDITION_CACHE
    _CONDITION_CACHE.clear()


def _cache_key(conditions: list[dict], base_path: str, variables: dict = None) -> str:
    """Generate a cache key from conditions, base path, and optional variables."""
    raw = json.dumps(conditions, sort_keys=True, default=str) + "|" + base_path
    if variables:
        raw += "|" + json.dumps(variables, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


_VAR_PATTERN = re.compile(r"\{\{var\.(\w+)\}\}")


def _resolve_vars(value: Any, variables: dict) -> Any:
    """Recursively resolve {{var.key}} patterns in string values."""
    if variables is None or not variables:
        return value
    if isinstance(value, str):
        def _replacer(m):
            key = m.group(1)
            return str(variables.get(key, m.group(0)))
        return _VAR_PATTERN.sub(_replacer, value)
    elif isinstance(value, dict):
        return {k: _resolve_vars(v, variables) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_vars(item, variables) for item in value]
    return value


def register(name: str):
    """Decorator to register a condition evaluator function."""
    def decorator(fn: Callable[[dict], Tuple[bool, str]]):
        _CONDITION_REGISTRY[name] = fn
        return fn
    return decorator


def evaluate(name: str, params: dict) -> Tuple[bool, str]:
    """Evaluate a condition by name with given params. Returns (passed, message)."""
    if name not in _CONDITION_REGISTRY:
        return False, f"Unknown condition type: {name}"
    return _CONDITION_REGISTRY[name](params)


def evaluate_all(conditions: list[dict], base_path: str = ".",
                 cache_ttl: Optional[float] = None,
                 variables: dict = None,
                 timeout: Optional[float] = None) -> Tuple[bool, list[str]]:
    """Evaluate a list of conditions. Returns (all_passed, messages).

    Results are cached by (conditions, base_path, variables) hash for configurable TTL.
    Pass cache_ttl=0 to disable caching for this call.
    Pass timeout (seconds) to fail gracefully if evaluation takes too long.

    String parameter values may contain {{var.key}} patterns that are resolved
    against the `variables` dict (e.g., from StateMachine's variable store).
    """
    if not conditions:
        return True, []

    # Resolve variables in conditions before caching
    if variables:
        conditions = _resolve_vars(conditions, variables)

    # Check cache — compute key once before evaluation so that mutations
    # inside handlers (e.g. any_of calling setdefault on sub-condition params)
    # don't cause key drift between lookup and storage.
    ttl = cache_ttl if cache_ttl is not None else _CACHE_TTL
    cache_key = None
    if ttl > 0:
        cache_key = _cache_key(conditions, base_path, variables)
        if cache_key in _CONDITION_CACHE:
            result, timestamp = _CONDITION_CACHE[cache_key]
            if time.time() - timestamp < ttl:
                return result

    if timeout and timeout > 0:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _evaluate_loop, conditions, base_path, ttl, cache_key
            )
            try:
                return future.result(timeout=timeout)
            except TimeoutError:
                result = (False, [f"[TIMEOUT] Condition evaluation exceeded {timeout}s"])
                if cache_key:
                    _CONDITION_CACHE[cache_key] = (result, time.time())
                return result

    return _evaluate_loop(conditions, base_path, ttl, cache_key)


def _evaluate_loop(conditions, base_path, ttl, cache_key):
    """Core condition evaluation loop. Extracted for timeout support."""
    messages = []
    for cond in conditions:
        severity = _get_severity(cond)
        cond_type, cond_params = _parse_condition(cond)
        if not isinstance(cond_params, dict):
            cond_params = {"value": cond_params}
        else:
            cond_params = dict(cond_params)
        cond_params.setdefault("base_path", base_path)
        passed, msg = evaluate(cond_type, cond_params)

        if severity == "warn":
            tag = "PASS" if passed else "WARN"
            messages.append(f"[{tag}] {cond_type}: {msg}")
        elif not passed:
            tag = "HARD_FAIL" if severity == "hard" else "FAIL"
            messages.append(f"[{tag}] {cond_type}: {msg}")
            result = (False, messages)
            if ttl > 0 and cache_key:
                _CONDITION_CACHE[cache_key] = (result, time.time())
            return result
        else:
            messages.append(f"[PASS] {cond_type}: {msg}")

    result = (True, messages)
    if ttl > 0 and cache_key:
        _CONDITION_CACHE[cache_key] = (result, time.time())
    return result


def list_conditions() -> list[str]:
    """Return names of all registered conditions."""
    return sorted(_CONDITION_REGISTRY.keys())


def _parse_condition(cond: dict) -> Tuple[str, dict]:
    """Parse a condition dict like {'file_exists': 'path/to/file'} or
    {'json_field': {'path': '...', 'field': '...', 'op': 'not_empty'}}.
    Returns (condition_type, params_dict)."""
    known_keys = set()
    for key in cond:
        if key not in ("severity", "max_attempts"):
            name = key
            break
    else:
        raise ValueError("Condition dict has no recognized type key")
    params = cond[name]
    if not isinstance(params, dict):
        params = {"value": params}
    return name, params


def _get_severity(cond: dict) -> str:
    return cond.get("severity", "soft")


# ─────────────────────────── Built-in Conditions ───────────────────────────


@register("file_exists")
def _file_exists(params: dict) -> Tuple[bool, str]:
    path = Path(params["base_path"]) / params.get("path", params.get("value", ""))
    ok = path.exists()
    return ok, f"File {'exists' if ok else 'not found'}: {path}"


@register("file_not_exists")
def _file_not_exists(params: dict) -> Tuple[bool, str]:
    path = Path(params["base_path"]) / params.get("path", params.get("value", ""))
    ok = not path.exists()
    return ok, f"File {'absent (ok)' if ok else 'exists (unwanted)'}: {path}"


@register("file_contains")
def _file_contains(params: dict) -> Tuple[bool, str]:
    path = Path(params["base_path"]) / params["path"]
    pattern = params.get("pattern", params.get("value", ""))
    if not path.exists():
        return False, f"File not found: {path}"
    content = path.read_text(encoding="utf-8", errors="ignore")
    ok = bool(re.search(pattern, content, re.MULTILINE | re.DOTALL))
    return ok, f"Pattern {'found' if ok else 'not found'} in {path}: {pattern}"


@register("file_not_contains")
def _file_not_contains(params: dict) -> Tuple[bool, str]:
    path = Path(params["base_path"]) / params["path"]
    pattern = params.get("pattern", params.get("value", ""))
    if not path.exists():
        return False, f"File not found: {path}"
    content = path.read_text(encoding="utf-8", errors="ignore")
    ok = not bool(re.search(pattern, content, re.MULTILINE | re.DOTALL))
    return ok, f"Pattern {'absent (ok)' if ok else 'found (unwanted)'} in {path}"


@register("json_field")
def _json_field(params: dict) -> Tuple[bool, str]:
    path = Path(params["base_path"]) / params["path"]
    field = params["field"]
    op = params.get("op", "exists")
    expected = params.get("value")

    if not path.exists():
        return False, f"File not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in {path}: {e}"

    # Navigate nested fields: "a.b.c"
    obj = data
    for part in field.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return False, f"Cannot navigate field '{part}' in non-dict value"

    if op == "exists":
        ok = obj is not None
        return ok, f"Field '{field}' {'exists' if ok else 'missing'} in {path}"
    elif op == "not_empty":
        ok = obj is not None and obj != "" and obj != [] and obj != {}
        return ok, f"Field '{field}' {'not empty' if ok else 'empty/missing'} in {path}"
    elif op == "equals":
        ok = obj == expected
        return ok, f"Field '{field}' == {expected!r}: {ok} (got {obj!r})"
    elif op == "not_equals":
        ok = obj != expected
        return ok, f"Field '{field}' != {expected!r}: {ok} (got {obj!r})"
    elif op == "gt":
        ok = float(obj) > float(expected)
        return ok, f"Field '{field}' > {expected}: {ok} (got {obj})"
    elif op == "lt":
        ok = float(obj) < float(expected)
        return ok, f"Field '{field}' < {expected}: {ok} (got {obj})"
    elif op == "in":
        ok = expected in obj
        return ok, f"'{expected}' in '{field}': {ok}"
    elif op == "matches":
        ok = bool(re.search(str(expected), str(obj)))
        return ok, f"Field '{field}' matches /{expected}/: {ok}"
    else:
        return False, f"Unknown op: {op}"


@register("yaml_field")
def _yaml_field(params: dict) -> Tuple[bool, str]:
    try:
        import yaml
    except ImportError:
        return False, "PyYAML not installed; cannot evaluate yaml_field"

    path = Path(params["base_path"]) / params["path"]
    field = params["field"]
    op = params.get("op", "exists")
    expected = params.get("value")

    if not path.exists():
        return False, f"File not found: {path}"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Invalid YAML in {path}: {e}"

    obj = data
    for part in field.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return False, f"Cannot navigate field '{part}'"

    if op == "exists":
        ok = obj is not None
        return ok, f"Field '{field}' {'exists' if ok else 'missing'} in {path}"
    elif op == "not_empty":
        ok = obj is not None and obj != "" and obj != [] and obj != {}
        return ok, f"Field '{field}' {'not empty' if ok else 'empty/missing'} in {path}"
    elif op == "equals":
        ok = obj == expected
        return ok, f"Field '{field}' == {expected!r}: {ok}"
    else:
        return False, f"Unknown op: {op}"


@register("shell_test")
def _shell_test(params: dict) -> Tuple[bool, str]:
    command = params.get("command", params.get("value", ""))
    op = params.get("op", "exit_zero")
    expected = params.get("value")
    stream = params.get("stream", "stdout")

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30,
            cwd=params.get("base_path", ".")
        )
    except subprocess.TimeoutExpired:
        return False, f"Shell command timed out: {command}"
    except Exception as e:
        return False, f"Shell command error: {e}"

    output = (result.stderr if stream == "stderr" else result.stdout).strip()

    if op == "exit_zero":
        ok = result.returncode == 0
        return ok, f"Command exited {'0' if ok else result.returncode}: {command}"
    elif op == "stdout_contains":
        ok = str(expected) in output
        return ok, f"stdout contains '{expected}' : {ok}"
    elif op == "stdout_not_empty":
        ok = bool(output)
        return ok, f"stdout not empty: {ok}"
    elif op == "stdout_matches":
        try:
            ok = bool(re.search(str(expected), output))
        except re.error as e:
            return False, f"Regex error: {e}"
        return ok, f"stdout matches /{expected}/: {ok}"
    elif op == "gt":
        try:
            ok = float(output) > float(expected)
        except ValueError:
            ok = False
        return ok, f"stdout({output}) > {expected}: {ok}"
    elif op == "lt":
        try:
            ok = float(output) < float(expected)
        except ValueError:
            ok = False
        return ok, f"stdout({output}) < {expected}: {ok}"
    elif op == "eq":
        try:
            ok = float(output) == float(expected)
        except ValueError:
            ok = False
        return ok, f"stdout({output}) == {expected}: {ok}"
    else:
        return False, f"Unknown op: {op}"


@register("python_expr")
def _python_expr(params: dict) -> Tuple[bool, str]:
    expr = params.get("expr", params.get("value", ""))
    ctx = params.get("context", {})
    base_path = params.get("base_path", ".")

    safe_builtins = {
        "True": True, "False": False, "None": None,
        "int": int, "float": float, "str": str, "bool": bool,
        "len": len, "abs": abs, "min": min, "max": max,
        "sum": sum, "any": any, "all": all,
        "Path": Path, "os": os, "base_path": base_path,
    }
    safe_builtins.update(ctx)

    try:
        result = eval(expr, {"__builtins__": {}}, {**safe_builtins, **ctx})
        ok = bool(result)
        return ok, f"Python expr '{expr}' => {result!r} ({ok})"
    except Exception as e:
        return False, f"Python expr error: {e}"


@register("env_var")
def _env_var(params: dict) -> Tuple[bool, str]:
    name = params.get("name", params.get("value", ""))
    op = params.get("op", "exists")
    expected = params.get("value")
    val = os.environ.get(name)

    if op == "exists":
        ok = val is not None
        return ok, f"Env var '{name}' {'exists' if ok else 'not set'}"
    elif op == "equals":
        ok = val == str(expected)
        return ok, f"Env var '{name}' == {expected!r}: {ok}"
    elif op == "not_empty":
        ok = bool(val)
        return ok, f"Env var '{name}' not empty: {ok}"
    else:
        return False, f"Unknown op: {op}"


@register("all_of")
def _all_of(params: dict) -> Tuple[bool, str]:
    sub = params.get("conditions", params.get("value", []))
    ok, msgs = evaluate_all(sub, params.get("base_path", "."))
    return ok, f"All {len(sub)} conditions: {'PASS' if ok else 'FAIL'} " + "; ".join(msgs)


@register("any_of")
def _any_of(params: dict) -> Tuple[bool, str]:
    sub = params.get("conditions", params.get("value", []))
    base_path = params.get("base_path", ".")
    for cond in sub:
        cond_type, cond_params = _parse_condition(cond)
        cond_params = dict(cond_params) if isinstance(cond_params, dict) else {"value": cond_params}
        cond_params.setdefault("base_path", base_path)
        passed, msg = evaluate(cond_type, cond_params)
        if passed:
            return True, f"Any condition passed: {cond_type}: {msg}"
    return False, f"None of {len(sub)} conditions passed"


@register("not")
def _not(params: dict) -> Tuple[bool, str]:
    sub = params.get("condition", params.get("value", {}))
    cond_type, cond_params = _parse_condition(sub)
    if not isinstance(cond_params, dict):
        cond_params = {"value": cond_params}
    cond_params.setdefault("base_path", params.get("base_path", "."))
    passed, msg = evaluate(cond_type, cond_params)
    return not passed, f"NOT({cond_type}: {msg}) => {not passed}"


@register("always")
def _always(params: dict) -> Tuple[bool, str]:
    return True, "Always passes"


@register("never")
def _never(params: dict) -> Tuple[bool, str]:
    reason = params.get("reason", params.get("value", "Blocked"))
    return False, f"Always fails: {reason}"


@register("git_status")
def _git_status(params: dict) -> Tuple[bool, str]:
    """Check git working tree status.
    ops: clean, dirty, files_changed (count), branch (matches)
    """
    op = params.get("op", "clean")
    expected = params.get("value")
    base_path = params.get("base_path", ".")

    try:
        import subprocess
        if op == "clean":
            r = subprocess.run("git status --porcelain", shell=True,
                               capture_output=True, text=True, cwd=base_path, timeout=10)
            ok = r.stdout.strip() == ""
            return ok, f"Git working tree {'clean' if ok else 'dirty'}"
        elif op == "files_changed":
            r = subprocess.run("git diff --name-only HEAD", shell=True,
                               capture_output=True, text=True, cwd=base_path, timeout=10)
            count = len([l for l in r.stdout.strip().split("\n") if l])
            if expected is not None:
                ok = count >= int(expected)
                return ok, f"Files changed: {count} >= {expected}: {ok}"
            ok = count > 0
            return ok, f"Files changed: {count}"
        elif op == "branch":
            r = subprocess.run("git branch --show-current", shell=True,
                               capture_output=True, text=True, cwd=base_path, timeout=10)
            branch = r.stdout.strip()
            ok = branch == str(expected)
            return ok, f"Git branch '{branch}' == '{expected}': {ok}"
        elif op == "has_commits":
            r = subprocess.run("git rev-list --count HEAD..@{u} || echo 0",
                               shell=True, capture_output=True, text=True,
                               cwd=base_path, timeout=10)
            count = int(r.stdout.strip() or 0)
            ok = count > 0
            return ok, f"Unpushed commits: {count}"
        else:
            return False, f"Unknown git op: {op}"
    except Exception as e:
        return False, f"Git command error: {e}"


@register("http_status")
def _http_status(params: dict) -> Tuple[bool, str]:
    """Check HTTP endpoint status code or response body content."""
    url = params.get("url", params.get("value", ""))
    op = params.get("op", "status")
    expected = params.get("expected", 200)
    timeout = params.get("timeout", 10)
    method = params.get("method", "GET")

    try:
        import urllib.request
        req = urllib.request.Request(url, method=method)
        resp = urllib.request.urlopen(req, timeout=timeout)
        if op == "body_contains":
            body = resp.read().decode("utf-8", errors="replace")
            pattern = str(params.get("pattern", params.get("value", "")))
            ok = pattern in body
            return ok, f"HTTP {url} body contains '{pattern[:80]}': {ok}"
        if op == "header_equals":
            header = str(params.get("header", ""))
            expected_val = str(params.get("expected", params.get("value", "")))
            actual_val = resp.getheader(header)
            ok = actual_val == expected_val
            return ok, f"HTTP {url} header '{header}' == '{expected_val}': {ok} (actual: {actual_val!r})"
        ok = resp.status == expected
        return ok, f"HTTP {url} -> {resp.status} (expected {expected})"
    except Exception as e:
        return False, f"HTTP error for {url}: {e}"


@register("time_range")
def _time_range(params: dict) -> Tuple[bool, str]:
    """Check if current time is within a range.
    Example: {time_range: {after: "09:00", before: "17:00", tz: "Asia/Shanghai"}}
    """
    after = params.get("after")
    before = params.get("before")
    tz_name = params.get("tz", "UTC")

    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = None

    now = datetime.now(tz)
    if after:
        h, m = map(int, after.split(":"))
        if now.hour < h or (now.hour == h and now.minute < m):
            return False, f"Current time {now.strftime('%H:%M')} is before {after}"
    if before:
        h, m = map(int, before.split(":"))
        if now.hour > h or (now.hour == h and now.minute > m):
            return False, f"Current time {now.strftime('%H:%M')} is after {before}"
    return True, f"Current time {now.strftime('%H:%M')} is within [{after}, {before}]"


@register("compare_files")
def _compare_files(params: dict) -> Tuple[bool, str]:
    """Compare two files and check if they are identical or different."""
    path1 = Path(params["base_path"]) / params["path1"]
    path2 = Path(params["base_path"]) / params.get("path2", params.get("value", ""))
    op = params.get("op", "identical")

    if not path1.exists():
        return False, f"File not found: {path1}"
    if not path2.exists():
        return False, f"File not found: {path2}"

    c1 = path1.read_text(encoding="utf-8", errors="ignore")
    c2 = path2.read_text(encoding="utf-8", errors="ignore")

    if op == "identical":
        ok = c1 == c2
        return ok, f"Files {'identical' if ok else 'different'}"
    elif op == "different":
        ok = c1 != c2
        return ok, f"Files {'different' if ok else 'identical'}"
    else:
        return False, f"Unknown op: {op}"


@register("json_schema")
def _json_schema(params: dict) -> Tuple[bool, str]:
    """Validate a JSON file against a JSON Schema (requires jsonschema).

    Example: {json_schema: {path: data.json, schema_path: schema.json}}
    Without schema_path: just checks the file is valid JSON.
    """
    path = Path(params["base_path"]) / params["path"]
    schema_path = params.get("schema_path")
    if schema_path:
        schema_path = Path(params["base_path"]) / schema_path

    if not path.exists():
        return False, f"File not found: {path}"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in {path}: {e}"

    if schema_path:
        if not schema_path.exists():
            return False, f"Schema file not found: {schema_path}"
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON Schema: {e}"

        try:
            import jsonschema
            jsonschema.validate(data, schema)
            return True, f"JSON {path} valid against schema {schema_path}"
        except ImportError:
            return True, ("JSON is valid, but jsonschema not installed "
                          "(no schema validation performed)")
        except Exception as e:
            return False, f"Schema validation error: {e}"

    return True, f"JSON {path} is valid"


@register("hash_file")
def _hash_file(params: dict) -> Tuple[bool, str]:
    """Compute file hash, optionally compare to expected value.

    Example: {hash_file: {path: artifact.zip, expected: abc123, algo: sha256}}
    """
    path = Path(params["base_path"]) / params["path"]
    expected = params.get("expected", params.get("value", ""))
    algo = params.get("algo", "sha256")

    if not path.exists():
        return False, f"File not found: {path}"

    h = hashlib.new(algo)
    h.update(path.read_bytes())
    actual = h.hexdigest()

    if expected:
        ok = actual == expected
        return ok, f"Hash({algo}) {'matches' if ok else 'differs'} for {path}"
    return True, f"Hash({algo}) for {path}: {actual[:16]}..."


@register("file_age")
def _file_age(params: dict) -> Tuple[bool, str]:
    """Check if a file's modification time is within a threshold.

    Example: {file_age: {path: output.log, max_age: 300}}  # modified within 5 min
    Example: {file_age: {path: output.log, min_age: 60}}   # at least 1 min old
    """
    path = Path(params["base_path"]) / params["path"]
    max_age = params.get("max_age")  # seconds — file must be newer than this
    min_age = params.get("min_age")  # seconds — file must be older than this

    if not path.exists():
        return False, f"File not found: {path}"

    mtime = path.stat().st_mtime
    age = time.time() - mtime

    if max_age is not None:
        if age > float(max_age):
            return False, f"File age {age:.0f}s > max {max_age}s: {path}"
    if min_age is not None:
        if age < float(min_age):
            return False, f"File age {age:.0f}s < min {min_age}s: {path}"
    return True, f"File age {age:.0f}s within bounds for {path}"


@register("file_size")
def _file_size(params: dict) -> Tuple[bool, str]:
    """Check file size in bytes with optional min/max bounds.

    Example: {file_size: {path: data.csv, min: 100}}    # at least 100 bytes
    Example: {file_size: {path: log.txt, max: 1048576}}  # no larger than 1 MB
    """
    path = Path(params["base_path"]) / params["path"]
    min_size = params.get("min")
    max_size = params.get("max")

    if not path.exists():
        return False, f"File not found: {path}"

    size = path.stat().st_size

    if min_size is not None:
        if size < int(min_size):
            return False, f"File size {size} < min {min_size}: {path}"
    if max_size is not None:
        if size > int(max_size):
            return False, f"File size {size} > max {max_size}: {path}"
    return True, f"File size {size} bytes within bounds for {path}"


@register("glob_count")
def _glob_count(params: dict) -> Tuple[bool, str]:
    """Count files matching a glob pattern and check against expected count.

    Example: {glob_count: {pattern: "**/*.py", min: 5}}      # at least 5 Python files
    Example: {glob_count: {pattern: "*.log", max: 0}}        # no log files
    Example: {glob_count: {pattern: "**/*.md", eq: 3}}       # exactly 3 markdown files
    """
    pattern = params.get("pattern", params.get("value", "**/*"))
    base_path = Path(params["base_path"])
    min_count = params.get("min")
    max_count = params.get("max")
    eq = params.get("eq")

    matches = list(base_path.glob(pattern))
    count = len(matches)

    if eq is not None:
        ok = count == int(eq)
        return ok, f"Glob '{pattern}' matched {count} files (expected {eq}): {ok}"
    if min_count is not None:
        if count < int(min_count):
            return False, f"Glob '{pattern}' matched {count} files < min {min_count}"
    if max_count is not None:
        if count > int(max_count):
            return False, f"Glob '{pattern}' matched {count} files > max {max_count}"
    return True, f"Glob '{pattern}' matched {count} files"


@register("retry")
def _retry(params: dict) -> Tuple[bool, str]:
    """Retry a sub-condition up to max_attempts times with a delay.

    Example: {retry: {condition: {file_exists: output.txt}, max_attempts: 12, delay: 5}}
    This retries the file_exists check every 5 seconds, up to 12 times (60s total).
    """
    sub = params.get("condition", params.get("value", {}))
    max_attempts = int(params.get("max_attempts", 3))
    delay = float(params.get("delay", 1.0))
    base_path = params.get("base_path", ".")

    cond_type, cond_params = _parse_condition(sub)
    if not isinstance(cond_params, dict):
        cond_params = {"value": cond_params}
    cond_params.setdefault("base_path", base_path)

    last_msg = ""
    for attempt in range(1, max_attempts + 1):
        passed, msg = evaluate(cond_type, cond_params)
        last_msg = msg
        if passed:
            return True, f"Retry(attempt {attempt}/{max_attempts}): {msg}"
        if attempt < max_attempts:
            time.sleep(delay)

    return False, f"Retry exhausted ({max_attempts} attempts): {last_msg}"


@register("command_exists")
def _command_exists(params: dict) -> Tuple[bool, str]:
    """Check if a CLI command is available on the system PATH.

    Example: {command_exists: "pytest"}
    Example: {command_exists: {command: "docker", op: "exists"}}
    """
    command = params.get("command", params.get("value", ""))
    op = params.get("op", "exists")

    import shutil
    if op == "exists":
        found = shutil.which(command) is not None
        return found, f"Command '{command}' {'found' if found else 'not found'} on PATH"
    elif op == "version":
        # Check command exists and can produce version output
        if shutil.which(command) is None:
            return False, f"Command '{command}' not found on PATH"
        try:
            r = subprocess.run(f"{command} --version", shell=True,
                               capture_output=True, text=True, timeout=10)
            ok = r.returncode == 0
            version = (r.stdout or r.stderr).strip().split("\n")[0]
            return ok, f"Command '{command}' version: {version[:80]}"
        except Exception as e:
            return False, f"Command '{command}' version check failed: {e}"
    else:
        return False, f"Unknown op: {op}"


@register("diff_contains")
def _diff_contains(params: dict) -> Tuple[bool, str]:
    """Check if git diff (staged + unstaged) contains or excludes specific patterns.
    Critical AI safety gate: detect dangerous code patterns before merging.

    ops:
      - contains: diff must include the pattern (fail if missing)
      - not_contains: diff must NOT include the pattern (fail if found — safety gate)

    Example: {diff_contains: {pattern: "eval\\(", op: not_contains}}
    Example: {diff_contains: {pattern: "TODO", op: contains}}
    """
    pattern = params.get("pattern", params.get("value", ""))
    op = params.get("op", "not_contains")
    base_path = params.get("base_path", ".")
    staged_only = params.get("staged_only", False)

    try:
        if staged_only:
            cmd = "git diff --cached 2>&1"
            label = "staged diff"
        else:
            cmd = "git diff HEAD 2>&1"
            label = "diff"

        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           cwd=base_path, timeout=30)
        diff_text = r.stdout + r.stderr

        found = bool(re.search(pattern, diff_text, re.MULTILINE | re.DOTALL))

        if op == "contains":
            return found, f"Pattern {'found' if found else 'not found'} in {label}: {pattern}"
        elif op == "not_contains":
            ok = not found
            return ok, f"Pattern {'absent (ok)' if ok else 'found (BLOCKED)'} in {label}: {pattern}"
        else:
            return False, f"Unknown op: {op}"
    except Exception as e:
        return False, f"Git diff error: {e}"


@register("json_count")
def _json_count(params: dict) -> Tuple[bool, str]:
    """Count items in a JSON array or keys in a JSON object. Check against bounds.

    Example: {json_count: {path: test_results.json, min: 5}}       # at least 5 items
    Example: {json_count: {path: coverage.json, field: files, eq: 10}}

    If `field` is provided, navigates to that field (dot-separated) and counts its contents.
    """
    path = Path(params["base_path"]) / params["path"]
    field = params.get("field")
    min_count = params.get("min")
    max_count = params.get("max")
    eq = params.get("eq")

    if not path.exists():
        return False, f"File not found: {path}"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON in {path}: {e}"

    obj = data
    if field:
        for part in field.split("."):
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif isinstance(obj, list):
                try:
                    obj = obj[int(part)]
                except (IndexError, ValueError):
                    return False, f"Cannot index into list with '{part}'"
            else:
                return False, f"Cannot navigate field '{part}' in {type(obj).__name__}"

    if isinstance(obj, list):
        count = len(obj)
    elif isinstance(obj, dict):
        count = len(obj)
    elif isinstance(obj, str):
        count = len(obj)
    else:
        count = 1 if obj is not None else 0

    if eq is not None:
        ok = count == int(eq)
        return ok, f"JSON count {count} == {eq}: {ok} for {path}"
    if min_count is not None:
        if count < int(min_count):
            return False, f"JSON count {count} < min {min_count} for {path}"
    if max_count is not None:
        if count > int(max_count):
            return False, f"JSON count {count} > max {max_count} for {path}"
    return True, f"JSON count {count} within bounds for {path}"


# ═══════════════════════════════════════════════════════════════════════════
# Runtime / system conditions
# ═══════════════════════════════════════════════════════════════════════════

@register("port_open")
def _port_open(params: dict) -> Tuple[bool, str]:
    """Check if a TCP port is listening.

    Params:
        port: Port number (required).
        host: Host to connect to (default "127.0.0.1").
        timeout: Connection timeout in seconds (default 2.0).
    """
    port = int(params.get("port", params.get("value", 0)))
    host = str(params.get("host", "127.0.0.1"))
    timeout = float(params.get("timeout", 2.0))
    if port <= 0:
        return False, f"Invalid port: {port}"
    import socket
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True, f"Port {host}:{port} is open"
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return False, f"Port {host}:{port} is closed ({e})"


@register("process_running")
def _process_running(params: dict) -> Tuple[bool, str]:
    """Check if a process is running by name or command line pattern.

    Params:
        name: Process name substring to search for (required).
    """
    name = str(params.get("name", params.get("value", "")))
    if not name:
        return False, "No process name specified"
    try:
        import psutil
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                info = proc.info
                if name.lower() in (info["name"] or "").lower():
                    return True, f"Process '{name}' found (name match: {info['name']})"
                cmdline = " ".join(info["cmdline"] or [])
                if name.lower() in cmdline.lower():
                    return True, f"Process '{name}' found (cmdline match)"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False, f"Process '{name}' not found"
    except ImportError:
        # Fallback: Windows tasklist or Unix ps
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/fo", "csv", "/nh"],
                    capture_output=True, text=True, timeout=10,
                )
                if name.lower() in result.stdout.lower():
                    return True, f"Process '{name}' found via tasklist"
            else:
                result = subprocess.run(
                    ["ps", "aux"], capture_output=True, text=True, timeout=10,
                )
                if name.lower() in result.stdout.lower():
                    return True, f"Process '{name}' found via ps"
            return False, f"Process '{name}' not found"
        except Exception as e:
            return False, f"Process check failed: {e}"


@register("docker_ps")
def _docker_ps(params: dict) -> Tuple[bool, str]:
    """Check if a Docker container is running by name.

    Params:
        name: Container name substring to match (required).
    """
    name = str(params.get("name", params.get("value", "")))
    if not name:
        return False, "No container name specified"
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        return False, "Docker is not installed or not in PATH"
    except Exception as e:
        return False, f"Docker check failed: {e}"

    container_names = result.stdout.strip().split("\n")
    for cname in container_names:
        if name in cname.strip():
            return True, f"Docker container '{cname.strip()}' is running"
    return False, f"No running container matching '{name}'"
