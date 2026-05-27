"""Run a Windows executable QA matrix against dist/MD5Mate.exe.

This script intentionally drives the packaged GUI, not the source-tree Qt
objects. It is meant for release smoke testing on Windows before publishing a
fresh demo asset or binary.
"""

from __future__ import annotations

import ctypes
import hashlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

try:
    import psutil
    import win32gui
    import win32ui
    from PIL import Image, ImageStat
    from pywinauto import Desktop
except ImportError as error:  # pragma: no cover - local release tooling guard.
    raise SystemExit(
        "exe_qa_matrix.py requires pywinauto, pywin32, psutil and Pillow. "
        "Install them in the local QA environment, then rerun this script."
    ) from error


ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "MD5Mate.exe"

APP_TITLE = "MD5Mate"
HASH_NAV = "\u8ba1\u7b97 MD5"
VERIFY_NAV = "\u6821\u9a8c .md5"
START_HASH = "\u5f00\u59cb\u8ba1\u7b97"
START_VERIFY = "\u5f00\u59cb\u6821\u9a8c"
STOP = "\u505c\u6b62"
COPY_HASH = "\u590d\u5236 MD5 \u884c"
COPY_VERIFY = "\u590d\u5236\u5b9e\u9645 MD5 \u884c"
CLEAR = "\u6e05\u7a7a"
RECURSIVE = "\u9012\u5f52\u626b\u63cf\u5b50\u76ee\u5f55"
OK = "OK"


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("exe binary exists and has PE header", check_exe_binary),
        ("exe launches a single main window", check_launch_window),
        ("default UI exposes primary workflow", check_default_ui),
        ("key controls fit inside the window", check_controls_in_bounds),
        ("stop is disabled before a job starts", check_stop_initially_disabled),
        ("filter help/question button is absent", check_no_question_button),
        ("advanced options are fixed by default", check_advanced_fixed),
        ("advanced options keep output/thread controls aligned", check_advanced_controls_aligned),
        ("filter dropdown popup stays light themed", check_filter_dropdown_theme),
        ("hash mode displays results when output path is blank", check_hash_no_output_file),
        ("hash filtering includes txt and excludes bin", check_hash_filter_txt_only),
        ("recursive hashing includes nested files by default", check_recursive_default),
        ("recursive toggle can exclude nested files", check_recursive_off),
        ("md5 export writes standard checksum lines", check_md5_export),
        ("thread spinner accepts a release value", check_thread_spinner),
        ("copy button invokes on exact md5 filename rows", check_copy_hash_format),
        ("clear button removes visible hash results", check_clear_hash_results),
        ("hash table handles spaces and unicode filenames", check_unicode_and_space_filename),
        ("verify mode hides hash-only controls", check_verify_mode_layout),
        ("verify mode reports matched md5 entries", check_verify_match),
        ("verify mode reports mismatched md5 entries", check_verify_mismatch),
        ("verify mode reports missing files", check_verify_missing),
        ("hash and verify result pages stay isolated", check_hash_verify_pages_isolated),
        ("verify mode reports malformed md5 files", check_verify_malformed_file),
        ("invalid directory shows a warning dialog", check_invalid_directory_warning),
        ("repeated launch and cleanup leaves no app process", check_repeated_launch_cleanup),
    ]

    failures: list[tuple[str, str]] = []
    for index, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"{index:02d} PASS {name}")
        except Exception as error:  # noqa: BLE001 - QA runner prints actionable failure text.
            print(f"{index:02d} FAIL {name}: {error}")
            failures.append((name, str(error)))
            break

    kill_md5mate()
    if failures:
        return 1
    print(f"Executable QA matrix passed: {len(checks)} checks")
    return 0


