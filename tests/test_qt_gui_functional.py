import hashlib
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from md5_tool import qt_gui  # noqa: E402
from md5_tool.qt_gui import MD5MateWindow  # noqa: E402


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def _wait_until(predicate, *, timeout=8):
    app = _app()
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError("Timed out waiting for GUI operation")


def _table_rows(window: MD5MateWindow) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in range(window.result_table.rowCount()):
        rows.append(
            [
                window.result_table.item(row, column).text() if window.result_table.item(row, column) else ""
                for column in range(window.result_table.columnCount())
            ]
        )
    return rows


def test_gui_calculates_md5_rows_from_selected_directory(tmp_path):
    first = tmp_path / "alpha.txt"
    second = tmp_path / "beta.log"
    skipped = tmp_path / "skip.bin"
    first.write_text("alpha", encoding="utf-8")
    second.write_text("beta", encoding="utf-8")
    skipped.write_bytes(b"skip")

    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    window.directory_edit.setText(str(tmp_path))
    window.filter_combo.setCurrentText(".txt,.log")
    window.start_button.click()

    _wait_until(lambda: window.thread is None)

    by_name = {result.relative_path: result for result in window.hash_results}
    assert window.result_table.rowCount() == 2
    table = _table_rows(window)
    assert any("alpha.txt" in row and hashlib.md5(b"alpha").hexdigest() in row for row in table)
    assert any("beta.log" in row and hashlib.md5(b"beta").hexdigest() in row for row in table)
    assert by_name["alpha.txt"].md5 == hashlib.md5(b"alpha").hexdigest()
    assert by_name["beta.log"].md5 == hashlib.md5(b"beta").hexdigest()
    assert "skip.bin" not in by_name
    assert window.metric_success.value_label.text() == "2"

    window.close()


def test_hash_and_verify_results_stay_independent_when_switching_modes(tmp_path, monkeypatch):
    warnings = []
    monkeypatch.setattr(qt_gui.QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))
    monkeypatch.setattr(qt_gui.QMessageBox, "critical", lambda *args, **kwargs: None)

    source = tmp_path / "source.hashonly"
    check_file = tmp_path / "check.txt"
    source.write_text("source", encoding="utf-8")
    check_file.write_text("check", encoding="utf-8")
    md5_file = tmp_path / "checksums.md5"
    md5_file.write_text(f"{hashlib.md5(b'check').hexdigest()}  check.txt\nnot-md5", encoding="utf-8")

    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    window.directory_edit.setText(str(tmp_path))
    window.filter_combo.setCurrentText(".hashonly")
    window.start_button.click()
    _wait_until(lambda: window.thread is None)

    assert window.mode == "hash"
    assert _table_rows(window)[0][1] == "source.hashonly"
    assert window.metric_total.title_label.text() == "文件总数"
    assert window.metric_success.title_label.text() == "成功"

    window._switch_mode("verify")
    window.directory_edit.setText(str(tmp_path))
    window.checksum_edit.setText(str(md5_file))
    window.start_button.click()
    _wait_until(lambda: window.thread is None)

    assert window.mode == "verify"
    verify_rows = _table_rows(window)
    assert any(row[1] == "check.txt" for row in verify_rows)
    assert any(row[1] == "checksums.md5" and row[-2] == "提醒" and "第 2 行" in row[-1] for row in verify_rows)
    assert window.metric_total.title_label.text() == "校验项"
    assert window.metric_success.title_label.text() == "一致"
    assert window.metric_success.value_label.text() == "1"
    assert window.metric_failed.title_label.text() == "需处理"
    assert window.metric_failed.value_label.text() == "1"
    assert not window.metric_warnings.isVisible()
    assert window.status_label.text() == "校验完成，有项目需要查看说明列"
    assert warnings == []

    window.verify_attention_button.click()
    QApplication.processEvents()
    filtered_rows = _table_rows(window)
    assert window.verify_attention_button.text() == "显示全部"
    assert any(row[1] == "checksums.md5" and row[-2] == "提醒" for row in filtered_rows)
    assert all(row[1] != "check.txt" for row in filtered_rows)

    window.verify_attention_button.click()
    QApplication.processEvents()
    verify_rows = _table_rows(window)
    assert window.verify_attention_button.text() == "仅看异常"
    assert any(row[1] == "check.txt" for row in verify_rows)

    window._switch_mode("hash")
    QApplication.processEvents()
    assert window.mode == "hash"
    hash_rows = _table_rows(window)
    assert hash_rows[0][1] == "source.hashonly"
    assert all(row[1] != "checksums.md5" for row in hash_rows)
    assert window.metric_total.title_label.text() == "文件总数"
    assert window.metric_success.title_label.text() == "成功"
    assert window.metric_success.value_label.text() == "1"
    assert window.metric_failed.value_label.text() == "0"
    assert not window.metric_warnings.isVisible()

    window._switch_mode("verify")
    QApplication.processEvents()
    verify_rows = _table_rows(window)
    assert any(row[1] == "check.txt" for row in verify_rows)
    assert any(row[1] == "checksums.md5" and row[-2] == "提醒" for row in verify_rows)

    window.close()


def test_gui_verifies_md5_file_and_reports_all_states(tmp_path, monkeypatch):
    monkeypatch.setattr(qt_gui.QMessageBox, "warning", lambda *args, **kwargs: None)

    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.txt"
    good.write_text("good", encoding="utf-8")
    bad.write_text("changed", encoding="utf-8")
    md5_file = tmp_path / "checksums.md5"
    md5_file.write_text(
        "\n".join(
            [
                f"{hashlib.md5(b'good').hexdigest()}  good.txt",
                f"{'0' * 32}  bad.txt",
                f"{'0' * 32}  missing.txt",
            ]
        ),
        encoding="utf-8",
    )

    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    window._switch_mode("verify")
    window.directory_edit.setText(str(tmp_path))
    window.checksum_edit.setText(str(md5_file))
    window.start_button.click()

    _wait_until(lambda: window.thread is None)

    statuses = {result.entry.relative_path: result.status for result in window.verify_results}
    assert statuses == {
        "good.txt": "matched",
        "bad.txt": "mismatched",
        "missing.txt": "missing",
    }
    assert window.result_table.rowCount() == 3
    table = _table_rows(window)
    assert any(
        "good.txt" in row
        and hashlib.md5(b"good").hexdigest() in row
        and hashlib.md5(b"good").hexdigest() in row
        for row in table
    )
    assert any("bad.txt" in row and "0" * 32 in row for row in table)
    assert window.metric_success.value_label.text() == "1"
    assert window.metric_failed.value_label.text() == "2"

    window.verify_attention_button.click()
    QApplication.processEvents()
    filtered_table = _table_rows(window)
    assert len(filtered_table) == 2
    assert any(row[1] == "bad.txt" and row[4] == "不一致" for row in filtered_table)
    assert any(row[1] == "missing.txt" and row[4] == "缺失" for row in filtered_table)
    assert all(row[1] != "good.txt" for row in filtered_table)

    window.verify_attention_button.click()
    QApplication.processEvents()
    assert window.result_table.rowCount() == 3

    window.close()
