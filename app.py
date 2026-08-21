from pathlib import Path

# Main entry point. The UI is kept in a separate module so the Streamlit
# entry file stays small and easy to maintain.
exec(compile(Path(__file__).with_name("app_v2.py").read_text(encoding="utf-8-sig"), "app_v2.py", "exec"))