class ExeHarness:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def launch(self) -> "ExeHarness":
        kill_md5mate()
        self.process = subprocess.Popen([str(EXE)], cwd=ROOT)
        deadline = time.time() + 25
        while time.time() < deadline:
            windows = self._owned_windows()
            if windows:
                window = largest_window(windows)
                set_window_bounds(window.element_info.handle)
                time.sleep(0.5)
                return self
            time.sleep(0.25)
        raise AssertionError("MD5Mate window did not appear")

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
        kill_md5mate()

    def window(self):
        windows = self._owned_windows()
        if not windows:
            raise AssertionError("MD5Mate window is not present")
        return largest_window(windows)

    def _owned_windows(self):
        windows = desktop().windows(title=APP_TITLE)
        process_ids = self._owned_process_ids()
        if process_ids:
            return [window for window in windows if window.element_info.process_id in process_ids]
        return windows

    def _owned_process_ids(self) -> set[int]:
        if not self.process:
            return set()
        try:
            root_process = psutil.Process(self.process.pid)
            return {root_process.pid, *(child.pid for child in root_process.children(recursive=True))}
        except psutil.Error:
            return set()

    def controls(self, control_type: str | None = None, name: str | None = None):
        matches = []
        for control in self.window().descendants():
            info = control.element_info
            if control_type and info.control_type != control_type:
                continue
            if name is not None and info.name != name:
                continue
            matches.append(control)
        return matches

    def first(self, control_type: str | None = None, name: str | None = None, index: int = 0):
        matches = self.controls(control_type, name)
        if len(matches) <= index:
            raise AssertionError(f"missing control: type={control_type!r} name={name!r} index={index}")
        return matches[index]

    def texts(self) -> list[str]:
        return [
            control.element_info.name
            for control in self.controls()
            if control.element_info.control_type in {"Text", "ListItem", "DataItem", "Header"}
        ]

    def table_names(self) -> list[str]:
        table = self.first("Table")
        return [control.element_info.name for control in table.descendants()]

    def set_edit(self, index: int, value: str) -> None:
        self.first("Edit", index=index).set_edit_text(value)

    def invoke(self, control_type: str, name: str, *, index: int = 0) -> None:
        self.first(control_type, name, index=index).invoke()
        time.sleep(0.25)

    def open_advanced(self) -> None:
        wait_until(lambda: bool(self.controls("Spinner")), "advanced options are not visible")

    def switch_verify(self) -> None:
        self.invoke("CheckBox", VERIFY_NAV)
        wait_until(lambda: any("\u6821\u9a8c MD5" in text for text in self.texts()), "verify mode did not open")

    def run_hash(
        self,
        directory: Path,
        *,
        filter_text: str | None = None,
        output: Path | None = None,
        recursive: bool = True,
        threads: int | None = None,
    ) -> None:
        needs_advanced = output is not None or threads is not None or not recursive
        if needs_advanced:
            self.open_advanced()
        self.set_edit(0, str(directory))
        if filter_text is not None:
            self.set_edit(1, filter_text)
        if output is not None:
            self.set_edit(2, str(output))
        if threads is not None:
            spinner = self.first("Spinner")
            spinner.iface_range_value.SetValue(float(threads))
        if not recursive:
            self.invoke("CheckBox", RECURSIVE)
        self.invoke("Button", START_HASH)

    def run_verify(self, directory: Path, checksum: Path) -> None:
        self.switch_verify()
        self.set_edit(0, str(directory))
        self.set_edit(1, str(checksum))
        self.invoke("Button", START_VERIFY)

    def wait_table_contains(self, token: str, timeout: float = 20) -> None:
        wait_until(lambda: any(token in name for name in self.table_names()), f"table never contained {token!r}", timeout)

    def wait_text_contains(self, token: str, timeout: float = 20) -> None:
        wait_until(lambda: any(token in text for text in self.texts()), f"text never contained {token!r}", timeout)


def check_exe_binary() -> None:
    assert EXE.exists(), f"{EXE} does not exist"
    assert EXE.stat().st_size > 30_000_000, "exe is unexpectedly small"
    with EXE.open("rb") as file:
        assert file.read(2) == b"MZ", "exe does not start with an MZ header"


def check_launch_window() -> None:
    with launched_app() as app:
        window = app.window()
        assert window.element_info.name == APP_TITLE
        assert window.rectangle().width() >= 1000
        assert len([w for w in desktop().windows(title=APP_TITLE) if w.rectangle().width() > 900]) == 1


def check_default_ui() -> None:
    with launched_app() as app:
        text = "\n".join(app.texts())
        assert "MD5Mate" in text
        assert "\u8ba1\u7b97\u6587\u4ef6 MD5" in text
        assert app.controls("Button", START_HASH)
        assert app.controls("Table")
        assert "\u6587\u4ef6\u540d" in text


def check_controls_in_bounds() -> None:
    with launched_app() as app:
        window_rect = app.window().rectangle()
        for control in app.controls():
            control_type = control.element_info.control_type
            if control_type not in {"Button", "CheckBox", "Edit", "ComboBox", "Table", "List", "Text"}:
                continue
            rect = control.rectangle()
            if rect.width() <= 0 or rect.height() <= 0:
                continue
            assert rect.left >= window_rect.left - 2, f"{control_type} clips left"
            assert rect.right <= window_rect.right + 2, f"{control_type} clips right"
            assert rect.top >= window_rect.top - 32, f"{control_type} clips top"
            assert rect.bottom <= window_rect.bottom + 2, f"{control_type} clips bottom"


def check_stop_initially_disabled() -> None:
    with launched_app() as app:
        assert not app.first("Button", STOP).is_enabled(), "Stop should be disabled before a job starts"


def check_no_question_button() -> None:
    with launched_app() as app:
        assert not app.controls("Button", "?"), "the filter question button should not be present"


