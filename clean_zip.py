import csv
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import psutil
except ImportError:
    psutil = None

try:
    from rembg import new_session, remove
except ImportError:
    new_session = None
    remove = None

try:
    import pynvml
except ImportError:
    pynvml = None

try:
    from PIL import Image
except ImportError:
    Image = None


class ProcessingCancelled(Exception):
    """Raised when user requests processing stop."""


class PhotoCleanerApp:
    def __init__(self, root):
        self.root = root

        self.colors = {
            "bg": "#F5F5F7",
            "card": "#FFFFFF",
            "border": "#E5E5EA",
            "text": "#1D1D1F",
            "subtext": "#6E6E73",
            "accent": "#0071E3",
            "accent_hover": "#0062C4",
            "danger": "#FF3B30",
            "danger_hover": "#E13228",
            "muted_btn": "#F2F2F7",
            "muted_btn_hover": "#EAEAEE",
            "muted_btn_text": "#1D1D1F",
            "log_bg": "#FBFBFD",
        }

        self.font_title = ("SF Pro Display", 24, "bold")
        self.font_subtitle = ("SF Pro Text", 11)
        self.font_body = ("SF Pro Text", 11)
        self.font_body_bold = ("SF Pro Text", 11, "bold")
        self.font_small = ("SF Pro Text", 10)
        self.font_mono = ("SF Mono", 10)

        self.root.title("Photo Cleaner")
        self.root.geometry("920x860")
        self.root.minsize(920, 760)
        self.root.configure(bg=self.colors["bg"])

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.settings_path = os.path.join(self.script_dir, "photo_cleaner_settings.json")
        self.reports_dir = os.path.join(self.script_dir, "reports")
        self.rembg_model = "birefnet-massive"

        self.input_path = ""
        self.output_path = ""
        self.backup_dir = ""
        self.bg_check_dest_dir = ""

        self.mode = tk.StringVar(value="zip")
        self.make_backup = tk.BooleanVar(value=False)
        self.skip_existing = tk.BooleanVar(value=True)
        self.parallel_enabled = tk.BooleanVar(value=True)
        self.delete_only_except_first = tk.BooleanVar(value=False)
        self.worker_count = tk.IntVar(value=self.default_worker_count())

        self.stop_event = threading.Event()
        self.processing = False

        self.nvml_ready = False
        self.nvml_device = None

        self.loading_settings = False

        self.run_started_at = None
        self.run_started_perf = None
        self.run_errors = []
        self.run_stats = {}
        self.last_run_status = ""
        self.last_critical_error = ""

        self.bgless_relative_paths = []
        self.bgless_scanned_files = 0
        self.bgless_source_signature = ""
        self.bg_scan_running = False
        self.bg_move_running = False

        self.setup_styles()
        self.build_ui()

        self.load_settings()
        self.update_ui(reset_paths=False)
        self.refresh_path_labels()
        self.toggle_backup_controls(save=False)
        self.update_worker_controls()

        self.check_dependencies(show_in_log=True)
        self.init_nvml()
        self.update_system_stats()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    @staticmethod
    def default_worker_count():
        cores = os.cpu_count() or 8
        return max(2, min(12, cores - 2))

    def setup_styles(self):
        self.ttk_style = ttk.Style()
        self.ttk_style.theme_use("clam")
        self.ttk_style.configure(
            "Apple.Horizontal.TProgressbar",
            troughcolor="#E9E9ED",
            background=self.colors["accent"],
            bordercolor="#E9E9ED",
            lightcolor=self.colors["accent"],
            darkcolor=self.colors["accent"],
            thickness=10,
        )

    def build_ui(self):
        self.main_container = tk.Frame(self.root, bg=self.colors["bg"])
        self.main_container.pack(fill="both", expand=True)

        self.main_canvas = tk.Canvas(
            self.main_container,
            bg=self.colors["bg"],
            highlightthickness=0,
            bd=0,
        )
        self.main_canvas.pack(side="left", fill="both", expand=True)

        self.main_scrollbar = ttk.Scrollbar(
            self.main_container,
            orient="vertical",
            command=self.main_canvas.yview,
        )
        self.main_scrollbar.pack(side="right", fill="y")
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)

        self.main = tk.Frame(self.main_canvas, bg=self.colors["bg"])
        self.main_window_id = self.main_canvas.create_window((0, 0), window=self.main, anchor="nw")

        self.main.bind("<Configure>", self.on_main_frame_configure)
        self.main_canvas.bind("<Configure>", self.on_main_canvas_configure)
        self.main_canvas.bind_all("<MouseWheel>", self.on_main_mousewheel)

        self.main_pad = tk.Frame(self.main, bg=self.colors["bg"])
        self.main_pad.pack(fill="both", expand=True, padx=24, pady=20)

        header = tk.Frame(self.main_pad, bg=self.colors["bg"])
        header.pack(fill="x", pady=(0, 14))

        tk.Label(
            header,
            text="Photo Cleaner",
            bg=self.colors["bg"],
            fg=self.colors["text"],
            font=self.font_title,
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Удаление фона, бэкапы и контроль ресурсов в одном окне",
            bg=self.colors["bg"],
            fg=self.colors["subtext"],
            font=self.font_subtitle,
        ).pack(anchor="w", pady=(4, 0))

        files_card = self.create_card(self.main_pad, "Источник и результат")

        mode_frame = tk.Frame(files_card, bg=self.colors["card"])
        mode_frame.pack(fill="x", pady=(0, 10))

        self.rb_zip = tk.Radiobutton(
            mode_frame,
            text="ZIP-архив",
            variable=self.mode,
            value="zip",
            command=self.on_mode_change,
            bg=self.colors["card"],
            fg=self.colors["text"],
            selectcolor=self.colors["card"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            font=self.font_body,
        )
        self.rb_zip.pack(side="left", padx=(0, 20))

        self.rb_folder = tk.Radiobutton(
            mode_frame,
            text="Папка напрямую",
            variable=self.mode,
            value="folder",
            command=self.on_mode_change,
            bg=self.colors["card"],
            fg=self.colors["text"],
            selectcolor=self.colors["card"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            font=self.font_body,
        )
        self.rb_folder.pack(side="left")

        self.btn_input = tk.Button(files_card, text="1. Выбрать исходный ZIP-архив", command=self.select_input)
        self.style_button(self.btn_input, "secondary")
        self.btn_input.pack(fill="x")

        self.lbl_input = tk.Label(
            files_card,
            text="Файл/папка не выбраны",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.lbl_input.pack(fill="x", pady=(6, 10))

        self.btn_output = tk.Button(files_card, text="2. Выбрать место сохранения", command=self.select_output)
        self.style_button(self.btn_output, "secondary")
        self.btn_output.pack(fill="x")

        self.lbl_output = tk.Label(
            files_card,
            text="Место не выбрано",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.lbl_output.pack(fill="x", pady=(6, 0))

        backup_card = self.create_card(self.main_pad, "Бэкап")

        backup_top = tk.Frame(backup_card, bg=self.colors["card"])
        backup_top.pack(fill="x")

        self.chk_backup = tk.Checkbutton(
            backup_top,
            text="Сделать бэкап перед обработкой",
            variable=self.make_backup,
            command=self.toggle_backup_controls,
            bg=self.colors["card"],
            fg=self.colors["text"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["card"],
            font=self.font_body,
        )
        self.chk_backup.pack(side="left")

        self.btn_backup = tk.Button(backup_top, text="Выбрать папку для бэкапа", command=self.select_backup_dir, state="disabled")
        self.style_button(self.btn_backup, "secondary")
        self.btn_backup.pack(side="right")

        self.lbl_backup = tk.Label(
            backup_card,
            text="Бэкап отключен",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.lbl_backup.pack(fill="x", pady=(8, 0))

        performance_card = self.create_card(self.main_pad, "Производительность")

        perf_row_1 = tk.Frame(performance_card, bg=self.colors["card"])
        perf_row_1.pack(fill="x")

        self.chk_skip_existing = tk.Checkbutton(
            perf_row_1,
            text="Пропускать уже обработанные",
            variable=self.skip_existing,
            command=self.on_skip_existing_toggle,
            bg=self.colors["card"],
            fg=self.colors["text"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["card"],
            font=self.font_body,
        )
        self.chk_skip_existing.pack(side="left", padx=(0, 20))

        self.chk_parallel = tk.Checkbutton(
            perf_row_1,
            text="Параллельная обработка",
            variable=self.parallel_enabled,
            command=self.on_parallel_toggle,
            bg=self.colors["card"],
            fg=self.colors["text"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["card"],
            font=self.font_body,
        )
        self.chk_parallel.pack(side="left")

        self.chk_delete_only = tk.Checkbutton(
            perf_row_1,
            text="Удалять только фото кроме первого",
            variable=self.delete_only_except_first,
            command=self.on_delete_only_toggle,
            bg=self.colors["card"],
            fg=self.colors["text"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["text"],
            selectcolor=self.colors["card"],
            font=self.font_body,
        )
        self.chk_delete_only.pack(side="left", padx=(20, 0))

        perf_row_2 = tk.Frame(performance_card, bg=self.colors["card"])
        perf_row_2.pack(fill="x", pady=(8, 0))

        tk.Label(
            perf_row_2,
            text="Потоков (CPU-режим):",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
        ).pack(side="left")

        self.spin_workers = tk.Spinbox(
            perf_row_2,
            from_=1,
            to=32,
            textvariable=self.worker_count,
            width=5,
            font=self.font_body,
            justify="center",
            relief="flat",
            bd=1,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
            command=self.on_worker_count_change,
        )
        self.spin_workers.pack(side="left", padx=(8, 0))
        self.spin_workers.bind("<FocusOut>", self.on_worker_count_change)
        self.spin_workers.bind("<Return>", self.on_worker_count_change)

        self.lbl_performance_hint = tk.Label(
            performance_card,
            text="CUDA: удаление фона стабильно в 1 поток, остальное ускоряется параллельно.",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.lbl_performance_hint.pack(fill="x", pady=(6, 0))

        controls_card = self.create_card(self.main_pad, "Управление")

        controls_row = tk.Frame(controls_card, bg=self.colors["card"])
        controls_row.pack(fill="x")

        self.btn_start = tk.Button(controls_row, text="СТАРТ", command=self.start_processing)
        self.style_button(self.btn_start, "primary")
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_stop = tk.Button(controls_row, text="СТОП", command=self.stop_processing, state="disabled")
        self.style_button(self.btn_stop, "danger")
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.progress = ttk.Progressbar(
            controls_card,
            orient="horizontal",
            length=620,
            mode="determinate",
            style="Apple.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x", pady=(14, 6))

        self.progress_info_label = tk.Label(
            controls_card,
            text="Прогресс: 0/0 | ETA: --",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.progress_info_label.pack(fill="x")

        self.current_task_label = tk.Label(
            controls_card,
            text="Текущий файл: --",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.current_task_label.pack(fill="x", pady=(4, 0))

        self.system_stats_label = tk.Label(
            controls_card,
            text="CPU: --% | RAM: --% | GPU: N/A",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_mono,
            anchor="w",
        )
        self.system_stats_label.pack(fill="x", pady=(6, 0))

        bg_check_card = self.create_card(self.main_pad, "Проверка фото без фона")

        bg_check_top = tk.Frame(bg_check_card, bg=self.colors["card"])
        bg_check_top.pack(fill="x")

        self.btn_bg_dest = tk.Button(bg_check_top, text="Выбрать папку для найденных", command=self.select_bg_check_dest_dir)
        self.style_button(self.btn_bg_dest, "secondary")
        self.btn_bg_dest.pack(side="right")

        self.btn_bg_scan = tk.Button(bg_check_top, text="Проверить сейчас", command=self.start_bgless_scan)
        self.style_button(self.btn_bg_scan, "secondary")
        self.btn_bg_scan.pack(side="left")

        self.lbl_bg_dest = tk.Label(
            bg_check_card,
            text="Папка для найденных не выбрана",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.lbl_bg_dest.pack(fill="x", pady=(8, 4))

        self.lbl_bg_scan = tk.Label(
            bg_check_card,
            text="Без фона найдено: --",
            bg=self.colors["card"],
            fg=self.colors["subtext"],
            font=self.font_small,
            anchor="w",
        )
        self.lbl_bg_scan.pack(fill="x")

        self.btn_bg_move = tk.Button(
            bg_check_card,
            text="Переместить найденные (с удалением из источника)",
            command=self.move_bgless_files,
            state="disabled",
        )
        self.style_button(self.btn_bg_move, "secondary")
        self.btn_bg_move.pack(fill="x", pady=(8, 0))

        logs_card = self.create_card(self.main_pad, "Лог выполнения")

        self.log_area = scrolledtext.ScrolledText(
            logs_card,
            height=6,
            state="disabled",
            wrap="word",
            font=("SF Mono", 10),
            bg=self.colors["log_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            borderwidth=0,
        )
        self.log_area.pack(fill="both", expand=True)

        # Keep START/STOP and progress section near the top so it stays visible.
        controls_outer = controls_card.master
        controls_outer.pack_forget()
        controls_outer.pack(fill="x", pady=(0, 12), before=backup_card.master)

    def on_main_frame_configure(self, _event=None):
        if hasattr(self, "main_canvas"):
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def on_main_canvas_configure(self, event):
        if hasattr(self, "main_canvas") and hasattr(self, "main_window_id"):
            self.main_canvas.itemconfigure(self.main_window_id, width=event.width)

    def on_main_mousewheel(self, event):
        if hasattr(self, "main_canvas"):
            self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def create_card(self, parent, title):
        card = tk.Frame(
            parent,
            bg=self.colors["card"],
            highlightbackground=self.colors["border"],
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="x", pady=(0, 12))

        inner = tk.Frame(card, bg=self.colors["card"])
        inner.pack(fill="x", padx=14, pady=12)

        tk.Label(
            inner,
            text=title,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=self.font_body_bold,
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        return inner

    def style_button(self, button, variant="secondary"):
        common = {
            "relief": "flat",
            "bd": 0,
            "font": self.font_body_bold,
            "padx": 12,
            "pady": 9,
            "cursor": "hand2",
            "disabledforeground": "#9B9BA1",
        }

        if variant == "primary":
            button.config(
                bg=self.colors["accent"],
                fg="white",
                activebackground=self.colors["accent_hover"],
                activeforeground="white",
                **common,
            )
            return

        if variant == "danger":
            button.config(
                bg=self.colors["danger"],
                fg="white",
                activebackground=self.colors["danger_hover"],
                activeforeground="white",
                **common,
            )
            return

        button.config(
            bg=self.colors["muted_btn"],
            fg=self.colors["muted_btn_text"],
            activebackground=self.colors["muted_btn_hover"],
            activeforeground=self.colors["muted_btn_text"],
            **common,
        )

    def _append_log(self, message):
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")
        self.root.update_idletasks()

    def log(self, message):
        if threading.current_thread() is threading.main_thread():
            self._append_log(message)
        else:
            self.root.after(0, self._append_log, message)

    def load_settings(self):
        self.loading_settings = True
        try:
            if not os.path.exists(self.settings_path):
                return

            with open(self.settings_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            mode = data.get("mode", "zip")
            if mode not in ("zip", "folder"):
                mode = "zip"
            self.mode.set(mode)

            self.input_path = data.get("input_path", "")
            self.output_path = data.get("output_path", "")
            self.backup_dir = data.get("backup_dir", "")
            self.bg_check_dest_dir = data.get("bg_check_dest_dir", "")

            self.make_backup.set(bool(data.get("make_backup", False)))
            self.skip_existing.set(bool(data.get("skip_existing", True)))
            self.parallel_enabled.set(bool(data.get("parallel_enabled", True)))
            self.delete_only_except_first.set(bool(data.get("delete_only_except_first", False)))

            workers = data.get("worker_count", self.default_worker_count())
            try:
                workers = int(workers)
            except (TypeError, ValueError):
                workers = self.default_worker_count()
            self.worker_count.set(max(1, min(32, workers)))

        except Exception as error:
            self.log(f"Внимание: не удалось загрузить настройки: {error}")
        finally:
            self.loading_settings = False

    def save_settings(self):
        if self.loading_settings:
            return

        data = {
            "mode": self.mode.get(),
            "input_path": self.input_path,
            "output_path": self.output_path,
            "backup_dir": self.backup_dir,
            "bg_check_dest_dir": self.bg_check_dest_dir,
            "make_backup": bool(self.make_backup.get()),
            "skip_existing": bool(self.skip_existing.get()),
            "parallel_enabled": bool(self.parallel_enabled.get()),
            "delete_only_except_first": bool(self.delete_only_except_first.get()),
            "worker_count": int(max(1, min(32, self.worker_count.get()))),
        }

        try:
            with open(self.settings_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except Exception as error:
            self.log(f"Внимание: не удалось сохранить настройки: {error}")

    def refresh_path_labels(self):
        if self.input_path:
            self.lbl_input.config(text=os.path.basename(self.input_path) or self.input_path, fg=self.colors["text"])
        else:
            self.lbl_input.config(text="Файл/папка не выбраны", fg=self.colors["subtext"])

        if self.mode.get() == "zip":
            if self.output_path:
                self.lbl_output.config(text=os.path.basename(self.output_path), fg=self.colors["text"])
            else:
                self.lbl_output.config(text="Место не выбрано", fg=self.colors["subtext"])
        else:
            self.lbl_output.config(text="Фото будут изменены прямо в выбранной папке", fg=self.colors["subtext"])

        if self.make_backup.get():
            if self.backup_dir:
                self.lbl_backup.config(text=self.backup_dir, fg=self.colors["text"])
            else:
                self.lbl_backup.config(text="Папка для бэкапа не выбрана", fg=self.colors["subtext"])
        else:
            self.lbl_backup.config(text="Бэкап отключен", fg=self.colors["subtext"])

        if self.bg_check_dest_dir:
            self.lbl_bg_dest.config(text=self.bg_check_dest_dir, fg=self.colors["text"])
        else:
            self.lbl_bg_dest.config(text="Папка для найденных не выбрана", fg=self.colors["subtext"])

    def on_mode_change(self):
        self.update_ui(reset_paths=True)
        self.save_settings()

    def update_ui(self, reset_paths=True):
        if reset_paths:
            self.input_path = ""
            self.output_path = ""
            self.reset_bgless_results()

        if self.mode.get() == "zip":
            self.btn_input.config(text="1. Выбрать исходный ZIP-архив")
            if not self.processing:
                self.btn_output.config(state="normal", text="2. Куда сохранить готовый ZIP-архив")
            else:
                self.btn_output.config(text="2. Куда сохранить готовый ZIP-архив")
        else:
            self.btn_input.config(text="1. Выбрать главную папку с фото")
            self.btn_output.config(text="(Не требуется для режима папки)")
            if not self.processing:
                self.btn_output.config(state="disabled")

        self.refresh_path_labels()

    def toggle_backup_controls(self, save=True):
        if self.make_backup.get():
            if not self.processing:
                self.btn_backup.config(state="normal")
        else:
            self.btn_backup.config(state="disabled")

        self.refresh_path_labels()

        if save:
            self.save_settings()

    def on_skip_existing_toggle(self):
        self.save_settings()

    def on_parallel_toggle(self):
        self.update_worker_controls()
        self.save_settings()

    def on_delete_only_toggle(self):
        self.save_settings()

    def on_worker_count_change(self, _event=None):
        try:
            value = int(self.worker_count.get())
        except Exception:
            value = self.default_worker_count()

        value = max(1, min(32, value))
        if self.worker_count.get() != value:
            self.worker_count.set(value)

        self.save_settings()

    def update_worker_controls(self):
        if self.processing:
            self.spin_workers.config(state="disabled")
            return

        if self.parallel_enabled.get():
            self.spin_workers.config(state="normal")
        else:
            self.spin_workers.config(state="disabled")

    def check_dependencies(self, show_in_log=False):
        critical_ok = True

        if remove is None or new_session is None:
            critical_ok = False
            if show_in_log:
                self.log("Ошибка: не найден пакет rembg. Установите: pip install rembg")

        if psutil is None and show_in_log:
            self.log("Внимание: psutil не установлен. Мониторинг CPU/RAM будет недоступен.")

        if pynvml is None and show_in_log:
            self.log("Внимание: pynvml не установлен. Мониторинг GPU будет недоступен (N/A).")

        if Image is None and show_in_log:
            self.log("Внимание: Pillow не установлен. Проверка фото без фона будет недоступна.")

        return critical_ok

    def init_nvml(self):
        if pynvml is None:
            return

        try:
            pynvml.nvmlInit()
            self.nvml_device = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.nvml_ready = True
            self.log("GPU-мониторинг активирован (NVIDIA NVML).")
        except Exception as error:
            self.nvml_ready = False
            self.nvml_device = None
            self.log(f"Внимание: GPU-мониторинг недоступен: {error}")

    def shutdown_nvml(self):
        if not self.nvml_ready:
            return

        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        finally:
            self.nvml_ready = False
            self.nvml_device = None

    def on_close(self):
        self.stop_event.set()
        self.save_settings()
        self.shutdown_nvml()
        if hasattr(self, "main_canvas"):
            try:
                self.main_canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
        self.root.destroy()

    @staticmethod
    def make_default_ready_zip_path(input_zip_path):
        base_dir = os.path.dirname(input_zip_path)
        base_name = os.path.splitext(os.path.basename(input_zip_path))[0]
        return os.path.join(base_dir, f"{base_name}_ready.zip")

    def select_input(self):
        if self.mode.get() == "zip":
            path = filedialog.askopenfilename(
                title="Выберите ZIP-архив",
                filetypes=[("ZIP архивы", "*.zip")],
            )
        else:
            path = filedialog.askdirectory(title="Выберите главную папку с фото")

        if path:
            self.input_path = path
            if self.mode.get() == "zip":
                self.output_path = self.make_default_ready_zip_path(path)
            self.reset_bgless_results()
            self.refresh_path_labels()
            self.save_settings()
            self.start_bgless_scan(auto=True)

    def select_output(self):
        folder = filedialog.askdirectory(title="Выберите папку для готового ZIP-архива")
        if folder:
            if self.input_path and self.input_path.lower().endswith(".zip"):
                file_name = os.path.basename(self.make_default_ready_zip_path(self.input_path))
            else:
                file_name = "result_ready.zip"
            self.output_path = os.path.join(folder, file_name)
            self.refresh_path_labels()
            self.save_settings()

    def select_backup_dir(self):
        path = filedialog.askdirectory(title="Выберите папку для сохранения бэкапа")
        if path:
            self.backup_dir = path
            self.refresh_path_labels()
            self.save_settings()

    def select_bg_check_dest_dir(self):
        path = filedialog.askdirectory(title="Выберите папку для фото без фона")
        if path:
            self.bg_check_dest_dir = path
            self.refresh_path_labels()
            self.save_settings()
            if self.bgless_relative_paths and not self.bg_scan_running and not self.bg_move_running and not self.processing:
                self.btn_bg_move.config(state="normal")

    @staticmethod
    def make_source_signature(mode, input_path):
        return f"{mode}|{os.path.abspath(input_path)}"

    def reset_bgless_results(self):
        self.bgless_relative_paths = []
        self.bgless_scanned_files = 0
        self.bgless_source_signature = ""
        if hasattr(self, "lbl_bg_scan"):
            self.lbl_bg_scan.config(text="Без фона найдено: --", fg=self.colors["subtext"])
        if hasattr(self, "btn_bg_move"):
            self.btn_bg_move.config(state="disabled")

    @staticmethod
    def is_image_file(file_name):
        ext = os.path.splitext(file_name)[1].lower()
        return ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    @staticmethod
    def make_unique_path(path):
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        index = 1
        while True:
            candidate = f"{base}_{index}{ext}"
            if not os.path.exists(candidate):
                return candidate
            index += 1

    def is_bgless_image(self, file_path):
        if Image is None:
            return False

        if os.path.splitext(file_path)[1].lower() != ".png":
            return False

        try:
            with Image.open(file_path) as image:
                has_alpha = ("A" in image.getbands()) or ("transparency" in image.info)
                if not has_alpha:
                    return False

                alpha = image.convert("RGBA").getchannel("A")
                min_alpha, _ = alpha.getextrema()
                if min_alpha >= 250:
                    return False

                histogram = alpha.histogram()
                near_transparent = sum(histogram[:6])
                total_pixels = max(1, image.width * image.height)
                return (near_transparent / total_pixels) >= 0.003
        except Exception:
            return False

    def scan_bgless_in_folder(self, base_dir):
        found_rel_paths = []
        scanned_images = 0
        for folder_path, _, files in os.walk(base_dir):
            for file_name in files:
                if not self.is_image_file(file_name):
                    continue
                scanned_images += 1
                file_path = os.path.join(folder_path, file_name)
                if self.is_bgless_image(file_path):
                    rel_path = os.path.relpath(file_path, base_dir).replace("\\", "/")
                    found_rel_paths.append(rel_path)
        return found_rel_paths, scanned_images

    def collect_bgless_paths(self, mode, input_path):
        if mode == "folder":
            return self.scan_bgless_in_folder(input_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(input_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            return self.scan_bgless_in_folder(temp_dir)

    def start_bgless_scan(self, auto=False):
        if self.processing or self.bg_move_running:
            if not auto:
                messagebox.showinfo("Недоступно", "Сейчас идет обработка или перенос. Дождитесь завершения.")
                self.log("Проверка без фона недоступна: идет обработка или перенос.")
            return

        if self.bg_scan_running:
            if not auto:
                messagebox.showinfo("Проверка уже идет", "Проверка фото без фона уже выполняется.")
                self.log("Проверка фото без фона уже выполняется.")
            return

        if not self.input_path:
            if not auto:
                messagebox.showinfo("Нет источника", "Сначала выберите исходный архив или папку.")
                self.log("Сначала выберите исходный архив или папку.")
            return

        if Image is None:
            self.lbl_bg_scan.config(text="Проверка без фона недоступна: установите Pillow", fg=self.colors["subtext"])
            if not auto:
                messagebox.showwarning("Нужен Pillow", "Проверка без фона недоступна.\nУстановите: pip install pillow")
                self.log("Внимание: Pillow не установлен. Проверка фото без фона недоступна.")
            return

        mode = self.mode.get()
        input_path = self.input_path
        signature = self.make_source_signature(mode, input_path)

        self.bg_scan_running = True
        self.btn_bg_scan.config(state="disabled")
        self.btn_bg_move.config(state="disabled")
        self.lbl_bg_scan.config(text="Проверка фото без фона...", fg=self.colors["subtext"])
        if not auto:
            self.log("Запущена проверка фото без фона...")

        threading.Thread(
            target=self._bgless_scan_worker,
            args=(mode, input_path, signature, auto),
            daemon=True,
        ).start()

    def _bgless_scan_worker(self, mode, input_path, signature, auto):
        error = ""
        found_paths = []
        scanned_images = 0
        try:
            found_paths, scanned_images = self.collect_bgless_paths(mode, input_path)
        except Exception as exc:
            error = str(exc)

        self.root.after(
            0,
            self.finish_bgless_scan,
            mode,
            input_path,
            signature,
            found_paths,
            scanned_images,
            error,
            auto,
        )

    def finish_bgless_scan(self, mode, input_path, signature, found_paths, scanned_images, error, auto):
        self.bg_scan_running = False

        current_signature = self.make_source_signature(self.mode.get(), self.input_path) if self.input_path else ""
        if signature != current_signature:
            self.btn_bg_scan.config(state="normal")
            self.btn_bg_move.config(state="disabled")
            return

        if error:
            self.reset_bgless_results()
            self.lbl_bg_scan.config(text=f"Ошибка проверки: {error}", fg=self.colors["subtext"])
            self.btn_bg_scan.config(state="normal")
            if not auto:
                messagebox.showerror("Ошибка проверки", f"Не удалось выполнить проверку.\n\n{error}")
                self.log(f"Ошибка проверки фото без фона: {error}")
            return

        self.bgless_relative_paths = found_paths
        self.bgless_scanned_files = scanned_images
        self.bgless_source_signature = signature

        found_count = len(found_paths)
        self.lbl_bg_scan.config(
            text=f"Без фона найдено: {found_count} (проверено изображений: {scanned_images})",
            fg=self.colors["text"] if found_count else self.colors["subtext"],
        )
        self.btn_bg_scan.config(state="normal")

        if found_count > 0 and self.bg_check_dest_dir and not self.processing and not self.bg_move_running:
            self.btn_bg_move.config(state="normal")
        else:
            self.btn_bg_move.config(state="disabled")

        if not auto:
            self.log(f"Проверка завершена: найдено без фона {found_count} из {scanned_images} изображений.")
            if found_count > 0 and self.bg_check_dest_dir:
                should_move_now = messagebox.askyesno(
                    "Проверка завершена",
                    f"Найдено без фона: {found_count}\nПроверено изображений: {scanned_images}\n\nПереместить найденные сейчас?",
                )
                if should_move_now:
                    self.move_bgless_files(skip_confirm=True)
                return

            messagebox.showinfo(
                "Проверка завершена",
                f"Найдено без фона: {found_count}\nПроверено изображений: {scanned_images}\n\n"
                "Чтобы перенести найденные фото, выберите папку для найденных и нажмите кнопку переноса.",
            )

    @staticmethod
    def cleanup_empty_dirs(base_dir):
        for root_dir, dirs, files in os.walk(base_dir, topdown=False):
            if dirs or files:
                continue
            if os.path.abspath(root_dir) == os.path.abspath(base_dir):
                continue
            try:
                os.rmdir(root_dir)
            except Exception:
                pass

    def move_bgless_from_folder(self, source_dir, target_dir, rel_paths):
        moved = 0
        for rel_path in rel_paths:
            src = os.path.join(source_dir, rel_path.replace("/", os.sep))
            if not os.path.exists(src):
                continue
            dst = os.path.join(target_dir, rel_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            dst = self.make_unique_path(dst)
            shutil.move(src, dst)
            moved += 1
        self.cleanup_empty_dirs(source_dir)
        return moved

    def move_bgless_from_zip(self, zip_path, target_dir, rel_paths):
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            moved = self.move_bgless_from_folder(temp_dir, target_dir, rel_paths)
            if moved <= 0:
                return 0

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
                for root_dir, _, files in os.walk(temp_dir):
                    for file_name in files:
                        file_path = os.path.join(root_dir, file_name)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zip_out.write(file_path, arcname)

            return moved

    def set_bg_operation_state(self, running):
        if running:
            self.btn_start.config(state="disabled")
            self.btn_input.config(state="disabled")
            self.btn_output.config(state="disabled")
            self.rb_zip.config(state="disabled")
            self.rb_folder.config(state="disabled")
            self.btn_bg_dest.config(state="disabled")
            self.btn_bg_scan.config(state="disabled")
            self.btn_bg_move.config(state="disabled")
            return

        self.set_controls_state(running=False)
        if self.bg_scan_running or self.bg_move_running:
            self.btn_bg_scan.config(state="disabled")
        else:
            self.btn_bg_scan.config(state="normal")
        if self.bgless_relative_paths and self.bg_check_dest_dir and not self.bg_scan_running and not self.bg_move_running:
            self.btn_bg_move.config(state="normal")
        else:
            self.btn_bg_move.config(state="disabled")

    def move_bgless_files(self, skip_confirm=False):
        if self.processing or self.bg_scan_running or self.bg_move_running:
            return

        if not self.input_path:
            self.log("Сначала выберите исходный архив или папку.")
            return

        if not self.bgless_relative_paths:
            messagebox.showinfo("Нечего переносить", "Фото без фона не найдены. Запустите проверку.")
            return

        current_signature = self.make_source_signature(self.mode.get(), self.input_path)
        if current_signature != self.bgless_source_signature:
            messagebox.showinfo("Источник изменился", "Источник был изменен. Запустите проверку заново.")
            self.start_bgless_scan(auto=False)
            return

        if not self.bg_check_dest_dir:
            self.select_bg_check_dest_dir()
            if not self.bg_check_dest_dir:
                return

        count = len(self.bgless_relative_paths)
        if not skip_confirm:
            answer = messagebox.askyesno(
                "Перемещение фото без фона",
                f"Найдено {count} фото без фона.\n\nПереместить их в выбранную папку и удалить из источника?",
            )
            if not answer:
                return

        mode = self.mode.get()
        input_path = self.input_path
        destination = self.bg_check_dest_dir
        rel_paths = list(self.bgless_relative_paths)

        if mode == "folder":
            src_abs = os.path.abspath(input_path)
            dst_abs = os.path.abspath(destination)
            if dst_abs == src_abs or dst_abs.startswith(src_abs + os.sep):
                messagebox.showwarning(
                    "Некорректная папка",
                    "Папка для найденных должна быть вне исходной папки, иначе файлы будут зацикливаться.",
                )
                return

        self.bg_move_running = True
        self.set_bg_operation_state(running=True)
        self.lbl_bg_scan.config(text="Перемещение фото без фона...", fg=self.colors["subtext"])

        threading.Thread(
            target=self._move_bgless_worker,
            args=(mode, input_path, destination, rel_paths),
            daemon=True,
        ).start()

    def _move_bgless_worker(self, mode, input_path, destination, rel_paths):
        moved = 0
        error = ""
        try:
            if mode == "folder":
                moved = self.move_bgless_from_folder(input_path, destination, rel_paths)
            else:
                moved = self.move_bgless_from_zip(input_path, destination, rel_paths)
        except Exception as exc:
            error = str(exc)

        self.root.after(0, self.finish_move_bgless, moved, error)

    def finish_move_bgless(self, moved_count, error):
        self.bg_move_running = False
        self.set_bg_operation_state(running=False)

        if error:
            self.lbl_bg_scan.config(text=f"Ошибка перемещения: {error}", fg=self.colors["subtext"])
            messagebox.showerror("Ошибка", f"Не удалось переместить фото без фона.\n\n{error}")
            return

        self.log(f"Перемещено фото без фона: {moved_count}")
        if moved_count <= 0:
            messagebox.showwarning(
                "Ничего не перенесено",
                "Найденные файлы не удалось перенести.\nПроверьте, что источник не был изменен после проверки.",
            )
        else:
            messagebox.showinfo(
                "Готово",
                f"Перемещено фото без фона: {moved_count}\n\nПапка назначения:\n{self.bg_check_dest_dir}",
            )
        self.start_bgless_scan(auto=True)

    def start_processing(self):
        if self.processing:
            self.log("Обработка уже запущена.")
            return

        if self.bg_scan_running or self.bg_move_running:
            self.log("Дождитесь завершения проверки/перемещения фото без фона.")
            return

        if not self.check_dependencies(show_in_log=True):
            return

        if not self.input_path:
            self.log("Ошибка: выберите исходный файл или папку.")
            return

        if self.mode.get() == "zip" and not self.output_path:
            self.output_path = self.make_default_ready_zip_path(self.input_path)
            self.refresh_path_labels()

        if self.make_backup.get() and not self.backup_dir:
            self.log("Ошибка: включен бэкап, но не выбрана папка для сохранения.")
            return

        self.processing = True
        self.stop_event.clear()

        self.set_controls_state(running=True)
        self.setup_progress(1)
        self.update_progress(0, 1, None)
        self.log("--- Начинаем работу ---")

        threading.Thread(target=self.process_files, daemon=True).start()

    def stop_processing(self):
        if not self.processing:
            return

        if not self.stop_event.is_set():
            self.stop_event.set()
            self.log("Запрошена остановка. Завершаем текущий шаг...")

    def set_controls_state(self, running):
        if running:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.btn_input.config(state="disabled")
            self.btn_output.config(state="disabled")
            self.btn_backup.config(state="disabled")
            self.btn_bg_dest.config(state="disabled")
            self.btn_bg_scan.config(state="disabled")
            self.btn_bg_move.config(state="disabled")
            self.chk_backup.config(state="disabled")
            self.chk_skip_existing.config(state="disabled")
            self.chk_parallel.config(state="disabled")
            self.chk_delete_only.config(state="disabled")
            self.spin_workers.config(state="disabled")
            self.rb_zip.config(state="disabled")
            self.rb_folder.config(state="disabled")
            return

        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_input.config(state="normal")
        self.chk_backup.config(state="normal")
        self.chk_skip_existing.config(state="normal")
        self.chk_parallel.config(state="normal")
        self.chk_delete_only.config(state="normal")
        self.rb_zip.config(state="normal")
        self.rb_folder.config(state="normal")
        self.btn_bg_dest.config(state="normal")
        if self.bg_scan_running or self.bg_move_running:
            self.btn_bg_scan.config(state="disabled")
        else:
            self.btn_bg_scan.config(state="normal")

        if self.mode.get() == "zip":
            self.btn_output.config(state="normal")
        else:
            self.btn_output.config(state="disabled")

        if self.make_backup.get():
            self.btn_backup.config(state="normal")

        if self.bgless_relative_paths and self.bg_check_dest_dir and not self.bg_scan_running and not self.bg_move_running:
            self.btn_bg_move.config(state="normal")
        else:
            self.btn_bg_move.config(state="disabled")

        self.update_worker_controls()

    def ensure_not_stopped(self):
        if self.stop_event.is_set():
            raise ProcessingCancelled()

    def init_run_tracking(self):
        self.run_started_at = datetime.now()
        self.run_started_perf = time.perf_counter()
        self.run_errors = []
        self.run_stats = {
            "mode": self.mode.get(),
            "input_path": self.input_path,
            "output_path": self.output_path if self.mode.get() == "zip" else "",
            "backup_enabled": bool(self.make_backup.get()),
            "backup_file": "",
            "compute_mode": "Unknown",
            "model_name": self.rembg_model,
            "delete_only_mode": bool(self.delete_only_except_first.get()),
            "parallel_enabled": bool(self.parallel_enabled.get()),
            "workers_requested": int(self.worker_count.get() if self.parallel_enabled.get() else 1),
            "workers_used": 1,
            "scanned_files": 0,
            "total_candidates": 0,
            "processed": 0,
            "renamed_png": 0,
            "background_removed": 0,
            "removed_extra": 0,
            "skipped_existing": 0,
            "errors": 0,
        }

    def append_run_error(self, message):
        if len(self.run_errors) < 25:
            self.run_errors.append(message)

    def process_files(self):
        status = "failed"
        critical_error = ""

        self.init_run_tracking()

        try:
            self.ensure_not_stopped()

            self.log(f"[0] Инициализация модели удаления фона ({self.rembg_model})...")
            using_cuda = False
            try:
                session = self.create_rembg_session(["CUDAExecutionProvider", "CPUExecutionProvider"])
                using_cuda = True
                self.run_stats["compute_mode"] = "CUDA"
            except Exception as error:
                self.log(f"Внимание: CUDA недоступна, переключаемся на CPU. Детали: {error}")
                session = self.create_rembg_session(["CPUExecutionProvider"])
                self.run_stats["compute_mode"] = "CPU"

            self.ensure_not_stopped()

            if self.make_backup.get():
                self.log("[0.5] Создание резервной копии...")
                backup_file = self.create_backup()
                self.run_stats["backup_file"] = backup_file

            self.ensure_not_stopped()

            if self.mode.get() == "zip":
                self.log("[1] Распаковка архива во временную папку...")
                with tempfile.TemporaryDirectory() as temp_dir:
                    with zipfile.ZipFile(self.input_path, "r") as zip_ref:
                        zip_ref.extractall(temp_dir)

                    self.perform_cleaning(temp_dir, session, using_cuda)
                    self.ensure_not_stopped()

                    self.log("[3] Упаковка результата в новый ZIP-архив...")
                    with zipfile.ZipFile(self.output_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
                        for root_dir, _, files in os.walk(temp_dir):
                            self.ensure_not_stopped()
                            for file in files:
                                self.ensure_not_stopped()
                                file_path = os.path.join(root_dir, file)
                                arcname = os.path.relpath(file_path, temp_dir)
                                zip_out.write(file_path, arcname)
            else:
                self.log("[1] Обработка файлов напрямую в вашей папке...")
                self.perform_cleaning(self.input_path, session, using_cuda)

            status = "success"
            self.log("\nУСПЕХ! Работа завершена.")

        except ProcessingCancelled:
            status = "cancelled"
            self.log("\nОстановлено пользователем.")
        except Exception as error:
            status = "failed"
            critical_error = str(error)
            self.log(f"\nПроизошла критическая ошибка: {error}")
        finally:
            self.log_run_summary()
            report_paths = self.write_run_report(status=status, critical_error=critical_error)
            if report_paths:
                self.log(f"Отчет TXT: {report_paths[0]}")
                self.log(f"Отчет CSV: {report_paths[1]}")
            self.last_run_status = status
            self.last_critical_error = critical_error
            self.root.after(0, self.finish_processing)

    def finish_processing(self):
        self.processing = False
        self.set_controls_state(running=False)
        self.update_current_task("", "done")
        self.show_completion_notification()

    def show_completion_notification(self):
        status = self.last_run_status or "success"
        processed = self.run_stats.get("processed", 0)
        total = self.run_stats.get("total_candidates", 0)
        removed_bg = self.run_stats.get("background_removed", 0)
        removed_extra = self.run_stats.get("removed_extra", 0)
        errors = self.run_stats.get("errors", 0)

        summary = (
            f"Обработано: {processed}/{total}\n"
            f"Фон удален: {removed_bg}\n"
            f"Удалено лишних: {removed_extra}\n"
            f"Ошибок: {errors}"
        )

        if status == "success":
            messagebox.showinfo("Готово", f"Обработка завершена.\n\n{summary}")
            return

        if status == "cancelled":
            messagebox.showwarning("Остановлено", f"Обработка остановлена пользователем.\n\n{summary}")
            return

        details = self.last_critical_error.strip()
        if details:
            summary = f"{summary}\n\nКритическая ошибка:\n{details}"
        messagebox.showerror("Ошибка", f"Обработка завершилась с ошибкой.\n\n{summary}")

    def create_backup(self):
        self.ensure_not_stopped()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.mode.get() == "zip":
            src = self.input_path
            base_name = os.path.splitext(os.path.basename(src))[0]
            backup_name = f"{base_name}_backup_{timestamp}.zip"
            destination = os.path.join(self.backup_dir, backup_name)
            shutil.copy2(src, destination)
            self.log(f"Бэкап ZIP сохранен: {destination}")
            return destination

        src_folder = self.input_path
        folder_name = os.path.basename(os.path.normpath(src_folder))
        backup_zip = os.path.join(self.backup_dir, f"{folder_name}_backup_{timestamp}.zip")

        try:
            with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as archive:
                for root_dir, _, files in os.walk(src_folder):
                    self.ensure_not_stopped()
                    for file_name in files:
                        self.ensure_not_stopped()
                        file_path = os.path.join(root_dir, file_name)
                        arcname = os.path.relpath(file_path, src_folder)
                        archive.write(file_path, arcname)
        except ProcessingCancelled:
            if os.path.exists(backup_zip):
                try:
                    os.remove(backup_zip)
                except Exception:
                    pass
            raise

        self.log(f"Бэкап папки сохранен: {backup_zip}")
        return backup_zip

    @staticmethod
    def collect_tasks(base_dir, delete_only_mode=False):
        tasks = []
        scanned_files = 0
        for folder_path, _, files in os.walk(base_dir):
            folder_name = os.path.basename(folder_path)
            for file_name in files:
                scanned_files += 1
                name, ext = os.path.splitext(file_name)
                if "_images_" not in name:
                    continue

                if name.endswith("_images_1"):
                    if delete_only_mode:
                        # In delete-only mode keep the first image and only rename it.
                        task_type = "rename" if ext.lower() == ".png" else "rename_keep_ext"
                    else:
                        task_type = "rename" if ext.lower() == ".png" else "remove_bg"
                else:
                    task_type = "delete"

                tasks.append(
                    {
                        "task_type": task_type,
                        "folder_path": folder_path,
                        "folder_name": folder_name,
                        "file_name": file_name,
                        "file_path": os.path.join(folder_path, file_name),
                        "ext": ext,
                    }
                )
        return tasks, scanned_files

    def create_rembg_session(self, providers):
        try:
            return new_session(model_name=self.rembg_model, providers=providers)
        except TypeError:
            try:
                return new_session(self.rembg_model, providers=providers)
            except TypeError:
                return new_session(providers=providers)

    def get_thread_session(self, thread_local, providers):
        session = getattr(thread_local, "session", None)
        if session is None:
            session = self.create_rembg_session(providers)
            thread_local.session = session
        return session

    def process_single_task(self, task, skip_existing, shared_session=None, thread_local=None, providers=None):
        self.ensure_not_stopped()
        self.root.after(0, self.update_current_task, task.get("file_name", ""), "in_progress")

        task_type = task["task_type"]
        file_path = task["file_path"]
        folder_path = task["folder_path"]
        folder_name = task["folder_name"]

        target_path = None
        if task_type in ("rename", "remove_bg"):
            target_path = os.path.join(folder_path, f"{folder_name}_1.png")
            if skip_existing and os.path.exists(target_path):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
                return {"action": "skipped_existing", "file_name": task["file_name"]}
        elif task_type == "rename_keep_ext":
            target_path = os.path.join(folder_path, f"{folder_name}_1{task.get('ext', '')}")
            if skip_existing and os.path.exists(target_path):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
                return {"action": "skipped_existing", "file_name": task["file_name"]}

        if task_type == "rename":
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.replace(file_path, target_path)
                return {"action": "renamed_png", "file_name": task["file_name"]}
            except FileNotFoundError:
                return {"action": "skipped_existing", "file_name": task["file_name"]}
            except Exception as error:
                return {"action": "error", "error": f"{task['file_name']}: {error}", "file_name": task["file_name"]}

        if task_type == "rename_keep_ext":
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                os.replace(file_path, target_path)
                return {"action": "renamed_png", "file_name": task["file_name"]}
            except FileNotFoundError:
                return {"action": "skipped_existing", "file_name": task["file_name"]}
            except Exception as error:
                return {"action": "error", "error": f"{task['file_name']}: {error}", "file_name": task["file_name"]}

        if task_type == "remove_bg":
            try:
                self.ensure_not_stopped()
                with open(file_path, "rb") as file_in:
                    input_data = file_in.read()

                if shared_session is not None:
                    session = shared_session
                else:
                    session = self.get_thread_session(thread_local, providers or ["CPUExecutionProvider"])

                output_data = remove(input_data, session=session)

                self.ensure_not_stopped()
                with open(target_path, "wb") as file_out:
                    file_out.write(output_data)

                if os.path.exists(file_path):
                    os.remove(file_path)

                return {"action": "background_removed", "file_name": task["file_name"]}
            except ProcessingCancelled:
                raise
            except Exception as error:
                return {"action": "error", "error": f"{task['file_name']}: {error}", "file_name": task["file_name"]}

        if task_type == "delete":
            try:
                os.remove(file_path)
                return {"action": "removed_extra", "file_name": task["file_name"]}
            except FileNotFoundError:
                return {"action": "skipped_existing", "file_name": task["file_name"]}
            except Exception as error:
                return {"action": "error", "error": f"{task['file_name']}: {error}", "file_name": task["file_name"]}

        return {"action": "error", "error": f"Неизвестный тип задачи: {task_type}", "file_name": task["file_name"]}

    def estimate_eta(self, processed, total, started_at):
        if processed <= 0 or processed >= total:
            return None

        elapsed = time.time() - started_at
        return (elapsed / processed) * (total - processed)

    def record_task_result(self, result, total_files, started_at):
        action = result.get("action")
        file_name = result.get("file_name", "")

        if action == "renamed_png":
            self.run_stats["renamed_png"] += 1
        elif action == "background_removed":
            self.run_stats["background_removed"] += 1
        elif action == "removed_extra":
            self.run_stats["removed_extra"] += 1
        elif action == "skipped_existing":
            self.run_stats["skipped_existing"] += 1
        elif action == "error":
            self.run_stats["errors"] += 1
            error_message = result.get("error", "Неизвестная ошибка")
            self.append_run_error(error_message)
            self.log(f"Ошибка: {error_message}")

        self.run_stats["processed"] += 1
        eta_seconds = self.estimate_eta(self.run_stats["processed"], total_files, started_at)
        self.root.after(0, self.update_current_task, file_name, action)
        self.root.after(0, self.update_progress, self.run_stats["processed"], total_files, eta_seconds)

    def process_tasks_sequential(self, tasks, total_files, started_at, skip_existing, shared_session):
        for task in tasks:
            self.ensure_not_stopped()
            result = self.process_single_task(
                task=task,
                skip_existing=skip_existing,
                shared_session=shared_session,
            )
            self.record_task_result(result, total_files, started_at)

    def process_tasks_parallel(self, tasks, workers, total_files, started_at, skip_existing, cpu_thread_sessions=False):
        if workers <= 1:
            self.process_tasks_sequential(
                tasks=tasks,
                total_files=total_files,
                started_at=started_at,
                skip_existing=skip_existing,
                shared_session=None,
            )
            return

        thread_local = threading.local() if cpu_thread_sessions else None
        providers = ["CPUExecutionProvider"] if cpu_thread_sessions else None

        futures = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for task in tasks:
                futures.append(
                    executor.submit(
                        self.process_single_task,
                        task,
                        skip_existing,
                        None,
                        thread_local,
                        providers,
                    )
                )

            for future in as_completed(futures):
                self.ensure_not_stopped()
                try:
                    result = future.result()
                except ProcessingCancelled:
                    raise
                except Exception as error:
                    result = {"action": "error", "error": f"Внутренняя ошибка потока: {error}"}
                self.record_task_result(result, total_files, started_at)

    def perform_cleaning(self, base_dir, session, using_cuda):
        delete_only_mode = bool(self.delete_only_except_first.get())
        tasks, scanned_files = self.collect_tasks(base_dir, delete_only_mode=delete_only_mode)
        total_files = len(tasks)

        self.run_stats["scanned_files"] = scanned_files
        self.run_stats["total_candidates"] = total_files

        if delete_only_mode:
            self.log(f"[2] Mode: delete extras only. Scanned: {scanned_files}, to delete: {total_files}")
        else:
            self.log(f"[2] Найдено файлов для обработки: {total_files}")
        self.root.after(0, self.setup_progress, total_files)

        if total_files == 0:
            self.run_stats["workers_used"] = 1
            self.root.after(
                0,
                lambda: self.progress_info_label.config(
                    text=f"Прогресс: 0/0 | нет подходящих файлов (проверено: {scanned_files})"
                ),
            )
            self.root.after(0, self.update_current_task, "", "no_tasks")
            return

        requested_workers = self.worker_count.get() if self.parallel_enabled.get() else 1
        requested_workers = max(1, requested_workers)
        skip_existing = bool(self.skip_existing.get())
        started_at = time.time()

        if using_cuda and not delete_only_mode:
            remove_tasks = [task for task in tasks if task["task_type"] == "remove_bg"]
            simple_tasks = [task for task in tasks if task["task_type"] != "remove_bg"]

            simple_workers = 1
            if self.parallel_enabled.get() and simple_tasks:
                simple_workers = min(requested_workers, len(simple_tasks))

            self.run_stats["workers_used"] = max(1, simple_workers)
            self.run_stats["parallel_enabled"] = bool(simple_workers > 1)

            if simple_tasks:
                if simple_workers > 1:
                    self.log(f"Параллельная файловая обработка: {simple_workers} потоков.")
                    self.process_tasks_parallel(
                        tasks=simple_tasks,
                        workers=simple_workers,
                        total_files=total_files,
                        started_at=started_at,
                        skip_existing=skip_existing,
                        cpu_thread_sessions=False,
                    )
                else:
                    self.process_tasks_sequential(
                        tasks=simple_tasks,
                        total_files=total_files,
                        started_at=started_at,
                        skip_existing=skip_existing,
                        shared_session=session,
                    )

            if remove_tasks:
                self.log("Удаление фона (CUDA): 1 поток для стабильности GPU-сессии.")
                self.process_tasks_sequential(
                    tasks=remove_tasks,
                    total_files=total_files,
                    started_at=started_at,
                    skip_existing=skip_existing,
                    shared_session=session,
                )
            self.root.after(0, self.update_progress, total_files, total_files, None)
            return

        workers = min(requested_workers, total_files) if self.parallel_enabled.get() else 1
        self.run_stats["workers_used"] = workers
        self.run_stats["parallel_enabled"] = bool(workers > 1)

        if workers > 1:
            self.log(f"CPU-параллель: {workers} потоков.")
            self.process_tasks_parallel(
                tasks=tasks,
                workers=workers,
                total_files=total_files,
                started_at=started_at,
                skip_existing=skip_existing,
                cpu_thread_sessions=True,
            )
        else:
            self.process_tasks_sequential(
                tasks=tasks,
                total_files=total_files,
                started_at=started_at,
                skip_existing=skip_existing,
                shared_session=session,
            )
        self.root.after(0, self.update_progress, total_files, total_files, None)

    @staticmethod
    def format_eta(seconds):
        if seconds is None:
            return "--"

        seconds = max(0, int(seconds))
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    def setup_progress(self, max_val):
        self.progress["maximum"] = max(1, max_val)
        self.progress["value"] = 0
        self.progress_info_label.config(text=f"Прогресс: 0/{max_val} | ETA: --")
        self.current_task_label.config(text="Текущий файл: ожидание...")

    @staticmethod
    def action_label(action):
        labels = {
            "in_progress": "Обработка",
            "background_removed": "Удаление фона",
            "renamed_png": "Переименование",
            "removed_extra": "Удаление лишнего",
            "skipped_existing": "Пропуск",
            "error": "Ошибка",
            "no_tasks": "Нет задач",
            "done": "Готово",
        }
        return labels.get(action, "Обработка")

    def update_current_task(self, file_name, action):
        action_text = self.action_label(action)
        file_text = (file_name or "--").strip()
        if len(file_text) > 90:
            file_text = f"{file_text[:87]}..."
        self.current_task_label.config(text=f"Текущий файл: {file_text} | {action_text}")

    def update_progress(self, value, total, eta_seconds):
        self.progress["maximum"] = max(1, total)
        self.progress["value"] = value
        self.progress_info_label.config(
            text=f"Прогресс: {value}/{total} | ETA: {self.format_eta(eta_seconds)}"
        )
        self.root.update_idletasks()

    def log_run_summary(self):
        summary = (
            "Итог: "
            f"проверено {self.run_stats.get('scanned_files', 0)}, "
            f"обработано {self.run_stats.get('processed', 0)}/{self.run_stats.get('total_candidates', 0)}, "
            f"переименовано {self.run_stats.get('renamed_png', 0)}, "
            f"фон удален {self.run_stats.get('background_removed', 0)}, "
            f"удалено лишних {self.run_stats.get('removed_extra', 0)}, "
            f"пропущено {self.run_stats.get('skipped_existing', 0)}, "
            f"ошибок {self.run_stats.get('errors', 0)}."
        )
        self.log(summary)

    def write_run_report(self, status, critical_error=""):
        finished_at = datetime.now()
        duration_seconds = 0.0
        if self.run_started_perf is not None:
            duration_seconds = time.perf_counter() - self.run_started_perf

        report = {
            "started_at": self.run_started_at.isoformat(sep=" ", timespec="seconds") if self.run_started_at else "",
            "finished_at": finished_at.isoformat(sep=" ", timespec="seconds"),
            "status": status,
            "mode": self.run_stats.get("mode", self.mode.get()),
            "input_path": self.run_stats.get("input_path", self.input_path),
            "output_path": self.run_stats.get("output_path", ""),
            "backup_enabled": self.run_stats.get("backup_enabled", False),
            "backup_file": self.run_stats.get("backup_file", ""),
            "compute_mode": self.run_stats.get("compute_mode", "Unknown"),
            "model_name": self.run_stats.get("model_name", self.rembg_model),
            "delete_only_mode": self.run_stats.get("delete_only_mode", False),
            "parallel_enabled": self.run_stats.get("parallel_enabled", False),
            "workers_requested": self.run_stats.get("workers_requested", 1),
            "workers_used": self.run_stats.get("workers_used", 1),
            "scanned_files": self.run_stats.get("scanned_files", 0),
            "total_candidates": self.run_stats.get("total_candidates", 0),
            "processed": self.run_stats.get("processed", 0),
            "renamed_png": self.run_stats.get("renamed_png", 0),
            "background_removed": self.run_stats.get("background_removed", 0),
            "removed_extra": self.run_stats.get("removed_extra", 0),
            "skipped_existing": self.run_stats.get("skipped_existing", 0),
            "errors": self.run_stats.get("errors", 0),
            "duration_seconds": round(duration_seconds, 2),
            "critical_error": critical_error,
        }

        timestamp = finished_at.strftime("%Y%m%d_%H%M%S")
        base_name = f"photo_cleaner_report_{timestamp}_{status}"

        try:
            os.makedirs(self.reports_dir, exist_ok=True)

            txt_path = os.path.join(self.reports_dir, f"{base_name}.txt")
            csv_path = os.path.join(self.reports_dir, f"{base_name}.csv")

            txt_lines = [
                "Photo Cleaner Report",
                "====================",
                f"Старт: {report['started_at']}",
                f"Финиш: {report['finished_at']}",
                f"Статус: {report['status']}",
                f"Режим: {report['mode']}",
                f"Источник: {report['input_path']}",
                f"Результат: {report['output_path'] or '-'}",
                f"Бэкап: {'включен' if report['backup_enabled'] else 'выключен'}",
                f"Файл бэкапа: {report['backup_file'] or '-'}",
                f"Инференс: {report['compute_mode']}",
                f"Модель: {report['model_name']}",
                f"Delete-only mode: {'yes' if report['delete_only_mode'] else 'no'}",
                f"Параллель: {'да' if report['parallel_enabled'] else 'нет'}",
                f"Потоков (запрошено/факт): {report['workers_requested']}/{report['workers_used']}",
                "",
                "Статистика",
                "----------",
                f"Проверено файлов: {report['scanned_files']}",
                f"Кандидатов: {report['total_candidates']}",
                f"Обработано: {report['processed']}",
                f"Переименовано PNG: {report['renamed_png']}",
                f"Удален фон: {report['background_removed']}",
                f"Удалено лишних: {report['removed_extra']}",
                f"Пропущено уже обработанных: {report['skipped_existing']}",
                f"Ошибок: {report['errors']}",
                f"Длительность: {report['duration_seconds']} сек",
            ]

            if report["critical_error"]:
                txt_lines.extend(["", f"Критическая ошибка: {report['critical_error']}"])

            if self.run_errors:
                txt_lines.extend(["", "Ошибки по файлам (первые 25):"])
                for item in self.run_errors:
                    txt_lines.append(f"- {item}")

            with open(txt_path, "w", encoding="utf-8") as txt_file:
                txt_file.write("\n".join(txt_lines))

            with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(report.keys()))
                writer.writeheader()
                writer.writerow(report)

            return txt_path, csv_path

        except Exception as error:
            self.log(f"Внимание: не удалось сохранить отчет: {error}")
            return None

    def get_gpu_stats(self):
        if not self.nvml_ready or self.nvml_device is None:
            return "N/A"

        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(self.nvml_device)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self.nvml_device)
            mem_used_mb = mem.used // (1024 * 1024)
            mem_total_mb = mem.total // (1024 * 1024)
            return f"{util.gpu}% ({mem_used_mb}/{mem_total_mb} MB)"
        except Exception:
            return "N/A"

    def update_system_stats(self):
        try:
            if psutil is None:
                cpu_text = "N/A"
                ram_text = "N/A"
            else:
                cpu_percent = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory()
                ram_used_gb = ram.used / (1024 ** 3)
                ram_total_gb = ram.total / (1024 ** 3)
                cpu_text = f"{cpu_percent:.0f}%"
                ram_text = f"{ram.percent:.0f}% ({ram_used_gb:.1f}/{ram_total_gb:.1f} GB)"

            gpu_text = self.get_gpu_stats()
            stats_text = f"CPU: {cpu_text} | RAM: {ram_text} | GPU: {gpu_text}"
            self.system_stats_label.config(text=stats_text)
        except Exception as error:
            error_text = f"Monitoring unavailable: {error}"
            self.system_stats_label.config(text=error_text)

        if self.root.winfo_exists():
            self.root.after(1000, self.update_system_stats)


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoCleanerApp(root)
    root.mainloop()


