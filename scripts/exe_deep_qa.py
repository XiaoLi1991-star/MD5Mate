"""Run an extended, scenario-heavy QA pass against dist/MD5Mate.exe."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from exe_qa_matrix import (
    EXE,
    OK,
    RECURSIVE,
    START_HASH,
    START_VERIFY,
    VERIFY_NAV,
    ExeHarness,
    kill_md5mate,
    launched_app,
    wait_until,
)


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("target directory can be outside exe folder", check_target_directory_outside_exe_folder),
        ("long directory path stays compact in drop panel", check_long_directory_drop_panel_stays_compact),
        ("output stays UI-only when blank", check_blank_output_no_file),
        ("standard md5sum spacing in exported file", check_standard_md5sum_spacing),
        ("long output path keeps footer status compact", check_long_output_status_stays_compact),
        ("csv extension still writes md5sum lines", check_csv_extension_still_md5sum),
        ("txt extension still writes md5sum lines", check_txt_extension_still_md5sum),
        ("missing output parent folder is created", check_output_parent_created),
        ("pre-existing output file is excluded from scan", check_existing_output_excluded),
        ("output file is overwritten cleanly", check_output_overwrite),
        ("extensionless file is included by all-files filter", check_extensionless_all_filter),
        ("filter accepts comma-separated bare extensions", check_filter_bare_extensions),
        ("filter accepts semicolon wildcards case-insensitively", check_filter_semicolon_case_insensitive),
        ("filter preset includes zip and excludes txt", check_filter_preset_zip),
        ("no-match filter shows readable error", check_no_match_filter_error),
        ("recursive default includes nested files", check_recursive_default_nested),
        ("recursive toggle excludes nested files", check_recursive_toggle_excludes_nested),
        ("thread spinner min value hashes normally", check_thread_min_value),
        ("thread spinner max value hashes normally", check_thread_max_value),
        ("thread up and down triangle buttons change value", check_thread_stepper_buttons),
        ("unicode and space filenames hash correctly", check_unicode_space_filename),
        ("long filename hashes correctly", check_long_filename),
        ("many small files all appear", check_many_small_files),
        ("locked file becomes failed row without crashing", check_locked_file_failed_row),
        ("rerun after clear works in same session", check_clear_and_rerun_same_session),
        ("invalid directory warning is modal and recoverable", check_invalid_directory_recoverable),
        ("file path in target directory field is rejected", check_file_as_directory_rejected),
        ("verify standard md5sum record matches", check_verify_standard_record),
        ("verify binary md5sum star record matches", check_verify_binary_star_record),
        ("verify BSD record matches", check_verify_bsd_record),
        ("verify uppercase digest matches", check_verify_uppercase_digest),
        ("verify CRLF md5 file matches", check_verify_crlf_file),
        ("verify subdirectory relative path matches", check_verify_subdirectory_path),
        ("verify mismatch is reported", check_verify_mismatch),
        ("verify missing file is reported", check_verify_missing),
        ("verify path traversal is blocked", check_verify_path_traversal_blocked),
        ("verify malformed file shows readable error", check_verify_malformed_error),
        ("verify mixed valid and malformed lines keeps issues visible", check_verify_mixed_valid_and_bad_lines),
        ("verify duplicate entries produce duplicate rows", check_verify_duplicate_entries),
        ("verify invalid checksum path warns", check_verify_invalid_checksum_path),
        ("verify target directory outside checksum folder works", check_verify_target_outside_checksum_folder),
        ("switching modes does not leave output controls visible", check_switch_modes_output_visibility),
        ("advanced verify mode exposes thread control only", check_verify_advanced_thread_only),
        ("format selector is absent from packaged UI", check_no_format_selector),
        ("checkbox checked and unchecked states both clickable", check_recursive_checkbox_clickable_states),
        ("start button label changes by mode", check_start_button_labels),
        ("packaged exe can relaunch repeatedly", check_repeated_relaunch),
    ]

    failures: list[tuple[str, str]] = []
    for index, (name, check) in enumerate(checks, start=1):
        try:
            check()
            print(f"{index:02d} PASS {name}")
        except Exception as error:  # noqa: BLE001 - QA reports all actionable failure text.
            print(f"{index:02d} FAIL {name}: {error}")
            failures.append((name, str(error)))
            break
        finally:
            kill_md5mate()

    if failures:
        return 1
    print(f"Deep executable QA passed: {len(checks)} checks")
    return 0


def check_target_directory_outside_exe_folder() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeepOutside-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "outside.txt").write_text("outside", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("outside.txt")


def check_long_directory_drop_panel_stays_compact() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateLongPath-") as tmp, launched_app() as app:
        long_dir = Path(tmp)
        for index in range(8):
            long_dir = long_dir / f"very-long-directory-name-{index:02d}"
        long_dir.mkdir(parents=True)

        app.set_edit(0, str(long_dir))
        wait_until(
            lambda: any("\u2026" in text and "very-long-directory-name-07" in text for text in app.texts()),
            "long directory path was not elided in the drop panel",
        )

        path_label = next(
            control
            for control in app.controls("Text")
            if "\u2026" in control.element_info.name and "very-long-directory-name-07" in control.element_info.name
        )
        directory_edit = app.first("Edit", index=0)
        choose_button = app.first("Button", "\u9009\u62e9\u76ee\u5f55")

        assert directory_edit.rectangle().height() >= 34, "directory input was vertically compressed"
        assert choose_button.rectangle().height() >= 34, "directory browse button was vertically compressed"
        assert path_label.rectangle().bottom + 20 <= directory_edit.rectangle().top, "long path label overlaps directory input"


def check_blank_output_no_file() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("a.txt")
        assert not list(root.glob("md5_results.*"))


def check_standard_md5sum_spacing() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        output = root / "out.md5"
        app.run_hash(root, output=output)
        app.wait_table_contains("a.txt")
        expected = hashlib.md5(b"alpha").hexdigest()
        assert output.read_text(encoding="utf-8") == f"{expected}  a.txt\n"


def check_long_output_status_stays_compact() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateLongOutput-") as tmp, launched_app() as app:
        root = Path(tmp) / "input"
        root.mkdir()
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        output_dir = Path(tmp)
        for index in range(5):
            output_dir = output_dir / f"very-long-output-directory-{index:02d}"
        output_dir.mkdir(parents=True)
        output = output_dir / "result.md5"

        app.run_hash(root, output=output)
        app.wait_table_contains("a.txt")
        wait_until(lambda: output.exists(), "long output file was not created")

        status_items = [
            control
            for control in app.controls("Text")
            if "\u2026" in control.element_info.name and "result.md5" in control.element_info.name
        ]
        assert status_items, "footer status did not elide the long output path"
        status_rect = status_items[-1].rectangle()
        window_rect = app.window().rectangle()
        assert status_rect.width() <= 340, "footer status consumed too much width"
        assert status_rect.right <= window_rect.right - 12, "footer status overflowed the window"

        directory_edit = app.first("Edit", index=0)
        filter_combo = app.first("ComboBox")
        assert directory_edit.rectangle().bottom + 8 <= filter_combo.rectangle().top, "directory and filter rows touch"
        path_labels = [
            control
            for control in app.controls("Text")
            if "input" in control.element_info.name and "result.md5" not in control.element_info.name
        ]
        assert path_labels, "target directory drop panel path label was not visible"
        assert path_labels[-1].rectangle().bottom + 18 <= directory_edit.rectangle().top, "drop panel crowds directory row"


def check_csv_extension_still_md5sum() -> None:
    check_extension_output_is_md5sum("report.csv")


def check_txt_extension_still_md5sum() -> None:
    check_extension_output_is_md5sum("report.txt")


def check_extension_output_is_md5sum(filename: str) -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        output = root / filename
        app.run_hash(root, output=output)
        app.wait_table_contains("a.txt")
        content = output.read_text(encoding="utf-8")
        assert content == f"{hashlib.md5(b'alpha').hexdigest()}  a.txt\n"
        assert "MD5Mate" not in content
        assert "," not in content


def check_output_parent_created() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        output = root / "nested" / "reports" / "checksums.md5"
        app.run_hash(root, output=output)
        app.wait_table_contains("a.txt")
        assert output.exists()


def check_existing_output_excluded() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        output = root / "checksums.md5"
        output.write_text("old-content\n", encoding="utf-8")
        app.run_hash(root, output=output)
        app.wait_table_contains("a.txt")
        content = output.read_text(encoding="utf-8")
        assert "checksums.md5" not in content
        assert "old-content" not in content


def check_output_overwrite() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("alpha", encoding="utf-8")
        output = root / "out.md5"
        output.write_text("stale\n", encoding="utf-8")
        app.run_hash(root, output=output)
        app.wait_table_contains("a.txt")
        assert "stale" not in output.read_text(encoding="utf-8")


def check_extensionless_all_filter() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "README").write_text("readme", encoding="utf-8")
        app.run_hash(root, filter_text="*.*")
        app.wait_table_contains("README")


def check_filter_bare_extensions() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("a", encoding="utf-8")
        (root / "b.log").write_text("b", encoding="utf-8")
        (root / "c.bin").write_bytes(b"c")
        app.run_hash(root, filter_text="txt,log")
        app.wait_table_contains("a.txt")
        table = table_text(app)
        assert "b.log" in table
        assert "c.bin" not in table


def check_filter_semicolon_case_insensitive() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "UPPER.TXT").write_text("upper", encoding="utf-8")
        (root / "notes.LOG").write_text("log", encoding="utf-8")
        (root / "skip.bin").write_bytes(b"skip")
        app.run_hash(root, filter_text="*.txt;*.log")
        app.wait_table_contains("UPPER.TXT")
        table = table_text(app)
        assert "notes.LOG" in table
        assert "skip.bin" not in table


def check_filter_preset_zip() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "release.ZIP").write_bytes(b"zip")
        (root / "readme.txt").write_text("readme", encoding="utf-8")
        app.run_hash(root, filter_text="压缩文件 (*.zip,*.rar,*.7z,*.tar,*.gz)")
        app.wait_table_contains("release.ZIP")
        assert "readme.txt" not in table_text(app)


def check_no_match_filter_error() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("a", encoding="utf-8")
        app.run_hash(root, filter_text="*.zip")
        app.wait_text_contains("没有找到符合筛选条件的文件")
        app.invoke("Button", OK)


def check_recursive_default_nested() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "sub").mkdir()
        (root / "sub" / "nested.txt").write_text("nested", encoding="utf-8")
        app.run_hash(root)
        wait_until(lambda: "sub/nested.txt" in table_text(app).replace("\\", "/"), "nested file missing")


def check_recursive_toggle_excludes_nested() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "top.txt").write_text("top", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "nested.txt").write_text("nested", encoding="utf-8")
        app.run_hash(root, recursive=False)
        app.wait_table_contains("top.txt")
        assert "nested.txt" not in table_text(app)


def check_thread_min_value() -> None:
    check_thread_value(1)


def check_thread_max_value() -> None:
    check_thread_value(64)


def check_thread_value(value: int) -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "a.txt").write_text("a", encoding="utf-8")
        app.run_hash(root, threads=value)
        app.wait_table_contains("a.txt")
        assert int(app.first("Spinner").iface_range_value.CurrentValue) == value


def check_thread_stepper_buttons() -> None:
    with launched_app() as app:
        app.open_advanced()
        spinner = app.first("Spinner")
        initial = int(spinner.iface_range_value.CurrentValue)
        app.invoke("Button", "▲")
        assert int(spinner.iface_range_value.CurrentValue) == min(initial + 1, 64)
        app.invoke("Button", "▼")
        assert int(spinner.iface_range_value.CurrentValue) == initial


def check_unicode_space_filename() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        name = "报告 final 版本.txt"
        (root / name).write_text("report", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains(name)


def check_long_filename() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        name = "long-" + ("a" * 120) + ".txt"
        (root / name).write_text("long", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains(name)


def check_many_small_files() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        for index in range(30):
            (root / f"file-{index:02d}.txt").write_text(str(index), encoding="utf-8")
        output = root / "many.md5"
        app.run_hash(root, output=output, threads=8)
        wait_until(
            lambda: output.exists() and len(output.read_text(encoding="utf-8").splitlines()) == 30,
            "export did not contain all 30 files",
        )
        content = output.read_text(encoding="utf-8")
        assert "file-00.txt" in content
        assert "file-29.txt" in content


def check_locked_file_failed_row() -> None:
    try:
        import win32con
        import win32file
    except ImportError:
        raise AssertionError("pywin32 is required for locked-file QA")

    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        locked = root / "locked.bin"
        locked.write_bytes(b"locked")
        handle = win32file.CreateFile(
            str(locked),
            win32con.GENERIC_READ,
            0,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            app.run_hash(root)
            app.wait_table_contains("locked.bin")
            assert "失败" in table_text(app)
        finally:
            handle.Close()


def check_clear_and_rerun_same_session() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "first.txt").write_text("first", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("first.txt")
        app.invoke("Button", "清空")
        (root / "first.txt").unlink()
        (root / "second.txt").write_text("second", encoding="utf-8")
        app.run_hash(root)
        app.wait_table_contains("second.txt")
        assert "first.txt" not in table_text(app)


def check_invalid_directory_recoverable() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        app.set_edit(0, str(root / "missing"))
        app.invoke("Button", START_HASH)
        app.wait_text_contains("请选择一个有效目录")
        app.invoke("Button", OK)
        (root / "ok.txt").write_text("ok", encoding="utf-8")
        app.set_edit(0, str(root))
        app.invoke("Button", START_HASH)
        app.wait_table_contains("ok.txt")


def check_file_as_directory_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        file_path = root / "not-a-dir.txt"
        file_path.write_text("x", encoding="utf-8")
        app.set_edit(0, str(file_path))
        app.invoke("Button", START_HASH)
        app.wait_text_contains("请选择一个有效目录")
        app.invoke("Button", OK)


def check_verify_standard_record() -> None:
    check_verify_content(lambda digest: f"{digest}  alpha.txt\n", "一致")


def check_verify_binary_star_record() -> None:
    check_verify_content(lambda digest: f"{digest} *alpha.txt\n", "一致")


def check_verify_bsd_record() -> None:
    check_verify_content(lambda digest: f"MD5 (alpha.txt) = {digest}\n", "一致")


def check_verify_uppercase_digest() -> None:
    check_verify_content(lambda digest: f"{digest.upper()}  alpha.txt\n", "一致")


def check_verify_crlf_file() -> None:
    check_verify_content(lambda digest: f"{digest}  alpha.txt\r\n", "一致")


def check_verify_content(line_builder: Callable[[str], str], expected_status: str) -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        digest = hashlib.md5(b"alpha").hexdigest()
        checksum = root / "checksums.md5"
        checksum.write_text(line_builder(digest), encoding="utf-8", newline="")
        app.run_verify(root, checksum)
        app.wait_table_contains("alpha.txt")
        assert expected_status in table_text(app)


def check_verify_subdirectory_path() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "sub").mkdir()
        (root / "sub" / "alpha.txt").write_text("alpha", encoding="utf-8")
        digest = hashlib.md5(b"alpha").hexdigest()
        checksum = root / "checksums.md5"
        checksum.write_text(f"{digest}  sub/alpha.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        wait_until(lambda: "sub/alpha.txt" in table_text(app).replace("\\", "/"), "subdirectory verify missing")
        assert "一致" in table_text(app)


def check_verify_mismatch() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        checksum = root / "checksums.md5"
        checksum.write_text(f"{'0' * 32}  alpha.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("alpha.txt")
        assert "不一致" in table_text(app)


def check_verify_missing() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        checksum = root / "checksums.md5"
        checksum.write_text(f"{'1' * 32}  missing.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("missing.txt")
        assert "缺失" in table_text(app)


def check_verify_path_traversal_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp) / "root"
        root.mkdir()
        checksum = Path(tmp) / "checksums.md5"
        checksum.write_text(f"{'2' * 32}  ../outside.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("../outside.txt")
        assert "错误" in table_text(app)


def check_verify_malformed_error() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        checksum = root / "bad.md5"
        checksum.write_text("not-md5\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_text_contains("没有可用的 MD5 记录")
        app.invoke("Button", OK)


def check_verify_mixed_valid_and_bad_lines() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        digest = hashlib.md5(b"alpha").hexdigest()
        checksum = root / "mixed.md5"
        checksum.write_text(f"{digest}  alpha.txt\nnot-md5\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("alpha.txt")
        assert "一致" in table_text(app)
        assert any("not-md5" in text or "第" in text for text in app.texts())


def check_verify_duplicate_entries() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        (root / "alpha.txt").write_text("alpha", encoding="utf-8")
        digest = hashlib.md5(b"alpha").hexdigest()
        checksum = root / "dup.md5"
        checksum.write_text(f"{digest}  alpha.txt\n{digest}  alpha.txt\n", encoding="utf-8")
        app.run_verify(root, checksum)
        app.wait_table_contains("alpha.txt")
        assert sum(1 for name in app.table_names() if name == "alpha.txt") == 2


def check_verify_invalid_checksum_path() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeep-") as tmp, launched_app() as app:
        root = Path(tmp)
        app.switch_verify()
        app.set_edit(0, str(root))
        app.set_edit(1, str(root / "missing.md5"))
        app.invoke("Button", START_VERIFY)
        app.wait_text_contains("请选择一个有效的 .md5 校验文件")
        app.invoke("Button", OK)


def check_verify_target_outside_checksum_folder() -> None:
    with tempfile.TemporaryDirectory(prefix="MD5MateDeepTarget-") as target_tmp, tempfile.TemporaryDirectory(
        prefix="MD5MateDeepChecksum-"
    ) as checksum_tmp, launched_app() as app:
        target = Path(target_tmp)
        checksum_dir = Path(checksum_tmp)
        (target / "alpha.txt").write_text("alpha", encoding="utf-8")
        digest = hashlib.md5(b"alpha").hexdigest()
        checksum = checksum_dir / "checksums.md5"
        checksum.write_text(f"{digest}  alpha.txt\n", encoding="utf-8")
        app.run_verify(target, checksum)
        app.wait_table_contains("alpha.txt")
        assert "一致" in table_text(app)


def check_switch_modes_output_visibility() -> None:
    with launched_app() as app:
        app.open_advanced()
        assert len(app.controls("Edit")) >= 3
        app.switch_verify()
        assert len(app.controls("Edit")) == 2
        app.invoke("CheckBox", "计算 MD5")
        assert len(app.controls("Edit")) >= 2


def check_verify_advanced_thread_only() -> None:
    with launched_app() as app:
        app.switch_verify()
        app.open_advanced()
        assert app.controls("Spinner")
        assert len(app.controls("ComboBox")) == 0


def check_no_format_selector() -> None:
    with launched_app() as app:
        app.open_advanced()
        visible_text = "\n".join(app.texts())
        assert "格式" not in visible_text
        assert "CSV" not in visible_text


def check_recursive_checkbox_clickable_states() -> None:
    with launched_app() as app:
        app.open_advanced()
        checkbox = app.first("CheckBox", RECURSIVE)
        assert checkbox.get_toggle_state() == 1
        app.invoke("CheckBox", RECURSIVE)
        assert checkbox.get_toggle_state() == 0
        app.invoke("CheckBox", RECURSIVE)
        assert checkbox.get_toggle_state() == 1


def check_start_button_labels() -> None:
    with launched_app() as app:
        assert app.controls("Button", START_HASH)
        app.invoke("CheckBox", VERIFY_NAV)
        assert app.controls("Button", START_VERIFY)


def check_repeated_relaunch() -> None:
    for _ in range(3):
        app = ExeHarness().launch()
        app.close()
    kill_md5mate()
    assert not subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Process -Name MD5Mate -ErrorAction SilentlyContinue"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def table_text(app: ExeHarness) -> str:
    return "\n".join(app.table_names())


if __name__ == "__main__":
    if not EXE.exists():
        raise SystemExit("dist/MD5Mate.exe does not exist. Run python build.py first.")
    raise SystemExit(main())
