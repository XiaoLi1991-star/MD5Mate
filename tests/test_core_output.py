import hashlib

from md5_tool.core import hash_files, normalize_thread_count, scan_files
from md5_tool.output import save_results


def test_normalize_thread_count_clamps_values():
    assert normalize_thread_count(0) == 1
    assert normalize_thread_count(999) == 64
    assert normalize_thread_count("bad", default=3) == 3


def test_scan_hash_and_save_outputs(tmp_path):
    first = tmp_path / "a.txt"
    second = tmp_path / "b.log"
    ignored = tmp_path / "c.bin"
    first.write_text("hello", encoding="utf-8")
    second.write_text("world", encoding="utf-8")
    ignored.write_bytes(b"ignored")

    scan = scan_files(tmp_path, ".txt,.log")
    assert [path.name for path in scan.files] == ["a.txt", "b.log"]

    results = hash_files(scan.files, root=tmp_path, threads=2)
    by_name = {result.relative_path: result for result in results}
    assert by_name["a.txt"].md5 == hashlib.md5(b"hello").hexdigest()
    assert by_name["b.log"].md5 == hashlib.md5(b"world").hexdigest()

    summary = save_results(results, tmp_path / "result.md5", root=tmp_path)
    assert summary.succeeded == 2
    assert summary.failed == 0
    content = (tmp_path / "result.md5").read_text(encoding="utf-8")
    assert "a.txt" in content


def test_hash_missing_file_returns_error_result(tmp_path):
    missing = tmp_path / "missing.txt"
    results = hash_files([missing], root=tmp_path, threads=1)
    assert len(results) == 1
    assert not results[0].ok
    assert results[0].error


def test_csv_output_includes_failed_rows(tmp_path):
    ok_file = tmp_path / "ok.txt"
    missing = tmp_path / "missing.txt"
    ok_file.write_text("ok", encoding="utf-8")

    results = hash_files([ok_file, missing], root=tmp_path, threads=1)
    summary = save_results(results, tmp_path / "result.csv", output_format="csv", root=tmp_path)

    assert summary.succeeded == 1
    assert summary.failed == 1
    content = (tmp_path / "result.csv").read_text(encoding="utf-8-sig")
    assert "失败" in content
    assert "missing.txt" in content
