from pathlib import Path

source = Path(__file__).with_name("app_v4.py").read_text(encoding="utf-8-sig")
source = source.replace('value=min(10, size // 2 - 1)', 'value=min(30, size // 2 - 1)', 1)
source = source.replace('padding-top:.45rem;padding-bottom:1rem', 'padding-top:.3rem;padding-bottom:.6rem', 1)
source = source.replace('margin:0 0 .05rem;font-size:clamp(1.65rem,2.6vw,2.25rem)', 'margin:0;font-size:clamp(1.65rem,2.6vw,2.25rem)', 1)
source = source.replace('margin:0 0 .35rem;font-size:.9rem', 'margin:0 0 .2rem;font-size:.9rem', 1)
source = source.replace('padding:.3rem .7rem}', 'padding:.2rem .6rem}', 1)
source = source.replace('min-height:85px;padding:.4rem', 'min-height:65px;padding:.3rem', 1)
source = source.replace('padding:.25rem}', 'padding:.15rem}', 1)
source = source.replace('padding:.15rem .35rem;margin:.15rem 0', 'padding:.1rem .3rem;margin:.1rem 0', 1)
source = source.replace('padding:.1rem .25rem}', 'padding:.05rem .2rem}', 1)
source = source.replace('gap:.4rem}', 'gap:.25rem}', 1)
source = source.replace('margin-bottom:.25rem}', 'margin-bottom:.15rem}', 1)
source = source.replace('min-height:2.15rem;padding:.3rem .65rem', 'min-height:1.9rem;padding:.2rem .55rem', 1)
source = source.replace('padding:.45rem .7rem}', 'padding:.35rem .6rem}', 1)
source = source.replace('margin:.2rem 0}', 'margin:.15rem 0}', 1)

# Показываем миниатюры сразу после загрузки, до запуска обработки.
preview_function = r'''

def _show_uploaded_previews(uploaded, collect_func, key_prefix):
    if not uploaded:
        return
    try:
        items = collect_func(uploaded)
    except Exception as exc:
        st.warning(f"Превью недоступно: {exc}")
        return
    if not items:
        return
    st.markdown("**👁️ Превью загруженных изображений**")
    preview_items = items[:30]
    cols = st.columns(5)
    for index, (name, data) in enumerate(preview_items):
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            with cols[index % 5]:
                st.image(image, use_container_width=True)
                st.caption(name)
        except Exception:
            with cols[index % 5]:
                st.caption(f"⚠️ {name}")
    if len(items) > len(preview_items):
        st.caption(f"Показаны первые {len(preview_items)} изображений из {len(items)}.")
'''

source = source.replace('def trim_background(img: Image.Image, threshold: int = 18):', preview_function + '\n\ndef trim_background(img: Image.Image, threshold: int = 18):', 1)
source = source.replace('        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in uploaded):\n            st.error("Один из ZIP-архивов превышает 300 МБ.")', '        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in uploaded):\n            st.error("Один из ZIP-архивов превышает 300 МБ.")\n        _show_uploaded_previews(uploaded, collect_image_inputs, "crop")', 1)
source = source.replace('        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in resize_uploaded): st.error("Один из ZIP-архивов превышает 300 МБ.")', '        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in resize_uploaded): st.error("Один из ZIP-архивов превышает 300 МБ.")\n        _show_uploaded_previews(resize_uploaded, collect_image_inputs, "resize")', 1)

exec(compile(source, "app_v4.py", "exec"))
