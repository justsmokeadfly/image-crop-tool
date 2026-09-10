from pathlib import Path

source = Path(__file__).with_name("app_v4.py").read_text(encoding="utf-8-sig")
source = source.replace('value=min(10, size // 2 - 1)', 'value=min(30, size // 2 - 1)', 1)
exec(compile(source, "app_v4.py", "exec"))
