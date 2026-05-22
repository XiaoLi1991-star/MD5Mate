"""Presentation helpers shared by desktop frontends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import FileHashResult, ScanIssue, VerificationResult
from .output import format_size


@dataclass(frozen=True)
class HashResultRow:
    md5: str
    file_name: str
    size: str
    status: str
    detail: str
    severity: str


@dataclass(frozen=True)
class VerificationResultRow:
    expected_md5: str
    file_name: str
    actual_md5: str
    size: str
    status: str
    detail: str
    severity: str


@dataclass(frozen=True)
class RunSummary:
    total: int
    succeeded: int
    failed: int
    warnings: int
    tone: str


def format_md5_copy_lines(results: Iterable[FileHashResult]) -> str:
    """Return successful rows in the standard `.md5` file format."""

    return "\n".join(f"{result.md5}  {result.relative_path}" for result in results if result.ok)


def build_hash_rows(results: Iterable[FileHashResult]) -> list[HashResultRow]:
    rows: list[HashResultRow] = []
    for result in results:
        rows.append(
            HashResultRow(
                md5=result.md5 or "",
                file_name=result.relative_path,
                size=format_size(result.size),
                status="完成" if result.ok else "失败",
                detail="-" if result.ok else result.error or "未知错误",
                severity="success" if result.ok else "error",
            )
        )
    return rows


def build_verification_rows(results: Iterable[VerificationResult]) -> list[VerificationResultRow]:
    rows: list[VerificationResultRow] = []
    for result in results:
        status, severity = _verification_status(result.status)
        rows.append(
            VerificationResultRow(
                expected_md5=result.entry.expected_md5,
                file_name=result.entry.relative_path,
                actual_md5=result.actual_md5 or "",
                size=format_size(result.size),
                status=status,
                detail=result.error or "-",
                severity=severity,
            )
        )
    return rows


def summarize_hash_results(results: Iterable[FileHashResult], issues: Iterable[ScanIssue]) -> RunSummary:
    result_list = list(results)
    warning_count = len(list(issues))
    succeeded = sum(1 for result in result_list if result.ok)
    failed = len(result_list) - succeeded
    return RunSummary(
        total=len(result_list),
        succeeded=succeeded,
        failed=failed,
        warnings=warning_count,
        tone=_summary_tone(failed, warning_count),
    )


def summarize_verification_results(
    results: Iterable[VerificationResult], issues: Iterable[ScanIssue]
) -> RunSummary:
    result_list = list(results)
    warning_count = len(list(issues))
    succeeded = sum(1 for result in result_list if result.ok)
    failed = len(result_list) - succeeded
    return RunSummary(
        total=len(result_list),
        succeeded=succeeded,
        failed=failed,
        warnings=warning_count,
        tone=_summary_tone(failed, warning_count),
    )


def _verification_status(status: str) -> tuple[str, str]:
    if status == "matched":
        return "一致", "success"
    if status == "mismatched":
        return "不一致", "warning"
    if status == "missing":
        return "缺失", "error"
    return "错误", "error"


def _summary_tone(failed: int, warnings: int) -> str:
    if failed or warnings:
        return "warning"
    return "success"
