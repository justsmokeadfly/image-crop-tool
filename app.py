from pathlib import Path

exec(compile(Path(__file__).with_name("app_v4.py").read_text(encoding="utf-8-sig"), "app_v4.py", "exec"))
