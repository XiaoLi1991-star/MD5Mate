"""File filter parsing and matching."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

ALL_FILE_LABELS = {"*", "*.*", "all", "all files", "所有文件", "全部文件"}


def parse_filter_text(filter_text: str | None) -> list[str]:
    """Convert desktop filter text into fnmatch patterns.

    Supported inputs:
    - empty, "*" or "所有文件 (*)"
    - ".txt,.log" or "txt,log"
    - "*.py;*.md"
    - labels such as "文本文件 (*.txt,*.log,*.md)"
    """

    text = (filter_text or "").strip()
    if not text:
        return ["*"]

    inner = _extract_parenthesized_patterns(text)
    if inner:
        text = inner

    normalized = text.strip().lower()
    if normalized in ALL_FILE_LABELS:
        return ["*"]

    tokens = [part.strip() for part in re.split(r"[,;\n]+", text) if part.strip()]
    if not tokens:
        return ["*"]

    patterns: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in ALL_FILE_LABELS:
            return ["*"]
        patterns.append(_normalize_pattern(token))

    return _dedupe(patterns) or ["*"]


def file_matches(path: Path, patterns: list[str]) -> bool:
    """Return whether path's file name matches any pattern."""

    if not patterns or patterns == ["*"]:
        return True

    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns)


def describe_patterns(patterns: list[str]) -> str:
    if not patterns or patterns == ["*"]:
        return "所有文件"
    return ", ".join(patterns)


def _extract_parenthesized_patterns(text: str) -> str:
    match = re.search(r"\(([^()]*)\)", text)
    if not match:
        return ""
    inner = match.group(1).strip()
    if "*" in inner or "." in inner:
        return inner
    return ""


def _normalize_pattern(token: str) -> str:
    token = token.strip()
    if not token:
        return "*"
    if any(ch in token for ch in "*?[]"):
        return token
    if token.startswith("."):
        return f"*{token}"
    return f"*.{token}"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
