from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from audio_converter_core import (  # noqa: E402
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    ConversionOptions,
    ConversionStats,
    run_conversion,
)

from update_cookie import update_cookie  # noqa: E402


class AudioConverterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("音频格式一键转换工具")
        self.geometry("920x640")
        self.minsize(820, 560)

        self.log_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()

        self.input_var = tk.StringVar(value=str(DEFAULT_INPUT_DIR))
        self.output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.mflac_var = tk.BooleanVar(value=True)
        self.mgg_var = tk.BooleanVar(value=True)
        self.ogg_var = tk.BooleanVar(value=True)
        self.ncm_var = tk.BooleanVar(value=True)
        self.lrc_var = tk.BooleanVar(value=True)

        self.total_var = tk.StringVar(value="0")
        self.success_var = tk.StringVar(value="0")
        self.skipped_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="准备就绪")

        self._build_ui()
        self.after(100, self._drain_queue)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="输入目录").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(header, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(header, text="选择", command=self._choose_input).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(header, text="输出目录").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(header, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(header, text="选择", command=self._choose_output).grid(row=1, column=2, padx=(8, 0), pady=4)

        options = ttk.LabelFrame(self, text="转换任务", padding=(14, 10))
        options.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        for col in range(4):
            options.columnconfigure(col, weight=1)
        ttk.Checkbutton(options, text="mflac 解密为 flac", variable=self.mflac_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options, text="mgg 转 mp3", variable=self.mgg_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(options, text="ogg 转 mp3", variable=self.ogg_var).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(options, text="复制 lrc 歌词", variable=self.lrc_var).grid(row=0, column=3, sticky="w")
        ttk.Checkbutton(options, text="ncm 转 mp3 / flac", variable=self.ncm_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        controls = ttk.Frame(self, padding=(14, 4, 14, 8))
        controls.grid(row=2, column=0, sticky="ew")
        controls.columnconfigure(7, weight=1)

        self.start_button = ttk.Button(controls, text="开始转换", command=self._start_conversion)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(controls, text="取消", command=self._cancel_conversion, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(controls, text="打开输出目录", command=self._open_output_dir).grid(row=0, column=2, padx=(0, 16))
        ttk.Button(controls, text="清空日志", command=self._clear_log).grid(row=0, column=3, padx=(0, 16))
        self.cookie_button = ttk.Button(controls, text="更新Cookie", command=self._update_cookie)
        self.cookie_button.grid(row=0, column=4, padx=(0, 16))

        ttk.Label(controls, text="总数").grid(row=0, column=5, padx=(0, 4))
        ttk.Label(controls, textvariable=self.total_var, width=5).grid(row=0, column=6, padx=(0, 10))
        ttk.Label(controls, text="成功").grid(row=0, column=7, sticky="e", padx=(0, 4))
        ttk.Label(controls, textvariable=self.success_var, width=5).grid(row=0, column=8, padx=(0, 10))
        ttk.Label(controls, text="跳过").grid(row=0, column=9, padx=(0, 4))
        ttk.Label(controls, textvariable=self.skipped_var, width=5).grid(row=0, column=10, padx=(0, 10))
        ttk.Label(controls, text="失败").grid(row=0, column=11, padx=(0, 4))
        ttk.Label(controls, textvariable=self.failed_var, width=5).grid(row=0, column=12)

        log_frame = ttk.Frame(self, padding=(14, 4, 14, 6))
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=20, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(self, padding=(14, 4, 14, 12))
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Label(footer, textvariable=self.status_var, width=18).grid(row=0, column=1, sticky="e")

    def _choose_input(self) -> None:
        path = filedialog.askdirectory(initialdir=self.input_var.get() or str(PROJECT_ROOT))
        if path:
            self.input_var.set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(initialdir=self.output_var.get() or str(PROJECT_ROOT))
        if path:
            self.output_var.set(path)

    def _open_output_dir(self) -> None:
        path = Path(self.output_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _update_cookie(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("任务运行中", "请先等待当前转换任务完成，再更新 Cookie。")
            return
        self.cookie_button.configure(state="disabled")
        self.status_var.set("正在更新 Cookie...")
        self._append_log("正在从 QQ 音乐客户端提取 Cookie...\n")
        threading.Thread(target=self._run_cookie_worker, daemon=True).start()

    def _run_cookie_worker(self) -> None:
        try:
            result = update_cookie()
        except Exception:
            self.log_queue.put(("log", "[失败] 更新 Cookie 异常："))
            self.log_queue.put(("log", traceback.format_exc()))
            self.log_queue.put(("cookie_done", False))
            return
        if result.get("ok"):
            self.log_queue.put(("log", f"[成功] Cookie 已更新：uin={result['uin']}，长度={result['cookie_len']}"))
            self.log_queue.put(("cookie_done", True))
        else:
            self.log_queue.put(("log", f"[失败] {result.get('error', '未知错误')}"))
            self.log_queue.put(("log", "提示：请确认 QQ 音乐客户端已启动并登录，必要时以管理员身份运行。"))
            self.log_queue.put(("cookie_done", False))

    def _start_conversion(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not any((self.mflac_var.get(), self.mgg_var.get(), self.ogg_var.get(), self.ncm_var.get(), self.lrc_var.get())):
            messagebox.showwarning("未选择任务", "请至少选择一种转换或复制任务。")
            return

        options = ConversionOptions(
            input_dir=Path(self.input_var.get()).expanduser(),
            output_dir=Path(self.output_var.get()).expanduser(),
            convert_mflac=self.mflac_var.get(),
            convert_mgg=self.mgg_var.get(),
            convert_ogg=self.ogg_var.get(),
            convert_ncm=self.ncm_var.get(),
            copy_lrc=self.lrc_var.get(),
        )

        self.cancel_event.clear()
        self._set_running(True)
        self._reset_stats()
        self._append_log("开始转换...\n")

        self.worker = threading.Thread(target=self._run_worker, args=(options,), daemon=True)
        self.worker.start()

    def _run_worker(self, options: ConversionOptions) -> None:
        try:
            run_conversion(
                options,
                log=lambda msg: self.log_queue.put(("log", msg)),
                progress=lambda stats: self.log_queue.put(("stats", stats)),
                cancelled=self.cancel_event.is_set,
            )
        except Exception:
            self.log_queue.put(("log", "[严重错误] 转换任务异常退出："))
            self.log_queue.put(("log", traceback.format_exc()))
        finally:
            self.log_queue.put(("done", None))

    def _cancel_conversion(self) -> None:
        self.cancel_event.set()
        self.status_var.set("正在取消...")
        self.stop_button.configure(state="disabled")
        self._append_log("已请求取消，当前文件处理完成后停止。\n")

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.status_var.set("转换中" if running else "准备就绪")

    def _reset_stats(self) -> None:
        self.total_var.set("0")
        self.success_var.set("0")
        self.skipped_var.set("0")
        self.failed_var.set("0")
        self.progress.configure(maximum=1, value=0)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message if message.endswith("\n") else f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_stats(self, stats: ConversionStats) -> None:
        processed = stats.success + stats.skipped + stats.failed
        maximum = max(stats.total, processed, 1)
        self.total_var.set(str(stats.total))
        self.success_var.set(str(stats.success))
        self.skipped_var.set(str(stats.skipped))
        self.failed_var.set(str(stats.failed))
        self.progress.configure(maximum=maximum, value=min(processed, maximum))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "stats":
                    self._update_stats(payload)  # type: ignore[arg-type]
                elif kind == "done":
                    self._set_running(False)
                elif kind == "cookie_done":
                    self.cookie_button.configure(state="normal")
                    self.status_var.set("准备就绪")
                    if payload:
                        messagebox.showinfo("更新成功", "qmdec Cookie 已更新，现在可以开始转换了。")
                    else:
                        messagebox.showerror("更新失败", "未能提取 QQ 音乐 Cookie，请确认 QQ 音乐客户端已启动并登录。")
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)


def main() -> None:
    app = AudioConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