def check_advanced_fixed() -> None:
    with launched_app() as app:
        assert app.controls("Spinner")
        assert app.controls("CheckBox", RECURSIVE)
        assert any(text == "\u8f93\u51fa" for text in app.texts())
        assert not any(text in {"\u663e\u793a\u9ad8\u7ea7\u9009\u9879", "\u6536\u8d77\u9ad8\u7ea7\u9009\u9879"} for text in app.texts())


def check_advanced_controls_aligned() -> None:
    with launched_app() as app:
        assert app.controls("Spinner")
        assert app.controls("CheckBox", RECURSIVE)
        assert len(app.controls("Edit")) >= 3
        assert len(app.controls("ComboBox")) == 1, "format selector should not be present"
        assert app.controls("Button", "\u25b2"), "thread increment triangle is missing"
        assert app.controls("Button", "\u25bc"), "thread decrement triangle is missing"
        output_edit = app.first("Edit", index=2)
        threads_spin = app.first("Spinner")
        assert output_edit.rectangle().right + 8 <= threads_spin.rectangle().left, "advanced controls overlap"


def check_filter_dropdown_theme() -> None:
    with launched_app() as app:
        main_handle = app.window().element_info.handle
        combo = app.first("ComboBox")
        combo.expand()
        time.sleep(0.5)
        popups = [
            window
            for window in desktop().windows(title=APP_TITLE)
            if window.element_info.handle != main_handle and window.rectangle().height() < 400
        ]
        assert popups, "filter dropdown popup did not open"
        image = print_window(popups[0].element_info.handle)
        mean_luminance = ImageStat.Stat(image.convert("L")).mean[0]
        assert mean_luminance > 220, f"dropdown popup is too dark: luminance={mean_luminance:.1f}"
        names = "\n".join(control.element_info.name for control in popups[0].descendants())
        assert "*.txt" in names
        combo.collapse()


def check_hash_no_output_file() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("alpha.txt")
        table = "\n".join(app.table_names())
        assert hashlib.md5(b"alpha").hexdigest() in table
        assert "alpha.txt" in table
        assert "5 B" in table
        assert "\u5b8c\u6210" in table
        assert not list(root.glob("md5_results.*")), "blank output path should not create a default output file"


def check_hash_filter_txt_only() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        (root / "beta.bin").write_bytes(b"beta")
        app.run_hash(root, filter_text="*.txt")
        app.wait_table_contains("alpha.txt")
        table = "\n".join(app.table_names())
        assert "alpha.txt" in table
        assert "beta.bin" not in table


def check_recursive_default() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "sub").mkdir()
        (root / "sub" / "nested.txt").write_text("nested", encoding="utf-8")
        app.run_hash(root)
        wait_until(
            lambda: "sub/nested.txt" in "\n".join(app.table_names()).replace("\\", "/"),
            "table never contained nested recursive result",
        )


def check_recursive_off() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "top.txt").write_text("top", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "nested.txt").write_text("nested", encoding="utf-8")
        app.run_hash(root, recursive=False)
        app.wait_table_contains("top.txt")
        table = "\n".join(app.table_names())
        assert "nested.txt" not in table


def check_md5_export() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        output = root / "checksums.md5"
        app.run_hash(root, output=output)
        app.wait_table_contains("alpha.txt")
        content = output.read_text(encoding="utf-8")
        assert f"{hashlib.md5(b'alpha').hexdigest()}  alpha.txt" in content


def check_thread_spinner() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("a", encoding="utf-8")
        app.run_hash(root, threads=4)
        spinner_value = int(app.first("Spinner").iface_range_value.CurrentValue)
        assert spinner_value == 4
        app.wait_table_contains("a.txt")


def check_copy_hash_format() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        expected = hashlib.md5(b"alpha").hexdigest()
        app.run_hash(root)
        app.wait_table_contains("alpha.txt")
        table = "\n".join(app.table_names())
        assert expected in table
        assert "alpha.txt" in table
        app.invoke("Button", COPY_HASH)
        assert app.controls("Table"), "copy action should not close or crash the result table"


def check_clear_hash_results() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("alpha.txt")
        app.invoke("Button", CLEAR)
        wait_until(lambda: "alpha.txt" not in "\n".join(app.table_names()), "clear did not remove hash result")


