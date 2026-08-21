import io
import zipfile

from clean_zip import clean_zip_bytes


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


def read_zip(data):
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_first_image_is_renamed_and_other_images_are_deleted():
    source = make_zip(
        {
            "product/folder_images_1.jpg": b"first",
            "product/folder_images_2.png": b"second",
            "product/folder_images_3.webp": b"third",
            "product/description.txt": b"keep",
        }
    )

    result, stats = clean_zip_bytes(source)
    files = read_zip(result)

    assert "product/folder_1.jpg" in files
    assert files["product/folder_1.jpg"] == b"first"
    assert "product/folder_images_1.jpg" not in files
    assert "product/folder_images_2.png" not in files
    assert "product/folder_images_3.webp" not in files
    assert files["product/description.txt"] == b"keep"
    assert stats["renamed"] == 1
    assert stats["deleted"] == 2


def test_non_matching_files_are_untouched():
    source = make_zip(
        {
            "folder/photo.jpg": b"photo",
            "folder/photo_1.png": b"other",
            "folder/readme.txt": b"text",
        }
    )

    result, stats = clean_zip_bytes(source)
    files = read_zip(result)

    assert files == {
        "folder/photo.jpg": b"photo",
        "folder/photo_1.png": b"other",
        "folder/readme.txt": b"text",
    }
    assert stats["candidates"] == 0
    assert stats["renamed"] == 0
    assert stats["deleted"] == 0


def test_existing_target_deletes_source_and_skips_rename():
    source = make_zip(
        {
            "folder/folder_1.png": b"existing",
            "folder/folder_images_1.png": b"source",
            "folder/folder_images_2.png": b"extra",
        }
    )

    result, stats = clean_zip_bytes(source)
    files = read_zip(result)

    assert files["folder/folder_1.png"] == b"existing"
    assert "folder/folder_images_1.png" not in files
    assert "folder/folder_images_2.png" not in files
    assert stats["skipped_existing"] == 1
    assert stats["deleted"] == 1


def test_first_image_keeps_original_extension():
    source = make_zip(
        {
            "folder/item_images_1.webp": b"webp",
            "folder/item_images_2.jpg": b"extra",
        }
    )

    result, _ = clean_zip_bytes(source)
    files = read_zip(result)

    assert "folder/item_1.webp" in files
    assert "folder/item_1.png" not in files
