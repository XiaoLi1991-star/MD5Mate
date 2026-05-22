"""Core MD5 scanning and hashing logic."""

from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from .filters import file_matches, parse_filter_text
from .models import FileHashResult, ScanIssue, ScanResult

DEFAULT_CHUNK_SIZE = 1024 * 1024
MAX_THREADS = 64
ProgressCallback = Callable[[FileHashResult, int, int], None]


class CalculationStopped(RuntimeError):
    """Raised internally when a stop event cancels a hash operation."""


def normalize_thread_count(value: int | str | None, default: int | None = None) -> int:
    """Normalize a user supplied thread count into the supported range."""

    if default is None:
        default = min(8, os.cpu_count() or 4)

    try:
        count = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        count = int(default)

    return max(1, min(MAX_THREADS, count))


def scan_files(
    root: str | Path,
    filter_text: str = "*",
    *,
    recursive: bool = True,
    exclude_paths: Iterable[str | Path] | None = None,
    stop_event: Event | None = None,
) -> ScanResult:
    """Scan a directory and return files matching the filter."""

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"目录不存在: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"不是目录: {root_path}")

    patterns = parse_filter_text(filter_text)
    excluded = _resolve_excluded_paths(exclude_paths)
    files: list[Path] = []
    issues: list[ScanIssue] = []

    def on_error(error: OSError) -> None:
        path = Path(error.filename).resolve() if error.filename else root_path
        issues.append(ScanIssue(path=path, message=_format_os_error(error)))

    for current_root, dirs, names in os.walk(root_path, onerror=on_error):
        if stop_event and stop_event.is_set():
            break
        if not recursive:
            dirs.clear()

        current = Path(current_root)
        for name in names:
            if stop_event and stop_event.is_set():
                break
            path = current / name
            try:
                resolved = path.resolve()
                if resolved in excluded:
                    continue
                if path.is_file() and file_matches(path, patterns):
                    files.append(resolved)
            except OSError as error:
                issues.append(ScanIssue(path=path, message=_format_os_error(error)))

    files.sort(key=lambda item: str(item).lower())
    return ScanResult(root=root_path, files=files, issues=issues)


def calculate_md5(
    path: str | Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stop_event: Event | None = None,
) -> str:
    """Calculate the MD5 digest for one file."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    digest = hashlib.md5()
    with Path(path).open("rb") as file:
        while True:
            if stop_event and stop_event.is_set():
                raise CalculationStopped("计算已取消")
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def hash_files(
    files: Iterable[str | Path],
    *,
    root: str | Path,
    threads: int | str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    stop_event: Event | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[FileHashResult]:
    """Hash files with a thread pool and return per-file results."""

    file_paths = [Path(file).resolve() for file in files]
    total = len(file_paths)
    if total == 0:
        return []

    root_path = Path(root).expanduser().resolve()
    workers = normalize_thread_count(threads)
    results: list[FileHashResult] = []

    executor = ThreadPoolExecutor(max_workers=workers)
    futures: dict[Future[FileHashResult], Path] = {
        executor.submit(_hash_one_file, path, root_path, chunk_size, stop_event): path
        for path in file_paths
    }

    try:
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if progress_callback:
                progress_callback(result, len(results), total)

            if stop_event and stop_event.is_set():
                for pending in futures:
                    pending.cancel()
                break
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    results.sort(key=lambda item: item.relative_path.lower())
    return results


def _hash_one_file(
    path: Path,
    root: Path,
    chunk_size: int,
    stop_event: Event | None,
) -> FileHashResult:
    started = time.perf_counter()
    relative_path = _relative_to_root(path, root)

    try:
        size = path.stat().st_size
        digest = calculate_md5(path, chunk_size=chunk_size, stop_event=stop_event)
        return FileHashResult(
            path=path,
            relative_path=relative_path,
            size=size,
            md5=digest,
            duration_seconds=time.perf_counter() - started,
        )
    except CalculationStopped as error:
        return FileHashResult(
            path=path,
            relative_path=relative_path,
            size=_safe_size(path),
            error=str(error),
            duration_seconds=time.perf_counter() - started,
        )
    except Exception as error:  # noqa: BLE001 - every file error should become a row.
        return FileHashResult(
            path=path,
            relative_path=relative_path,
            size=_safe_size(path),
            error=_format_os_error(error),
            duration_seconds=time.perf_counter() - started,
        )


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _resolve_excluded_paths(paths: Iterable[str | Path] | None) -> set[Path]:
    resolved: set[Path] = set()
    for item in paths or []:
        try:
            resolved.add(Path(item).expanduser().resolve())
        except OSError:
            continue
    return resolved


def _format_os_error(error: BaseException) -> str:
    if isinstance(error, PermissionError):
        return "没有访问权限"
    if isinstance(error, FileNotFoundError):
        return "文件不存在"
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    return str(error)
