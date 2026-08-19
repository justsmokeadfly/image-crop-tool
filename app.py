import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from PIL import Image

try:
    import pillow_avif  # noqa: F401
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

APP_VERSION = "1.7"
APP_NAME = f"Обработчик изображений v{APP_VERSION}"
SUPPORTED_INPUTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif") + ((".avif",) if AVIF_SUPPORTED else ())
st.set_page_config(page_title=APP_NAME, page_icon="🖼️", layout="wide", initial_sidebar_state="expanded")


def finish_crop(img, bbox, margin, size, fmt, transparent):
    cropped = img.crop(bbox)
    available = max(1, size - margin * 2)
    scale = min(available / max(1, cropped.width), available / max(1, cropped.height))
    nw, nh = max(1, int(cropped.width * scale)), max(1, int(cropped.height * scale))
    cropped = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    if fmt == "PNG":
        bg = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
        result = Image.new("RGBA", (size, size), bg)
    else:
        result = Image.new("RGB", (size, size), (255, 255, 255))
    pos = ((size - nw) // 2, (size - nh) // 2)
    result.paste(cropped, pos, cropped if cropped.mode == "RGBA" else None)
    return result


def smart_crop(img, margin, size, fmt, transparent):
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    bbox = img.getbbox()
    if not bbox or bbox == (0, 0, img.width, img.height):
        rgb = img.convert("RGB")
        px = rgb.load(); w, h = rgb.size; threshold = 245
        def empty_col(x): return all(all(c > threshold for c in px[x, y]) for y in range(h))
        def empty_row(y): return all(all(c > threshold for c in px[x, y]) for x in range(w))
        left, right, top, bottom = 0, w, 0, h
        if all(empty_col(x) for x in range(int(w * .05))):
            for x in range(w):
                if not empty_col(x): left = max(0, x - 5); break
        if all(empty_col(x) for x in range(w - 1, w - int(w * .05) - 1, -1)):
            for x in range(w - 1, -1, -1):
                if not empty_col(x): right = min(w, x + 5); break
        if all(empty_row(y) for y in range(int(h * .05))):
            for y in range(h):
                if not empty_row(y): top = max(0, y - 5); break
        if all(empty_row(y) for y in range(h - 1, h - int(h * .05) - 1, -1)):
            for y in range(h - 1, -1, -1):
                if not empty_row(y): bottom = min(h, y + 5); break
        bbox = (left, top, right, bottom)
    return finish_crop(img, bbox, margin, size, fmt, transparent)


def process_one(img, name, size, margin, mode, fmt, manual, transparent):
    ext = Path(name).suffix.lower()
    effective = fmt if fmt != "AUTO" else ("PNG" if ext in (".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif") else "JPG")
    if mode == "auto":
        out = smart_crop(img, margin, size, effective, transparent)
    elif mode == "manual":
        top, bottom, left, right = manual
        w, h = img.size
        box = (min(left, w - 1), min(top, h - 1), max(min(w - right, w), min(left, w - 1) + 1), max(min(h - bottom, h), min(top, h - 1) + 1))
        out = finish_crop(img, box, margin, size, effective, transparent)
    else:
        out = finish_crop(img, (0, 0, img.width, img.height), margin, size, effective, transparent)
    if effective == "PNG":
        extension, mime = ".png", "image/png"
    else:
        extension, mime = ".jpg", "image/jpeg"
        if out.mode == "RGBA": out = out.convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "PNG" if effective == "PNG" else "JPEG", quality=95 if effective == "JPG" else None)
    data = buf.getvalue()
    return f"{Path(name).stem}{extension}", data, out, mime


for key, default in (("theme", "Светлая"), ("excluded_files", set()), ("uploader_key", 0), ("results", []), ("upload_signature", None)):
    st.session_state.setdefault(key, default)

