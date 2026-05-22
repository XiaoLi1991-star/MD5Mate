"""Data models shared by the CLI and GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ScanIssue:
    """A non-fatal issue found while scanning a directory."""

    path: Path
    message: str


@dataclass(frozen=True)
class ScanResult:
    """Files selected for hashing plus scan-time issues."""

    root: Path
    files: list[Path]
    issues: list[ScanIssue] = field(default_factory=list)


@dataclass(frozen=True)
class FileHashResult:
    """Hash result for one file."""

    path: Path
    relative_path: str
    size: int
    md5: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    completed_at: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.md5)


@dataclass(frozen=True)
class ChecksumEntry:
    """One expected MD5 entry parsed from a checksum file."""

    expected_md5: str
    relative_path: str
    line_number: int


@dataclass(frozen=True)
class VerificationResult:
    """Verification result for one checksum entry."""

    entry: ChecksumEntry
    path: Path
    size: int = 0
    actual_md5: str | None = None
    status: str = "error"
    error: str | None = None
    duration_seconds: float = 0.0
    completed_at: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        return self.status == "matched"


@dataclass(frozen=True)
class OutputSummary:
    """Summary returned after saving output."""

    output_path: Path
    output_format: str
    total: int
    succeeded: int
    failed: int
    scan_issues: int = 0

    @property
    def has_errors(self) -> bool:
        return self.failed > 0 or self.scan_issues > 0
