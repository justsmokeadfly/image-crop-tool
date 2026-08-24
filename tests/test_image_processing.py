import ast
import io
from pathlib import Path

from PIL import Image, ImageChops


APP = Path(__file__).resolve().parents[1] / "app_v3.py"


def _load_processing_functions():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    wanted = {"trim_background", "crop_to_square"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {"Image": Image, "ImageChops": ImageChops}
    exec(compile(module, str(APP), "exec"), namespace)
    return namespace["trim_background"], namespace["crop_to_square"]


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


def test_crop_to_square_produces_exact_requested_size_and_margin():
    _, crop_to_square = _load_processing_functions()
    image = Image.new("RGB", (200, 100), "black")

    output = crop_to_square(image, (0, 0, 200, 100), margin=10, size=1200, fmt="JPG", transparent=False)

    assert output.size == (1200, 1200)
    assert output.mode == "RGB"


def test_crop_to_square_png_transparency():
    _, crop_to_square = _load_processing_functions()
    image = Image.new("RGBA", (100, 100), (255, 0, 0, 255))

    output = crop_to_square(image, (0, 0, 100, 100), margin=20, size=200, fmt="PNG", transparent=True)

    assert output.mode == "RGBA"
    assert output.getpixel((0, 0))[3] == 0
    assert output.getpixel((100, 100))[3] == 255


def test_output_can_be_encoded_as_png_and_jpeg():
    _, crop_to_square = _load_processing_functions()
    image = Image.new("RGB", (80, 120), "white")

    for fmt, expected in (("PNG", "PNG"), ("JPG", "JPEG")):
        output = crop_to_square(image, (0, 0, 80, 120), margin=10, size=300, fmt=fmt, transparent=False)
        buffer = io.BytesIO()
        output.save(buffer, expected)
        buffer.seek(0)
        reopened = Image.open(buffer)
        assert reopened.size == (300, 300)
        assert reopened.format == expected
