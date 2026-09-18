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

# Показываем компактные миниатюры сразу после загрузки, до запуска обработки.
preview_function = r"""

def _show_uploaded_previews(uploaded, collect_func):
    if not uploaded:
        return
    try:
        items = collect_func(uploaded)
    except Exception as exc:
        st.warning(f"Превью недоступно: {exc}")
        return
    if not items:
        return

    import base64
    from html import escape

    cards = []
    for name, data in items[:30]:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            fmt = (image.format or "PNG").lower()
            mime = "image/jpeg" if fmt in ("jpg", "jpeg") else f"image/{fmt}"
            encoded = base64.b64encode(data).decode("ascii")
            safe_name = escape(name)
            size_mb = len(data) / (1024 * 1024)
            size_text = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{len(data) / 1024:.0f} KB"
            cards.append(
                f'''<div style="display:flex;align-items:center;gap:9px;min-width:210px;max-width:290px;height:48px;padding:5px 9px;border-radius:9px;background:var(--secondary-background-color);border:1px solid rgba(128,128,128,.12);box-sizing:border-box;overflow:hidden;">
                    <img src="data:{mime};base64,{encoded}" style="width:36px;height:36px;object-fit:cover;border-radius:5px;flex:0 0 36px;">
                    <div style="min-width:0;line-height:1.2;">
                        <div title="{safe_name}" style="font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{safe_name}</div>
                        <div style="font-size:11px;opacity:.65;margin-top:3px;">{size_text}</div>
                    </div>
                </div>'''
            )
        except Exception:
            cards.append(
                f'''<div style="display:flex;align-items:center;gap:9px;min-width:210px;max-width:290px;height:48px;padding:5px 9px;border-radius:9px;background:var(--secondary-background-color);border:1px solid rgba(128,128,128,.12);box-sizing:border-box;overflow:hidden;">
                    <div style="width:36px;height:36px;border-radius:5px;background:#343943;display:flex;align-items:center;justify-content:center;flex:0 0 36px;">⚠️</div>
                    <div style="min-width:0;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{escape(name)}">{escape(name)}</div>
                </div>'''
            )

    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px;margin-bottom:8px;">' + ''.join(cards) + '</div>',
        unsafe_allow_html=True,
    )
    if len(items) > 30:
        st.caption(f"Показаны первые 30 изображений из {len(items)}.")
"""

source = source.replace('def trim_background(img: Image.Image, threshold: int = 18):', preview_function + '\n\ndef trim_background(img: Image.Image, threshold: int = 18):', 1)
source = source.replace('        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in uploaded):\n            st.error("Один из ZIP-архивов превышает 300 МБ.")', '        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in uploaded):\n            st.error("Один из ZIP-архивов превышает 300 МБ.")\n        if not any(Path(f.name).suffix.lower() == ".zip" for f in uploaded):
            _show_uploaded_previews(uploaded, collect_image_inputs)', 1)
source = source.replace('        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in resize_uploaded): st.error("Один из ZIP-архивов превышает 300 МБ.")', '        if any(Path(f.name).suffix.lower() == ".zip" and f.size > MAX_ZIP_BYTES for f in resize_uploaded): st.error("Один из ZIP-архивов превышает 300 МБ.")\n        if not any(Path(f.name).suffix.lower() == ".zip" for f in resize_uploaded):
            _show_uploaded_previews(resize_uploaded, collect_image_inputs)', 1)

exec(compile(source, "app_v4.py", "exec"))
