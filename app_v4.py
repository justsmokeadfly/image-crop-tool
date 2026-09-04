import hashlib
import io
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from PIL import Image, ImageChops

try:
    import pillow_avif  # noqa: F401
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

from clean_zip import clean_zip_bytes

APP_VERSION = "3.0"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"] + (["avif"] if AVIF_SUPPORTED else [])
MAX_IMAGE_FILES = 30
MAX_IMAGE_FILE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_TOTAL_BYTES = 100 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000
MAX_IMAGE_DIMENSION = 10_000
MAX_ZIP_BYTES = 300 * 1024 * 1024
MAX_ZIP_ENTRIES = 500

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container{max-width:1500px;padding-top:.75rem;padding-bottom:1.5rem}
.hero h1{margin:0 0 .1rem;font-size:clamp(1.65rem,2.6vw,2.25rem);letter-spacing:-.04em}.hero p{opacity:.7;margin:0 0 .55rem;font-size:.9rem}
[data-testid="stTabs"] button{font-size:.95rem;font-weight:700;padding:.45rem .8rem}
[data-testid="stFileUploaderDropzone"]{border-radius:10px;min-height:105px;padding:.55rem}
[data-testid="stFileUploaderDropzone"] > div{padding:.35rem}
[data-testid="stFileUploaderFile"]{padding:.2rem .4rem;margin:.2rem 0}
[data-testid="stFileUploaderFileData"]{padding:.15rem .3rem}
[data-testid="stVerticalBlock"]{gap:.55rem}
[data-testid="stExpander"]{margin-bottom:.35rem}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button{min-height:2.35rem;padding:.35rem .7rem}
[data-testid="stAlert"]{padding:.55rem .8rem}
[data-testid="stProgressBar"]{margin:.25rem 0}
</style>
""", unsafe_allow_html=True)
st.markdown(f'<div class="hero"><h1>🖼️ Обработчик изображений</h1><p>Обрезка изображений, изменение размера и очистка ZIP-архивов · v{APP_VERSION}</p></div>', unsafe_allow_html=True)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_archive_name(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}_{secrets.token_hex(4)}.zip"


def crop_signature(uploaded):
    if not uploaded:
        return None
    return tuple((f.name, f.size, content_hash(f.getvalue())) for f in uploaded)


def reset_crop_state(uploaded):
    sig = crop_signature(uploaded)
    if sig != st.session_state.get("crop_input_signature"):
        st.session_state.crop_input_signature = sig
        st.session_state.pop("crop_results", None)
        st.session_state.pop("crop_errors", None)


def resize_signature(uploaded, size):
    if not uploaded:
        return None
    return (int(size), tuple((f.name, f.size, content_hash(f.getvalue())) for f in uploaded))


def reset_resize_state(uploaded, size):
    sig = resize_signature(uploaded, size)
    if sig != st.session_state.get("resize_input_signature"):
        st.session_state.resize_input_signature = sig
        st.session_state.pop("resize_results", None)
        st.session_state.pop("resize_errors", None)


def reset_zip_state(uploaded):
    sig = None if uploaded is None else (uploaded.name, uploaded.size, content_hash(uploaded.getvalue()))
    if sig != st.session_state.get("zip_input_signature"):
        st.session_state.zip_input_signature = sig
        st.session_state.pop("cleaned_zip", None)
        st.session_state.pop("cleaned_zip_name", None)
        st.session_state.pop("cleaned_zip_stats", None)


def clear_crop_uploads():
    st.session_state.crop_uploader_key = st.session_state.get("crop_uploader_key", 0) + 1
    st.session_state.pop("crop_input_signature", None)
    st.session_state.pop("crop_results", None)
    st.session_state.pop("crop_errors", None)
    st.rerun()


def clear_resize_uploads():
    st.session_state.resize_uploader_key = st.session_state.get("resize_uploader_key", 0) + 1
    st.session_state.pop("resize_input_signature", None)
    st.session_state.pop("resize_results", None)
    st.session_state.pop("resize_errors", None)
    st.rerun()


def collect_image_inputs(uploaded):
    """Collect direct images and images contained in uploaded ZIP archives."""
    items = []
    total_bytes = 0
    seen_names = set()

    def add_item(name, data):
        nonlocal total_bytes
        if len(data) > MAX_IMAGE_FILE_BYTES:
            raise ValueError(f"{name}: файл больше 50 МБ")
        if len(items) >= MAX_IMAGE_FILES:
            raise ValueError(f"Слишком много изображений. Максимум: {MAX_IMAGE_FILES}.")
        if total_bytes + len(data) > MAX_IMAGE_TOTAL_BYTES:
            raise ValueError("Общий размер изображений превышает 100 МБ.")
        base_name = Path(name).name or "image"
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        unique_name = base_name
        index = 2
        while unique_name.lower() in seen_names:
            unique_name = f"{stem}_{index}{suffix}"
            index += 1
        seen_names.add(unique_name.lower())
        items.append((unique_name, data))
        total_bytes += len(data)

    for file in uploaded or []:
        file_name = file.name
        file_data = file.getvalue()
        if Path(file_name).suffix.lower() == ".zip":
            if len(file_data) > MAX_ZIP_BYTES:
                raise ValueError(f"{file_name}: ZIP слишком большой. Максимум 300 МБ.")
            try:
                with zipfile.ZipFile(io.BytesIO(file_data)) as archive:
                    infos = [info for info in archive.infolist() if not info.is_dir()]
                    if len(infos) > MAX_ZIP_ENTRIES:
                        raise ValueError(f"{file_name}: в архиве больше {MAX_ZIP_ENTRIES} файлов.")
                    for info in infos:
                        member_name = info.filename.replace("\\", "/")
                        suffix = Path(member_name).suffix.lower().lstrip(".")
                        if suffix not in IMAGE_EXTENSIONS:
                            continue
                        if info.file_size > MAX_IMAGE_FILE_BYTES:
                            raise ValueError(f"{member_name}: файл больше 50 МБ")
                        with archive.open(info) as source:
                            data = source.read(MAX_IMAGE_FILE_BYTES + 1)
                        add_item(member_name, data)
            except zipfile.BadZipFile as exc:
                raise ValueError(f"{file_name}: повреждённый или некорректный ZIP") from exc
        else:
            add_item(file_name, file_data)

    return items


def trim_background(img: Image.Image, threshold: int = 18):
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    alpha_bbox = alpha.point(lambda p: 255 if p > 8 else 0).getbbox() or (0, 0, img.width, img.height)
    rgb = rgba.convert("RGB")
    corners = [rgb.getpixel((0, 0)), rgb.getpixel((rgb.width - 1, 0)), rgb.getpixel((0, rgb.height - 1)), rgb.getpixel((rgb.width - 1, rgb.height - 1))]
    bg = tuple(sum(p[i] for p in corners) // 4 for i in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    bbox = diff.point(lambda p: 255 if p > threshold else 0).getbbox()
    if not bbox:
        return alpha_bbox
    area_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / max(1, img.width * img.height)
    return alpha_bbox if area_ratio > 0.995 and alpha_bbox != (0, 0, img.width, img.height) else bbox


def process_image(data, name, size, margin, mode, fmt, manual, transparent):
    if len(data) > MAX_IMAGE_FILE_BYTES:
        raise ValueError("файл больше 50 МБ")
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    img = Image.open(io.BytesIO(data))
    if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION or img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError(f"изображение больше допустимого размера {MAX_IMAGE_DIMENSION} × {MAX_IMAGE_DIMENSION} px или 100 Мп")
    img.load()
    ext = Path(name).suffix.lower()
    if transparent:
        effective = "PNG"
    else:
        effective = fmt if fmt != "AUTO" else ("PNG" if ext in {".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"} else "JPG")
    if mode == "auto":
        bbox = trim_background(img)
    elif mode == "manual":
        top, bottom, left, right = manual
        bbox = (left, top, max(left + 1, img.width - right), max(top + 1, img.height - bottom))
    else:
        bbox = (0, 0, img.width, img.height)
    cropped = img.crop(bbox)
    available = max(1, size - 2 * margin)
    scale = min(available / cropped.width, available / cropped.height)
    nw, nh = max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))
    cropped = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    if effective == "PNG":
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
        cropped = cropped.convert("RGBA")
    else:
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        cropped = cropped.convert("RGB")
    x, y = margin + (available - nw) // 2, margin + (available - nh) // 2
    canvas.paste(cropped, (x, y), cropped if cropped.mode == "RGBA" else None)
    out_name = f"{Path(name).stem}.png" if effective == "PNG" else f"{Path(name).stem}.jpg"
    mime = "image/png" if effective == "PNG" else "image/jpeg"
    buf = io.BytesIO()
    canvas.save(buf, "PNG" if effective == "PNG" else "JPEG", quality=95 if effective != "PNG" else None)
    return out_name, buf.getvalue(), mime


def resize_image(data, name, size):
    """Resize an image directly to size × size without cropping or adding a canvas."""
    if len(data) > MAX_IMAGE_FILE_BYTES:
        raise ValueError("файл больше 50 МБ")
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    img = Image.open(io.BytesIO(data))
    if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION or img.width * img.height > MAX_IMAGE_PIXELS:
        raise ValueError(f"изображение больше допустимого размера {MAX_IMAGE_DIMENSION} × {MAX_IMAGE_DIMENSION} px или 100 Мп")
    img.load()
    ext = Path(name).suffix.lower()
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    has_alpha = "A" in resized.getbands() or "transparency" in resized.info
    if ext in {".jpg", ".jpeg"}:
        output_format = "JPEG"; mime = "image/jpeg"; resized = resized.convert("RGB")
    elif ext == ".webp":
        output_format = "WEBP"; mime = "image/webp"; resized = resized.convert("RGBA" if has_alpha else "RGB")
    elif ext == ".bmp":
        output_format = "BMP"; mime = "image/bmp"; resized = resized.convert("RGBA" if has_alpha else "RGB")
    elif ext in {".tif", ".tiff"}:
        output_format = "TIFF"; mime = "image/tiff"; resized = resized.convert("RGBA" if has_alpha else "RGB")
    elif ext == ".gif":
        output_format = "GIF"; mime = "image/gif"; resized = resized.convert("RGBA" if has_alpha else "RGB")
    else:
        output_format = "PNG"; mime = "image/png"; resized = resized.convert("RGBA" if has_alpha else "RGB")
    buf = io.BytesIO()
    save_kwargs = {"quality": 95} if output_format == "JPEG" else {}
    resized.save(buf, format=output_format, **save_kwargs)
    return name, buf.getvalue(), mime


def crop_signature(uploaded):
    if not uploaded:
        return None
    return tuple((f.name, f.size, content_hash(f.getvalue())) for f in uploaded)


def reset_crop_state(uploaded):
    sig = crop_signature(uploaded)
    if sig != st.session_state.get("crop_input_signature"):
        st.session_state.crop_input_signature = sig
        st.session_state.pop("crop_results", None)
        st.session_state.pop("crop_errors", None)


def build_zip(results):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data, _mime in results:
            archive.writestr(name, data)
    return buf.getvalue()


tab_crop, tab_resize, tab_zip = st.tabs(["✂️ Обрезка изображений", "📐 Изменить размер 1:1", "🧹 Очистка ZIP"])

with tab_crop:
    st.subheader("Обрезка и подготовка изображений")
    with st.expander("⚙️ Параметры", expanded=True):
        c1, c2, c3 = st.columns(3)
        size = c1.selectbox("Размер холста", [1200, 1000], format_func=lambda x: f"{x} × {x} px")
        margin = c2.number_input("Отступ вокруг объекта (px)", min_value=0, max_value=max(0, size // 2 - 1), value=min(10, size // 2 - 1))
        fmt = c3.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True)
        transparent = st.checkbox("Прозрачный фон", value=False) if fmt in ("AUTO", "PNG") else False
        if transparent and fmt == "AUTO":
            st.caption("AUTO + прозрачный фон → автоматически PNG")
        mode = st.radio("Режим обрезки", ["auto", "manual", "none"], format_func=lambda x: {"auto": "Авто — обрезать по объекту", "manual": "Вручную", "none": "Без обрезки"}[x], horizontal=True)
        manual = (0, 0, 0, 0)
        if mode == "manual":
            a, b, c, d = st.columns(4)
            manual = (a.number_input("Сверху", 0, 100000, 0), b.number_input("Снизу", 0, 100000, 0), c.number_input("Слева", 0, 100000, 0), d.number_input("Справа", 0, 100000, 0))
    uploader_key = f"crop_upload_{st.session_state.get('crop_uploader_key', 0)}"
    uploaded = st.file_uploader("Загрузите изображения или ZIP-архивы", type=IMAGE_EXTENSIONS + ["zip"], accept_multiple_files=True, key=uploader_key)
    reset_crop_state(uploaded)
    if uploaded:
        total = sum(f.size for f in uploaded)
        st.caption(f"Загружено: {len(uploaded)} файлов/архивов · общий размер загрузок {total / 1024 / 1024:.1f} МБ · из ZIP берутся только изображения")
        if st.button("🗑️ Очистить загруженные изображения", key="clear_crop_uploads", use_container_width=True):
            clear_crop_uploads()
        if total > MAX_IMAGE_TOTAL_BYTES and all(Path(f.name).suffix.lower() != ".zip" for f in uploaded):
            st.error("Общий размер файлов превышает 100 МБ.")
        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in uploaded):
            st.error("Один из ZIP-архивов превышает 300 МБ.")
    if uploaded:
        if st.button("▶ Обработать изображения", key="process_crop_images", type="primary", use_container_width=True):
            results, errors = [], []
            try:
                image_inputs = collect_image_inputs(uploaded)
            except Exception as exc:
                image_inputs = []; errors.append(str(exc))
            if image_inputs:
                progress = st.progress(0, text="Подготовка…")
                for i, (name, data) in enumerate(image_inputs, 1):
                    try: results.append(process_image(data, name, int(size), int(margin), mode, fmt, manual, transparent))
                    except Exception as exc: errors.append(f"{name}: {exc}")
                    progress.progress(i / len(image_inputs), text=f"Обработано {i}/{len(image_inputs)}")
                progress.empty()
            st.session_state.crop_results = results; st.session_state.crop_errors = errors
            if errors: st.error("\n".join(errors))
    results = st.session_state.get("crop_results", [])
    if results:
        st.success(f"Готово: {len(results)} изображений")
        if len(results) == 1:
            st.download_button("⬇️ Скачать результат", results[0][1], file_name=results[0][0], mime=results[0][2], use_container_width=True)
        else:
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data, _ in results: z.writestr(name, data)
            st.download_button("⬇️ Скачать все ZIP-архивом", archive.getvalue(), file_name=unique_archive_name("processed_images"), mime="application/zip", key="download_crop_zip", use_container_width=True)

with tab_resize:
    st.subheader("Изменение размера 1:1")
    st.caption(f"Прямое масштабирование до квадратного размера без кадрирования и без полей. Исходные изображения: до {MAX_IMAGE_DIMENSION} × {MAX_IMAGE_DIMENSION} px / 100 Мп.")
    resize_size = st.number_input("Новый размер, px", min_value=1, max_value=MAX_IMAGE_DIMENSION, value=1000, step=100, format="%d", key="resize_size")
    resize_uploader_key = f"resize_upload_{st.session_state.get('resize_uploader_key', 0)}"
    resize_uploaded = st.file_uploader("Загрузите изображения или ZIP-архивы", type=IMAGE_EXTENSIONS + ["zip"], accept_multiple_files=True, key=resize_uploader_key)
    reset_resize_state(resize_uploaded, resize_size)
    if resize_uploaded:
        total = sum(f.size for f in resize_uploaded)
        st.caption(f"Загружено: {len(resize_uploaded)} файлов/архивов · общий размер загрузок {total / 1024 / 1024:.1f} МБ · из ZIP берутся только изображения")
        if st.button("🗑️ Очистить загруженные изображения", key="clear_resize_uploads", use_container_width=True): clear_resize_uploads()
        if total > MAX_IMAGE_TOTAL_BYTES and all(Path(f.name).suffix.lower() != ".zip" for f in resize_uploaded): st.error("Общий размер файлов превышает 100 МБ.")
        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in resize_uploaded): st.error("Один из ZIP-архивов превышает 300 МБ.")
    if resize_uploaded:
        if st.button("▶ Изменить размер", key="resize_images_button", type="primary", use_container_width=True):
            results, errors = [], []
            try: image_inputs = collect_image_inputs(resize_uploaded)
            except Exception as exc: image_inputs = []; errors.append(str(exc))
            if image_inputs:
                progress = st.progress(0, text="Подготовка…")
                for i, (name, data) in enumerate(image_inputs, 1):
                    try: results.append(resize_image(data, name, int(resize_size)))
                    except Exception as exc: errors.append(f"{name}: {exc}")
                    progress.progress(i / len(image_inputs), text=f"Обработано {i}/{len(image_inputs)}")
                progress.empty()
            st.session_state.resize_results = results; st.session_state.resize_errors = errors
            if errors: st.error("\n".join(errors))
    resize_results = st.session_state.get("resize_results", [])
    if resize_results:
        st.success(f"Готово: {len(resize_results)} изображений · {int(resize_size)} × {int(resize_size)} px")
        if len(resize_results) == 1:
            st.download_button("⬇️ Скачать результат", resize_results[0][1], file_name=resize_results[0][0], mime=resize_results[0][2], key="download_resize_single", use_container_width=True)
        else:
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data, _ in resize_results: z.writestr(name, data)
            st.download_button("⬇️ Скачать все ZIP-архивом", archive.getvalue(), file_name=unique_archive_name("resized_images"), mime="application/zip", key="download_resize_zip", use_container_width=True)

with tab_zip:
    st.subheader("Очистка ZIP-архивов")
    st.caption("Максимум 500 файлов и 300 МБ на исходный архив.")
    zip_file = st.file_uploader("Загрузите исходный ZIP-архив", type=["zip"], key="clean_zip_upload")
    reset_zip_state(zip_file)
    if zip_file:
        st.info(f"Архив: **{zip_file.name}** · {zip_file.size / 1024 / 1024:.2f} МБ")
        if zip_file.size > MAX_ZIP_BYTES:
            st.error("ZIP слишком большой. Максимум 300 МБ.")
        elif st.button("🧹 Очистить ZIP", key="clean_zip_button", type="primary", use_container_width=True):
            try:
                cleaned, stats = clean_zip_bytes(zip_file.getvalue())
                st.session_state.cleaned_zip = cleaned
                st.session_state.cleaned_zip_name = unique_archive_name("cleaned_images")
                st.session_state.cleaned_zip_stats = stats
            except Exception as exc:
                st.error(f"Ошибка обработки ZIP: {exc}")
    if st.session_state.get("cleaned_zip"):
        stats = st.session_state.get("cleaned_zip_stats", {})
        st.success(f"Готово. Обработано изображений: {stats.get('renamed', 0)}")
        st.download_button("⬇️ Скачать очищенный ZIP", st.session_state.cleaned_zip, file_name=st.session_state.cleaned_zip_name, mime="application/zip", use_container_width=True)
