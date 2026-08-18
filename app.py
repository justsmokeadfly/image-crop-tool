import io
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

APP_VERSION = "1.0"
APP_NAME = f"Обработчик изображений (веб) v{APP_VERSION}"
SUPPORTED_INPUTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif")

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide")


# ---------------------------------------------------------------------------
# Логика кропа — перенесена из оригинального desktop-скрипта без изменений
# ---------------------------------------------------------------------------

def smart_crop_with_margin(img, margin_px, size, background):
    """Автоматическая обрезка пустых полей (близких к белому) по краям."""
    bg_color = (255, 255, 255) if background == "JPG" else (0, 0, 0, 0)

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    bbox = img.getbbox()

    if not bbox or bbox == (0, 0, img.width, img.height):
        rgb_img = img.convert("RGB")
        rgb_img.load()
        threshold = 245

        width, height = rgb_img.size
        pixels = rgb_img.load()

        def is_empty_col(x):
            for y in range(height):
                r, g, b = pixels[x, y]
                if not (r > threshold and g > threshold and b > threshold):
                    return False
            return True

        def is_empty_row(y):
            for x in range(width):
                r, g, b = pixels[x, y]
                if not (r > threshold and g > threshold and b > threshold):
                    return False
            return True

        left_bound = int(width * 0.05)
        left_empty = all(is_empty_col(x) for x in range(left_bound)) if left_bound else True

        right_bound = width - int(width * 0.05)
        right_empty = all(is_empty_col(x) for x in range(width - 1, right_bound - 1, -1)) if right_bound < width else True

        top_bound = int(height * 0.05)
        top_empty = all(is_empty_row(y) for y in range(top_bound)) if top_bound else True

        bottom_bound = height - int(height * 0.05)
        bottom_empty = all(is_empty_row(y) for y in range(height - 1, bottom_bound - 1, -1)) if bottom_bound < height else True

        new_left, new_right, new_top, new_bottom = 0, width, 0, height

        if left_empty:
            for x in range(width):
                if not is_empty_col(x):
                    new_left = max(0, x - 5)
                    break
        if right_empty:
            for x in range(width - 1, -1, -1):
                if not is_empty_col(x):
                    new_right = min(width, x + 5)
                    break
        if top_empty:
            for y in range(height):
                if not is_empty_row(y):
                    new_top = max(0, y - 5)
                    break
        if bottom_empty:
            for y in range(height - 1, -1, -1):
                if not is_empty_row(y):
                    new_bottom = min(height, y + 5)
                    break

        bbox = (new_left, new_top, new_right, new_bottom)

    if not bbox:
        bbox = (0, 0, img.width, img.height)

    return _finish_crop(img, bbox, margin_px, size, background, bg_color)


def manual_crop_with_margin(img, margin_px, size, background, top, bottom, left, right):
    """Обрезка на заданное число пикселей с каждой стороны."""
    width, height = img.size

    top = min(top, height - 1)
    bottom = min(bottom, height - 1)
    left = min(left, width - 1)
    right = min(right, width - 1)

    new_left = left
    new_top = top
    new_right = width - right
    new_bottom = height - bottom

    if new_right <= new_left:
        new_right = new_left + 1
    if new_bottom <= new_top:
        new_bottom = new_top + 1

    bbox = (new_left, new_top, new_right, new_bottom)
    bg_color = (255, 255, 255) if background == "JPG" else (0, 0, 0, 0)
    return _finish_crop(img, bbox, margin_px, size, background, bg_color)


def no_crop_with_margin(img, margin_px, size, background):
    """Без обрезки — просто вписать изображение в холст с отступом."""
    bbox = (0, 0, img.width, img.height)
    bg_color = (255, 255, 255) if background == "JPG" else (0, 0, 0, 0)
    return _finish_crop(img, bbox, margin_px, size, background, bg_color)


def _finish_crop(img, bbox, margin_px, size, background, bg_color):
    cropped = img.crop(bbox)

    cw, ch = cropped.size
    scale = min(
        (size - margin_px * 2) / max(1, cw),
        (size - margin_px * 2) / max(1, ch),
    )

    new_w, new_h = max(1, int(cw * scale)), max(1, int(ch * scale))
    cropped = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    if background == "PNG":
        new_img = Image.new("RGBA", (size, size), bg_color)
    else:
        new_img = Image.new("RGB", (size, size), bg_color)

    paste_x = (size - new_w) // 2
    paste_y = (size - new_h) // 2

    if cropped.mode == "RGBA":
        new_img.paste(cropped, (paste_x, paste_y), cropped)
    else:
        new_img.paste(cropped, (paste_x, paste_y))

    return new_img


