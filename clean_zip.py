"""ZIP cleaner used by the Streamlit ZIP tab.

The cleaner intentionally does not use any background-removal library.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".gif"}


def _is_candidate(file_name: str) -> bool:
    return "_images_" in Path(file_name).stem


def clean_zip_bytes(
    zip_bytes: bytes,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[bytes, dict[str, int]]:
    """Clean a ZIP according to the image naming convention.

    Rules:
      * Only filenames containing ``_images_`` are processed.
      * ``*_images_1.ext`` is the first image and is renamed to
        ``{parent_folder}_1.ext`` while preserving its original extension.
      * Other ``*_images_*`` files are deleted.
      * Files without ``_images_`` are untouched.
      * If the target already exists, the source first image is deleted and
        counted as skipped.
      * Renames are performed with ``os.replace``.
      * No rembg or other background-removal processing is performed.
    """
    stats = {
        "scanned": 0,
        "candidates": 0,
        "renamed": 0,
        "deleted": 0,
        "skipped_existing": 0,
    }

    output = io.BytesIO()
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
                stem = Path(file_name).stem

                if not stem.endswith("_images_1"):
                    os.remove(source_path)
                    stats["deleted"] += 1
                    continue

                folder_name = os.path.basename(root)
                if not folder_name:
                    continue

                target_path = os.path.join(
                    root,
                    f"{folder_name}_1{Path(file_name).suffix}",
                )

                if os.path.normcase(os.path.abspath(source_path)) == os.path.normcase(
                    os.path.abspath(target_path)
                ):
                    continue

                if os.path.exists(target_path):
                    os.remove(source_path)
                    stats["skipped_existing"] += 1
                    continue

                os.replace(source_path, target_path)
                stats["renamed"] += 1

        files_to_write = []
        for root, _, files in os.walk(temp_dir):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                arcname = os.path.relpath(file_path, temp_dir)
                files_to_write.append((file_path, arcname))

        total = len(files_to_write)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as result_zip:
            for processed, (file_path, arcname) in enumerate(files_to_write, 1):
                result_zip.write(file_path, arcname)
                if progress_callback:
                    progress_callback(processed, total)

    return output.getvalue(), stats


if __name__ == "__main__":
    print("clean_zip.py: import clean_zip_bytes() to clean ZIP archives.")
