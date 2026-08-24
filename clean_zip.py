"""Safe ZIP cleaner used by the Streamlit ZIP tab."""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".gif"}
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_ARCHIVE_FILES = 30


def _is_candidate(file_name: str) -> bool:
    return "_images_" in Path(file_name).stem


def _is_first_image(file_name: str) -> bool:
    path = Path(file_name)
    return path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.endswith("_images_1")


def _safe_member_path(temp_dir: str, member_name: str) -> str:
    """Return a safe extraction path or raise ValueError for unsafe ZIP names."""
    normalized = member_name.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Небезопасный путь в ZIP: {member_name!r}")
    destination = Path(temp_dir, *path.parts).resolve()
    root = Path(temp_dir).resolve()
    if destination != root and root not in destination.parents:
        raise ValueError(f"Небезопасный путь в ZIP: {member_name!r}")
    return str(destination)


def _extract_safely(source_zip: zipfile.ZipFile, temp_dir: str) -> None:
    infos = source_zip.infolist()
    if len(infos) > MAX_ARCHIVE_FILES:
        raise ValueError(f"В ZIP слишком много файлов: максимум {MAX_ARCHIVE_FILES}")

    total_uncompressed = 0
    for info in infos:
        if info.is_dir():
            continue
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ValueError(f"Распакованный ZIP слишком большой: максимум {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} МБ")
        destination = _safe_member_path(temp_dir, info.filename)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        with source_zip.open(info, "r") as src, open(destination, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)


def _convert_to_png(source_path: str, target_path: str) -> None:
    """Convert an image to PNG, preserving transparency when present."""
    with Image.open(source_path) as image:
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            converted = image.convert("RGBA")
        else:
            converted = image.convert("RGB")
        converted.save(target_path, format="PNG")


def clean_zip_bytes(
    zip_bytes: bytes,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[bytes, dict[str, int]]:
    """Clean a ZIP and return a flattened ZIP containing only first images.

    Only ``*_images_1`` image files are retained, converted to PNG and renamed
    to ``{parent_folder}_1.png``. Other ``*_images_*`` files are discarded.
    Non-matching files are intentionally excluded from the output.
    """
    if len(zip_bytes) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"ZIP слишком большой: максимум {MAX_ARCHIVE_BYTES // (1024 * 1024)} МБ")

    stats = {
        "scanned": 0,
        "candidates": 0,
        "renamed": 0,
        "converted": 0,
        "deleted": 0,
        "skipped_existing": 0,
    }

    output = io.BytesIO()
    selected: list[tuple[str, str]] = []
    used_names: set[str] = set()

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as source_zip:
                if source_zip.testzip() is not None:
                    raise ValueError("ZIP содержит повреждённый файл")
                _extract_safely(source_zip, temp_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError("Файл не является корректным ZIP-архивом") from exc

        for root, _, files in os.walk(temp_dir):
            for file_name in files:
                stats["scanned"] += 1
                if not _is_candidate(file_name):
                    continue

                stats["candidates"] += 1
                source_path = os.path.join(root, file_name)

                if not _is_first_image(file_name):
                    os.remove(source_path)
                    stats["deleted"] += 1
                    continue

                folder_name = os.path.basename(root)
                if not folder_name:
                    os.remove(source_path)
                    stats["deleted"] += 1
                    continue

                output_name = f"{folder_name}_1.png"
                if output_name.casefold() in used_names:
                    os.remove(source_path)
                    stats["skipped_existing"] += 1
                    continue

                target_path = os.path.join(root, output_name)
                if os.path.exists(target_path):
                    os.remove(source_path)
                    stats["skipped_existing"] += 1
                    continue

                _convert_to_png(source_path, target_path)
                os.remove(source_path)
                used_names.add(output_name.casefold())
                selected.append((target_path, output_name))
                stats["renamed"] += 1
                stats["converted"] += 1

        total = len(selected)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as result_zip:
            for processed, (file_path, arcname) in enumerate(selected, 1):
                result_zip.write(file_path, arcname)
                if progress_callback:
                    progress_callback(processed, total)

    return output.getvalue(), stats


if __name__ == "__main__":
    print("clean_zip.py: import clean_zip_bytes() to clean ZIP archives.")