COMMON = """
<style>
.block-container{max-width:1540px;padding-top:1.6rem;padding-bottom:3rem}
.hero h1{margin:0 0 .25rem;font-size:clamp(1.8rem,3vw,2.55rem);letter-spacing:-.04em}.hero p{opacity:.72;margin:0 0 1.25rem}
.section-title{font-size:1.15rem;font-weight:750;margin:1.25rem 0 .55rem}
.file-card{border:1px solid var(--border);border-radius:14px;background:var(--card);padding:.75rem .9rem;min-height:64px}.file-name{font-weight:650;overflow-wrap:anywhere}.file-meta{font-size:.82rem;color:var(--muted);margin-top:.18rem}
.success-box{border:1px solid var(--success-border);background:var(--success-bg);color:var(--success-text);border-radius:12px;padding:.75rem .95rem}
.stButton button,.stDownloadButton button{border-radius:10px}.stDownloadButton button{min-height:2.55rem}
[data-testid="stFileUploaderDropzone"]{background:var(--widget-bg)!important;border-color:var(--widget-border)!important;border-radius:14px;min-height:150px}
[data-testid="stFileUploaderDropzone"] *{color:var(--widget-text)!important}
[data-testid="stFileUploaderDropzone"] button{background:var(--button-bg)!important;color:var(--widget-text)!important;border-color:var(--widget-border)!important}
[data-baseweb="select"]>div,[data-baseweb="input"]>div{background:var(--widget-bg)!important;border-color:var(--widget-border)!important;color:var(--widget-text)!important}
[data-baseweb="select"] input,[data-baseweb="input"] input{color:var(--widget-text)!important;-webkit-text-fill-color:var(--widget-text)!important}
[data-baseweb="select"] svg{fill:var(--widget-text)!important}
[data-testid="stNumberInput"] button{background:var(--button-bg)!important;color:var(--widget-text)!important;border-color:var(--widget-border)!important}
[data-testid="stSidebar"] [role="radiogroup"] label,[data-testid="stSidebar"] [role="radiogroup"] label p{color:var(--widget-text)!important}
[data-testid="stSidebar"] small{color:var(--muted)!important}
@media(max-width:900px){.block-container{padding-left:1rem;padding-right:1rem}}
</style>
"""
LIGHT = """
<style>
:root{--border:#e2e8f0;--card:#fff;--muted:#64748b;--success-border:#86efac;--success-bg:#f0fdf4;--success-text:#166534;--widget-bg:#fff;--widget-border:#cbd5e1;--widget-text:#0f172a;--button-bg:#fff}
.stApp{background:#f6f8fb;color:#0f172a}section[data-testid="stSidebar"]{background:#fff;border-right:1px solid #e2e8f0}
</style>
"""
DARK = """
<style>
:root{--border:#3b4a60;--card:#151e2e;--muted:#b4c0d1;--success-border:#1f7a43;--success-bg:#12351f;--success-text:#d1fae5;--widget-bg:#172033;--widget-border:#52637a;--widget-text:#f8fafc;--button-bg:#202c40}
.stApp{background:#0b1020;color:#f8fafc}section[data-testid="stSidebar"]{background:#111827;border-right:1px solid #334155}
.stCaption,small{color:#b4c0d1!important}.stAlert{color:#f8fafc!important}
[data-testid="stFileUploaderDropzone"]{background:#111827!important;border-color:#52637a!important}
.stDownloadButton button,.stButton button:not([kind="primary"]){background:#202c40!important;color:#f8fafc!important;border-color:#52637a!important}
.stDownloadButton button:hover,.stButton button:not([kind="primary"]):hover{background:#334155!important}
</style>
"""
st.markdown(COMMON + (DARK if st.session_state.theme == "Тёмная" else LIGHT), unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Параметры")
    st.caption("Настройки применяются ко всем изображениям.")
    size = st.number_input("Размер холста (px)", 10, 10000, 1200, 10)
    max_margin = max(0, int(size // 2) - 1)
    margin = st.number_input("Отступ (px)", 0, max_margin, min(10, max_margin), 1)
    st.markdown("**Формат результата**")
    fmt = st.radio("Формат", ["AUTO", "PNG", "JPG"], horizontal=True, label_visibility="collapsed")
    transparent = False
    if fmt in ("AUTO", "PNG"):
        transparent = st.radio("Цвет полей", ["Белый", "Прозрачный"], horizontal=True) == "Прозрачный"
    st.markdown("**Режим обрезки**")
    mode = st.radio("Режим", ["auto", "manual", "none"], format_func=lambda x:{"auto":"Авто — убрать пустые поля","manual":"Вручную — указать пиксели","none":"Без обрезки"}[x], label_visibility="collapsed")
    manual = (0, 0, 0, 0)
    if mode == "manual":
        c1,c2=st.columns(2); top=c1.number_input("Сверху",0,100000,0); bottom=c2.number_input("Снизу",0,100000,0); left=c1.number_input("Слева",0,100000,0); right=c2.number_input("Справа",0,100000,0); manual=(top,bottom,left,right)
    st.divider()
    theme_choice = st.radio("Тема", ["☀️ Светлая", "🌙 Тёмная"], index=0 if st.session_state.theme == "Светлая" else 1, horizontal=True)
    selected_theme = "Тёмная" if "Тёмная" in theme_choice else "Светлая"
    if selected_theme != st.session_state.theme:
        st.session_state.theme = selected_theme
        st.rerun()

st.markdown('<div class="hero"><h1>🖼️ Обработчик изображений</h1><p>Обрезка с отступом · квадратный холст · конвертация формата</p></div>', unsafe_allow_html=True)
if not AVIF_SUPPORTED: st.warning("Поддержка AVIF не активна. В requirements.txt должен быть установлен pillow-avif-plugin.")
st.markdown('<div class="section-title">1. Загрузка изображений</div>', unsafe_allow_html=True)
with st.container(border=True):
    st.caption("Перетащите файлы в область ниже или выберите их на компьютере")
    key = f"image_uploader_{st.session_state.uploader_key}"
    uploaded = st.file_uploader("Выбрать изображения", type=[x.strip('.') for x in SUPPORTED_INPUTS], accept_multiple_files=True, key=key, label_visibility="collapsed")
    st.caption("Можно загрузить несколько файлов одновременно. Для полностью новой загрузки нажмите «Очистить».")

active=[]
for uf in uploaded or []:
    raw=uf.getvalue(); fp=hashlib.sha256(raw).hexdigest(); fid=f"{uf.name}:{fp}"
    if fid not in st.session_state.excluded_files: active.append((fid,uf,fp))
sig=tuple(x[2] for x in active)
if sig != st.session_state.upload_signature:
    st.session_state.upload_signature=sig; st.session_state.results=[]

if uploaded:
    st.markdown('<div class="section-title">Загруженные файлы</div>', unsafe_allow_html=True)
    a,b=st.columns([4,1]); a.caption(f"Выбрано: {len(active)} из {len(uploaded)}")
    if b.button("🗑️ Очистить", use_container_width=True):
        st.session_state.excluded_files=set(); st.session_state.uploader_key+=1; st.session_state.results=[]; st.session_state.upload_signature=None; st.rerun()
    for fid,uf,fp in active:
        ci,ca=st.columns([9,1],vertical_alignment="center"); ext=Path(uf.name).suffix.upper().lstrip('.') or 'FILE'
        ci.markdown(f'<div class="file-card"><div class="file-name">📄 {uf.name}</div><div class="file-meta">{uf.size/1024:.1f} КБ · {ext}</div></div>',unsafe_allow_html=True)
        if ca.button("×",key=f"remove_{fp}",help=f"Убрать {uf.name}"):
            st.session_state.excluded_files.add(fid); st.session_state.results=[]; st.rerun()

st.markdown('<div class="section-title">2. Обработка</div>', unsafe_allow_html=True)
if active and margin*2 < size and st.button("▶ Обработать изображения",type="primary",use_container_width=True):
    results=[]; errors=[]; progress=st.progress(0.0,text="Подготовка…"); status=st.empty()
    for i,(_,uf,fp) in enumerate(active,1):
        status.markdown(f"**Обработка:** `{uf.name}` · {i} из {len(active)}")
        try:
            img=Image.open(io.BytesIO(uf.getvalue())); img.load()
            name,data,out,mime=process_one(img,uf.name,int(size),int(margin),mode,fmt,manual,transparent)
            results.append({"name":name,"data":data,"width":out.width,"height":out.height,"mime":mime,"key":hashlib.sha256(data).hexdigest()[:20]})
        except Exception as exc: errors.append(f"{uf.name}: {exc}")
        progress.progress(i/len(active),text=f"Готово: {i} из {len(active)}")
    status.empty(); progress.empty(); st.session_state.results=results
    if errors:
        st.warning(f"Не удалось обработать: {len(errors)} файл(а).")
        for e in errors: st.caption(f"• {e}")
elif active and margin*2 >= size:
    st.warning("Отступ слишком большой для выбранного размера холста.")

if st.session_state.results:
    results=st.session_state.results
    st.markdown('<div class="section-title">3. Скачать результат</div>',unsafe_allow_html=True)
    st.markdown(f'<div class="success-box">✓ Обработка завершена · <strong>{len(results)} файлов</strong></div>',unsafe_allow_html=True)
    z=io.BytesIO()
    with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as archive:
        for r in results: archive.writestr(r["name"],r["data"])
    archive_name=f"processed_images_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
    st.download_button("📦 Скачать всё (ZIP)",z.getvalue(),archive_name,"application/zip",use_container_width=True,type="primary",on_click="ignore")
elif not active:
    st.info("Добавьте одно или несколько изображений выше, чтобы начать обработку.")
