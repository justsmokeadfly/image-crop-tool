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
MAX_ARCHIVE_BYTES = 300 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1500 * 1024 * 1024
MAX_ARCHIVE_FILES = 500


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


def _extract_safely(
    source_zip: zipfile.ZipFile,
    temp_dir: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    infos = source_zip.infolist()
    file_infos = [info for info in infos if not info.is_dir()]
    if len(file_infos) > MAX_ARCHIVE_FILES:
        raise ValueError(f"В ZIP слишком много файлов: максимум {MAX_ARCHIVE_FILES}")

    total_uncompressed = 0
    total = len(file_infos)
    for processed, info in enumerate(file_infos, 1):
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
        if progress_callback:
            progress_callback(processed, total, "Распаковка")


def _convert_to_png(source_path: str, target_path: str) -> None:
    """Convert an image to PNG, preserving transparency when present."""
    with Image.open(source_path) as image:
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            converted = image.convert("RGBA")
        else:
            converted = image.convert("RGB")
        converted.save(target_path, format="PNG")


def _default_progress_callback() -> Callable[[int, int, str], None] | None:
    """Create a Streamlit progress bar when running inside the Streamlit app."""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx() is None:
            return None
    except Exception:
        return None

    progress = st.progress(0, text="Подготовка ZIP…")

    def update(processed: int, total: int, stage: str) -> None:
        stage_weights = {
            "Распаковка": (0.00, 0.45),
            "Обработка изображений": (0.45, 0.85),
            "Сборка ZIP": (0.85, 1.00),
        }
        start, end = stage_weights.get(stage, (0.0, 1.0))
        fraction = processed / total if total else 1.0
        value = start + (end - start) * fraction
        progress.progress(value, text=f"{stage} · {processed}/{total}")
        if value >= 1.0:
            progress.empty()

    return update


def clean_zip_bytes(
    zip_bytes: bytes,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[bytes, dict[str, int]]:
    """Clean a ZIP and return a flat ZIP containing only first images.

    Only ``*_images_1`` image files are retained, converted to PNG and renamed
    to ``{parent_folder}_1.png``. Other ``*_images_*`` files are discarded.
    Non-matching files are intentionally excluded from the output.
    All output files are stored at the ZIP root without folders.
    Output order follows the order of matching entries in the source ZIP.
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

    if progress_callback is None:
        progress_callback = _default_progress_callback()

    output = io.BytesIO()
    selected: list[tuple[str, str]] = []
    used_names: set[str] = set()

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as source_zip:
                if source_zip.testzip() is not None:
                    raise ValueError("ZIP содержит повреждённый файл")
                infos = source_zip.infolist()
                _extract_safely(source_zip, temp_dir, progress_callback)
        except zipfile.BadZipFile as exc:
            raise ValueError("Файл не является корректным ZIP-архивом") from exc

        total = len([info for info in infos if not info.is_dir()])
        for processed, info in enumerate(infos, 1):
            if info.is_dir():
                continue
            file_name = Path(info.filename).name
            stats["scanned"] += 1
            if not _is_candidate(file_name):
                if progress_callback:
                    progress_callback(processed, total, "Обработка изображений")
                continue

            stats["candidates"] += 1
            source_path = _safe_member_path(temp_dir, info.filename)

            if not _is_first_image(file_name):
                os.remove(source_path)
                stats["deleted"] += 1
                if progress_callback:
                    progress_callback(processed, total, "Обработка изображений")
                continue

            folder_name = Path(info.filename).parent.name
            if not folder_name:
                os.remove(source_path)
                stats["deleted"] += 1
                if progress_callback:
                    progress_callback(processed, total, "Обработка изображений")
                continue

            output_name = f"{folder_name}_1.png"
            if output_name.casefold() in used_names:
                os.remove(source_path)
                stats["skipped_existing"] += 1
                if progress_callback:
                    progress_callback(processed, total, "Обработка изображений")
                continue

            target_path = os.path.join(os.path.dirname(source_path), output_name)
            if os.path.exists(target_path):
                os.remove(source_path)
                stats["skipped_existing"] += 1
                if progress_callback:
                    progress_callback(processed, total, "Обработка изображений")
                continue

            _convert_to_png(source_path, target_path)
            os.remove(source_path)
            used_names.add(output_name.casefold())
            selected.append((target_path, output_name))
            stats["renamed"] += 1
            stats["converted"] += 1
            if progress_callback:
                progress_callback(processed, total, "Обработка изображений")

        total_selected = len(selected)
        if total_selected == 0 and progress_callback:
            progress_callback(1, 1, "Сборка ZIP")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as result_zip:
            for processed, (file_path, arcname) in enumerate(selected, 1):
                result_zip.write(file_path, arcname=arcname)
                if progress_callback:
                    progress_callback(processed, total_selected, "Сборка ZIP")

    return output.getvalue(), stats


if __name__ == "__main__":
    print("clean_zip.py: import clean_zip_bytes() to clean ZIP archives.")
