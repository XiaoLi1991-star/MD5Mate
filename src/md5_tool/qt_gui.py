"""Modern PySide6 desktop interface for MD5Mate."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRect, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .core import DEFAULT_CHUNK_SIZE, hash_files, normalize_thread_count, scan_files
from .models import FileHashResult, OutputSummary, ScanIssue, VerificationResult
from .output import save_results
from .ui_presenters import (
    build_hash_rows,
    build_verification_rows,
    format_md5_copy_lines,
    summarize_hash_results,
    summarize_verification_results,
)
from .verification import verify_md5_file


APP_TITLE = "MD5Mate"
FILTER_PRESETS = [
    "所有文件 (*)",
    "文本文件 (*.txt,*.log,*.md)",
    "压缩文件 (*.zip,*.rar,*.7z,*.tar,*.gz)",
    "安装包 (*.exe,*.msi,*.dll)",
    "图片文件 (*.jpg,*.jpeg,*.png,*.gif,*.bmp)",
    "文档文件 (*.doc,*.docx,*.pdf,*.xls,*.xlsx)",
]
FORMAT_LABELS = {
    "MD5 列表": "md5",
}

COLORS = {
    "text": "#182230",
    "muted": "#667085",
    "line": "#d9e2ec",
    "surface": "#ffffff",
    "canvas": "#f4f7fb",
    "ink": "#111827",
    "teal": "#0f766e",
    "teal_dark": "#115e59",
    "blue": "#2563eb",
    "success": "#087443",
    "warning": "#b54708",
    "error": "#b42318",
}


class DropPanel(QFrame):
    """Clickable and droppable path target."""

    path_dropped = Signal(str)
    clicked = Signal()

    def __init__(self, title: str, hint: str, *, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dropPanel")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(88)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("dropTitle")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("dropHint")
        self.path_label = QLabel("尚未选择")
        self.path_label.setObjectName("dropPath")
        self._full_path_text = ""
        self._empty_path_text = self.path_label.text()
        self.path_label.setWordWrap(False)
        self.path_label.setMinimumWidth(0)
        self.path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        layout.addWidget(self.title_label)
        layout.addWidget(self.hint_label)
        layout.addStretch(1)
        layout.addWidget(self.path_label)

    def set_path(self, value: str) -> None:
        self._full_path_text = value or ""
        self.path_label.setToolTip(self._full_path_text)
        self._refresh_path_label()

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._refresh_path_label()

    def _refresh_path_label(self) -> None:
        if not self._full_path_text:
            self.path_label.setText(self._empty_path_text)
            return

        available_width = max(80, self.path_label.width())
        text = self.path_label.fontMetrics().elidedText(
            self._full_path_text,
            Qt.TextElideMode.ElideMiddle,
            available_width,
        )
        self.path_label.setText(text)

    def mousePressEvent(self, event):  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802 - Qt API
        urls = event.mimeData().urls()
        if not urls:
            return
        local_path = urls[0].toLocalFile()
        if local_path:
            self.path_dropped.emit(local_path)
            event.acceptProposedAction()


class MetricCard(QFrame):
    """Small status card used in the workspace header."""

    def __init__(self, title: str, value: str = "0", *, accent: str = "neutral"):
        super().__init__()
        self.setObjectName("metricCard")
        self.setProperty("accent", accent)
        self.setMaximumHeight(72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("metricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_value(self, value: int | str) -> None:
        self.value_label.setText(str(value))


class ClearCheckBox(QCheckBox):
    """High-contrast checkbox for compact option rows."""

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        size = super().sizeHint()
        return QSize(size.width() + 4, max(size.height(), 24))

    def paintEvent(self, _event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        indicator_size = 16
        top = (self.height() - indicator_size) // 2
        indicator = QRect(0, top, indicator_size, indicator_size)

        if not self.isEnabled():
            fill = QColor("#eef2f7")
            border = QColor("#cbd5e1")
            text = QColor("#98a2b3")
        elif self.isChecked():
            fill = QColor(COLORS["teal"])
            border = QColor(COLORS["teal_dark"])
            text = QColor(COLORS["text"])
        else:
            fill = QColor("#ffffff")
            border = QColor("#64748b")
            text = QColor(COLORS["text"])

        painter.setBrush(fill)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(indicator, 4, 4)

        if self.isChecked() and self.isEnabled():
            painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(indicator.left() + 4, indicator.top() + 8, indicator.left() + 7, indicator.top() + 11)
            painter.drawLine(indicator.left() + 7, indicator.top() + 11, indicator.left() + 12, indicator.top() + 5)

        painter.setPen(text)
        text_rect = QRect(24, 0, self.width() - 24, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class ClearComboBox(QComboBox):
    """Combo box with a reliable Windows-friendly dropdown chevron."""

    def paintEvent(self, event):  # noqa: N802 - Qt API
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        button_width = 28
        button_left = self.width() - button_width - 1
        center_x = button_left + button_width // 2
        center_y = self.height() // 2 + 1
        arrow_color = QColor(COLORS["muted"] if self.isEnabled() else "#98a2b3")

        painter.setPen(QPen(QColor("#d9e2ec"), 1))
        painter.drawLine(button_left, 7, button_left, self.height() - 7)

        painter.setPen(QPen(arrow_color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(center_x - 4, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 4, center_y - 2)


class ElidedLabel(QLabel):
    """Label that keeps full text in a tooltip and draws compact text."""

    def __init__(self, text: str = "", *, mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle):
        self._full_text = ""
        self._elide_mode = mode
        super().__init__("")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._refresh_text()

    def resizeEvent(self, event):  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._refresh_text()

    def _refresh_text(self) -> None:
        available_width = max(24, self.width())
        text = self.fontMetrics().elidedText(self._full_text, self._elide_mode, available_width)
        QLabel.setText(self, text)


class JobWorker(QObject):
    """Runs hash or verification work away from the UI thread."""

    status_changed = Signal(str)
    progress_changed = Signal(int, int)
    hash_result_ready = Signal(object)
    verification_result_ready = Signal(object)
    issues_ready = Signal(object)
    finished = Signal(object)

    def __init__(self, mode: str, params: dict[str, object]):
        super().__init__()
        self.mode = mode
        self.params = params
        self.stop_event = Event()

    def request_stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        try:
            if self.mode == "hash":
                payload = self._run_hash()
            else:
                payload = self._run_verify()
        except Exception as error:  # noqa: BLE001 - UI must receive a readable failure.
            payload = {
                "mode": self.mode,
                "results": [],
                "issues": [],
                "output_summary": None,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        self.finished.emit(payload)

    def _run_hash(self) -> dict[str, object]:
        directory = Path(str(self.params["directory"])).expanduser().resolve()
        filter_text = str(self.params["filter_text"])
        output = self.params.get("output")
        output_path = Path(str(output)).expanduser().resolve() if output else None
        output_format = str(self.params.get("output_format", "md5"))
        recursive = bool(self.params["recursive"])
        threads = int(self.params["threads"])

        self.status_changed.emit("正在扫描目录...")
        scan = scan_files(
            directory,
            filter_text,
            recursive=recursive,
            exclude_paths=[output_path] if output_path else None,
            stop_event=self.stop_event,
        )
        self.issues_ready.emit(scan.issues)

        if not scan.files:
            raise ValueError("没有找到符合筛选条件的文件。")

        self.status_changed.emit(f"正在计算 MD5，线程数 {threads}...")

        def on_progress(result: FileHashResult, done: int, total: int) -> None:
            self.hash_result_ready.emit(result)
            self.progress_changed.emit(done, total)

        results = hash_files(
            scan.files,
            root=scan.root,
            threads=threads,
            chunk_size=DEFAULT_CHUNK_SIZE,
            stop_event=self.stop_event,
            progress_callback=on_progress,
        )

        output_summary: OutputSummary | None = None
        if output_path:
            self.status_changed.emit("正在保存结果...")
            output_summary = save_results(
                results,
                output_path,
                output_format=output_format,
                root=scan.root,
                filter_text=filter_text,
                scan_issues=scan.issues,
            )

        return {
            "mode": "hash",
            "results": results,
            "issues": scan.issues,
            "output_summary": output_summary,
            "error": None,
        }

    def _run_verify(self) -> dict[str, object]:
        directory = Path(str(self.params["directory"])).expanduser().resolve()
        checksum = Path(str(self.params["checksum"])).expanduser().resolve()
        threads = int(self.params["threads"])

        self.status_changed.emit(f"正在校验 MD5，线程数 {threads}...")

        def on_progress(result: VerificationResult, done: int, total: int) -> None:
            self.verification_result_ready.emit(result)
            self.progress_changed.emit(done, total)

        results, issues = verify_md5_file(
            checksum,
            directory,
            threads=threads,
            stop_event=self.stop_event,
            progress_callback=on_progress,
        )
        self.issues_ready.emit(issues)

        if not results and issues:
            raise ValueError("校验文件中没有可用的 MD5 记录。")

        return {
            "mode": "verify",
            "results": results,
            "issues": issues,
            "output_summary": None,
            "error": None,
        }


class MD5MateWindow(QMainWindow):
    """Main MD5Mate desktop window."""

    def __init__(self):
        super().__init__()
        self.mode = "hash"
        self.thread: QThread | None = None
        self.worker: JobWorker | None = None
        self.hash_results: list[FileHashResult] = []
        self.verify_results: list[VerificationResult] = []
        self.issues: list[ScanIssue] = []
        self.output_summary: OutputSummary | None = None

        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 760)
        self.setMinimumSize(1040, 680)
        self.setAcceptDrops(True)
        self._build_ui()
        self._apply_styles()
        self._switch_mode("hash")
        self._reset_summary()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_workspace(), 1)
        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(22, 24, 18, 20)
        layout.setSpacing(16)

        brand = QLabel("MD5Mate")
        brand.setObjectName("brand")
        tagline = QLabel("本地文件校验工作台")
        tagline.setObjectName("tagline")
        layout.addWidget(brand)
        layout.addWidget(tagline)
        layout.addSpacing(12)

        self.hash_nav = self._nav_button("计算 MD5")
        self.verify_nav = self._nav_button("校验 .md5")
        self.hash_nav.clicked.connect(lambda: self._switch_mode("hash"))
        self.verify_nav.clicked.connect(lambda: self._switch_mode("verify"))
        layout.addWidget(self.hash_nav)
        layout.addWidget(self.verify_nav)
        layout.addStretch(1)

        note = QLabel("离线运行\n不上传文件\n结果可复制或导出")
        note.setObjectName("sidebarNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        return sidebar

    def _build_workspace(self) -> QWidget:
        workspace = QFrame()
        workspace.setObjectName("workspace")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_metrics())
        layout.addWidget(self._build_control_panel())
        layout.addWidget(self._build_result_area(), 1)
        layout.addWidget(self._build_footer())
        return workspace

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        self.mode_title = QLabel()
        self.mode_title.setObjectName("pageTitle")
        self.mode_subtitle = QLabel()
        self.mode_subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(self.mode_title)
        title_box.addWidget(self.mode_subtitle)

        self.start_button = QPushButton("开始")
        self.start_button.setProperty("variant", "primary")
        self.start_button.clicked.connect(self._start_job)
        self.stop_button = QPushButton("停止")
        self.stop_button.setProperty("variant", "secondary")
        self.stop_button.clicked.connect(self._stop_job)
        self.stop_button.setEnabled(False)

        layout.addLayout(title_box, 1)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        return header

    def _build_metrics(self) -> QWidget:
        panel = QWidget()
        self.metrics_panel = panel
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        self.metric_total = MetricCard("文件总数", accent="blue")
        self.metric_success = MetricCard("成功", accent="success")
        self.metric_failed = MetricCard("失败", accent="warning")
        self.metric_warnings = MetricCard("提醒", accent="neutral")

        for index, card in enumerate(
            [self.metric_total, self.metric_success, self.metric_failed, self.metric_warnings]
        ):
            layout.addWidget(card, 0, index)
        return panel

    def _build_control_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("surface")
        outer_layout = QVBoxLayout(panel)
        outer_layout.setContentsMargins(18, 18, 18, 18)
        outer_layout.setSpacing(14)

        self.directory_drop = DropPanel("目标目录", "拖入文件夹，或点击选择")
        self.checksum_drop = DropPanel("MD5 文件", "拖入 .md5 文件，或点击选择")
        self.directory_drop.clicked.connect(self._browse_directory)
        self.checksum_drop.clicked.connect(self._browse_checksum)
        self.directory_drop.path_dropped.connect(self._set_directory_from_drop)
        self.checksum_drop.path_dropped.connect(self._set_checksum_from_drop)

        drop_row = QHBoxLayout()
        drop_row.setContentsMargins(0, 0, 0, 0)
        drop_row.setSpacing(14)
        drop_row.addWidget(self.directory_drop, 1)
        drop_row.addWidget(self.checksum_drop, 1)
        outer_layout.addLayout(drop_row)
        outer_layout.addSpacing(22)

        form_widget = QWidget()
        layout = QGridLayout(form_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(12)
        layout.setColumnMinimumWidth(0, 86)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        form_widget.setMinimumHeight(100)
        outer_layout.addWidget(form_widget)

        self.directory_edit = QLineEdit()
        self.directory_edit.setPlaceholderText("选择或拖入要处理的目录")
        self.directory_edit.textChanged.connect(self.directory_drop.set_path)
        directory_button = QPushButton("选择目录")
        directory_button.setProperty("variant", "secondary")
        directory_button.clicked.connect(self._browse_directory)

        self.checksum_edit = QLineEdit()
        self.checksum_edit.setPlaceholderText("选择 .md5 校验文件")
        self.checksum_edit.textChanged.connect(self.checksum_drop.set_path)
        checksum_button = QPushButton("选择文件")
        checksum_button.setProperty("variant", "secondary")
        checksum_button.clicked.connect(self._browse_checksum)

        self.filter_combo = ClearComboBox()
        self.filter_combo.setEditable(True)
        self.filter_combo.addItems(FILTER_PRESETS)
        self.filter_combo.setMinimumWidth(360)
        self._style_combo_popup(self.filter_combo)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("留空时只在界面显示，不生成文件")
        output_button = QPushButton("保存到")
        output_button.setProperty("variant", "secondary")
        output_button.clicked.connect(self._browse_output)
        clear_output_button = QPushButton("清空")
        clear_output_button.setProperty("variant", "ghost")
        clear_output_button.clicked.connect(lambda: self.output_edit.setText(""))

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 64)
        self.threads_spin.setValue(normalize_thread_count(None))
        self.threads_spin.setMinimumWidth(104)
        self.threads_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.thread_stepper = QWidget()
        stepper_layout = QVBoxLayout(self.thread_stepper)
        stepper_layout.setContentsMargins(0, 0, 0, 0)
        stepper_layout.setSpacing(2)
        self.thread_up_button = QToolButton()
        self.thread_up_button.setText("▲")
        self.thread_up_button.setObjectName("stepButton")
        self.thread_up_button.clicked.connect(lambda: self.threads_spin.stepUp())
        self.thread_down_button = QToolButton()
        self.thread_down_button.setText("▼")
        self.thread_down_button.setObjectName("stepButton")
        self.thread_down_button.clicked.connect(lambda: self.threads_spin.stepDown())
        stepper_layout.addWidget(self.thread_up_button)
        stepper_layout.addWidget(self.thread_down_button)
        self.recursive_check = ClearCheckBox("递归扫描子目录")
        self.recursive_check.setChecked(True)

        self._add_labeled_row(layout, 0, "目录", self.directory_edit, directory_button)
        self.checksum_label = QLabel("校验文件")
        self.checksum_label.setObjectName("fieldLabel")
        layout.addWidget(self.checksum_label, 1, 0)
        checksum_row = QWidget()
        checksum_layout = QHBoxLayout(checksum_row)
        checksum_layout.setContentsMargins(0, 0, 0, 0)
        checksum_layout.setSpacing(8)
        checksum_layout.addWidget(self.checksum_edit, 1)
        checksum_layout.addWidget(checksum_button)
        layout.addWidget(checksum_row, 1, 1)
        self.checksum_widgets = [self.checksum_label, checksum_row, self.checksum_drop]

        self.filter_label, self.filter_row = self._add_labeled_row(layout, 2, "筛选", self.filter_combo)
        self.filter_widgets = [self.filter_label, self.filter_row]

        advanced_header = QHBoxLayout()
        advanced_header.setContentsMargins(0, 0, 0, 0)
        advanced_header.addStretch(1)
        self.advanced_toggle = QPushButton("显示高级选项")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setProperty("variant", "ghost")
        self.advanced_toggle.clicked.connect(self._toggle_advanced_options)
        advanced_header.addWidget(self.advanced_toggle)
        outer_layout.addLayout(advanced_header)

        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("advancedPanel")
        advanced_layout = QHBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(14, 14, 14, 14)
        advanced_layout.setSpacing(12)
        outer_layout.addWidget(self.advanced_panel)

        output_label = QLabel("输出")
        output_label.setObjectName("fieldLabel")
        thread_caption = QLabel("线程")
        thread_caption.setObjectName("inlineCaption")
        advanced_layout.addWidget(output_label)
        advanced_layout.addWidget(self.output_edit, 1)
        advanced_layout.addWidget(output_button)
        advanced_layout.addWidget(clear_output_button)
        advanced_layout.addSpacing(8)
        advanced_layout.addWidget(thread_caption)
        advanced_layout.addWidget(self.threads_spin)
        advanced_layout.addWidget(self.thread_stepper)
        advanced_layout.addWidget(self.recursive_check)
        self.output_widgets = [output_label, self.output_edit, output_button, clear_output_button]
        self.hash_option_widgets = [self.recursive_check]
        self.advanced_panel.setVisible(False)
        return panel

    def _build_result_area(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        result_panel = QFrame()
        result_panel.setObjectName("surface")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(18, 16, 18, 18)
        result_layout.setSpacing(12)

        result_header = QHBoxLayout()
        result_title = QLabel("结果")
        result_title.setObjectName("sectionTitle")
        self.copy_button = QPushButton("复制 MD5 行")
        self.copy_button.setProperty("variant", "secondary")
        self.copy_button.clicked.connect(self._copy_md5_lines)
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setProperty("variant", "secondary")
        self.open_output_button.clicked.connect(self._open_output_folder)
        clear_button = QPushButton("清空")
        clear_button.setProperty("variant", "ghost")
        clear_button.clicked.connect(self._clear_results)
        result_header.addWidget(result_title)
        result_header.addStretch(1)
        result_header.addWidget(self.copy_button)
        result_header.addWidget(self.open_output_button)
        result_header.addWidget(clear_button)
        result_layout.addLayout(result_header)

        self.result_table = QTableWidget(0, 5)
        self.result_table.setObjectName("resultTable")
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.result_table.setAlternatingRowColors(True)
        result_layout.addWidget(self.result_table, 1)

        issue_panel = QFrame()
        issue_panel.setObjectName("surface")
        issue_layout = QVBoxLayout(issue_panel)
        issue_layout.setContentsMargins(16, 16, 16, 18)
        issue_layout.setSpacing(10)
        issue_title = QLabel("提醒")
        issue_title.setObjectName("sectionTitle")
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("issueList")
        self.issue_list.addItem("暂无提醒")
        issue_layout.addWidget(issue_title)
        issue_layout.addWidget(self.issue_list, 1)

        splitter.addWidget(result_panel)
        splitter.addWidget(issue_panel)
        splitter.setSizes([900, 230])
        return splitter

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.progress = QTableProgress()
        self.status_label = ElidedLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setFixedWidth(320)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.progress, 1)
        layout.addWidget(self.status_label)
        return footer

    def _nav_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setProperty("nav", True)
        return button

    def _add_labeled_row(
        self, layout: QGridLayout, row: int, label_text: str, editor: QWidget, button: QPushButton | None = None
    ) -> tuple[QLabel, QWidget]:
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label, row, 0)
        if button:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(editor, 1)
            row_layout.addWidget(button)
            layout.addWidget(row_widget, row, 1)
            return label, row_widget
        else:
            layout.addWidget(editor, row, 1)
            return label, editor

    def _style_combo_popup(self, combo: QComboBox) -> None:
        combo.view().setStyleSheet(
            f"""
            QListView {{
                background: #ffffff;
                color: {COLORS["text"]};
                border: 1px solid #cbd5e1;
                selection-background-color: #ccfbf1;
                selection-color: {COLORS["text"]};
                outline: 0;
                padding: 4px;
            }}
            QListView::item {{
                min-height: 28px;
                padding: 6px 8px;
            }}
            """
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget#root {{
                background: {COLORS["canvas"]};
                color: {COLORS["text"]};
                font-family: "Microsoft YaHei UI", "Segoe UI";
                font-size: 11pt;
            }}
            QFrame#sidebar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #111827, stop:1 #172033);
            }}
            QLabel#brand {{
                color: #f8fafc;
                font-size: 24pt;
                font-weight: 800;
            }}
            QLabel#tagline {{
                color: #9fb2c8;
                font-size: 10pt;
            }}
            QLabel#sidebarNote {{
                color: #b8c4d4;
                line-height: 1.5;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 12px;
            }}
            QPushButton[nav="true"] {{
                text-align: left;
                padding: 12px 14px;
                border-radius: 8px;
                border: 1px solid transparent;
                background: transparent;
                color: #cbd5e1;
                font-size: 11pt;
                font-weight: 700;
            }}
            QPushButton[nav="true"]:hover {{
                background: rgba(255, 255, 255, 0.07);
                color: #ffffff;
            }}
            QPushButton[nav="true"]:checked {{
                background: #0f766e;
                color: #ffffff;
                border-color: #2dd4bf;
            }}
            QFrame#workspace {{
                background: {COLORS["canvas"]};
            }}
            QLabel#pageTitle {{
                color: {COLORS["text"]};
                font-size: 22pt;
                font-weight: 800;
            }}
            QLabel#pageSubtitle {{
                color: {COLORS["muted"]};
                font-size: 10.5pt;
            }}
            QFrame#surface {{
                background: {COLORS["surface"]};
                border: 1px solid {COLORS["line"]};
                border-radius: 8px;
            }}
            QFrame#advancedPanel {{
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }}
            QFrame#metricCard {{
                background: {COLORS["surface"]};
                border: 1px solid {COLORS["line"]};
                border-radius: 8px;
            }}
            QLabel#metricTitle {{
                color: {COLORS["muted"]};
                font-size: 9.5pt;
                font-weight: 700;
            }}
            QLabel#metricValue {{
                color: {COLORS["text"]};
                font-size: 22pt;
                font-weight: 800;
            }}
            QLabel#sectionTitle {{
                color: {COLORS["text"]};
                font-size: 13pt;
                font-weight: 800;
            }}
            QLabel#fieldLabel, QLabel#inlineCaption {{
                color: {COLORS["muted"]};
                font-size: 9.5pt;
                font-weight: 700;
            }}
            QFrame#dropPanel {{
                background: #f8fafc;
                border: 1px dashed #9fb2c8;
                border-radius: 8px;
            }}
            QFrame#dropPanel:hover {{
                border-color: {COLORS["teal"]};
                background: #f0fdfa;
            }}
            QLabel#dropTitle {{
                color: {COLORS["text"]};
                font-size: 12pt;
                font-weight: 800;
            }}
            QLabel#dropHint {{
                color: {COLORS["muted"]};
                font-size: 9.5pt;
            }}
            QLabel#dropPath {{
                color: {COLORS["teal_dark"]};
                font-size: 9pt;
            }}
            QLineEdit, QComboBox, QSpinBox {{
                min-height: 34px;
                border-radius: 7px;
                border: 1px solid #cbd5e1;
                background: #ffffff;
                padding: 4px 10px;
                color: {COLORS["text"]};
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border: 1px solid {COLORS["teal"]};
            }}
            QSpinBox {{
                padding-right: 10px;
            }}
            QToolButton#stepButton {{
                min-width: 24px;
                max-width: 24px;
                min-height: 15px;
                max-height: 15px;
                padding: 0;
                border-radius: 4px;
                border: 1px solid #cbd5e1;
                background: #f8fafc;
                color: {COLORS["muted"]};
                font-size: 8pt;
                font-weight: 800;
            }}
            QToolButton#stepButton:hover {{
                background: #eef2f7;
                color: {COLORS["text"]};
            }}
            QComboBox::drop-down {{
                width: 28px;
                border: 0;
                border-left: 1px solid #d9e2ec;
                background: #f8fafc;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }}
            QComboBox QAbstractItemView {{
                background: #ffffff;
                color: {COLORS["text"]};
                border: 1px solid #cbd5e1;
                selection-background-color: #ccfbf1;
                selection-color: {COLORS["text"]};
                outline: 0;
            }}
            QCheckBox {{
                color: {COLORS["text"]};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #64748b;
                background: #ffffff;
            }}
            QCheckBox::indicator:hover {{
                border-color: {COLORS["teal"]};
                background: #f0fdfa;
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid {COLORS["teal_dark"]};
                background: {COLORS["teal"]};
            }}
            QCheckBox::indicator:unchecked {{
                border: 1px solid #64748b;
                background: #ffffff;
            }}
            QCheckBox::indicator:disabled {{
                border-color: #cbd5e1;
                background: #eef2f7;
            }}
            QPushButton {{
                min-height: 34px;
                padding: 6px 14px;
                border-radius: 8px;
                font-weight: 800;
            }}
            QPushButton[variant="primary"] {{
                color: #ffffff;
                border: 1px solid {COLORS["teal"]};
                background: {COLORS["teal"]};
            }}
            QPushButton[variant="primary"]:hover {{
                background: {COLORS["teal_dark"]};
            }}
            QPushButton[variant="secondary"] {{
                color: {COLORS["text"]};
                border: 1px solid #cbd5e1;
                background: #ffffff;
            }}
            QPushButton[variant="secondary"]:hover {{
                background: #f1f5f9;
                border-color: #9fb2c8;
            }}
            QPushButton[variant="ghost"] {{
                color: {COLORS["muted"]};
                border: 1px solid transparent;
                background: transparent;
            }}
            QPushButton[variant="ghost"]:hover {{
                color: {COLORS["text"]};
                background: #eef2f7;
            }}
            QPushButton:disabled {{
                color: #98a2b3;
                background: #eef2f7;
                border-color: #e4e7ec;
            }}
            QTableWidget#resultTable {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #edf2f7;
                background: #ffffff;
                alternate-background-color: #f8fafc;
                selection-background-color: #ccfbf1;
                selection-color: {COLORS["text"]};
            }}
            QHeaderView::section {{
                background: #eef2f7;
                color: {COLORS["text"]};
                font-weight: 800;
                border: 0;
                border-right: 1px solid #dde5ef;
                padding: 9px 8px;
            }}
            QListWidget#issueList {{
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                background: #ffffff;
                padding: 6px;
            }}
            QLabel#statusLabel {{
                color: {COLORS["muted"]};
                font-size: 10pt;
            }}
            """
        )

    def _switch_mode(self, mode: str) -> None:
        if self.thread is not None:
            return
        self.mode = mode
        is_verify = mode == "verify"
        self.hash_nav.setChecked(not is_verify)
        self.verify_nav.setChecked(is_verify)
        self.mode_title.setText("校验 MD5 文件" if is_verify else "计算文件 MD5")
        self.mode_subtitle.setText(
            "导入 .md5 清单，对当前目录中的文件做一致性检查。"
            if is_verify
            else "批量扫描目录，生成标准 MD5 行，可复制或导出。"
        )
        self.start_button.setText("开始校验" if is_verify else "开始计算")
        self.copy_button.setText("复制实际 MD5 行" if is_verify else "复制 MD5 行")
        self._set_headers()
        for widget in self.checksum_widgets:
            widget.setVisible(is_verify)
        for widget in self.filter_widgets:
            widget.setVisible(not is_verify)
        for widget in self.output_widgets:
            widget.setVisible(not is_verify)
        for widget in self.hash_option_widgets:
            widget.setVisible(not is_verify)
        self.filter_combo.setEnabled(not is_verify)
        self.recursive_check.setEnabled(not is_verify)
        self._reset_summary()

    def _toggle_advanced_options(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setText("收起高级选项" if checked else "显示高级选项")

    def _set_headers(self) -> None:
        if self.mode == "verify":
            headers = ["期望 MD5", "文件名", "实际 MD5", "大小", "状态", "说明"]
        else:
            headers = ["MD5", "文件名", "大小", "状态", "说明"]
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        stretch_column = 1
        for column in range(len(headers)):
            mode = QHeaderView.ResizeMode.Stretch if column == stretch_column else QHeaderView.ResizeMode.ResizeToContents
            self.result_table.horizontalHeader().setSectionResizeMode(column, mode)

    def _start_job(self) -> None:
        directory = Path(self.directory_edit.text().strip()).expanduser()
        if not directory.exists() or not directory.is_dir():
            self._show_warning("请选择一个有效目录。")
            return

        self._clear_results()
        params: dict[str, object] = {
            "directory": str(directory),
            "threads": normalize_thread_count(self.threads_spin.value()),
        }
        if self.mode == "verify":
            checksum = Path(self.checksum_edit.text().strip()).expanduser()
            if not checksum.exists() or not checksum.is_file():
                self._show_warning("请选择一个有效的 .md5 校验文件。")
                return
            params["checksum"] = str(checksum)
        else:
            output_text = self.output_edit.text().strip()
            params.update(
                {
                    "filter_text": self.filter_combo.currentText(),
                    "output": output_text or None,
                    "output_format": FORMAT_LABELS["MD5 列表"],
                    "recursive": self.recursive_check.isChecked(),
                }
            )

        self._set_running(True)
        self.worker = JobWorker(self.mode, params)
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.status_changed.connect(self._set_status)
        self.worker.progress_changed.connect(self._set_progress)
        self.worker.hash_result_ready.connect(self._append_hash_result)
        self.worker.verification_result_ready.connect(self._append_verification_result)
        self.worker.issues_ready.connect(self._set_issues)
        self.worker.finished.connect(self._finish_job)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._release_thread)
        self.thread.start()

    def _stop_job(self) -> None:
        if self.worker:
            self.worker.request_stop()
            self._set_status("正在停止当前任务...")
            self.stop_button.setEnabled(False)

    def _finish_job(self, payload: dict[str, object]) -> None:
        self._set_running(False)
        error = payload.get("error")
        if error:
            self._set_status("任务失败")
            self._show_error(str(error))
            details = payload.get("traceback")
            if details:
                self._add_issue("运行错误", str(details))
            return

        self.output_summary = payload.get("output_summary")  # type: ignore[assignment]
        self.issues = list(payload.get("issues", []))  # type: ignore[arg-type]
        if self.mode == "verify":
            self.verify_results = list(payload.get("results", []))  # type: ignore[arg-type]
            self._reload_verification_table()
            summary = summarize_verification_results(self.verify_results, self.issues)
            self._apply_summary(summary.total, summary.succeeded, summary.failed, summary.warnings)
            self._set_status("校验完成")
        else:
            self.hash_results = list(payload.get("results", []))  # type: ignore[arg-type]
            self._reload_hash_table()
            summary = summarize_hash_results(self.hash_results, self.issues)
            self._apply_summary(summary.total, summary.succeeded, summary.failed, summary.warnings)
            if self.output_summary:
                self._set_status(f"完成，结果已保存到 {self.output_summary.output_path}")
            else:
                self._set_status("完成，结果已在界面中展示")

        if self._has_attention():
            QMessageBox.warning(self, APP_TITLE, "任务已完成，但有文件需要处理。请查看右侧提醒。")

    def _release_thread(self) -> None:
        self.thread = None
        self.worker = None

    def _append_hash_result(self, result: FileHashResult) -> None:
        self.hash_results.append(result)
        self._append_hash_row(result)

    def _append_verification_result(self, result: VerificationResult) -> None:
        self.verify_results.append(result)
        self._append_verification_row(result)

    def _append_hash_row(self, result: FileHashResult) -> None:
        row_data = build_hash_rows([result])[0]
        self._append_table_row(
            [row_data.md5, row_data.file_name, row_data.size, row_data.status, row_data.detail],
            row_data.severity,
        )

    def _append_verification_row(self, result: VerificationResult) -> None:
        row_data = build_verification_rows([result])[0]
        self._append_table_row(
            [
                row_data.expected_md5,
                row_data.file_name,
                row_data.actual_md5,
                row_data.size,
                row_data.status,
                row_data.detail,
            ],
            row_data.severity,
        )

    def _append_table_row(self, values: list[str], severity: str) -> None:
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            if column == len(values) - 2:
                item.setForeground(self._severity_color(severity))
                font = QFont()
                font.setBold(True)
                item.setFont(font)
            self.result_table.setItem(row, column, item)

    def _reload_hash_table(self) -> None:
        self.result_table.setRowCount(0)
        for result in self.hash_results:
            self._append_hash_row(result)

    def _reload_verification_table(self) -> None:
        self.result_table.setRowCount(0)
        for result in self.verify_results:
            self._append_verification_row(result)

    def _set_issues(self, issues: list[ScanIssue]) -> None:
        self.issues = list(issues)
        self.issue_list.clear()
        if not self.issues:
            self.issue_list.addItem("暂无提醒")
            return
        for issue in self.issues:
            self._add_issue(str(issue.path), issue.message)

    def _add_issue(self, title: str, message: str) -> None:
        if self.issue_list.count() == 1 and self.issue_list.item(0).text() == "暂无提醒":
            self.issue_list.clear()
        item = QListWidgetItem(f"{title}\n{message}")
        item.setForeground(QColor(COLORS["warning"]))
        self.issue_list.addItem(item)

    def _clear_results(self) -> None:
        self.result_table.setRowCount(0)
        self.issue_list.clear()
        self.issue_list.addItem("暂无提醒")
        self.hash_results = []
        self.verify_results = []
        self.issues = []
        self.output_summary = None
        self.progress.setValue(0)
        self.progress.setFormat("0 / 0")
        self._reset_summary()
        self._set_status("就绪")

    def _copy_md5_lines(self) -> None:
        if self.mode == "verify":
            selected_files = self._selected_file_names()
            rows = [
                result
                for result in self.verify_results
                if result.actual_md5 and (not selected_files or result.entry.relative_path in selected_files)
            ]
            text = "\n".join(f"{result.actual_md5}  {result.entry.relative_path}" for result in rows)
        else:
            selected_files = self._selected_file_names()
            rows = [
                result
                for result in self.hash_results
                if not selected_files or result.relative_path in selected_files
            ]
            text = format_md5_copy_lines(rows)

        if not text:
            self._show_warning("没有可复制的 MD5 行。")
            return
        QGuiApplication.clipboard().setText(text)
        self._set_status("已复制 MD5 行")

    def _selected_file_names(self) -> set[str]:
        selected_rows = {index.row() for index in self.result_table.selectedIndexes()}
        if not selected_rows:
            return set()
        file_column = 1
        names: set[str] = set()
        for row in selected_rows:
            item = self.result_table.item(row, file_column)
            if item:
                names.add(item.text())
        return names

    def _open_output_folder(self) -> None:
        folder: Path | None = None
        if self.output_summary:
            folder = self.output_summary.output_path.parent
        elif self.output_edit.text().strip():
            folder = Path(self.output_edit.text().strip()).expanduser().resolve().parent
        if not folder or not folder.exists():
            self._show_warning("当前没有可打开的输出目录。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _browse_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择目录", self.directory_edit.text() or str(Path.home()))
        if selected:
            self.directory_edit.setText(selected)

    def _browse_checksum(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择 MD5 文件",
            self.checksum_edit.text() or str(Path.home()),
            "MD5 files (*.md5 *.txt);;All files (*)",
        )
        if selected:
            self.checksum_edit.setText(selected)

    def _browse_output(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "保存结果",
            self.output_edit.text() or str(Path.home() / "md5_results.md5"),
            "MD5 list (*.md5);;All files (*)",
        )
        if selected:
            self.output_edit.setText(selected)

    def _set_directory_from_drop(self, value: str) -> None:
        path = Path(value)
        if path.is_file():
            path = path.parent
        self.directory_edit.setText(str(path))

    def _set_checksum_from_drop(self, value: str) -> None:
        path = Path(value)
        if path.is_file():
            self.checksum_edit.setText(str(path))
            self._switch_mode("verify")

    def dragEnterEvent(self, event):  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802 - Qt API
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.is_dir():
            self.directory_edit.setText(str(path))
        elif path.suffix.lower() in {".md5", ".txt"}:
            self.checksum_edit.setText(str(path))
            self._switch_mode("verify")
        else:
            self.directory_edit.setText(str(path.parent))
        event.acceptProposedAction()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.hash_nav.setEnabled(not running)
        self.verify_nav.setEnabled(not running)

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _set_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress.setFormat(f"{done} / {total}")

    def _reset_summary(self) -> None:
        if self.mode == "verify":
            self.metric_total.set_title("校验项")
            self.metric_success.set_title("一致")
            self.metric_failed.set_title("异常")
            self.metric_warnings.set_title("提醒")
        else:
            self.metric_total.set_title("文件总数")
            self.metric_success.set_title("成功")
            self.metric_failed.set_title("失败")
            self.metric_warnings.set_title("提醒")
        self._apply_summary(0, 0, 0, 0)

    def _apply_summary(self, total: int, succeeded: int, failed: int, warnings: int) -> None:
        self.metric_total.set_value(total)
        self.metric_success.set_value(succeeded)
        self.metric_failed.set_value(failed)
        self.metric_warnings.set_value(warnings)
        if hasattr(self, "metrics_panel"):
            self.metrics_panel.setVisible(any((total, succeeded, failed, warnings)))

    def _has_attention(self) -> bool:
        if self.issues:
            return True
        if self.mode == "verify":
            return any(not result.ok for result in self.verify_results)
        return any(not result.ok for result in self.hash_results)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, APP_TITLE, message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, APP_TITLE, message)

    def _severity_color(self, severity: str) -> QColor:
        if severity == "success":
            return QColor(COLORS["success"])
        if severity == "warning":
            return QColor(COLORS["warning"])
        if severity == "error":
            return QColor(COLORS["error"])
        return QColor(COLORS["text"])


