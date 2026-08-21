import io
import os
import tempfile
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageChops

try:
    import pillow_avif  # noqa: F401
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

APP_VERSION = "2.0"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"] + (["avif"] if AVIF_SUPPORTED else [])
ZIP_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".gif"}

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="collapsed")

LIGHT = """
<style>
.block-container{max-width:1500px;padding-top:1.5rem;padding-bottom:3rem}
.hero h1{margin:0 0 .2rem;font-size:clamp(1.9rem,3vw,2.7rem);letter-spacing:-.04em}.hero p{opacity:.7;margin:0 0 1rem}
[data-testid="stTabs"] button{font-size:1.05rem;font-weight:700;padding:.7rem 1rem}
[data-testid="stFileUploaderDropzone"]{border-radius:14px;min-height:145px}
</style>
"""
DARK = """
<style>
.block-container{max-width:1500px;padding-top:1.5rem;padding-bottom:3rem}
.hero h1{margin:0 0 .2rem;font-size:clamp(1.9rem,3vw,2.7rem);letter-spacing:-.04em}.hero p{color:#b4c0d1;margin:0 0 1rem}
[data-testid="stTabs"] button{font-size:1.05rem;font-weight:700;padding:.7rem 1rem;color:#f8fafc}
[data-testid="stFileUploaderDropzone"]{background:#111827!important;border-color:#52637a!important;border-radius:14px;min-height:145px}
[data-testid="stFileUploaderDropzone"] *{color:#f8fafc!important}
.stApp{background:#0b1020;color:#f8fafc}section[data-testid="stSidebar"]{background:#111827}
</style>
"""

if "theme" not in st.session_state:
    st.session_state.theme = "Светлая"

with st.sidebar:
    theme = st.radio("Тема", ["☀️ Светлая", "🌙 Тёмная"], horizontal=True, index=0 if st.session_state.theme == "Светлая" else 1)
    st.session_state.theme = "Тёмная" if "Тёмная" in theme else "Светлая"

st.markdown(DARK if st.session_state.theme == "Тёмная" else LIGHT, unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>🖼️ Обработчик изображений</h1><p>Обрезка изображений и очистка ZIP-архивов в одном интерфейсе</p></div>', unsafe_allow_html=True)


def trim_background(img: Image.Image, threshold: int = 18):
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    alpha_bbox = alpha.point(lambda p: 255 if p > 8 else 0).getbbox()
    if not alpha_bbox:
        alpha_bbox = (0, 0, img.width, img.height)
    rgb = rgba.convert("RGB")
    samples = [
        rgb.getpixel((0, 0)), rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)), rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    bg = tuple(sum(p[i] for p in samples) // 4 for i in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    mask = diff.point(lambda p: 255 if p > threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return alpha_bbox
    ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / max(1, img.width * img.height)
    return alpha_bbox if ratio > 0.995 and alpha_bbox != (0, 0, img.width, img.height) else bbox


def crop_to_square(img, bbox, margin, size, fmt, transparent):
    cropped = img.crop(bbox)
    available = max(1, size - 2 * margin)
    scale = min(available / cropped.width, available / cropped.height)
    nw = max(1, round(cropped.width * scale))
    nh = max(1, round(cropped.height * scale))
    cropped = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    if fmt == "PNG":
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
        cropped = cropped.convert("RGBA")
    else:
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        cropped = cropped.convert("RGB")
    x = margin + (available - nw) // 2
    y = margin + (available - nh) // 2
    canvas.paste(cropped, (x, y), cropped if cropped.mode == "RGBA" else None)
    return canvas


def process_image(data, name, size, margin, mode, fmt, manual, transparent):
    img = Image.open(io.BytesIO(data))
    img.load()
    ext = Path(name).suffix.lower()
    effective = fmt if fmt != "AUTO" else ("PNG" if ext in {".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"} else "JPG")
    if mode == "auto":
        bbox = trim_background(img)
    elif mode == "manual":
        top, bottom, left, right = manual
        bbox = (left, top, max(left + 1, img.width - right), max(top + 1, img.height - bottom))
    else:
        bbox = (0, 0, img.width, img.height)
    out = crop_to_square(img, bbox, margin, size, effective, transparent)
    if effective == "PNG":
        out_name, save_format, mime = f"{Path(name).stem}.png", "PNG", "image/png"
    else:
        out_name, save_format, mime = f"{Path(name).stem}.jpg", "JPEG", "image/jpeg"
        out = out.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, save_format, quality=95 if save_format == "JPEG" else None)
    return out_name, buf.getvalue(), mime


def _zip_folder_name(filename: str) -> str:
    """Return the name of the parent folder for a ZIP member."""
    parent = Path(filename).parent
    name = parent.name
    return "" if name == "." else name


def _zip_clean_target_name(filename: str) -> str | None:
    """Return the cleaned target name for *_images_1 files, or None."""
    path = Path(filename)
    stem = path.stem
    if "_images_" not in stem or not stem.endswith("_images_1"):
        return None
    folder_name = _zip_folder_name(filename)
    if not folder_name:
        return None
    return f"{folder_name}_1{path.suffix}"


