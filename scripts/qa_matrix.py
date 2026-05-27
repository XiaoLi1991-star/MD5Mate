"""Run a broad pre-release QA matrix for MD5Mate."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PYTHON = sys.executable


def main() -> int:
    checks = [
        ("compileall", check_compileall),
        ("pytest all", lambda: run([PYTHON, "-m", "pytest", "-q"])),
        ("pytest core/output", lambda: run([PYTHON, "-m", "pytest", "tests/test_core_output.py", "-q"])),
        ("pytest filters", lambda: run([PYTHON, "-m", "pytest", "tests/test_filters.py", "-q"])),
        ("pytest verification", lambda: run([PYTHON, "-m", "pytest", "tests/test_verification.py", "-q"])),
        ("pytest ui presenters", lambda: run([PYTHON, "-m", "pytest", "tests/test_ui_presenters.py", "-q"])),
        ("pytest qt layout", lambda: run([PYTHON, "-m", "pytest", "tests/test_qt_gui_layout.py", "-q"])),
        ("pytest qt functional", lambda: run([PYTHON, "-m", "pytest", "tests/test_qt_gui_functional.py", "-q"])),
        ("thread count normalization", check_thread_count_normalization),
        ("filter preset parsing", check_filter_preset_parsing),
        ("md5 parser issue reporting", check_md5_parser_issue_reporting),
        ("verification path traversal guard", check_verification_path_guard),
        ("gui no-output calculation", check_gui_no_output_calculation),
        ("gui clipboard md5 format", check_gui_clipboard_format),
        ("gui verify mode visibility", check_gui_verify_mode_visibility),
        ("packaged exe starts", check_packaged_exe_starts),
        ("screenshot asset metadata", check_screenshot_asset_metadata),
        ("readme screenshot links", check_readme_screenshot_links),
        ("no gif or mp4 demo assets", check_no_gif_or_mp4_demo_assets),
        ("source text encoding sanity", check_source_text_encoding),
        ("pyproject metadata", check_pyproject_metadata),
        ("build script dry inspection", check_build_script),
    ]

    failures: list[tuple[str, str]] = []
    for index, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"{index:02d} PASS {name}")
        except Exception as error:  # noqa: BLE001 - QA runner reports all failure text.
            print(f"{index:02d} FAIL {name}: {error}")
            failures.append((name, str(error)))
            break

    if failures:
        return 1

    print(f"QA matrix passed: {len(checks)} checks")
    return 0


def run(command: list[str], *, env: dict[str, str] | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    merged_env = os.environ.copy()
    merged_env["PYTHONPATH"] = str(SRC)
    if env:
        merged_env.update(env)
    completed = subprocess.run(command, cwd=ROOT, env=merged_env, capture_output=True, text=True, timeout=timeout)
    if completed.returncode != 0:
        raise AssertionError(_command_failure(command, completed))
    return completed


def run_code(code: str, *, env: dict[str, str] | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return run([PYTHON, "-c", textwrap.dedent(code)], env=env, timeout=timeout)


def check_compileall() -> None:
    run([PYTHON, "-m", "compileall", "src", "tests", "main.py", "build.py"])


def check_thread_count_normalization() -> None:
    run_code(
        """
        from md5_tool.core import normalize_thread_count
        assert normalize_thread_count(0) == 1
        assert normalize_thread_count(9999) == 64
        assert normalize_thread_count('bad', default=5) == 5
        """
    )


def check_filter_preset_parsing() -> None:
    run_code(
        """
        from pathlib import Path
        from md5_tool.filters import file_matches, parse_filter_text
        assert parse_filter_text('所有文件 (*)') == ['*']
        patterns = parse_filter_text('压缩文件 (*.zip,*.rar,*.7z)')
        assert file_matches(Path('release.ZIP'), patterns)
        assert not file_matches(Path('manual.txt'), patterns)
        """
    )


def check_md5_parser_issue_reporting() -> None:
    run_code(
        """
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from md5_tool.verification import parse_md5_file
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checksums.md5'
            path.write_text('d41d8cd98f00b204e9800998ecf8427e  empty.txt\\nnot-md5\\n', encoding='utf-8')
            entries, issues = parse_md5_file(path)
            assert len(entries) == 1
            assert len(issues) == 1
        """
    )


def check_verification_path_guard() -> None:
    run_code(
        """
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from md5_tool.verification import verify_md5_file
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'
            root.mkdir()
            md5 = Path(tmp) / 'checksums.md5'
            md5.write_text(f\"{'0' * 32}  ../outside.txt\\n\", encoding='utf-8')
            results, _ = verify_md5_file(md5, root, threads=1)
            assert len(results) == 1
            assert results[0].status == 'error'
        """
    )


def check_gui_no_output_calculation() -> None:
    run_code(
        """
        import os, sys, tempfile, time
        from pathlib import Path
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from md5_tool.qt_gui import MD5MateWindow
        app = QApplication.instance() or QApplication(sys.argv)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.txt').write_text('alpha', encoding='utf-8')
            window = MD5MateWindow()
            window.show()
            app.processEvents()
            window.directory_edit.setText(str(root))
            window.output_edit.setText('')
            window.start_button.click()
            deadline = time.time() + 8
            while time.time() < deadline and window.thread is not None:
                app.processEvents()
                time.sleep(0.03)
            assert window.thread is None
            assert len(window.hash_results) == 1
            assert not (root / 'md5_results.md5').exists()
            window.close()
        """,
        env={"QT_QPA_PLATFORM": "offscreen"},
    )


def check_gui_clipboard_format() -> None:
    run_code(
        """
        import os, sys
        from pathlib import Path
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from md5_tool.models import FileHashResult
        from md5_tool.qt_gui import MD5MateWindow
        app = QApplication.instance() or QApplication(sys.argv)
        window = MD5MateWindow()
        window.hash_results = [FileHashResult(Path('ok.txt'), 'ok.txt', 2, md5='444bcb3a3fcf8389296c49467f27e1d6')]
        window._copy_md5_lines()
        assert QApplication.clipboard().text() == '444bcb3a3fcf8389296c49467f27e1d6  ok.txt'
        window.close()
        """,
        env={"QT_QPA_PLATFORM": "offscreen"},
    )


def check_gui_verify_mode_visibility() -> None:
    run_code(
        """
        import os, sys
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from md5_tool.qt_gui import MD5MateWindow
        app = QApplication.instance() or QApplication(sys.argv)
        window = MD5MateWindow()
        window.show()
        app.processEvents()
        window._switch_mode('verify')
        app.processEvents()
        assert window.checksum_drop.isVisible()
        assert not window.filter_combo.isVisible()
        assert window.threads_spin.isVisible()
        assert not hasattr(window, 'advanced_toggle')
        window.close()
        """,
        env={"QT_QPA_PLATFORM": "offscreen"},
    )


def check_packaged_exe_starts() -> None:
    exe = ROOT / "dist" / "MD5Mate.exe"
    if not exe.exists():
        raise AssertionError("dist/MD5Mate.exe does not exist")
    process = subprocess.Popen([str(exe)], cwd=ROOT)
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            if _windows_title_exists("MD5Mate"):
                return
            time.sleep(0.25)
        raise AssertionError("MD5Mate window did not appear")
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()


def check_screenshot_asset_metadata() -> None:
    from PIL import Image

    for relative_path in screenshot_asset_paths():
        path = ROOT / relative_path
        if not path.exists():
            raise AssertionError(f"README screenshot is missing: {relative_path}")
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size[0] >= 1000
            assert image.size[1] >= 650
        assert path.stat().st_size < 1_000_000


def check_readme_screenshot_links() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for relative_path in screenshot_asset_paths():
        assert f"]({relative_path})" in readme, f"README does not reference {relative_path}"


def check_no_gif_or_mp4_demo_assets() -> None:
    demo_assets = ROOT / "docs" / "assets"
    leftovers = [path for pattern in ("*.gif", "*.mp4") for path in demo_assets.glob(pattern)]
    assert not leftovers, f"old demo media should be removed: {leftovers}"


def screenshot_asset_paths() -> tuple[str, ...]:
    return (
        "docs/assets/md5mate-hash-results.png",
        "docs/assets/md5mate-verify-results.png",
        "docs/assets/md5mate-verify-attention.png",
    )


def check_source_text_encoding() -> None:
    for path in [*Path(ROOT / "src").rglob("*.py"), ROOT / "README.md", ROOT / "CHANGELOG.md"]:
        text = path.read_text(encoding="utf-8")
        assert "\ufffd" not in text, f"replacement character found in {path}"
        assert "锟斤拷" not in text, f"mojibake marker found in {path}"


def check_pyproject_metadata() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PySide6" in text
    assert "Intended Audience :: End Users/Desktop" in text


def check_build_script() -> None:
    text = (ROOT / "build.py").read_text(encoding="utf-8")
    assert "--windowed" in text
    assert "--collect-all" not in text
    assert "PyInstaller" in text


def _windows_title_exists(title: str) -> bool:
    if not sys.platform.startswith("win"):
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = False

    def callback(hwnd, _lparam):
        nonlocal found
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value == title:
                found = True
                return False
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback)
    user32.EnumWindows(enum_proc, 0)
    return found


def _command_failure(command: list[str], completed: subprocess.CompletedProcess) -> str:
    return "\n".join(
        [
            f"command failed: {' '.join(command)}",
            f"exit code: {completed.returncode}",
            "--- stdout ---",
            completed.stdout,
            "--- stderr ---",
            completed.stderr,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
