import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from md5_tool.qt_gui import MD5MateWindow  # noqa: E402


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def test_hash_mode_keeps_core_controls_visible_and_advanced_options_collapsed():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    assert window.mode == "hash"
    assert window.directory_drop.isVisible()
    assert not window.checksum_drop.isVisible()
    assert window.filter_combo.isVisible()
    assert not window.metrics_panel.isVisible()
    assert not window.advanced_panel.isVisible()
    assert window.advanced_toggle.text() == "显示高级选项"

    window.close()


def test_combobox_popup_is_explicitly_light_themed():
    _app()
    window = MD5MateWindow()
    stylesheet = window.styleSheet()

    assert "QComboBox QAbstractItemView" in stylesheet
    assert "background: #ffffff" in stylesheet
    assert "selection-background-color: #ccfbf1" in stylesheet

    window.close()


def test_advanced_options_toggle_and_verify_mode_field_visibility():
    _app()
    window = MD5MateWindow()
    window.show()
    QApplication.processEvents()

    window.advanced_toggle.click()
    QApplication.processEvents()
    assert window.advanced_panel.isVisible()
    assert window.advanced_toggle.text() == "收起高级选项"

    window._switch_mode("verify")
    QApplication.processEvents()
    assert window.checksum_drop.isVisible()
    assert not window.filter_combo.isVisible()
    assert not window.output_edit.isVisible()
    assert not window.format_combo.isVisible()
    assert window.threads_spin.isVisible()

    window.close()
