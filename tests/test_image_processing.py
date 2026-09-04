import ast
import io
import zipfile
from pathlib import Path

from PIL import Image, ImageChops


APP = Path(__file__).resolve().parents[1] / "app_v4.py"


def _load_processing_functions():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    wanted = {"trim_background", "process_image", "collect_image_inputs"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    module = ast.fix_missing_locations(module)
    namespace = {
        "Image": Image,
        "ImageChops": ImageChops,
        "ImageResampling": Image.Resampling,
        "io": io,
        "zipfile": zipfile,
        "Path": Path,
        "MAX_IMAGE_FILE_BYTES": 50 * 1024 * 1024,
        "MAX_IMAGE_TOTAL_BYTES": 100 * 1024 * 1024,
        "MAX_IMAGE_FILES": 30,
        "MAX_IMAGE_PIXELS": 100_000_000,
        "MAX_IMAGE_DIMENSION": 10_000,
        "MAX_ZIP_BYTES": 300 * 1024 * 1024,
        "MAX_ZIP_ENTRIES": 500,
        "IMAGE_EXTENSIONS": ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif", "avif"],
    }
    exec(compile(module, str(APP), "exec"), namespace)
    return namespace["trim_background"], namespace["process_image"], namespace["collect_image_inputs"]


def test_trim_background_finds_object_on_white_canvas():
    trim_background, _, _ = _load_processing_functions()
    image = Image.new("RGB", (200, 100), "white")
    for x in range(60, 140):
        for y in range(20, 80):
            image.putpixel((x, y), (20, 20, 20))

    bbox = trim_background(image)

    assert bbox[0] <= 60
    assert bbox[1] <= 20
    assert bbox[2] >= 140
    assert bbox[3] >= 80


def test_trim_background_keeps_full_image_when_no_contrast():
    trim_background, _, _ = _load_processing_functions()
    image = Image.new("RGB", (120, 80), "white")

    assert trim_background(image) == (0, 0, 120, 80)


def test_process_image_produces_exact_requested_size_jpg():
    _, process_image, _ = _load_processing_functions()
    image = Image.new("RGB", (200, 100), "black")
    source = io.BytesIO()
    image.save(source, "PNG")

    name, data, mime = process_image(
        source.getvalue(), "test.png", 1200, 10, "none", "JPG", (0, 0, 0, 0), False
    )

    assert name == "test.jpg"
    assert mime == "image/jpeg"
    output = Image.open(io.BytesIO(data))
    assert output.size == (1200, 1200)
    assert output.mode == "RGB"


def test_process_image_png_transparency():
    _, process_image, _ = _load_processing_functions()
    image = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    source = io.BytesIO()
    image.save(source, "PNG")

    name, data, mime = process_image(
        source.getvalue(), "test.png", 200, 20, "none", "PNG", (0, 0, 0, 0), True
    )

    assert name == "test.png"
    assert mime == "image/png"
    output = Image.open(io.BytesIO(data))
    assert output.size == (200, 200)
    assert output.mode == "RGBA"
    assert output.getpixel((0, 0))[3] == 0
    assert output.getpixel((100, 100))[3] == 255


def test_process_image_auto_crop_and_encoding():
    _, process_image, _ = _load_processing_functions()
    image = Image.new("RGB", (80, 120), "white")
    for x in range(20, 60):
        for y in range(30, 90):
            image.putpixel((x, y), (20, 20, 20))
    source = io.BytesIO()
    image.save(source, "PNG")

    name, data, mime = process_image(
        source.getvalue(), "object.png", 300, 10, "auto", "PNG", (0, 0, 0, 0), False
    )

    assert name == "object.png"
    assert mime == "image/png"
    output = Image.open(io.BytesIO(data))
    assert output.size == (300, 300)
    assert output.format == "PNG"


def test_collect_image_inputs_extracts_images_from_zip_and_ignores_other_files():
    _, _, collect_image_inputs = _load_processing_functions()
    image = Image.new("RGB", (32, 24), "red")
    image_data = io.BytesIO()
    image.save(image_data, "PNG")

    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("folder/product.png", image_data.getvalue())
        archive.writestr("folder/readme.txt", "ignore me")

    class Upload:
        name = "products.zip"

        def getvalue(self):
            return archive_data.getvalue()

    items = collect_image_inputs([Upload()])

    assert len(items) == 1
    assert items[0][0] == "product.png"
    assert items[0][1] == image_data.getvalue()


def test_collect_image_inputs_renames_duplicate_archive_image_names():
    _, _, collect_image_inputs = _load_processing_functions()
    image_data = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(image_data, "PNG")

    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("one/product.png", image_data.getvalue())
        archive.writestr("two/product.png", image_data.getvalue())

    class Upload:
        name = "products.zip"

        def getvalue(self):
            return archive_data.getvalue()

    items = collect_image_inputs([Upload()])

    assert [item[0] for item in items] == ["product.png", "product_2.png"]


def test_collect_image_inputs_enforces_image_count_limit():
    _, _, collect_image_inputs = _load_processing_functions()
    image_data = io.BytesIO()
    Image.new("RGB", (2, 2), "black").save(image_data, "PNG")

    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w", zipfile.ZIP_DEFLATED) as archive:
        for index in range(31):
            archive.writestr(f"image_{index}.png", image_data.getvalue())

    class Upload:
        name = "too_many.zip"

        def getvalue(self):
            return archive_data.getvalue()

    try:
        collect_image_inputs([Upload()])
    except ValueError as exc:
        assert "30" in str(exc)
    else:
        raise AssertionError("Expected image count limit error")
