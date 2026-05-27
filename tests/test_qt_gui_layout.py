import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QAbstractSpinBox, QApplication  # noqa: E402

from md5_tool.models import ScanIssue  # noqa: E402
from md5_tool.qt_gui import COLORS, ClearCheckBox, ClearComboBox, MD5MateWindow, app_icon_path  # noqa: E402


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def test_app_icon_asset_is_available_and_used_by_window():
    _app()
    window = MD5MateWindow()

    assert app_icon_path().exists()
    assert not window.windowIcon().isNull()

    window.close()


def test_hash_mode_keeps_core_controls_visible_and_advanced_options_fixed():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    assert window.mode == "hash"
    assert window.directory_drop.isVisible()
    assert not window.checksum_drop.isVisible()
    assert window.filter_combo.isVisible()
    assert window.metrics_panel.isVisible()
    assert window.metrics_panel.height() == 64
    assert window.advanced_panel.isVisible()
    assert not hasattr(window, "advanced_toggle")
    assert not hasattr(window, "issue_list")
    assert window.copy_button.isVisible()
    assert window.open_output_button.isVisible()
    assert not window.verify_attention_button.isVisible()

    window.close()


def test_combobox_popup_is_explicitly_light_themed():
    _app()
    window = MD5MateWindow()
    stylesheet = window.styleSheet()

    assert "QComboBox QAbstractItemView" in stylesheet
    assert "background: #ffffff" in stylesheet
    assert "selection-background-color: #ccfbf1" in stylesheet
    assert "QComboBox::down-arrow" not in stylesheet
    assert "border-left: 5px solid transparent" not in stylesheet
    assert isinstance(window.filter_combo, ClearComboBox)

    window.close()


def test_advanced_options_are_fixed_and_verify_mode_field_visibility():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    assert window.advanced_panel.isVisible()
    output_right = window.output_edit.mapTo(window, QPoint(window.output_edit.width(), 0)).x()
    threads_left = window.threads_spin.mapTo(window, QPoint(0, 0)).x()
    assert output_right + 8 <= threads_left

    window._switch_mode("verify")
    QApplication.processEvents()
    assert window.checksum_drop.isVisible()
    assert not window.filter_combo.isVisible()
    assert not window.output_edit.isVisible()
    assert window.advanced_panel.isVisible()
    assert not hasattr(window, "format_combo")
    assert window.threads_spin.isVisible()
    assert not window.copy_button.isVisible()
    assert not window.open_output_button.isVisible()
    assert window.verify_attention_button.isVisible()
    assert window.verify_attention_button.text() == "仅看异常"

    window.close()


def test_thread_spinner_has_explicit_arrow_styles():
    _app()
    window = MD5MateWindow()
    stylesheet = window.styleSheet()

    assert window.threads_spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    assert window.thread_up_button.text() == "▲"
    assert window.thread_down_button.text() == "▼"
    assert "QToolButton#stepButton" in stylesheet

    window.close()


def test_checkbox_indicator_has_clear_checked_and_unchecked_styles():
    _app()
    window = MD5MateWindow()
    stylesheet = window.styleSheet()

    assert isinstance(window.recursive_check, ClearCheckBox)
    assert "QCheckBox::indicator:checked" in stylesheet
    assert "QCheckBox::indicator:unchecked" in stylesheet
    assert "background: #ffffff" in stylesheet
    assert "background: #0f766e" in stylesheet

    window.close()


def test_drop_panel_elides_long_directory_path_and_keeps_full_tooltip():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    long_path = "D:\\" + "\\".join(["very-long-directory-name"] * 24)
    original_height = window.directory_drop.height()

    window._set_directory_from_drop(long_path)
    QApplication.processEvents()

    shown_path = window.directory_drop.path_label.text()
    assert window.directory_edit.text() == long_path
    assert window.directory_drop.path_label.toolTip() == long_path
    assert not window.directory_drop.path_label.wordWrap()
    assert shown_path != long_path
    assert len(shown_path) < len(long_path)
    assert window.directory_drop.height() <= original_height + 4

    window.close()


def test_long_status_message_does_not_compress_progress_bar():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    long_output = "D:\\" + "\\".join(["very-long-directory-name"] * 24) + "\\result.md5"
    message = f"完成，结果已保存到 {long_output}"

    window._set_status(message)
    QApplication.processEvents()

    assert window.status_label.toolTip() == message
    assert window.status_label.text() != message
    assert len(window.status_label.text()) < len(message)
    assert window.progress.width() >= 160
    assert 180 <= window.status_label.width() <= 420
    status_right = window.status_label.mapTo(window, QPoint(window.status_label.width(), 0)).x()
    assert status_right <= window.width()

    window.close()