class QTableProgress(QFrame):
    """Slim progress bar with text overlay."""

    def __init__(self):
        super().__init__()
        self._value = 0
        self._maximum = 0
        self._format = "0 / 0"
        self.setObjectName("progressBar")
        self.setMinimumHeight(12)
        self.setMaximumHeight(12)

    def setRange(self, minimum: int, maximum: int) -> None:  # noqa: N802 - Qt-style compatibility
        self._value = max(minimum, min(self._value, maximum))
        self._maximum = maximum
        self.update()

    def setValue(self, value: int) -> None:  # noqa: N802 - Qt-style compatibility
        self._value = max(0, min(value, self._maximum))
        self.update()

    def setFormat(self, value: str) -> None:  # noqa: N802 - Qt-style compatibility
        self._format = value
        self.setToolTip(value)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        from PySide6.QtGui import QPainter

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d9e2ec"))
        painter.drawRoundedRect(rect, 6, 6)
        if self._maximum:
            width = int(rect.width() * (self._value / self._maximum))
            fill = rect.adjusted(0, 0, -(rect.width() - width), 0)
            painter.setBrush(QColor(COLORS["teal"]))
            painter.drawRoundedRect(fill, 6, 6)


def main() -> int:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setStyle("Fusion")
    window = MD5MateWindow()
    window.show()
    if owns_app:
        return app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
