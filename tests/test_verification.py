import hashlib

from md5_tool.verification import parse_md5_file, verify_md5_file


def test_parse_md5_file_supports_standard_and_bsd_formats(tmp_path):
    md5_file = tmp_path / "checksums.md5"
    md5_file.write_text(
        "\n".join(
            [
                "d41d8cd98f00b204e9800998ecf8427e  empty.txt",
                "MD5 (hello.txt) = 5d41402abc4b2a76b9719d911017c592",
                "not a checksum",
            ]
        ),
        encoding="utf-8",
    )

    entries, issues = parse_md5_file(md5_file)

    assert [entry.relative_path for entry in entries] == ["empty.txt", "hello.txt"]
    assert entries[0].expected_md5 == "d41d8cd98f00b204e9800998ecf8427e"
    assert len(issues) == 1


def test_verify_md5_file_reports_match_mismatch_and_missing(tmp_path):
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.txt"
    good.write_text("good", encoding="utf-8")
    bad.write_text("changed", encoding="utf-8")

    good_md5 = hashlib.md5(good.read_bytes()).hexdigest()
    wrong_md5 = "0" * 32
    md5_file = tmp_path / "checksums.md5"
    md5_file.write_text(
        "\n".join(
            [
                f"{good_md5}  good.txt",
                f"{wrong_md5}  bad.txt",
                f"{wrong_md5}  missing.txt",
            ]
        ),
        encoding="utf-8",
    )

    results, issues = verify_md5_file(md5_file, tmp_path, threads=2)
    by_name = {result.entry.relative_path: result for result in results}

    assert issues == []
    assert by_name["good.txt"].status == "matched"
    assert by_name["bad.txt"].status == "mismatched"
    assert by_name["missing.txt"].status == "missing"
