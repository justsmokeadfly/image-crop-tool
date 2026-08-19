import hashlib
import io
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

try:
    import pillow_avif  # noqa: F401
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

APP_VERSION = "1.4"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
SUPPORTED_INPUTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif") + ((".avif",) if AVIF_SUPPORTED else ())

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="expanded")


def smart_crop_with_margin(img, margin_px, size, background, fill_transparent=False):
    bg_color = _get_bg_color(background, fill_transparent)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    bbox = img.getbbox()
    if not bbox or bbox == (0, 0, img.width, img.height):
        rgb = img.convert("RGB")
        threshold = 245
        width, height = rgb.size
        pixels = rgb.load()

        def empty_col(x):
            return all(all(c > threshold for c in pixels[x, y]) for y in range(height))

        def empty_row(y):
            return all(all(c > threshold for c in pixels[x, y]) for x in range(width))

        left_ok = all(empty_col(x) for x in range(int(width * .05)))
        right_start = width - int(width * .05)
        right_ok = all(empty_col(x) for x in range(width - 1, right_start - 1, -1))
        top_ok = all(empty_row(y) for y in range(int(height * .05)))
        bottom_start = height - int(height * .05)
        bottom_ok = all(empty_row(y) for y in range(height - 1, bottom_start - 1, -1))

        l, r, t, b = 0, width, 0, height
        if left_ok:
            for x in range(width):
                if not empty_col(x):
                    l = max(0, x - 5)
                    break
        if right_ok:
            for x in range(width - 1, -1, -1):
                if not empty_col(x):
                    r = min(width, x + 5)
                    break
        if top_ok:
            for y in range(height):
                if not empty_row(y):
                    t = max(0, y - 5)
                    break
        if bottom_ok:
            for y in range(height - 1, -1, -1):
                if not empty_row(y):
                    b = min(height, y + 5)
                    break
        bbox = (l, t, r, b)
    return _finish_crop(img, bbox, margin_px, size, background, bg_color)


def manual_crop_with_margin(img, margin_px, size, background, top, bottom, left, right, fill_transparent=False):
    width, height = img.size
    top, bottom = min(int(top), height - 1), min(int(bottom), height - 1)
    left, right = min(int(left), width - 1), min(int(right), width - 1)
    new_left, new_top = left, top
    new_right, new_bottom = width - right, height - bottom
    if new_right <= new_left:
        new_right = new_left + 1
    if new_bottom <= new_top:
        new_bottom = new_top + 1
    return _finish_crop(
        img, (new_left, new_top, new_right, new_bottom), margin_px, size,
        background, _get_bg_color(background, fill_transparent)
    )


def no_crop_with_margin(img, margin_px, size, background, fill_transparent=False):
    return _finish_crop(
        img, (0, 0, img.width, img.height), margin_px, size,
        background, _get_bg_color(background, fill_transparent)
    )


def _get_bg_color(background, fill_transparent):
    if background == "PNG" and fill_transparent:
        return (0, 0, 0, 0)
    return (255, 255, 255, 255) if background == "PNG" else (255, 255, 255)


