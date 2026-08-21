import hashlib
import io
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
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

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="collapsed")

LIGHT = """
<style>
.block-container{max-width:1500px;padding-top:1.5rem;padding-bottom:3rem}
.hero h1{margin:0 0 .2rem;font-size:clamp(1.9rem,3vw,2.7rem);letter-spacing:-.04em}.hero p{opacity:.7;margin:0 0 1rem}
[data-testid="stTabs"] button{font-size:1.05rem;font-weight:700;padding:0.7rem 1rem}
[data-testid="stFileUploaderDropzone"]{border-radius:14px;min-height:145px}
</style>
"""
DARK = """
<style>
.block-container{max-width:1500px;padding-top:1.5rem;padding-bottom:3rem}
.hero h1{margin:0 0 .2rem;font-size:clamp(1.9rem,3vw,2.7rem);letter-spacing:-.04em}.hero p{color:#b4c0d1;margin:0 0 1rem}
[data-testid="stTabs"] button{font-size:1.05rem;font-weight:700;padding:0.7rem 1rem;color:#f8fafc}
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
st.markdown('<div class="hero"><h1>🖼️ Обработчик изображений</h1><p>Обрезка, подготовка изображений и очистка ZIP-архивов — теперь в одном интерфейсе</p></div>', unsafe_allow_html=True)


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
    nw, nh = max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))
    cropped = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    if fmt == "PNG":
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if transparent else (255, 255, 255, 255))
        cropped = cropped.convert("RGBA")
    else:
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        if cropped.mode != "RGB":
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


def get_rembg_session(model):
    try:
        from rembg import new_session
        return new_session(model)
    except ImportError as exc:
        raise RuntimeError("Для удаления фона нужен пакет rembg. Добавьте его в requirements.txt и перезапустите приложение.") from exc


def remove_background(data, session):
    from rembg import remove
    return remove(data, session=session)


def clean_zip_bytes(zip_bytes, remove_bg, keep_first, skip_existing, workers, model, progress_callback=None):
    session = get_rembg_session(model) if remove_bg else None
    output = io.BytesIO()
    image_ext = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".avif"}
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as src, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as dst:
        infos = [i for i in src.infolist() if not i.is_dir()]
        first_by_folder = {}
        if keep_first:
            for info in infos:
                ext = Path(info.filename).suffix.lower()
                if ext in image_ext:
                    folder = str(Path(info.filename).parent).replace("\\", "/")
                    first_by_folder.setdefault(folder, info.filename)

        tasks = []
        for info in infos:
            ext = Path(info.filename).suffix.lower()
            if keep_first and ext in image_ext:
                folder = str(Path(info.filename).parent).replace("\\", "/")
                if first_by_folder.get(folder) != info.filename:
                    continue
            tasks.append(info)

        processed = 0
        total = len(tasks)
        def transform(info):
            data = src.read(info)
            if remove_bg and Path(info.filename).suffix.lower() in image_ext:
                data = remove_background(data, session)
                if Path(info.filename).suffix.lower() not in {".png", ".webp"}:
                    info_name = f"{Path(info.filename).with_suffix('')}.png"
                else:
                    info_name = info.filename
                return info_name, data
            return info.filename, data

        if remove_bg and workers > 1:
            with ThreadPoolExecutor(max_workers=min(workers, 8)) as executor:
                futures = {executor.submit(transform, info): info for info in tasks}
                for future in as_completed(futures):
                    name, data = future.result()
                    dst.writestr(name, data)
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, total)
        else:
            for info in tasks:
                name, data = transform(info)
                dst.writestr(name, data)
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)

    return output.getvalue(), total, len(infos) - total


crop_tab, zip_tab = st.tabs(["✂️ Обрезка изображений", "🧹 Очистка ZIP"])

with crop_tab:
    st.subheader("Обрезка и подготовка изображений")
    with st.expander("⚙️ Параметры", expanded=True):
        c1, c2, c3 = st.columns(3)
        size = c1.selectbox("Размер холста", [1200, 1000], format_func=lambda x: f"{x} × {x} px")
        margin = c2.number_input("Отступ вокруг объекта (px)", min_value=0, max_value=max(0, size // 2 - 1), value=min(10, size // 2 - 1), step=1)
        fmt = c3.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True)
        transparent = False
        if fmt in ("AUTO", "PNG"):
            transparent = st.checkbox("Прозрачный фон", value=False)
        mode = st.radio("Режим обрезки", ["auto", "manual", "none"], format_func=lambda x: {"auto": "Авто — убрать пустой фон", "manual": "Вручную", "none": "Без обрезки"}[x], horizontal=True)
        manual = (0, 0, 0, 0)
        if mode == "manual":
            a, b, c, d = st.columns(4)
            manual = (a.number_input("Сверху", 0, 100000, 0), b.number_input("Снизу", 0, 100000, 0), c.number_input("Слева", 0, 100000, 0), d.number_input("Справа", 0, 100000, 0))

    uploaded = st.file_uploader("Загрузите изображения", type=IMAGE_EXTENSIONS, accept_multiple_files=True, key="crop_upload")
    if uploaded:
        st.caption(f"Выбрано файлов: **{len(uploaded)}**")
        if st.button("▶ Обработать изображения", type="primary", use_container_width=True):
            results, errors = [], []
            progress = st.progress(0, text="Подготовка…")
            for i, uf in enumerate(uploaded, 1):
                try:
                    name, data, mime = process_image(uf.getvalue(), uf.name, int(size), int(margin), mode, fmt, manual, transparent)
                    results.append((name, data, mime))
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
    st.caption("Веб-версия инструмента из clean_zip.py: обработка ZIP, удаление фона и очистка лишних фотографий.")
    zip_file = st.file_uploader("Загрузите исходный ZIP-архив", type=["zip"], key="clean_zip_upload")

    with st.expander("⚙️ Параметры очистки", expanded=True):
        c1, c2 = st.columns(2)
        remove_bg = c1.checkbox("Удалять фон у фотографий", value=True)
        keep_first = c2.checkbox("Оставлять только первое фото в каждой папке", value=False)
        skip_existing = c1.checkbox("Пропускать файлы, которые уже PNG без фона", value=True)
        workers = c2.slider("Параллельных потоков", 1, 8, 2)
        model = st.selectbox("Модель удаления фона", ["birefnet-massive", "u2net"], index=0)

    if zip_file:
        st.info(f"Архив: **{zip_file.name}** · {zip_file.size / 1024 / 1024:.2f} МБ")
        if st.button("🧹 Очистить ZIP", type="primary", use_container_width=True):
            progress = st.progress(0, text="Подготовка…")
            status = st.empty()
            def on_progress(done, total):
                progress.progress(done / max(1, total), text=f"Обработано {done}/{total}")
            try:
                result, total, removed = clean_zip_bytes(zip_file.getvalue(), remove_bg, keep_first, skip_existing, workers, model, on_progress)
                st.session_state.cleaned_zip = result
                st.session_state.cleaned_zip_name = f"{Path(zip_file.name).stem}_cleaned.zip"
                status.success(f"Готово. Файлов обработано: {total}; исключено из архива: {removed}.")
            except Exception as exc:
                status.empty()
                st.error(f"Не удалось обработать ZIP: {exc}")
            finally:
                progress.empty()

    if st.session_state.get("cleaned_zip"):
        st.success("Очистка завершена — архив готов к скачиванию.")
        st.download_button("⬇️ Скачать очищенный ZIP", st.session_state.cleaned_zip, file_name=st.session_state.cleaned_zip_name, mime="application/zip", use_container_width=True)

st.divider()
st.caption(f"{APP_NAME} · ZIP Cleaner based on clean_zip.py · Streamlit")
