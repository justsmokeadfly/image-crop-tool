import ast
import io
from pathlib import Path

from PIL import Image, ImageChops


APP = Path(__file__).resolve().parents[1] / "app_v4.py"


def _load_processing_functions():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    wanted = {"trim_background", "process_image"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    module = ast.fix_missing_locations(module)
    namespace = {
        "Image": Image,
        "ImageChops": ImageChops,
        "ImageResampling": Image.Resampling,
        "io": io,
        "Path": Path,
        "MAX_IMAGE_FILE_BYTES": 50 * 1024 * 1024,
        "MAX_IMAGE_PIXELS": 100_000_000,
        "MAX_IMAGE_DIMENSION": 10_000,
    }
    exec(compile(module, str(APP), "exec"), namespace)
    return namespace["trim_background"], namespace["process_image"]


def test_trim_background_finds_object_on_white_canvas():
    trim_background, _ = _load_processing_functions()
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
    trim_background, _ = _load_processing_functions()
    image = Image.new("RGB", (120, 80), "white")

    assert trim_background(image) == (0, 0, 120, 80)


def test_process_image_produces_exact_requested_size_jpg():
    _, process_image = _load_processing_functions()
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
    _, process_image = _load_processing_functions()
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
    _, process_image = _load_processing_functions()
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
