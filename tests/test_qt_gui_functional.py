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
    assert by_name["alpha.txt"].md5 == hashlib.md5(b"alpha").hexdigest()
    assert by_name["beta.log"].md5 == hashlib.md5(b"beta").hexdigest()
    assert "skip.bin" not in by_name
    assert window.metric_success.value_label.text() == "2"

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
    assert window.metric_success.value_label.text() == "1"
    assert window.metric_failed.value_label.text() == "2"

    window.close()
