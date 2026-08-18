import io
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

try:
    import pillow_avif  # noqa: F401 — регистрирует поддержку чтения .avif в Pillow
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

APP_VERSION = "1.2"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
SUPPORTED_INPUTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif") + ((".avif",) if AVIF_SUPPORTED else ())

st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="expanded")


# ---------------------------------------------------------------------------
# Логика кропа
# ---------------------------------------------------------------------------

def smart_crop_with_margin(img, margin_px, size, background, fill_transparent=False):
    """Автоматическая обрезка пустых полей (близких к белому) по краям."""
    bg_color = _get_bg_color(background, fill_transparent)

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


def manual_crop_with_margin(img, margin_px, size, background, top, bottom, left, right, fill_transparent=False):
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
    bg_color = _get_bg_color(background, fill_transparent)
    return _finish_crop(img, bbox, margin_px, size, background, bg_color)


def no_crop_with_margin(img, margin_px, size, background, fill_transparent=False):
    """Без обрезки — просто вписать изображение в холст с отступом."""
    bbox = (0, 0, img.width, img.height)
    bg_color = _get_bg_color(background, fill_transparent)
    return _finish_crop(img, bbox, margin_px, size, background, bg_color)


def _get_bg_color(background, fill_transparent):
    if background == "PNG" and fill_transparent:
        return (0, 0, 0, 0)
    if background == "PNG":
        return (255, 255, 255, 255)
    return (255, 255, 255)


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
    if ext in (".gif", ".webp", ".tif", ".tiff", ".avif"):
        return "PNG"
    return "JPG"


def process_one(img, file_name, size, margin, crop_mode, fmt, manual_vals, fill_transparent):
    effective_format = get_effective_output_format(fmt, file_name)

    if crop_mode == "auto":
        processed = smart_crop_with_margin(img, margin, size, effective_format, fill_transparent)
    elif crop_mode == "manual":
        top, bottom, left, right = manual_vals
        processed = manual_crop_with_margin(img, margin, size, effective_format, top, bottom, left, right, fill_transparent)
    else:
        processed = no_crop_with_margin(img, margin, size, effective_format, fill_transparent)

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

if "theme" not in st.session_state:
    st.session_state.theme = "Светлая"
if "excluded_files" not in st.session_state:
    st.session_state.excluded_files = set()
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

LIGHT_CSS = """
<style>
:root {
    --accent: #2563eb;
    --accent-soft: #eff6ff;
    --border: #e5e7eb;
    --muted: #64748b;
    --card: #ffffff;
    --bg: #f6f8fb;
}
.stApp { background: var(--bg); }
.block-container { max-width: 1500px; padding-top: 2rem; padding-bottom: 3rem; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { border-right: 1px solid var(--border); background: #fff; }
section[data-testid="stSidebar"] > div { padding-top: 2rem; }
.stTitle { letter-spacing: -0.03em; }
.hero { padding: 0.25rem 0 1.2rem; }
.hero h1 { margin-bottom: .25rem; font-size: 2.35rem; letter-spacing: -.04em; }
.hero p { color: var(--muted); font-size: 1rem; margin-top: 0; }
.section-title { font-size: 1.2rem; font-weight: 700; margin: 1.1rem 0 .55rem; }
.upload-card { border: 1px solid var(--border); border-radius: 18px; padding: 1rem; background: var(--card); box-shadow: 0 5px 18px rgba(15,23,42,.04); }
div[data-testid="stFileUploader"] { background: var(--card); border-radius: 16px; }
div[data-testid="stFileUploaderDropzone"] { border: 2px dashed #cbd5e1; border-radius: 14px; background: #fafcff; min-height: 170px; }
div[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent); background: var(--accent-soft); }
.file-card { border: 1px solid var(--border); border-radius: 14px; background: var(--card); padding: .8rem .95rem; margin: .35rem 0; }
.file-name { font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-meta { color: var(--muted); font-size: .82rem; margin-top: .15rem; }
.result-card { border: 1px solid var(--border); border-radius: 16px; background: var(--card); padding: 1rem; box-shadow: 0 5px 18px rgba(15,23,42,.04); min-height: 105px; }
.result-icon { font-size: 1.9rem; }
.result-name { font-weight: 650; overflow-wrap: anywhere; }
.result-meta { color: var(--muted); font-size: .82rem; margin-top: .2rem; }
.success-box { border: 1px solid #bbf7d0; background: #f0fdf4; border-radius: 14px; padding: .8rem 1rem; }
[data-testid="stProgressBar"] > div > div { border-radius: 99px; }
button[kind="primary"] { border-radius: 10px; }
</style>
"""

