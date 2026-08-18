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

APP_VERSION = "1.3"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
SUPPORTED_INPUTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif") + ((".avif",) if AVIF_SUPPORTED else ())

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Логика обработки
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
            return all(all(channel > threshold for channel in pixels[x, y]) for y in range(height))

        def is_empty_row(y):
            return all(all(channel > threshold for channel in pixels[x, y]) for x in range(width))

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
    top = min(int(top), height - 1)
    bottom = min(int(bottom), height - 1)
    left = min(int(left), width - 1)
    right = min(int(right), width - 1)

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
    """Без обрезки — вписать изображение в квадратный холст с отступом."""
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
    available = max(1, size - margin_px * 2)
    scale = min(available / max(1, cw), available / max(1, ch))
    new_w = max(1, int(cw * scale))
    new_h = max(1, int(ch * scale))
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
        processed = manual_crop_with_margin(
            img, margin, size, effective_format, top, bottom, left, right, fill_transparent
        )
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
    return out_name, buf.getvalue(), processed


# ---------------------------------------------------------------------------
# Состояние Streamlit
# ---------------------------------------------------------------------------

if "theme" not in st.session_state:
    st.session_state.theme = "Светлая"
if "excluded_files" not in st.session_state:
    st.session_state.excluded_files = set()
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "results" not in st.session_state:
    st.session_state.results = []


# ---------------------------------------------------------------------------
# Стили — рассчитаны на Streamlit Community Cloud
# ---------------------------------------------------------------------------

COMMON_CSS = """
<style>
.block-container {
    max-width: 1540px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}
.hero { padding: .1rem 0 1.25rem; }
.hero h1 {
    margin: 0 0 .25rem;
    font-size: clamp(1.8rem, 3vw, 2.55rem);
    line-height: 1.15;
    letter-spacing: -.04em;
}
.hero p { margin: 0; font-size: .98rem; opacity: .7; }
.section-title {
    font-size: 1.15rem;
    font-weight: 750;
    margin: 1.25rem 0 .55rem;
}
.file-card, .result-card {
    border: 1px solid var(--app-border);
    border-radius: 14px;
    background: var(--app-card);
    padding: .75rem .9rem;
}
.file-card { min-height: 64px; }
.file-name { font-weight: 650; overflow-wrap: anywhere; }
.file-meta, .result-meta { font-size: .82rem; opacity: .65; margin-top: .18rem; }
.result-card { min-height: 100px; margin-bottom: .55rem; }
.result-icon { font-size: 1.7rem; line-height: 1; margin-bottom: .45rem; }
.result-name { font-weight: 650; overflow-wrap: anywhere; }
.success-box {
    border: 1px solid #86efac;
    background: #f0fdf4;
    color: #166534;
    border-radius: 12px;
    padding: .75rem .95rem;
}
[data-testid="stProgressBar"] { margin: .35rem 0 .8rem; }
[data-testid="stProgressBar"] > div > div { border-radius: 999px; }
button[kind="primary"] { border-radius: 10px; min-height: 2.65rem; }
button[kind="secondary"] { border-radius: 10px; }
@media (max-width: 900px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    .hero h1 { font-size: 1.85rem; }
}
</style>
"""

LIGHT_CSS = """
<style>
:root {
    --app-border: #e2e8f0;
    --app-card: #ffffff;
}
.stApp { background: #f6f8fb; }
section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e2e8f0; }
div[data-testid="stFileUploaderDropzone"] {
    border: 2px dashed #cbd5e1;
    border-radius: 14px;
    background: #fbfdff;
    min-height: 150px;
}
div[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #2563eb;
    background: #eff6ff;
}
</style>
"""

DARK_CSS = """
<style>
:root {
    --app-border: #293548;
    --app-card: #111827;
}
.stApp { background: #0b1020; }
section[data-testid="stSidebar"] { background: #111827; border-right: 1px solid #293548; }
div[data-testid="stFileUploaderDropzone"] {
    border: 2px dashed #475569;
    border-radius: 14px;
    background: #0f172a;
    min-height: 150px;
}
div[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #60a5fa;
    background: #172033;
}
.success-box { background: #052e16; color: #bbf7d0; border-color: #166534; }
</style>
"""