def _finish_crop(img, bbox, margin_px, size, background, bg_color):
    cropped = img.crop(bbox)
    available = max(1, size - margin_px * 2)
    scale = min(available / max(1, cropped.width), available / max(1, cropped.height))
    new_size = (max(1, int(cropped.width * scale)), max(1, int(cropped.height * scale)))
    cropped = cropped.resize(new_size, Image.Resampling.LANCZOS)
    new_img = Image.new("RGBA" if background == "PNG" else "RGB", (size, size), bg_color)
    pos = ((size - new_size[0]) // 2, (size - new_size[1]) // 2)
    new_img.paste(cropped, pos, cropped if cropped.mode == "RGBA" else None)
    return new_img


def get_effective_output_format(selected_format, file_name):
    if selected_format in ("PNG", "JPG"):
        return selected_format
    ext = Path(file_name).suffix.lower()
    if ext == ".png":
        return "PNG"
    if ext in (".jpg", ".jpeg"):
        return "JPG"
    return "PNG" if ext in (".gif", ".webp", ".tif", ".tiff", ".avif") else "JPG"


def process_one(img, file_name, size, margin, crop_mode, fmt, manual_vals, fill_transparent):
    effective = get_effective_output_format(fmt, file_name)
    if crop_mode == "auto":
        processed = smart_crop_with_margin(img, margin, size, effective, fill_transparent)
    elif crop_mode == "manual":
        processed = manual_crop_with_margin(img, margin, size, effective, *manual_vals, fill_transparent)
    else:
        processed = no_crop_with_margin(img, margin, size, effective, fill_transparent)
    if effective == "PNG":
        ext, mime = ".png", "image/png"
    else:
        ext, mime = ".jpg", "image/jpeg"
        if processed.mode == "RGBA":
            processed = processed.convert("RGB")
    buf = io.BytesIO()
    processed.save(buf, "PNG" if ext == ".png" else "JPEG", quality=95 if ext == ".jpg" else None)
    data = buf.getvalue()
    return f"{Path(file_name).stem}{ext}", data, processed, mime


# Streamlit state
st.session_state.setdefault("theme", "Светлая")
st.session_state.setdefault("excluded_files", set())
st.session_state.setdefault("uploader_key", 0)
st.session_state.setdefault("results", [])
st.session_state.setdefault("upload_signature", None)

COMMON_CSS = """
<style>
.block-container{max-width:1540px;padding-top:1.6rem;padding-bottom:3rem}
.hero{padding:.1rem 0 1.25rem}.hero h1{margin:0 0 .25rem;font-size:clamp(1.8rem,3vw,2.55rem);line-height:1.15;letter-spacing:-.04em}.hero p{margin:0;opacity:.7}
.section-title{font-size:1.15rem;font-weight:750;margin:1.25rem 0 .55rem}.file-card,.result-card{border:1px solid var(--app-border);border-radius:14px;background:var(--app-card);padding:.75rem .9rem}.file-card{min-height:64px}.file-name,.result-name{font-weight:650;overflow-wrap:anywhere}.file-meta,.result-meta{font-size:.82rem;opacity:.65;margin-top:.18rem}.result-card{min-height:100px;margin-bottom:.55rem}.result-icon{font-size:1.7rem;line-height:1;margin-bottom:.45rem}.success-box{border:1px solid #86efac;background:#f0fdf4;color:#166534;border-radius:12px;padding:.75rem .95rem}button[kind="primary"],button[kind="secondary"]{border-radius:10px}.stDownloadButton button{min-height:2.55rem}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}.hero h1{font-size:1.85rem}}
</style>
"""
LIGHT_CSS = """
<style>
:root{--app-border:#e2e8f0;--app-card:#fff}.stApp{background:#f6f8fb}section[data-testid="stSidebar"]{background:#fff;border-right:1px solid #e2e8f0}div[data-testid="stFileUploaderDropzone"]{border:2px dashed #cbd5e1;border-radius:14px;background:#fbfdff;min-height:150px}div[data-testid="stFileUploaderDropzone"]:hover{border-color:#2563eb;background:#eff6ff}
</style>
"""
DARK_CSS = """
<style>
:root{--app-border:#293548;--app-card:#111827}.stApp{background:#0b1020}section[data-testid="stSidebar"]{background:#111827;border-right:1px solid #293548}div[data-testid="stFileUploaderDropzone"]{border:2px dashed #475569;border-radius:14px;background:#0f172a;min-height:150px}div[data-testid="stFileUploaderDropzone"]:hover{border-color:#60a5fa;background:#172033}.success-box{background:#052e16;color:#bbf7d0;border-color:#166534}
</style>
"""
st.markdown(COMMON_CSS + (DARK_CSS if st.session_state.theme == "Тёмная" else LIGHT_CSS), unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Параметры")
    st.caption("Настройки применяются ко всем изображениям.")
    size = st.number_input("Размер холста (px)", min_value=10, max_value=10000, value=1200, step=10)
    max_margin = max(0, int(size // 2) - 1)
    margin = st.number_input("Отступ (px)", min_value=0, max_value=max_margin, value=min(10, max_margin), step=1)
    st.markdown("**Формат результата**")
    fmt = st.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True, label_visibility="collapsed")
    fill_transparent = False
    if fmt in ("AUTO", "PNG"):
        fill_transparent = st.radio("Цвет полей", ["Белый", "Прозрачный"], horizontal=True) == "Прозрачный"
    st.markdown("**Режим обрезки**")
    crop_mode = st.radio("Режим", ["auto", "manual", "none"], format_func=lambda v: {"auto":"Авто — убрать пустые поля","manual":"Вручную — указать пиксели","none":"Без обрезки"}[v], label_visibility="collapsed")
    manual_vals = (0, 0, 0, 0)
    if crop_mode == "manual":
        c1, c2 = st.columns(2)
        top, bottom = c1.number_input("Сверху", min_value=0, value=0), c2.number_input("Снизу", min_value=0, value=0)
        left, right = c1.number_input("Слева", min_value=0, value=0), c2.number_input("Справа", min_value=0, value=0)
        manual_vals = (top, bottom, left, right)
    st.divider()
    theme_choice = st.radio("Тема", ["☀️ Светлая", "🌙 Тёмная"], index=0 if st.session_state.theme == "Светлая" else 1, horizontal=True)
    new_theme = "Тёмная" if "Тёмная" in theme_choice else "Светлая"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

st.markdown('<div class="hero"><h1>🖼️ Обработчик изображений</h1><p>Обрезка с отступом · квадратный холст · конвертация формата</p></div>', unsafe_allow_html=True)
if not AVIF_SUPPORTED:
    st.warning("Поддержка AVIF не активна. В requirements.txt должен быть установлен pillow-avif-plugin.")

st.markdown('<div class="section-title">1. Загрузка изображений</div>', unsafe_allow_html=True)
with st.container(border=True):
    st.caption("Перетащите файлы в область ниже или выберите их на компьютере")
    upload_key = f"image_uploader_{st.session_state.uploader_key}"
    uploaded_files = st.file_uploader("Выбрать изображения", type=[x.strip(".") for x in SUPPORTED_INPUTS], accept_multiple_files=True, key=upload_key, label_visibility="collapsed")
    st.caption("Можно загрузить несколько файлов одновременно. Для полностью новой загрузки нажмите «Очистить».")

active_files = []
for uf in uploaded_files or []:
    raw = uf.getvalue()
    fingerprint = hashlib.sha256(raw).hexdigest()
    file_id = f"{uf.name}:{fingerprint}"
    if file_id not in st.session_state.excluded_files:
        active_files.append((file_id, uf, fingerprint))

current_signature = tuple(item[2] for item in active_files)
if current_signature != st.session_state.upload_signature:
    st.session_state.upload_signature = current_signature
    st.session_state.results = []

if uploaded_files:
    st.markdown('<div class="section-title">Загруженные файлы</div>', unsafe_allow_html=True)
    info_col, clear_col = st.columns([4, 1])
    with info_col:
        st.caption(f"Выбрано: {len(active_files)} из {len(uploaded_files)}")
    with clear_col:
        if st.button("🗑️ Очистить", use_container_width=True):
            st.session_state.excluded_files = set()
            st.session_state.uploader_key += 1
            st.session_state.results = []
            st.session_state.upload_signature = None
            st.rerun()
    for file_id, uf, fingerprint in active_files:
        ci, ca = st.columns([9, 1], vertical_alignment="center")
        with ci:
            ext = Path(uf.name).suffix.upper().lstrip(".") or "FILE"
            st.markdown(f'<div class="file-card"><div class="file-name">📄 {uf.name}</div><div class="file-meta">{uf.size/1024:.1f} КБ · {ext}</div></div>', unsafe_allow_html=True)
        with ca:
            if st.button("×", key=f"remove_{fingerprint}", help=f"Убрать {uf.name}"):
                st.session_state.excluded_files.add(file_id)
                st.session_state.results = []
                st.rerun()

st.markdown('<div class="section-title">2. Обработка</div>', unsafe_allow_html=True)
if active_files and margin * 2 < size:
    if st.button("▶ Обработать изображения", type="primary", use_container_width=True):
        results, errors = [], []
        progress = st.progress(0.0, text="Подготовка…")
        status = st.empty()
        total = len(active_files)
        for index, (_, uf, fingerprint) in enumerate(active_files, 1):
            status.markdown(f"**Обработка:** `{uf.name}` · {index} из {total}")
            try:
                img = Image.open(io.BytesIO(uf.getvalue()))
                img.load()
                out_name, data, processed, mime = process_one(img, uf.name, int(size), int(margin), crop_mode, fmt, manual_vals, fill_transparent)
                results.append({"name": out_name, "data": data, "width": processed.width, "height": processed.height, "mime": mime, "fingerprint": fingerprint, "download_key": hashlib.sha256(data).hexdigest()[:20]})
            except Exception as exc:
                errors.append(f"{uf.name}: {exc}")
            progress.progress(index / total, text=f"Готово: {index} из {total}")
        status.empty(); progress.empty()
        st.session_state.results = results
        if errors:
            st.warning(f"Не удалось обработать: {len(errors)} файл(а).")
            for error in errors:
                st.caption(f"• {error}")

if st.session_state.results:
    results = st.session_state.results
    st.markdown('<div class="section-title">3. Результат</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="success-box">✓ Обработка завершена · <strong>{len(results)} файлов</strong></div>', unsafe_allow_html=True)
    st.write("")
    columns_count = min(3, len(results))
    cols = st.columns(columns_count)
    for index, result in enumerate(results):
        with cols[index % columns_count]:
            st.markdown(f'<div class="result-card"><div class="result-icon">🖼️</div><div class="result-name">{result["name"]}</div><div class="result-meta">{result["width"]} × {result["height"]} px · {len(result["data"])/1024:.1f} КБ</div></div>', unsafe_allow_html=True)
            st.download_button("⬇️ Скачать", data=result["data"], file_name=result["name"], mime=result["mime"], key=f"download_{result['download_key']}", use_container_width=True, on_click="ignore")
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for result in results:
            zf.writestr(result["name"], result["data"])
    st.download_button("📦 Скачать всё (ZIP)", data=zip_buf.getvalue(), file_name="processed_images.zip", mime="application/zip", use_container_width=True, type="primary", on_click="ignore")
elif not active_files:
    st.info("Добавьте одно или несколько изображений выше, чтобы начать обработку.")