def test_long_output_path_does_not_overlap_advanced_controls():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    long_output = "D:\\" + "\\".join(["very-long-directory-name"] * 24) + "\\result.md5"
    window.output_edit.setText(long_output)
    QApplication.processEvents()

    output_right = window.output_edit.mapTo(window, QPoint(window.output_edit.width(), 0)).x()
    threads_left = window.threads_spin.mapTo(window, QPoint(0, 0)).x()
    recursive_left = window.recursive_check.mapTo(window, QPoint(0, 0)).x()
    assert output_right + 8 <= threads_left
    assert threads_left + window.threads_spin.width() + 32 <= recursive_left
    assert window.output_edit.text() == long_output

    window.close()


def test_completed_expanded_layout_keeps_directory_row_clear_of_drop_panel():
    _app()
    window = MD5MateWindow()
    window.resize(1175, 768)
    window.show()
    QApplication.processEvents()

    window._apply_summary(1, 1, 0, 0)
    window._set_directory_from_drop("D:\\" + "\\".join(["MD5MateDeep"] * 8))
    window.output_edit.setText("D:\\" + "\\".join(["MD5MateDeep"] * 8) + "\\out.md5")
    QApplication.processEvents()

    drop_bottom = window.directory_drop.mapTo(window, QPoint(0, window.directory_drop.height())).y()
    directory_top = window.directory_edit.mapTo(window, QPoint(0, 0)).y()
    directory_bottom = window.directory_edit.mapTo(window, QPoint(0, window.directory_edit.height())).y()
    filter_top = window.filter_combo.mapTo(window, QPoint(0, 0)).y()
    assert directory_top - drop_bottom >= 22
    assert filter_top - directory_bottom >= 10

    window.close()


def test_verify_layout_keeps_fields_clear_when_summary_is_visible_at_minimum_size():
    _app()
    window = MD5MateWindow()
    window.resize(1040, 680)
    window.show()
    QApplication.processEvents()

    window._switch_mode("verify")
    window._apply_summary(2, 1, 1, 0)
    QApplication.processEvents()

    directory_bottom = window.directory_edit.mapTo(window, QPoint(0, window.directory_edit.height())).y()
    checksum_top = window.checksum_edit.mapTo(window, QPoint(0, 0)).y()
    checksum_bottom = window.checksum_edit.mapTo(window, QPoint(0, window.checksum_edit.height())).y()
    advanced_top = window.advanced_panel.mapTo(window, QPoint(0, 0)).y()
    advanced_bottom = window.advanced_panel.mapTo(window, QPoint(0, window.advanced_panel.height())).y()
    result_top = window.result_panel.mapTo(window, QPoint(0, 0)).y()

    assert checksum_top - directory_bottom >= 10
    assert advanced_top - checksum_bottom >= 10
    assert result_top - advanced_bottom >= 16

    window.close()


def test_summary_cards_hide_warning_card_and_color_key_values():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    assert not window.metric_warnings.isVisible()
    assert window.metrics_panel.isVisible()
    assert COLORS["success"] in window.metric_success.value_label.styleSheet()
    assert COLORS["error"] in window.metric_failed.value_label.styleSheet()

    window._switch_mode("verify")
    window._apply_summary(3, 1, 1, 1)
    QApplication.processEvents()

    assert window.metric_total.title_label.text() == "校验项"
    assert window.metric_success.title_label.text() == "一致"
    assert window.metric_failed.title_label.text() == "需处理"
    assert window.metric_failed.value_label.text() == "2"
    assert not window.metric_warnings.isVisible()

    window.close()


def test_result_area_is_compact_and_renders_issues_in_table_detail():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    assert window.result_panel.maximumHeight() <= 180
    assert not hasattr(window, "issue_list")

    window._set_issues([ScanIssue("locked.bin", "无法读取")])
    QApplication.processEvents()

    assert window.result_table.rowCount() == 1
    assert window.result_table.item(0, 1).text() == "locked.bin"
    assert window.result_table.item(0, 1).foreground().color().name() == COLORS["text"]
    assert window.result_table.item(0, 3).text() == "提醒"
    assert window.result_table.item(0, 4).text() == "无法读取"

    window.close()
