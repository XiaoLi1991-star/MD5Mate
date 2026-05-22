"""Record a compact, path-masked MD5Mate demo GIF from the packaged EXE."""

from __future__ import annotations

import hashlib
import re
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from exe_qa_matrix import (
    COPY_HASH,
    EXE,
    START_HASH,
    START_VERIFY,
    ExeHarness,
    kill_md5mate,
    print_window,
    wait_until,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "md5mate-demo.gif"
CHECK_SHEET = ROOT / "docs" / "assets" / "md5mate-demo-contact-sheet.png"
PATH_PATTERN = re.compile(r"[A-Za-z]:\\")
TARGET_WIDTH = 960


def main() -> int:
    if not EXE.exists():
        raise SystemExit("dist/MD5Mate.exe is missing; run python build.py first.")

    frames: list[Image.Image] = []
    durations: list[int] = []
    app = ExeHarness().launch()
    try:
        with tempfile.TemporaryDirectory(prefix="MD5MateDemo-") as tmp:
            root = Path(tmp)
            release = root / "package.dat"
            readme = root / "readme.txt"
            release.write_bytes(b"release package")
            readme.write_text("tampered content", encoding="utf-8")
            checksum = root / "checksums.md5"
            checksum.write_text(
                "\n".join(
                    [
                        f"{md5_bytes(b'release package')}  package.dat",
                        f"{'0' * 32}  readme.txt",
                        f"{'1' * 32}  missing.iso",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            capture(app, frames, durations, 700)

            app.set_edit(0, str(root))
            capture(app, frames, durations, 700)

            app.invoke("Button", START_HASH)
            app.wait_table_contains("package.dat")
            app.invoke("Button", COPY_HASH)
            capture(app, frames, durations, 1100)

            app.switch_verify()
            capture(app, frames, durations, 550)

            app.set_edit(0, str(root))
            app.set_edit(1, str(checksum))
            capture(app, frames, durations, 700)

            app.invoke("Button", START_VERIFY)
            wait_until(
                lambda: "missing.iso" in "\n".join(app.table_names()),
                "verification result did not appear in demo recording",
            )
            capture(app, frames, durations, 1300)
    finally:
        app.close()
        kill_md5mate()

    save_gif(frames, durations, OUTPUT)
    save_contact_sheet(frames, CHECK_SHEET)
    validate_gif(OUTPUT)
    print(f"Recorded masked demo GIF: {OUTPUT}")
    print(f"Contact sheet for review: {CHECK_SHEET}")
    return 0


def capture(app: ExeHarness, frames: list[Image.Image], durations: list[int], duration: int) -> None:
    image = print_window(app.window().element_info.handle).convert("RGB")
    mask_sensitive_paths(image, app)
    frames.append(resize_for_demo(image))
    durations.append(duration)


def mask_sensitive_paths(image: Image.Image, app: ExeHarness) -> None:
    window_rect = app.window().rectangle()
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for control in app.controls():
        info = control.element_info
        value = info.name or ""
        if info.control_type == "Edit":
            try:
                value = control.get_value() or ""
            except Exception:  # noqa: BLE001 - some controls do not expose ValuePattern.
                value = ""
        if not looks_like_sensitive_path(value):
            continue
        rect = control.rectangle()
        x1 = max(0, rect.left - window_rect.left - 12)
        y1 = max(0, rect.top - window_rect.top - 14)
        x2 = min(image.width - 28, max(rect.right - window_rect.left + 12, image.width - 120))
        y2 = min(image.height, rect.bottom - window_rect.top + 46)
        if x2 <= x1 or y2 <= y1:
            continue
        draw.rounded_rectangle([x1, y1, x2, y2], radius=6, fill="#e8eef6", outline="#b8c6d9", width=1)
        label = "PATH HIDDEN"
        text_x = x1 + 10
        text_y = y1 + max(4, (y2 - y1 - 10) // 2)
        draw.text((text_x, text_y), label, fill="#475467", font=font)


def looks_like_sensitive_path(value: str) -> bool:
    return bool(value and PATH_PATTERN.search(value))


def resize_for_demo(image: Image.Image) -> Image.Image:
    if image.width <= TARGET_WIDTH:
        return image
    ratio = TARGET_WIDTH / image.width
    target_height = round(image.height * ratio)
    return image.resize((TARGET_WIDTH, target_height), Image.Resampling.LANCZOS)


def save_gif(frames: list[Image.Image], durations: list[int], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    palette_frames = [frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=96) for frame in frames]
    palette_frames[0].save(
        output,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def save_contact_sheet(frames: list[Image.Image], output: Path) -> None:
    columns = 2
    gutter = 14
    thumb_width = 480
    thumbs = []
    for frame in frames:
        ratio = thumb_width / frame.width
        thumbs.append(frame.resize((thumb_width, round(frame.height * ratio)), Image.Resampling.LANCZOS))
    rows = (len(thumbs) + columns - 1) // columns
    sheet_width = columns * thumb_width + (columns + 1) * gutter
    sheet_height = rows * thumbs[0].height + (rows + 1) * gutter
    sheet = Image.new("RGB", (sheet_width, sheet_height), "#f4f7fb")
    for index, thumb in enumerate(thumbs):
        row = index // columns
        column = index % columns
        x = gutter + column * (thumb_width + gutter)
        y = gutter + row * (thumb.height + gutter)
        sheet.paste(thumb, (x, y))
    sheet.save(output)


def validate_gif(path: Path) -> None:
    with Image.open(path) as image:
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            durations.append(image.info.get("duration", 0))
        assert image.n_frames == 6, f"expected 6 frames, got {image.n_frames}"
        assert image.width <= TARGET_WIDTH, f"GIF too wide: {image.width}"
        assert sum(durations) <= 6000, f"GIF is too slow: {sum(durations)}ms"
    assert path.stat().st_size < 1_200_000, f"GIF too large: {path.stat().st_size} bytes"


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