st.markdown(COMMON_CSS + (DARK_CSS if st.session_state.theme == "Тёмная" else LIGHT_CSS), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Боковая панель
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Параметры")
    st.caption("Настройки применяются ко всем изображениям.")

    size = st.number_input(
        "Размер холста (px)",
        min_value=10,
        max_value=10000,
        value=1200,
        step=10,
    )
    max_margin = max(0, int(size // 2) - 1)
    margin = st.number_input(
        "Отступ (px)",
        min_value=0,
        max_value=max_margin,
        value=min(10, max_margin),
        step=1,
    )

    st.markdown("**Формат результата**")
    fmt = st.radio(
        "Формат",
        ["AUTO", "PNG", "JPG"],
        horizontal=True,
        label_visibility="collapsed",
        help="AUTO — PNG сохраняется как PNG, JPG/JPEG как JPG, остальные форматы как PNG.",
    )

    fill_transparent = False
    if fmt in ("AUTO", "PNG"):
        fill_choice = st.radio(
            "Цвет полей",
            ["Белый", "Прозрачный"],
            horizontal=True,
            help="Прозрачные поля доступны только для PNG.",
        )
        fill_transparent = fill_choice == "Прозрачный"

    st.markdown("**Режим обрезки**")
    crop_mode = st.radio(
        "Режим",
        ["auto", "manual", "none"],
        format_func=lambda value: {
            "auto": "Авто — убрать пустые поля",
            "manual": "Вручную — указать пиксели",
            "none": "Без обрезки",
        }[value],
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

    st.divider()
    theme_choice = st.radio(
        "Тема",
        ["☀️ Светлая", "🌙 Тёмная"],
        index=0 if st.session_state.theme == "Светлая" else 1,
        horizontal=True,
    )
    new_theme = "Тёмная" if "Тёмная" in theme_choice else "Светлая"
    if new_theme != st.session_state.theme:
        st.session_state.theme = new_theme
        st.rerun()


# ---------------------------------------------------------------------------
# Основной экран
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="hero">'
    '<h1>🖼️ Обработчик изображений</h1>'
    '<p>Обрезка с отступом · квадратный холст · конвертация формата</p>'
    '</div>',
    unsafe_allow_html=True,
)

if not AVIF_SUPPORTED:
    st.warning("Поддержка AVIF не активна. В requirements.txt должен быть установлен pillow-avif-plugin.")

st.markdown('<div class="section-title">1. Загрузка изображений</div>', unsafe_allow_html=True)

with st.container(border=True):
    st.caption("Перетащите файлы в область ниже или выберите их на компьютере")
    upload_key = f"image_uploader_{st.session_state.uploader_key}"
    uploaded_files = st.file_uploader(
        "Выбрать изображения",
        type=[ext.strip(".") for ext in SUPPORTED_INPUTS],
        accept_multiple_files=True,
        key=upload_key,
        label_visibility="collapsed",
        help="PNG, JPG, WEBP, BMP, TIFF, GIF и AVIF.",
    )
    st.caption("Можно загрузить несколько файлов одновременно.")

active_files = []
for uf in uploaded_files or []:
    file_id = f"{uf.name}:{uf.size}"
    if file_id not in st.session_state.excluded_files:
        active_files.append((file_id, uf))

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
            st.rerun()

    for file_id, uf in active_files:
        col_info, col_action = st.columns([9, 1], vertical_alignment="center")
        with col_info:
            ext = Path(uf.name).suffix.upper().lstrip(".") or "FILE"
            st.markdown(
                f'<div class="file-card">'
                f'<div class="file-name">📄 {uf.name}</div>'
                f'<div class="file-meta">{uf.size / 1024:.1f} КБ · {ext}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col_action:
            if st.button("×", key=f"remove_{file_id}", help=f"Убрать {uf.name}"):
                st.session_state.excluded_files.add(file_id)
                st.session_state.results = []
                st.rerun()

st.markdown('<div class="section-title">2. Обработка</div>', unsafe_allow_html=True)

if active_files and margin * 2 < size:
    if st.button("▶ Обработать изображения", type="primary", use_container_width=True):
        results = []
        errors = []
        progress_bar = st.progress(0.0, text="Подготовка…")
        status_text = st.empty()
        total = len(active_files)

        for index, (_, uf) in enumerate(active_files, start=1):
            status_text.markdown(f"**Обработка:** `{uf.name}` · {index} из {total}")
            try:
                img = Image.open(uf)
                img.load()
                out_name, data, processed_img = process_one(
                    img,
                    uf.name,
                    int(size),
                    int(margin),
                    crop_mode,
                    fmt,
                    manual_vals,
                    fill_transparent,
                )
                results.append(
                    {
                        "name": out_name,
                        "data": data,
                        "width": processed_img.width,
                        "height": processed_img.height,
                    }
                )
            except Exception as exc:
                errors.append(f"{uf.name}: {exc}")
            progress_bar.progress(index / total, text=f"Готово: {index} из {total}")

        status_text.empty()
        progress_bar.empty()
        st.session_state.results = results

        if errors:
            st.warning(f"Не удалось обработать: {len(errors)} файл(а).")
            for error in errors:
                st.caption(f"• {error}")

if st.session_state.results:
    results = st.session_state.results
    st.markdown('<div class="section-title">3. Результат</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="success-box">✓ Обработка завершена · <strong>{len(results)} файлов</strong></div>',
        unsafe_allow_html=True,
    )
    st.write("")

    columns_count = min(3, max(1, len(results)))
    cols = st.columns(columns_count)
    for index, result in enumerate(results):
        with cols[index % columns_count]:
            size_kb = len(result["data"]) / 1024
            st.markdown(
                f'<div class="result-card">'
                f'<div class="result-icon">🖼️</div>'
                f'<div class="result-name">{result["name"]}</div>'
                f'<div class="result-meta">{result["width"]} × {result["height"]} px · {size_kb:.1f} КБ</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇️ Скачать",
                data=result["data"],
                file_name=result["name"],
                mime="image/png" if result["name"].endswith(".png") else "image/jpeg",
                key=f"download_{index}_{result['name']}",
                use_container_width=True,
            )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for result in results:
            zf.writestr(result["name"], result["data"])
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
elif not active_files:
    st.info("Добавьте одно или несколько изображений выше, чтобы начать обработку.")
