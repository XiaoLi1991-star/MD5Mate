"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from threading import Event

from .core import DEFAULT_CHUNK_SIZE, hash_files, normalize_thread_count, scan_files
from .output import save_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md5mate",
        description="批量计算文件 MD5，支持目录扫描、筛选、线程数和多种输出格式。",
    )
    parser.add_argument("directory", help="要扫描的目录")
    parser.add_argument("-f", "--filter", default="*", help='文件筛选，例如 "*"、"*.zip"、".txt,.log"')
    parser.add_argument("-o", "--output", default="md5.txt", help="输出文件路径")
    parser.add_argument(
        "--format",
        default="auto",
        choices=["auto", "md5", "csv", "txt"],
        help="输出格式；auto 会根据扩展名推断",
    )
    parser.add_argument(
        "-t",
        "--threads",
        default=None,
        help="用于计算的线程数，范围 1-64，默认按 CPU 自动选择",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="读取块大小，默认 1MB")
    parser.add_argument("--no-recursive", action="store_true", help="只扫描目录第一层")
    parser.add_argument("--strict", action="store_true", help="有任何文件失败时返回非零退出码")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        threads = normalize_thread_count(args.threads)
        root = Path(args.directory)
        output = Path(args.output)
        stop_event = Event()

        print(f"扫描目录: {root}")
        scan = scan_files(
            root,
            args.filter,
            recursive=not args.no_recursive,
            exclude_paths=[output],
            stop_event=stop_event,
        )
        if not scan.files:
            print("没有找到符合条件的文件。", file=sys.stderr)
            return 2

        print(f"找到 {len(scan.files)} 个文件，使用 {threads} 个线程计算。")

        def on_progress(_result, done: int, total: int) -> None:
            print(f"\r进度: {done}/{total}", end="", flush=True)

        results = hash_files(
            scan.files,
            root=scan.root,
            threads=threads,
            chunk_size=args.chunk_size,
            stop_event=stop_event,
            progress_callback=on_progress,
        )
        print()

        summary = save_results(
            results,
            output,
            output_format=args.format,
            root=scan.root,
            filter_text=args.filter,
            scan_issues=scan.issues,
        )

        print(
            f"完成: 成功 {summary.succeeded}，失败 {summary.failed}，"
            f"扫描提醒 {summary.scan_issues}。"
        )
        print(f"输出文件: {summary.output_path}")

        if summary.has_errors and args.strict:
            return 1
        return 0
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
    except Exception as error:  # noqa: BLE001 - CLI should turn unexpected errors into messages.
        print(f"错误: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
