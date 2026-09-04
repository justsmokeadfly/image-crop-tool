import io
import zipfile

import pytest
from PIL import Image

from clean_zip import MAX_ARCHIVE_BYTES, clean_zip_bytes


def make_image(fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, format=fmt)
    return buf.getvalue()


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


def read_zip(data):
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_first_image_is_converted_to_png_and_other_images_are_deleted():
    source = make_zip(
        {
            "product/folder_images_1.jpg": make_image("JPEG"),
            "product/folder_images_2.png": make_image("PNG"),
            "product/folder_images_3.webp": make_image("WEBP"),
            "product/description.txt": b"ignore",
        }
    )

    result, stats = clean_zip_bytes(source)
    files = read_zip(result)

    assert list(files) == ["product_1.png"]
    assert all("/" not in name and "\\" not in name for name in files)
    assert Image.open(io.BytesIO(files["product_1.png"])).format == "PNG"
    assert stats["renamed"] == 1
    assert stats["converted"] == 1
    assert stats["deleted"] == 2


def test_non_matching_files_are_excluded_from_result():
    source = make_zip({"folder/photo.jpg": b"photo", "folder/readme.txt": b"text"})

    result, stats = clean_zip_bytes(source)

    assert read_zip(result) == {}
    assert stats["candidates"] == 0
    assert stats["renamed"] == 0
    assert stats["deleted"] == 0


def test_duplicate_output_names_from_different_folders_are_allowed():
    source = make_zip(
        {
            "same/shared_images_1.png": make_image(),
            "other/shared_images_1.png": make_image(),
        }
    )

    result, stats = clean_zip_bytes(source)
    files = read_zip(result)

    assert list(files) == ["same_1.png", "other_1.png"]
    assert all("/" not in name and "\\" not in name for name in files)
    assert stats["skipped_existing"] == 0


def test_existing_target_inside_folder_is_skipped():
    source = make_zip(
        {
            "folder/folder_1.png": make_image(),
            "folder/folder_images_1.png": make_image(),
            "folder/folder_images_2.png": make_image(),
        }
    )

    result, stats = clean_zip_bytes(source)
    files = read_zip(result)

    assert list(files) == []
    assert stats["skipped_existing"] == 1
    assert stats["deleted"] == 1


def test_zip_path_traversal_is_rejected():
    source = make_zip({"../evil.txt": b"bad"})

    with pytest.raises(ValueError, match="Небезопасный путь"):
        clean_zip_bytes(source)


def test_absolute_zip_path_is_rejected():
    source = make_zip({"/evil.txt": b"bad"})

    with pytest.raises(ValueError, match="Небезопасный путь"):
        clean_zip_bytes(source)


def test_archive_size_limit_is_enforced():
    with pytest.raises(ValueError, match="ZIP слишком большой"):
        clean_zip_bytes(b"0" * (MAX_ARCHIVE_BYTES + 1))
