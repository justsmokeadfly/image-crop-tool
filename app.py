import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from PIL import Image, ImageChops, ImageStat

try:
    import pillow_avif  # noqa: F401
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

APP_VERSION = "1.8"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
INPUT_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"] + (["avif"] if AVIF_SUPPORTED else [])

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="expanded")


def trim_background(img: Image.Image, threshold: int = 18):
    """Find the non-background bounding box without requiring pure-white rows/columns."""
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    # Transparent pixels are definitely background.
    alpha_bbox = alpha.point(lambda p: 255 if p > 8 else 0).getbbox()
    if not alpha_bbox:
        return (0, 0, img.width, img.height)

    rgb = rgba.convert("RGB")
    # Estimate background from the four corners. This works better for product
    # photos than checking whether whole rows are pure white.
    samples = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    bg = tuple(sum(p[i] for p in samples) // 4 for i in range(3))
    bg_img = Image.new("RGB", rgb.size, bg)
    diff = ImageChops.difference(rgb, bg_img)
    # Slightly reduce JPEG/compression noise before thresholding.
    gray = diff.convert("L")
    mask = gray.point(lambda p: 255 if p > threshold else 0)
    mask = mask.filter(ImageFilter.MinFilter(3)) if False else mask
    bbox = mask.getbbox()
    if not bbox:
        return alpha_bbox

    # If the detected box is almost the whole image, there is probably no
    # removable background. Keep the original bounds rather than cutting it.
    area_ratio = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / (img.width * img.height)
    if area_ratio > 0.995:
        return alpha_bbox if alpha_bbox != (0, 0, img.width, img.height) else (0, 0, img.width, img.height)

    return bbox


def crop_to_square(img: Image.Image, bbox, margin: int, size: int, fmt: str, transparent: bool):
    """Crop object, add exactly `margin` px around it, then fit inside square canvas."""
    cropped = img.crop(bbox)
    # The requested margin is measured on the final output canvas.
    available = max(1, size - 2 * margin)
    scale = min(available / cropped.width, available / cropped.height)
    nw = max(1, round(cropped.width * scale))
    nh = max(1, round(cropped.height * scale))
    cropped = cropped.resize((nw, nh), Image.Resampling.LANCZOS)

    if fmt == "PNG":
        bg = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
        canvas = Image.new("RGBA", (size, size), bg)
    else:
        canvas = Image.new("RGB", (size, size), (255, 255, 255))

    # If the object touches a dimension limit, this produces exactly `margin`
    # px on that dimension. Other dimensions necessarily have more empty space
    # because the output is square and the object's aspect ratio is preserved.
    x = margin + (available - nw) // 2
    y = margin + (available - nh) // 2
    if fmt == "PNG" and cropped.mode != "RGBA":
        cropped = cropped.convert("RGBA")
    canvas.paste(cropped, (x, y), cropped if cropped.mode == "RGBA" else None)
    return canvas


def process_one(img: Image.Image, name: str, size: int, margin: int, mode: str, fmt: str, manual, transparent: bool):
    ext = Path(name).suffix.lower()
    effective = fmt if fmt != "AUTO" else ("PNG" if ext in {".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"} else "JPG")

    if mode == "auto":
        bbox = trim_background(img)
    elif mode == "manual":
        top, bottom, left, right = manual
        w, h = img.size
        bbox = (left, top, max(left + 1, w - right), max(top + 1, h - bottom))
    else:
        bbox = (0, 0, img.width, img.height)

    out = crop_to_square(img, bbox, margin, size, effective, transparent)
    if effective == "PNG":
        extension, mime = ".png", "image/png"
        save_format = "PNG"
    else:
        extension, mime = ".jpg", "image/jpeg"
        save_format = "JPEG"
        if out.mode != "RGB":
            out = out.convert("RGB")

    buf = io.BytesIO()
    out.save(buf, save_format, quality=95 if save_format == "JPEG" else None)
    return f"{Path(name).stem}{extension}", buf.getvalue(), out, mime


for key, default in (
    ("theme", "Светлая"),
    ("excluded_files", set()),
    ("uploader_key", 0),
    ("results", []),
    ("upload_signature", None),
):
    st.session_state.setdefault(key, default)

LIGHT = """
<style>
.block-container{max-width:1540px;padding-top:1.6rem;padding-bottom:3rem}
.hero h1{margin:0 0 .25rem;font-size:clamp(1.8rem,3vw,2.55rem);letter-spacing:-.04em}.hero p{opacity:.72;margin:0 0 1.25rem}
.section-title{font-size:1.15rem;font-weight:750;margin:1.25rem 0 .55rem}
.file-card{border:1px solid #e2e8f0;border-radius:14px;background:#fff;padding:.75rem .9rem;min-height:64px}.file-name{font-weight:650;overflow-wrap:anywhere}.file-meta{font-size:.82rem;color:#64748b;margin-top:.18rem}
.success-box{border:1px solid #86efac;background:#f0fdf4;color:#166534;border-radius:12px;padding:.75rem .95rem}
.stButton button,.stDownloadButton button{border-radius:10px}.stDownloadButton button{min-height:2.55rem}
[data-testid="stFileUploaderDropzone"]{border-radius:14px;min-height:150px}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}}
</style>
"""
DARK = """
<style>
.block-container{max-width:1540px;padding-top:1.6rem;padding-bottom:3rem}
.hero h1{margin:0 0 .25rem;font-size:clamp(1.8rem,3vw,2.55rem);letter-spacing:-.04em}.hero p{color:#b4c0d1;margin:0 0 1.25rem}
.section-title{font-size:1.15rem;font-weight:750;margin:1.25rem 0 .55rem}
.file-card{border:1px solid #3b4a60;border-radius:14px;background:#151e2e;padding:.75rem .9rem;min-height:64px}.file-name{font-weight:650;overflow-wrap:anywhere}.file-meta{font-size:.82rem;color:#b4c0d1;margin-top:.18rem}
.success-box{border:1px solid #1f7a43;background:#12351f;color:#d1fae5;border-radius:12px;padding:.75rem .95rem}
.stButton button,.stDownloadButton button{border-radius:10px;background:#202c40!important;color:#f8fafc!important;border-color:#52637a!important}.stDownloadButton button{min-height:2.55rem}
[data-testid="stFileUploaderDropzone"]{background:#111827!important;border-color:#52637a!important;border-radius:14px;min-height:150px}.stApp{background:#0b1020;color:#f8fafc}section[data-testid="stSidebar"]{background:#111827;border-right:1px solid #334155}
[data-testid="stFileUploaderDropzone"] *{color:#f8fafc!important}
[data-testid="stFileUploaderDropzone"] button{background:#202c40!important;color:#f8fafc!important;border-color:#52637a!important}
[data-baseweb="input"]>div,[data-baseweb="select"]>div{background:#172033!important;border-color:#52637a!important;color:#f8fafc!important}
[data-baseweb="input"] input,[data-baseweb="select"] input{color:#f8fafc!important;-webkit-text-fill-color:#f8fafc!important}
[data-testid="stNumberInput"] button{background:#202c40!important;color:#f8fafc!important;border-color:#52637a!important}
[data-testid="stSidebar"] [role="radiogroup"] label,[data-testid="stSidebar"] [role="radiogroup"] label p{color:#f8fafc!important}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}}
</style>
"""
st.markdown(DARK if st.session_state.theme == "Тёмная" else LIGHT, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Параметры")
    st.caption("Настройки применяются ко всем изображениям.")
    size = st.selectbox("Размер холста", [1200, 1000], format_func=lambda x: f"{x} × {x} px", index=0)
    max_margin = max(0, size // 2 - 1)
    margin = st.number_input("Отступ вокруг объекта (px)", min_value=0, max_value=max_margin, value=min(10, max_margin), step=1)
    st.caption("Отступ задаётся на финальном квадратном холсте. Пропорции объекта сохраняются.")

    st.markdown("**Формат результата**")
    fmt = st.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True, label_visibility="collapsed")
    transparent = False
    if fmt in ("AUTO", "PNG"):
        transparent = st.radio("Цвет полей", ["Белый", "Прозрачный"], horizontal=True) == "Прозрачный"

    st.markdown("**Режим обрезки**")
    mode = st.radio(
        "Режим",
        ["auto", "manual", "none"],
        format_func=lambda x: {"auto": "Авто — убрать пустой фон", "manual": "Вручную — указать поля", "none": "Без обрезки"}[x],
        label_visibility="collapsed",
    )
    manual = (0, 0, 0, 0)
    if mode == "manual":
        c1, c2 = st.columns(2)
        top = c1.number_input("Сверху", 0, 100000, 0)
        bottom = c2.number_input("Снизу", 0, 100000, 0)
        left = c1.number_input("Слева", 0, 100000, 0)
        right = c2.number_input("Справа", 0, 100000, 0)
        manual = (top, bottom, left, right)

    st.divider()
    theme_choice = st.radio("Тема", ["☀️ Светлая", "🌙 Тёмная"], index=0 if st.session_state.theme == "Светлая" else 1, horizontal=True)
    selected_theme = "Тёмная" if "Тёмная" in theme_choice else "Светлая"
    if selected_theme != st.session_state.theme:
        st.session_state.theme = selected_theme
        st.rerun()

st.markdown('<div class="hero"><h1>🖼️ Обработчик изображений</h1><p>Обрезка объекта · квадратный холст · конвертация формата</p></div>', unsafe_allow_html=True)

if not AVIF_SUPPORTED:
    st.caption("AVIF не включён — установите pillow-avif-plugin для поддержки AVIF.")

st.markdown('<div class="section-title">1. Загрузка изображений</div>', unsafe_allow_html=True)
with st.container(border=True):
    st.caption("Перетащите файлы сюда или выберите их на компьютере")
    uploader_key = f"image_uploader_{st.session_state.uploader_key}"
    uploaded = st.file_uploader("Выбрать изображения", type=INPUT_EXTENSIONS, accept_multiple_files=True, key=uploader_key, label_visibility="collapsed")
    st.caption("Можно загрузить несколько файлов одновременно.")

active = []
for uf in uploaded or []:
    raw = uf.getvalue()
    fingerprint = hashlib.sha256(raw).hexdigest()
    file_id = f"{uf.name}:{fingerprint}"
    if file_id not in st.session_state.excluded_files:
        active.append((file_id, uf, fingerprint))

signature = tuple(x[2] for x in active)
if signature != st.session_state.upload_signature:
    st.session_state.upload_signature = signature
    st.session_state.results = []

if uploaded:
    st.markdown('<div class="section-title">Загруженные файлы</div>', unsafe_allow_html=True)
    a, b = st.columns([4, 1])
    a.caption(f"Выбрано: {len(active)} из {len(uploaded)}")
    if b.button("🗑️ Очистить", use_container_width=True):
        st.session_state.excluded_files = set()
        st.session_state.uploader_key += 1
        st.session_state.results = []
        st.session_state.upload_signature = None
        st.rerun()
    for fid, uf, fingerprint in active:
        ci, ca = st.columns([9, 1], vertical_alignment="center")
        ext = Path(uf.name).suffix.upper().lstrip(".") or "FILE"
        ci.markdown(f'<div class="file-card"><div class="file-name">📄 {uf.name}</div><div class="file-meta">{uf.size / 1024:.1f} КБ · {ext}</div></div>', unsafe_allow_html=True)
        if ca.button("×", key=f"remove_{fingerprint}", help=f"Убрать {uf.name}"):
            st.session_state.excluded_files.add(fid)
            st.session_state.results = []
            st.rerun()

st.markdown('<div class="section-title">2. Обработка</div>', unsafe_allow_html=True)
if active and margin * 2 < size:
    if st.button("▶ Обработать изображения", type="primary", use_container_width=True):
        results, errors = [], []
        progress = st.progress(0.0, text="Подготовка…")
        status = st.empty()
        for i, (_, uf, _) in enumerate(active, 1):
            status.markdown(f"**Обработка:** `{uf.name}` · {i} из {len(active)}")
            try:
                img = Image.open(io.BytesIO(uf.getvalue()))
                img.load()
                name, data, out, mime = process_one(img, uf.name, int(size), int(margin), mode, fmt, manual, transparent)
                results.append({"name": name, "data": data, "mime": mime})
            except Exception as exc:
                errors.append(f"{uf.name}: {exc}")
            progress.progress(i / len(active), text=f"Готово: {i} из {len(active)}")
        status.empty()
        progress.empty()
        st.session_state.results = results
        if errors:
            st.warning(f"Не удалось обработать: {len(errors)} файл(а).")
            for error in errors:
                st.caption(f"• {error}")
elif active:
    st.warning("Отступ слишком большой для выбранного размера холста.")

if st.session_state.results:
    results = st.session_state.results
    st.markdown('<div class="section-title">3. Скачать результат</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="success-box">✓ Обработка завершена · <strong>{len(results)} файлов</strong> · {size} × {size} px</div>', unsafe_allow_html=True)

    if len(results) == 1:
        result = results[0]
        st.download_button(
            "⬇ Скачать файл",
            data=result["data"],
            file_name=result["name"],
            mime=result["mime"],
            use_container_width=True,
            type="primary",
            on_click="ignore",
        )
    else:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for result in results:
                zf.writestr(result["name"], result["data"])
        archive_name = f"processed_images_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
        st.download_button(
            "📦 Скачать всё (ZIP)",
            data=archive.getvalue(),
            file_name=archive_name,
            mime="application/zip",
            use_container_width=True,
            type="primary",
            on_click="ignore",
        )
elif not active:
    st.info("Добавьте одно или несколько изображений выше, чтобы начать обработку.")
