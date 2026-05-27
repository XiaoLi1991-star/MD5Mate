"""Build a standalone Windows executable with PyInstaller."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ICON_PATH = Path("assets") / "md5mate.ico"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build MD5Mate executable.")
    parser.add_argument("--debug", action="store_true", help="Build with a console for debugging.")
    parser.add_argument("--clean", action="store_true", help="Clean PyInstaller build files.")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    if args.clean:
        for path in (root / "build", root / "dist"):
            if path.exists():
                import shutil

                shutil.rmtree(path)
        for spec in root.glob("*.spec"):
            spec.unlink()
        print("Cleaned build artifacts.")
        return 0

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "MD5Mate",
        "--paths",
        str(root / "src"),
    ]
    icon = root / ICON_PATH
    if icon.exists():
        command.extend(["--icon", str(icon)])
        command.extend(["--add-data", f"{icon};assets"])
    if not args.debug:
        command.append("--windowed")
    command.append(str(root / "main.py"))

    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=root)
    if completed.returncode != 0:
        return completed.returncode

    output = root / "dist" / ("MD5Mate.exe" if sys.platform.startswith("win") else "MD5Mate")
    print(f"Build output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
