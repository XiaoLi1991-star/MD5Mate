"""MD5 Toolkit package."""

from .core import (
    DEFAULT_CHUNK_SIZE,
    MAX_THREADS,
    CalculationStopped,
    calculate_md5,
    hash_files,
    normalize_thread_count,
    scan_files,
)
from .models import FileHashResult, ScanIssue, ScanResult
from .verification import parse_md5_file, verify_md5_file

__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "MAX_THREADS",
    "CalculationStopped",
    "FileHashResult",
    "ScanIssue",
    "ScanResult",
    "calculate_md5",
    "hash_files",
    "normalize_thread_count",
    "scan_files",
    "parse_md5_file",
    "verify_md5_file",
]

__version__ = "1.0.0"
