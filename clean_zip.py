"""ZIP cleaner used by the Streamlit ZIP tab.

The cleaner keeps the first *_images_1 image from each folder, converts it
into PNG, flattens all results into one output ZIP, and removes other
*_images_* variants. No background-removal library is used.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".gif"}


def _is_candidate(file_name: str) -> bool:
    return "_images_" in Path(file_name).stem


def _is_first_image(file_name: str) -> bool:
    path = Path(file_name)
    return path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.endswith("_images_1")


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

    Rules:
      * Only filenames containing ``_images_`` are processed.
      * ``*_images_1.ext`` is converted to PNG and renamed to
        ``{parent_folder}_1.png``.
      * Other ``*_images_*`` files are deleted.
      * Files without ``_images_`` are ignored by the cleaner and are not
        included in the result ZIP.
      * If the target name already exists, the source is discarded and counted
        as skipped.
      * The resulting ZIP contains all selected images at its root (no folders).
      * No rembg or background-removal processing is performed.
    """
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
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as source_zip:
            source_zip.extractall(temp_dir)

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
