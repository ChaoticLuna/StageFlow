"""Access policy enforcement for file-level read/write control.

Evaluates stage ``access`` policies against requested file paths.
Deny rules take precedence over allow rules. Paths outside the
project root are always blocked.

Policy rules (per the Phase 39 acceptance criteria):

- No access policy → current behavior (all allowed)
- Section with only ``deny`` → everything except denied is allowed
- Section with ``allow`` → only matching paths are allowed
- Section with neither ``allow`` nor ``deny`` → no additional restriction
- Deny takes precedence over allow
- Unresolved ``{{var.key}}`` variables → pattern matches nothing
"""

from __future__ import annotations

import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

_VAR_PATTERN = re.compile(r"\{\{var\.(\w+)\}\}")

_SENTINEL_UNRESOLVED = "\x00SF_UNRESOLVED:"


def _interpolate(pattern: str, variables: dict | None) -> str:
    """Replace ``{{var.key}}`` placeholders in a pattern string.

    Unresolved variables produce a sentinel that never matches real paths.
    """
    if variables is None:
        variables = {}

    def _replacer(m):
        key = m.group(1)
        val = variables.get(key)
        if val is None:
            return _SENTINEL_UNRESOLVED + key + "\x00"
        return str(val)

    return _VAR_PATTERN.sub(_replacer, pattern)


def _normalize_path(requested_path: str, project_root: str) -> str | None:
    """Resolve a user-supplied path relative to *project_root*.

    Returns a normalized relative path (forward slashes) or ``None``
    when the resolved path escapes the project root.
    """
    root = Path(project_root).resolve()
    p = Path(requested_path)

    if p.is_absolute():
        try:
            p = p.resolve()
        except (OSError, ValueError):
            return None
    else:
        p = (root / p).resolve()

    try:
        p.relative_to(root)
    except ValueError:
        return None

    return str(p.relative_to(root)).replace(os.sep, "/")


