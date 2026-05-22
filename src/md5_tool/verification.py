"""MD5 checksum file parsing and verification."""

from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Callable

from .core import CalculationStopped, calculate_md5, normalize_thread_count
from .models import ChecksumEntry, ScanIssue, VerificationResult

MD5_RE = re.compile(r"^[a-fA-F0-9]{32}$")
BSD_RE = re.compile(r"^MD5\s*\((?P<path>.+)\)\s*=\s*(?P<md5>[a-fA-F0-9]{32})$", re.IGNORECASE)
VerifyProgressCallback = Callable[[VerificationResult, int, int], None]


def parse_md5_file(path: str | Path) -> tuple[list[ChecksumEntry], list[ScanIssue]]:
    """Parse common .md5 file formats.

    Supported lines:
    - d41d8cd98f00b204e9800998ecf8427e  file.txt
    - d41d8cd98f00b204e9800998ecf8427e *file.txt
    - MD5 (file.txt) = d41d8cd98f00b204e9800998ecf8427e
    """

    md5_path = Path(path).expanduser().resolve()
    entries: list[ChecksumEntry] = []
    issues: list[ScanIssue] = []

    try:
        lines = md5_path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError:
        lines = md5_path.read_text(encoding="gbk", errors="replace").splitlines()

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        bsd_match = BSD_RE.match(line)
        if bsd_match:
            entries.append(
                ChecksumEntry(
                    expected_md5=bsd_match.group("md5").lower(),
                    relative_path=_clean_relative_path(bsd_match.group("path")),
                    line_number=line_number,
                )
            )
            continue

        parts = line.split(maxsplit=1)
        if len(parts) == 2 and MD5_RE.match(parts[0]):
            entries.append(
                ChecksumEntry(
                    expected_md5=parts[0].lower(),
                    relative_path=_clean_relative_path(parts[1]),
                    line_number=line_number,
                )
            )
            continue

        issues.append(ScanIssue(md5_path, f"第 {line_number} 行不是有效的 MD5 记录"))

    return entries, issues


def verify_md5_file(
    checksum_file: str | Path,
    root: str | Path,
    *,
    threads: int | str | None = None,
    stop_event: Event | None = None,
    progress_callback: VerifyProgressCallback | None = None,
) -> tuple[list[VerificationResult], list[ScanIssue]]:
    """Verify files under root against entries in a .md5 file."""

    root_path = Path(root).expanduser().resolve()
    entries, issues = parse_md5_file(checksum_file)
    if not entries:
        return [], issues

    workers = normalize_thread_count(threads)
    results: list[VerificationResult] = []

    executor = ThreadPoolExecutor(max_workers=workers)
    futures: dict[Future[VerificationResult], ChecksumEntry] = {
        executor.submit(_verify_one_entry, root_path, entry, stop_event): entry for entry in entries
    }

    try:
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result, len(results), len(entries))

            if stop_event and stop_event.is_set():
                for pending in futures:
                    pending.cancel()
                break
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    results.sort(key=lambda item: item.entry.relative_path.lower())
    return results, issues


def _verify_one_entry(root: Path, entry: ChecksumEntry, stop_event: Event | None) -> VerificationResult:
    started = time.perf_counter()
    path = (root / entry.relative_path).resolve()

    if not _is_inside_root(path, root):
        return VerificationResult(
            entry=entry,
            path=path,
            status="error",
            error="校验文件路径超出所选目录",
            duration_seconds=time.perf_counter() - started,
        )

    if not path.exists():
        return VerificationResult(
            entry=entry,
            path=path,
            status="missing",
            error="文件不存在",
            duration_seconds=time.perf_counter() - started,
        )

    try:
        size = path.stat().st_size
        actual_md5 = calculate_md5(path, stop_event=stop_event)
        status = "matched" if actual_md5.lower() == entry.expected_md5.lower() else "mismatched"
        error = None if status == "matched" else f"期望: {entry.expected_md5}"
        return VerificationResult(
            entry=entry,
            path=path,
            size=size,
            actual_md5=actual_md5,
            status=status,
            error=error,
            duration_seconds=time.perf_counter() - started,
        )
    except CalculationStopped as error:
        return VerificationResult(
            entry=entry,
            path=path,
            size=_safe_size(path),
            status="error",
            error=str(error),
            duration_seconds=time.perf_counter() - started,
        )
    except Exception as error:  # noqa: BLE001 - verification should keep going.
        return VerificationResult(
            entry=entry,
            path=path,
            size=_safe_size(path),
            status="error",
            error=str(error),
            duration_seconds=time.perf_counter() - started,
        )


def _clean_relative_path(value: str) -> str:
    cleaned = value.strip().strip('"').strip("'")
    if cleaned.startswith("*"):
        cleaned = cleaned[1:].lstrip()
    return cleaned.replace("\\", "/")


def _is_inside_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