def get_effective_output_format(selected_format, file_name):
    if selected_format in ("PNG", "JPG"):
        return selected_format

    ext = Path(file_name).suffix.lower()
    if ext == ".png":
        return "PNG"
    if ext in (".jpg", ".jpeg"):
        return "JPG"
    if ext in (".gif", ".webp", ".tif", ".tiff"):
        return "PNG"
    return "JPG"


def process_one(img, file_name, size, margin, crop_mode, fmt, manual_vals):
    effective_format = get_effective_output_format(fmt, file_name)

    if crop_mode == "auto":
        processed = smart_crop_with_margin(img, margin, size, effective_format)
    elif crop_mode == "manual":
        top, bottom, left, right = manual_vals
        processed = manual_crop_with_margin(img, margin, size, effective_format, top, bottom, left, right)
    else:
        processed = no_crop_with_margin(img, margin, size, effective_format)

    if effective_format == "PNG":
        out_ext = ".png"
    else:
        out_ext = ".jpg"
        if processed.mode == "RGBA":
            processed = processed.convert("RGB")

    buf = io.BytesIO()
    if out_ext == ".png":
        processed.save(buf, "PNG")
    else:
        processed.save(buf, "JPEG", quality=95)
    buf.seek(0)

    out_name = f"{Path(file_name).stem}{out_ext}"
    return out_name, buf, processed


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🖼️ Обработчик изображений")
st.caption("Обрезка с отступом, вписывание в квадратный холст, конвертация формата")

with st.sidebar:
    st.header("Параметры")

    size = st.number_input("Размер холста (px)", min_value=10, max_value=10000, value=1200, step=10)
    margin = st.number_input("Отступ (px)", min_value=0, max_value=int(size // 2) - 1 if size > 1 else 0, value=min(10, max(0, size // 2 - 1)), step=1)

    fmt = st.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True,
                    help="AUTO — определяется по исходному расширению файла")

    crop_mode = st.radio(
        "Режим обрезки",
        ["auto", "manual", "none"],
        format_func=lambda v: {"auto": "Авто (обрезать пустые поля)", "manual": "Вручную (пиксели с каждой стороны)", "none": "Без обрезки"}[v],
    )

    manual_vals = (0, 0, 0, 0)
    if crop_mode == "manual":
        st.caption("Сколько пикселей срезать с каждой стороны:")
        c1, c2 = st.columns(2)
        top = c1.number_input("Сверху", min_value=0, value=0, step=1)
        bottom = c2.number_input("Снизу", min_value=0, value=0, step=1)
        left = c1.number_input("Слева", min_value=0, value=0, step=1)
        right = c2.number_input("Справа", min_value=0, value=0, step=1)
        manual_vals = (top, bottom, left, right)

    if margin * 2 >= size:
        st.error("Отступ должен быть меньше половины размера холста")

uploaded_files = st.file_uploader(
    "Загрузите изображения",
    type=[ext.strip(".") for ext in SUPPORTED_INPUTS],
    accept_multiple_files=True,
)

if uploaded_files and margin * 2 < size:
    results = []
    for uf in uploaded_files:
        try:
            img = Image.open(uf)
            img.load()
            out_name, buf, processed_img = process_one(
                img, uf.name, int(size), int(margin), crop_mode, fmt, manual_vals
            )
            results.append({"name": out_name, "buf": buf, "original": img, "processed": processed_img})
        except Exception as e:
            st.error(f"Ошибка при обработке {uf.name}: {e}")

    if results:
        st.subheader(f"Результат ({len(results)})")

        for r in results:
            col1, col2 = st.columns(2)
            with col1:
                st.image(r["original"], caption=f"До: {r['name']}", use_container_width=True)
            with col2:
                st.image(r["processed"], caption=f"После: {r['name']}", use_container_width=True)
            st.download_button(
                f"Скачать {r['name']}",
                data=r["buf"].getvalue(),
                file_name=r["name"],
                mime="image/png" if r["name"].endswith(".png") else "image/jpeg",
                key=f"dl_{r['name']}_{id(r)}",
            )
            st.divider()

        if len(results) > 1:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for r in results:
                    zf.writestr(r["name"], r["buf"].getvalue())
            zip_buf.seek(0)
            st.download_button(
                "📦 Скачать все (ZIP)",
                data=zip_buf.getvalue(),
                file_name="processed_images.zip",
                mime="application/zip",
            )
else:
    st.info("Загрузите одно или несколько изображений слева, чтобы начать.")