def _glob_to_regex(pattern: str) -> str:
    """Compile a path glob (with ``**`` support) to an anchored regex string.

    ======== ============================
    Token    Matches
    ======== ============================
    ``**/``  zero or more path segments
    ``**``   everything (only at end)
    ``*``    any characters except ``/``
    ``?``    single character except ``/``
    ======== ============================
    """
    parts = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i : i + 2] == "**":
            if i + 2 >= n:
                parts.append(r".*")
                i += 2
            elif pattern[i + 2] == "/":
                parts.append(r"(?:[^/]*/)*")
                i += 3
            else:
                parts.append(r".*")
                i += 2
        elif pattern[i] == "*":
            parts.append(r"[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append(r"[^/]")
            i += 1
        else:
            c = pattern[i]
            if c in ".+^$()[]{}|\\":
                parts.append("\\" + c)
            else:
                parts.append(c)
            i += 1

    return "^" + "".join(parts) + "$"


def _match_glob(path: str, pattern: str) -> bool:
    """Return ``True`` if *path* matches *pattern*.

    Uses regex when the pattern contains ``**`` or ``/`` (multi-segment).
    Falls back to :func:`fnmatch` for simple single-segment (filename) globs
    where ``*`` should NOT cross directory boundaries anyway.
    """
    if _SENTINEL_UNRESOLVED in pattern:
        return False
    pattern_norm = pattern.replace("\\", "/")
    # Use regex for multi-segment patterns so * doesn't cross /
    if "**" in pattern_norm or "/" in pattern_norm:
        return bool(re.match(_glob_to_regex(pattern_norm), path))
    return fnmatch(path.rsplit("/", 1)[-1], pattern_norm)


class AccessPolicy:
    """Evaluates file access rules from a stage's ``access`` configuration."""

    def __init__(self, access_config: dict | None = None):
        self._config = access_config or {}

    @property
    def has_policy(self) -> bool:
        """True when any access sections are defined."""
        return bool(self._config)

    @property
    def has_read_policy(self) -> bool:
        """True when ``access.read`` is non-empty."""
        return bool(self._config.get("read"))

    @property
    def has_write_policy(self) -> bool:
        """True when ``access.write`` is non-empty."""
        return bool(self._config.get("write"))

    # ── public API ──────────────────────────────────────────────────────

    def check_read(self, requested_path: str, project_root: str,
                   variables: dict | None = None) -> tuple[bool, str]:
        """Evaluate *requested_path* against the ``read`` policy."""
        return self._check("read", requested_path, project_root, variables)

    def check_write(self, requested_path: str, project_root: str,
                    variables: dict | None = None) -> tuple[bool, str]:
        """Evaluate *requested_path* against the ``write`` policy."""
        return self._check("write", requested_path, project_root, variables)

    def check_search(self, search_root: str, project_root: str,
                     variables: dict | None = None) -> tuple[bool, str]:
        """Evaluate a directory search-root against the ``read`` policy.

        A search root is allowed only when the entire requested scope
        sits inside at least one allow pattern and does not intersect
        any deny pattern.  Because the engine cannot enumerate every
        file under the search root, it checks containment of the
        directory prefix itself.
        """
        return self._check_search("read", search_root, project_root, variables)

    # ── internal ────────────────────────────────────────────────────────

    def _check(self, operation: str, requested_path: str,
               project_root: str, variables: dict | None) -> tuple[bool, str]:
        section = self._config.get(operation)
        if not section:
            return True, ""

        normalized = _normalize_path(requested_path, project_root)
        if normalized is None:
            return False, (
                f"access.{operation}: '{requested_path}' escapes project root"
            )

        allow_patterns = [_interpolate(p, variables)
                          for p in section.get("allow", [])]
        deny_patterns = [_interpolate(p, variables)
                         for p in section.get("deny", [])]

        for pat in deny_patterns:
            if _match_glob(normalized, pat):
                return False, (
                    f"access.{operation}: '{requested_path}' denied by '{pat}'"
                )

        allow_list = section.get("allow", [])
        if allow_list:
            for pat in allow_patterns:
                if _match_glob(normalized, pat):
                    return True, ""
            return False, (
                f"access.{operation}: '{requested_path}' not in allow list"
            )

        return True, ""

    def _check_search(self, operation: str, search_root: str,
                      project_root: str, variables: dict | None) -> tuple[bool, str]:
        section = self._config.get(operation)
        if not section:
            return True, ""

        normalized = _normalize_path(search_root, project_root)
        if normalized is None:
            return False, (
                f"access.{operation}: search root '{search_root}' escapes project root"
            )

        allow_patterns = [_interpolate(p, variables)
                          for p in section.get("allow", [])]
        deny_patterns = [_interpolate(p, variables)
                         for p in section.get("deny", [])]

        # If a deny pattern may match anything inside the search scope, block.
        for pat in deny_patterns:
            if _pattern_intersects_dir(pat, normalized):
                return False, (
                    f"access.{operation}: search root '{search_root}' "
                    f"intersects denied pattern '{pat}'"
                )

        allow_list = section.get("allow", [])
        if allow_list:
            for pat in allow_patterns:
                if _pattern_covers_dir(pat, normalized):
                    return True, ""
            return False, (
                f"access.{operation}: search root '{search_root}' "
                f"not covered by any allow pattern"
            )

        return True, ""


def _pattern_prefix(pattern: str) -> str:
    """Return the literal prefix of a glob pattern, stripping wildcards."""
    cleaned = pattern.replace("\\", "/")
    cleaned = re.sub(r"\*\*/?", "", cleaned)
    cleaned = re.sub(r"[*?]", "", cleaned)
    cleaned = re.sub(r"\x00SF_UNRESOLVED:\w+\x00", "UNRESOLVED_VAR", cleaned)
    return cleaned.rstrip("/")


def _pattern_covers_dir(pattern: str, dir_path: str) -> bool:
    """Return True if *pattern* covers *every* file under *dir_path*.

    Conservative: only returns True when the pattern's scope is a
    superset of the directory scope. Single-segment patterns (no ``/``,
    no ``**``) can never cover a directory because they don't guarantee
    that all files under that directory would match.
    """
    if _SENTINEL_UNRESOLVED in pattern:
        return False

    pattern_norm = pattern.replace("\\", "/")
    prefix = _pattern_prefix(pattern)

    # Dir is under the pattern's literal prefix → covered
    if prefix:
        if dir_path == prefix:
            return True
        if dir_path.startswith(prefix + "/"):
            return True

    # Pattern prefix is inside dir → pattern is narrower, not covering all
    if prefix and prefix.startswith(dir_path + "/"):
        return False

    # Dir_path also covered if pattern covers everything via **
    if pattern_norm.endswith("**"):
        base = pattern_norm[: -2].rstrip("/")
        if base == dir_path or dir_path.startswith(base + "/"):
            return True

    # Match dir_path directly against pattern (e.g., exact match pattern)
    if _match_glob(dir_path, pattern_norm):
        return True

    return False


def _pattern_intersects_dir(pattern: str, dir_path: str) -> bool:
    """Return True if *pattern* may match any path under *dir_path*.

    Used for deny rules on search roots. This is intentionally conservative:
    if a deny pattern could apply somewhere inside the requested search scope,
    the search is blocked unless the caller narrows the search root.
    """
    if _SENTINEL_UNRESOLVED in pattern:
        return False

    pattern_norm = pattern.replace("\\", "/")
    prefix = _pattern_prefix(pattern_norm)
    root_dir = dir_path in ("", ".")

    # Single-segment deny patterns such as "*.env" may match a file anywhere
    # below the requested directory, so a directory search cannot prove safety.
    if "/" not in pattern_norm:
        return True

    if root_dir:
        return True

    if prefix:
        if prefix == dir_path:
            return True
        if prefix.startswith(dir_path + "/"):
            return True
        if dir_path.startswith(prefix + "/"):
            return True

    return _match_glob(dir_path, pattern_norm)
