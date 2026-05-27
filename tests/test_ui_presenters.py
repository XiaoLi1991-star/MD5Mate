from pathlib import Path

from md5_tool.models import ChecksumEntry, FileHashResult, ScanIssue, VerificationResult
from md5_tool.ui_presenters import (
    build_hash_rows,
    build_verification_rows,
    format_md5_copy_lines,
    summarize_hash_results,
    summarize_verification_results,
)


def test_format_md5_copy_lines_matches_standard_md5_output():
    results = [
        FileHashResult(Path("ok.txt"), "ok.txt", 2, md5="444bcb3a3fcf8389296c49467f27e1d6"),
        FileHashResult(Path("missing.txt"), "missing.txt", 0, error="文件不存在"),
    ]

    assert format_md5_copy_lines(results) == "444bcb3a3fcf8389296c49467f27e1d6  ok.txt"


def test_build_hash_rows_uses_user_facing_status_and_severity():
    rows = build_hash_rows(
        [
            FileHashResult(Path("ok.txt"), "ok.txt", 2, md5="444bcb3a3fcf8389296c49467f27e1d6"),
            FileHashResult(Path("bad.txt"), "bad.txt", 0, error="没有访问权限"),
        ]
    )

    assert rows[0].status == "完成"
    assert rows[0].severity == "success"
    assert rows[0].md5 == "444bcb3a3fcf8389296c49467f27e1d6"
    assert rows[0].file_name == "ok.txt"
    assert rows[0].size == "2 B"
    assert rows[1].status == "失败"
    assert rows[1].severity == "error"
    assert rows[1].detail == "没有访问权限"


def test_summarize_hash_results_counts_failures_and_scan_issues():
    summary = summarize_hash_results(
        [
            FileHashResult(Path("ok.txt"), "ok.txt", 2, md5="444bcb3a3fcf8389296c49467f27e1d6"),
            FileHashResult(Path("bad.txt"), "bad.txt", 0, error="没有访问权限"),
        ],
        [ScanIssue(Path("locked"), "扫描失败")],
    )

    assert summary.total == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert summary.warnings == 1
    assert summary.tone == "warning"


def test_build_verification_rows_maps_all_verification_states():
    entry = ChecksumEntry("0" * 32, "file.txt", 1)
    rows = build_verification_rows(
        [
            VerificationResult(entry, Path("file.txt"), size=2, status="matched", actual_md5="0" * 32),
            VerificationResult(entry, Path("file.txt"), status="mismatched", actual_md5="1" * 32, error="期望: 000"),
            VerificationResult(entry, Path("file.txt"), status="missing", error="文件不存在"),
            VerificationResult(entry, Path("file.txt"), status="error", error="读取失败"),
        ]
    )

    assert [row.status for row in rows] == ["一致", "不一致", "缺失", "错误"]
    assert [row.severity for row in rows] == ["success", "warning", "error", "error"]
    assert rows[0].expected_md5 == "0" * 32
    assert rows[0].file_name == "file.txt"
    assert rows[0].actual_md5 == "0" * 32
    assert rows[0].size == "2 B"


def test_summarize_verification_results_prefers_warning_when_anything_needs_attention():
    entry = ChecksumEntry("0" * 32, "file.txt", 1)
    summary = summarize_verification_results(
        [
            VerificationResult(entry, Path("ok.txt"), status="matched", actual_md5="0" * 32),
            VerificationResult(entry, Path("bad.txt"), status="mismatched", actual_md5="1" * 32),
            VerificationResult(entry, Path("missing.txt"), status="missing"),
        ],
        [],
    )

    assert summary.total == 3
    assert summary.succeeded == 1
    assert summary.failed == 2
    assert summary.warnings == 0
    assert summary.tone == "warning"