DARK_CSS = """
<style>
.stApp { background: #0b1020; color: #eef2ff; }
.block-container { max-width: 1500px; }
section[data-testid="stSidebar"] { background: #111827; border-right: 1px solid #273449; }
[data-testid="stMarkdownContainer"], label, p, span, h1, h2, h3 { color: #eef2ff !important; }
.hero p, .file-meta, .result-meta { color: #94a3b8 !important; }
.upload-card, .file-card, .result-card { background: #111827; border-color: #273449; box-shadow: none; }
div[data-testid="stFileUploaderDropzone"] { background: #0f172a; border-color: #475569; }
div[data-testid="stFileUploaderDropzone"]:hover { background: #172033; border-color: #60a5fa; }
.success-box { background: #052e16; border-color: #166534; }
</style>
"""

st.markdown(DARK_CSS if st.session_state.theme == "Тёмная" else LIGHT_CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Параметры")
    st.caption("Настройки применяются ко всем загруженным изображениям.")

    size = st.number_input("Размер холста (px)", min_value=10, max_value=10000, value=1200, step=10)
    margin = st.number_input(
        "Отступ (px)",
        min_value=0,
        max_value=int(size // 2) - 1 if size > 1 else 0,
        value=min(10, max(0, size // 2 - 1)),
        step=1,
    )

    st.markdown("**Формат результата**")
    fmt = st.radio(
        "Формат",
        ["AUTO", "PNG", "JPG"],
        horizontal=True,
        label_visibility="collapsed",
        help="AUTO — определяется по исходному расширению файла.",
    )

    fill_transparent = False
    if fmt in ("AUTO", "PNG"):
        fill_choice = st.radio(
            "Цвет полей",
            ["Белый", "Прозрачный"],
            horizontal=True,
            help="Прозрачный работает только для PNG.",
        )
        fill_transparent = fill_choice == "Прозрачный"

    st.markdown("**Режим обрезки**")
    crop_mode = st.radio(
        "Режим",
        ["auto", "manual", "none"],
        format_func=lambda v: {
            "auto": "Авто — убрать пустые поля",
            "manual": "Вручную — указать пиксели",
            "none": "Без обрезки",
        }[v],
        label_visibility="collapsed",
    )

    manual_vals = (0, 0, 0, 0)
    if crop_mode == "manual":
        st.caption("Сколько пикселей срезать с каждой стороны")
        c1, c2 = st.columns(2)
        top = c1.number_input("Сверху", min_value=0, value=0, step=1)
        bottom = c2.number_input("Снизу", min_value=0, value=0, step=1)
        left = c1.number_input("Слева", min_value=0, value=0, step=1)
        right = c2.number_input("Справа", min_value=0, value=0, step=1)
        manual_vals = (top, bottom, left, right)

    if margin * 2 >= size:
        st.error("Отступ должен быть меньше половины размера холста.")

    st.divider()
    theme = st.radio("Тема интерфейса", ["☀️ Светлая", "🌙 Тёмная"], index=0 if st.session_state.theme == "Светлая" else 1)
    new_theme = "Тёмная" if "Тёмная" in theme else "Светлая"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()

# Header
st.markdown(
    '<div class="hero"><h1>🖼️ Обработчик изображений</h1>'
    '<p>Обрезка с отступом · квадратный холст · конвертация формата</p></div>',
    unsafe_allow_html=True,
)

if not AVIF_SUPPORTED:
    st.warning("Поддержка AVIF не активна: добавьте `pillow-avif-plugin` в requirements.txt, чтобы включить AVIF.")

st.markdown('<div class="section-title">1. Загрузите изображения</div>', unsafe_allow_html=True)

upload_key = f"image_uploader_{st.session_state.uploader_key}"
uploaded_files = st.file_uploader(
    "Перетащите изображения сюда или нажмите «Browse files»",
    type=[ext.strip(".") for ext in SUPPORTED_INPUTS],
    accept_multiple_files=True,
    key=upload_key,
    help="Поддерживаются PNG, JPG, WEBP, BMP, TIFF, GIF и AVIF (если установлен плагин).",
)

active_files = []
for index, uf in enumerate(uploaded_files or []):
    file_id = f"{uf.name}:{uf.size}:{index}"
    if file_id not in st.session_state.excluded_files:
        active_files.append((file_id, uf))

if uploaded_files:
    st.markdown('<div class="section-title">Загруженные файлы</div>', unsafe_allow_html=True)
    st.caption(f"Выбрано: {len(active_files)} из {len(uploaded_files)}")

    for file_id, uf in active_files:
        col_info, col_action = st.columns([8, 1])
        with col_info:
            st.markdown(
                f'<div class="file-card"><div class="file-name">📄 {uf.name}</div>'
                f'<div class="file-meta">{uf.size / 1024:.1f} КБ · {Path(uf.name).suffix.upper().lstrip(".") or "FILE"}</div></div>',
                unsafe_allow_html=True,
            )
        with col_action:
            st.write("")
            if st.button("×", key=f"remove_{file_id}", help=f"Удалить {uf.name}"):
                st.session_state.excluded_files.add(file_id)
                st.rerun()

    controls_left, controls_right = st.columns([1, 4])
    with controls_left:
        if st.button("🗑️ Очистить список", use_container_width=True):
            st.session_state.excluded_files = set()
            st.session_state.uploader_key += 1
            st.rerun()
    with controls_right:
        if active_files:
            st.caption("Можно удалить отдельные файлы кнопкой × справа от имени.")

st.markdown('<div class="section-title">2. Обработка</div>', unsafe_allow_html=True)

if active_files and margin * 2 < size:
    if st.button("▶ Обработать изображения", type="primary", use_container_width=True):
        results = []
        progress_bar = st.progress(0.0, text="Подготовка…")
        status_text = st.empty()
        total = len(active_files)

        for i, (_, uf) in enumerate(active_files, start=1):
            status_text.markdown(f"**Обработка:** `{uf.name}` — {i} из {total}")
            try:
                img = Image.open(uf)
                img.load()
                out_name, buf, processed_img = process_one(
                    img, uf.name, int(size), int(margin), crop_mode, fmt, manual_vals, fill_transparent
                )
                results.append(
                    {
                        "name": out_name,
                        "buf": buf,
                        "width": processed_img.width,
                        "height": processed_img.height,
                    }
                )
            except Exception as e:
                st.error(f"Ошибка при обработке {uf.name}: {e}")
            progress_bar.progress(i / total, text=f"Готово: {i} из {total}")

        status_text.empty()
        progress_bar.empty()

        if results:
            st.markdown('<div class="section-title">3. Результат</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="success-box">✓ Обработка завершена · <strong>{len(results)} из {total}</strong> файлов</div>',
                unsafe_allow_html=True,
            )
            st.write("")

            cols = st.columns(min(3, len(results)))
            for idx, result in enumerate(results):
                with cols[idx % len(cols)]:
                    st.markdown(
                        f'<div class="result-card"><div class="result-icon">🖼️</div>'
                        f'<div class="result-name">{result["name"]}</div>'
                        f'<div class="result-meta">{result["width"]} × {result["height"]} px · {len(result["buf"].getvalue()) / 1024:.1f} КБ</div></div>',
                        unsafe_allow_html=True,
                    )
                    st.download_button(
                        "⬇️ Скачать",
                        data=result["buf"].getvalue(),
                        file_name=result["name"],
                        mime="image/png" if result["name"].endswith(".png") else "image/jpeg",
                        key=f"dl_{idx}_{result['name']}",
                        use_container_width=True,
                    )

            if len(results) > 1:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for result in results:
                        zf.writestr(result["name"], result["buf"].getvalue())
                zip_buf.seek(0)
                st.write("")
                st.download_button(
                    "📦 Скачать всё (ZIP)",
                    data=zip_buf.getvalue(),
                    file_name="processed_images.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary",
                )
else:
    st.info("Добавьте одно или несколько изображений выше, чтобы начать обработку.")