def clean_zip_bytes(zip_bytes, progress_callback=None):
    """Clean files matching the image naming convention inside a ZIP.

    Rules:
    - Only filenames containing ``_images_`` are candidates.
    - ``*_images_1.ext`` is kept and renamed to ``{parent_folder}_1.ext``.
    - Other ``*_images_*`` files are deleted.
    - Files without ``_images_`` are untouched.
    - Existing target files cause the source first image to be removed and skipped.
    - Renames use ``os.replace`` on the extracted working tree.
    - No background-removal library is used.
    """
    output = io.BytesIO()
    stats = {"scanned": 0, "candidates": 0, "renamed": 0, "deleted": 0, "skipped_existing": 0}

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as src:
            src.extractall(temp_dir)

        for root, _, files in os.walk(temp_dir):
            for file_name in files:
                stats["scanned"] += 1
                if "_images_" not in Path(file_name).stem:
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
                target_path = os.path.join(root, f"{folder_name}_1{Path(file_name).suffix}")

                if os.path.normcase(os.path.abspath(source_path)) == os.path.normcase(os.path.abspath(target_path)):
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
                files_to_write.append((file_path, os.path.relpath(file_path, temp_dir)))

        total = len(files_to_write)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as dst:
            for processed, (file_path, arcname) in enumerate(files_to_write, 1):
                dst.write(file_path, arcname)
                if progress_callback:
                    progress_callback(processed, total)

    return output.getvalue(), stats


crop_tab, zip_tab = st.tabs(["✂️ Обрезка изображений", "🧹 Очистка ZIP"])

with crop_tab:
    st.subheader("Обрезка и подготовка изображений")
    with st.expander("⚙️ Параметры", expanded=True):
        c1, c2, c3 = st.columns(3)
        size = c1.selectbox("Размер холста", [1200, 1000], format_func=lambda x: f"{x} × {x} px")
        margin = c2.number_input("Отступ вокруг объекта (px)", min_value=0, max_value=max(0, size // 2 - 1), value=min(10, size // 2 - 1), step=1)
        fmt = c3.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True)
        transparent = st.checkbox("Прозрачный фон", value=False) if fmt in ("AUTO", "PNG") else False
        mode = st.radio("Режим обрезки", ["auto", "manual", "none"], format_func=lambda x: {"auto": "Авто — убрать пустой фон", "manual": "Вручную", "none": "Без обрезки"}[x], horizontal=True)
        manual = (0, 0, 0, 0)
        if mode == "manual":
            a, b, c, d = st.columns(4)
            manual = (a.number_input("Сверху", 0, 100000, 0), b.number_input("Снизу", 0, 100000, 0), c.number_input("Слева", 0, 100000, 0), d.number_input("Справа", 0, 100000, 0))

    uploaded = st.file_uploader("Загрузите изображения", type=IMAGE_EXTENSIONS, accept_multiple_files=True, key="crop_upload")
    if uploaded and st.button("▶ Обработать изображения", type="primary", use_container_width=True):
        results, errors = [], []
        progress = st.progress(0, text="Подготовка…")
        for i, uf in enumerate(uploaded, 1):
            try:
                results.append(process_image(uf.getvalue(), uf.name, int(size), int(margin), mode, fmt, manual, transparent))
            except Exception as exc:
                errors.append(f"{uf.name}: {exc}")
            progress.progress(i / len(uploaded), text=f"Обработано {i}/{len(uploaded)}")
        progress.empty()
        st.session_state.crop_results = results
        if errors:
            st.error("\n".join(errors))

    results = st.session_state.get("crop_results", [])
    if results:
        st.success(f"Готово: {len(results)} изображений")
        if len(results) == 1:
            st.download_button("⬇️ Скачать результат", results[0][1], file_name=results[0][0], mime=results[0][2], use_container_width=True)
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data, _ in results:
                    z.writestr(name, data)
            st.download_button("⬇️ Скачать все ZIP-архивом", buf.getvalue(), file_name="processed_images.zip", mime="application/zip", use_container_width=True)

with zip_tab:
    st.subheader("Очистка ZIP-архивов")
    st.caption("Оставляет только *_images_1 в каждой папке, переименовывает его в имя папки_1 и удаляет остальные *_images_* файлы. Остальные файлы не трогаются.")
    zip_file = st.file_uploader("Загрузите исходный ZIP-архив", type=["zip"], key="clean_zip_upload")
    if zip_file:
        st.info(f"Архив: **{zip_file.name}** · {zip_file.size / 1024 / 1024:.2f} МБ")
        if st.button("🧹 Очистить ZIP", type="primary", use_container_width=True):
            progress = st.progress(0, text="Подготовка…")
            try:
                result, stats = clean_zip_bytes(
                    zip_file.getvalue(),
                    lambda done, count: progress.progress(done / max(1, count), text=f"Упаковано {done}/{count}"),
                )
                st.session_state.cleaned_zip = result
                st.session_state.cleaned_zip_name = f"{Path(zip_file.name).stem}_cleaned.zip"
                st.session_state.cleaned_zip_stats = stats
                st.success(
                    f"Готово. Переименовано: {stats['renamed']}; "
                    f"удалено лишних: {stats['deleted']}; "
                    f"пропущено из-за существующего имени: {stats['skipped_existing']}."
                )
            except Exception as exc:
                st.error(f"Не удалось обработать ZIP: {exc}")
            finally:
                progress.empty()

    if st.session_state.get("cleaned_zip"):
        stats = st.session_state.get("cleaned_zip_stats", {})
        if stats:
            st.caption(
                f"Проверено: {stats.get('scanned', 0)} · "
                f"кандидатов: {stats.get('candidates', 0)} · "
                f"переименовано: {stats.get('renamed', 0)} · "
                f"удалено: {stats.get('deleted', 0)}"
            )
        st.download_button("⬇️ Скачать очищенный ZIP", st.session_state.cleaned_zip, file_name=st.session_state.cleaned_zip_name, mime="application/zip", use_container_width=True)

st.divider()
st.caption(f"{APP_NAME} · ZIP Cleaner · Streamlit")
