from pathlib import Path

from md5_tool.filters import file_matches, parse_filter_text


def test_parse_empty_filter_matches_everything():
    assert parse_filter_text("") == ["*"]
    assert parse_filter_text("所有文件 (*)") == ["*"]


def test_parse_extensions_and_patterns():
    assert parse_filter_text(".txt,.log") == ["*.txt", "*.log"]
    assert parse_filter_text("txt;log") == ["*.txt", "*.log"]
    assert parse_filter_text("*.zip,*.7z") == ["*.zip", "*.7z"]


def test_match_is_case_insensitive():
    patterns = parse_filter_text(".TXT")
    assert file_matches(Path("Report.txt"), patterns)
    assert not file_matches(Path("archive.zip"), patterns)
