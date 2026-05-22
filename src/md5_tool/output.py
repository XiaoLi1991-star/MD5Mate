"""Output writers for MD5 results."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .filters import describe_patterns, parse_filter_text
from .models import FileHashResult, OutputSummary, ScanIssue

SUPPORTED_FORMATS = {"auto", "md5", "csv", "txt"}


def detect_output_format(output_path: str | Path, requested: str = "auto") -> str:
    """Resolve the output format from a request and file extension."""

    requested = (requested or "auto").lower()
    if requested not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的输出格式: {requested}")
    if requested != "auto":
        return requested

    suffix = Path(output_path).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".log"}:
        return "txt"
    return "md5"


def save_results(
    results: Iterable[FileHashResult],
    output_path: str | Path,
    *,
    output_format: str = "auto",
    root: str | Path | None = None,
    filter_text: str = "*",
    scan_issues: Iterable[ScanIssue] | None = None,
) -> OutputSummary:
    """Save results in md5, csv, or text report format."""

    result_list = list(results)
    issue_list = list(scan_issues or [])
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    fmt = detect_output_format(path, output_format)
    if fmt == "csv":
        _write_csv(path, result_list)
    elif fmt == "txt":
        _write_text_report(path, result_list, root=root, filter_text=filter_text, issues=issue_list)
    else:
        _write_md5(path, result_list)

    succeeded = sum(1 for item in result_list if item.ok)
    failed = len(result_list) - succeeded
    return OutputSummary(
        output_path=path,
        output_format=fmt,
        total=len(result_list),
        succeeded=succeeded,
        failed=failed,
        scan_issues=len(issue_list),
    )


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _write_md5(path: Path, results: list[FileHashResult]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for result in results:
            if result.ok:
                file.write(f"{result.md5}  {result.relative_path}\n")


def _write_csv(path: Path, results: list[FileHashResult]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["状态", "MD5", "相对路径", "文件大小", "文件大小(字节)", "耗时(秒)", "错误"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "状态": "成功" if result.ok else "失败",
                    "MD5": result.md5 or "",
                    "相对路径": result.relative_path,
                    "文件大小": format_size(result.size),
                    "文件大小(字节)": result.size,
                    "耗时(秒)": f"{result.duration_seconds:.3f}",
                    "错误": result.error or "",
                }
            )


def _write_text_report(
    path: Path,
    results: list[FileHashResult],
    *,
    root: str | Path | None,
    filter_text: str,
    issues: list[ScanIssue],
) -> None:
    succeeded = [item for item in results if item.ok]
    failed = [item for item in results if not item.ok]
    total_size = sum(item.size for item in succeeded)
    patterns = describe_patterns(parse_filter_text(filter_text))

    lines = [
        "MD5Mate 文件校验报告",
        "=" * 72,
        f"生成时间: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"扫描目录: {Path(root).resolve() if root else '-'}",
        f"文件筛选: {patterns}",
        f"文件总数: {len(results)}",
        f"成功数量: {len(succeeded)}",
        f"失败数量: {len(failed)}",
        f"扫描提醒: {len(issues)}",
        f"成功文件总大小: {format_size(total_size)}",
        "",
        "结果",
        "-" * 72,
    ]

    for result in results:
        status = "OK" if result.ok else "ERROR"
        digest = result.md5 or "-"
        lines.append(f"{status}  {digest}  {result.relative_path}")
        if result.error:
            lines.append(f"      错误: {result.error}")

    if issues:
        lines.extend(["", "扫描提醒", "-" * 72])
        for issue in issues:
            lines.append(f"{issue.path}: {issue.message}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