def check_unicode_and_space_filename() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "\u62a5\u544a final.txt").write_text("report", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("\u62a5\u544a final.txt")


def check_verify_mode_layout() -> None:
    with launched_app() as app:
        app.switch_verify()
        assert not app.controls("ComboBox"), "hash filter should be hidden in verify mode"
        text = "\n".join(app.texts())
        assert "\u671f\u671b MD5" in text
        assert "\u5b9e\u9645 MD5" in text


def check_verify_match() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        target = root / "alpha.txt"
        target.write_text("alpha", encoding="utf-8")
        expected = hashlib.md5(b"alpha").hexdigest()
        checksum = root / "checksums.md5"
        checksum.write_text(f"{expected}  alpha.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("alpha.txt")
        table = "\n".join(app.table_names())
        assert expected in table
        assert "5 B" in table
        assert "\u4e00\u81f4" in table
        app.invoke("Button", COPY_VERIFY)
        assert app.controls("Table"), "copy action should not close or crash the result table"


def check_verify_mismatch() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        checksum = root / "checksums.md5"
        checksum.write_text(f"{'0' * 32}  alpha.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("alpha.txt")
        assert "\u4e0d\u4e00\u81f4" in "\n".join(app.table_names())


def check_verify_missing() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        checksum = root / "checksums.md5"
        checksum.write_text(f"{'1' * 32}  missing.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("missing.txt")
        assert "\u7f3a\u5931" in "\n".join(app.table_names())


def check_hash_verify_pages_isolated() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "source.hashonly").write_text("source", encoding="utf-8")
        (root / "check.txt").write_text("check", encoding="utf-8")
        checksum = root / "checksums.md5"
        checksum.write_text(f"{hashlib.md5(b'check').hexdigest()}  check.txt\nnot-md5", encoding="utf-8")

        app.run_hash(root, filter_text="*.hashonly")
        app.wait_table_contains("source.hashonly")
        hash_table = "\n".join(app.table_names())
        assert "source.hashonly" in hash_table
        assert "check.txt" not in hash_table

        app.run_verify(root, checksum)
        app.wait_table_contains("check.txt")
        verify_table = "\n".join(app.table_names())
        assert "check.txt" in verify_table
        assert "checksums.md5" in verify_table
        assert "\u7b2c 2 \u884c" in verify_table
        assert "source.hashonly" not in verify_table

        app.invoke("CheckBox", HASH_NAV)
        app.wait_table_contains("source.hashonly")
        hash_table = "\n".join(app.table_names())
        assert "source.hashonly" in hash_table
        assert "checksums.md5" not in hash_table
        assert "check.txt" not in hash_table


def check_verify_malformed_file() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        root = Path(tmp)
        checksum = root / "bad.md5"
        checksum.write_text("not-md5\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_text_contains("\u6ca1\u6709\u53ef\u7528\u7684 MD5 \u8bb0\u5f55")
        app.invoke("Button", OK)


def check_invalid_directory_warning() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateExeQA-") as tmp, launched_app() as app:
        missing = Path(tmp) / "missing"
        app.set_edit(0, str(missing))
        app.invoke("Button", START_HASH)
        app.wait_text_contains("\u8bf7\u9009\u62e9\u4e00\u4e2a\u6709\u6548\u76ee\u5f55")
        app.invoke("Button", OK)


def check_repeated_launch_cleanup() -> None:
    for _ in range(2):
        app = ExeHarness().launch()
        app.close()
    assert not md5mate_processes(), "MD5Mate process remained after cleanup"


class launched_app:
    def __enter__(self) -> ExeHarness:
        self.app = ExeHarness().launch()
        return self.app

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.app.close()


def desktop() -> Desktop:
    return Desktop(backend="uia")


def largest_window(windows):
    return max(windows, key=lambda window: window.rectangle().width() * window.rectangle().height())


def set_window_bounds(hwnd: int) -> None:
    win32gui.SetWindowPos(hwnd, None, 80, 80, 1180, 760, 0)


def print_window(hwnd: int) -> Image.Image:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left
    height = bottom - top
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(bitmap)
    ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
    bitmap_info = bitmap.GetInfo()
    bitmap_bits = bitmap.GetBitmapBits(True)
    image = Image.frombuffer(
        "RGB",
        (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
        bitmap_bits,
        "raw",
        "BGRX",
        0,
        1,
    )
    win32gui.DeleteObject(bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    return image


def wait_until(predicate: Callable[[], bool], message: str, timeout: float = 20) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if predicate():
                return
        except Exception as error:  # noqa: BLE001 - transient UIA failures are retried.
            last_error = error
        time.sleep(0.25)
    if last_error:
        raise AssertionError(f"{message}; last error: {last_error}")
    raise AssertionError(message)


def md5mate_processes() -> list[psutil.Process]:
    processes: list[psutil.Process] = []
    for process in psutil.process_iter(["pid", "name"]):
        if process.info["name"] and process.info["name"].lower() == "md5mate.exe":
            processes.append(process)
    return processes


def kill_md5mate() -> None:
    for process in md5mate_processes():
        try:
            process.kill()
        except psutil.Error:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        if not md5mate_processes():
            return
        time.sleep(0.1)


if __name__ == "__main__":
    if not sys.platform.startswith("win"):
        raise SystemExit("Executable QA matrix is Windows-only.")
    raise SystemExit(main())
