"""Drag-and-drop window for the book-to-skill extractor.

The window runs the same command as:

    python scripts/extract.py <book> --mode text --install-missing no

It writes full_text.txt and metadata.json. It does not write the skill
files; those are produced later by an agent following SKILL.md.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "extract.py"

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _Root = TkinterDnD.Tk
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    _Root = tk.Tk
    DND_AVAILABLE = False

PAPER = "#f4efe6"
INK = "#1e1914"
MUTED = "#6e6458"
CARD = "#fffdf8"
LINE = "#e2d5c3"
ACCENT = "#2c4a3e"
ACCENT_ACTIVE = "#1e342b"
DROP_HOT = "#efe4d2"
DANGER = "#8c3a2f"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".epub",
    ".docx",
    ".rtf",
    ".txt",
    ".text",
    ".md",
    ".markdown",
    ".rst",
    ".adoc",
    ".asciidoc",
    ".html",
    ".htm",
    ".xhtml",
    ".mobi",
    ".azw",
    ".azw3",
}


def build_extract_command(python: str, script: Path, files: list[Path], mode: str) -> list[str]:
    """Build the extractor command. Mode falls back to text when unknown."""
    chosen = mode if mode in {"text", "technical"} else "text"
    return [
        python,
        str(script),
        *[str(path) for path in files],
        "--mode",
        chosen,
        "--install-missing",
        "no",
    ]


def run_extract(files: list[Path], mode: str, workdir: Path, on_line, proc_box: dict | None = None) -> int:
    """Run scripts/extract.py and stream each output line to on_line."""
    workdir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["BOOK_SKILL_WORKDIR"] = str(workdir)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    command = build_extract_command(sys.executable, EXTRACT_SCRIPT, files, mode)
    proc = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if proc_box is not None:
        proc_box["proc"] = proc
    assert proc.stdout is not None
    for line in proc.stdout:
        on_line(line.rstrip("\n"))
    return proc.wait()


def load_metadata(workdir: Path) -> dict | None:
    path = workdir / "metadata.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def output_dir_for(files: list[Path]) -> Path:
    if len(files) == 1:
        return files[0].parent / f"{files[0].stem}-b2s"
    return files[0].parent / "b2s-extract"


def supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


class ExtractorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.files: list[Path] = []
        self.output_custom = False
        self.running = False
        self.proc_box: dict = {}
        self.events: queue.Queue = queue.Queue()

        root.title("B2S — Drop a book")
        root.configure(bg=PAPER)
        root.minsize(680, 720)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.mode = tk.StringVar(value="text")
        self.output_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Drop a book to extract its text.")

        self._build()
        self._center(760, 820)
        self.root.after(100, self._poll)

    def _build(self) -> None:
        outer = tk.Frame(self.root, bg=PAPER, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="B2S",
            bg=PAPER,
            fg=INK,
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="Drop a book. This extracts the text into a folder you can read.\nThe chapter skill files are a later step, done by your coding agent.",
            bg=PAPER,
            fg=MUTED,
            font=("Segoe UI", 10),
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(2, 14))

        self.drop = tk.Frame(outer, bg=CARD, highlightbackground=LINE, highlightthickness=1, padx=16, pady=22)
        self.drop.pack(fill="x")
        self.drop_title = tk.Label(
            self.drop,
            text="Drop a book here",
            bg=CARD,
            fg=INK,
            font=("Segoe UI", 16, "bold"),
        )
        self.drop_title.pack()
        self.drop_hint = tk.Label(
            self.drop,
            text="PDF, EPUB, DOCX, HTML, Markdown, or plain text",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        self.drop_hint.pack(pady=(4, 0))
        self._register_drop(self.drop, self.drop_title, self.drop_hint)
        if not DND_AVAILABLE:
            self.drop_hint.configure(text="Drag-and-drop needs tkinterdnd2. Use Browse for now.")

        actions = tk.Frame(outer, bg=PAPER)
        actions.pack(fill="x", pady=(10, 0))
        self._button(actions, "Browse…", self.browse).pack(side="left")
        self._button(actions, "Clear", self.clear_files).pack(side="left", padx=(8, 0))

        self.file_list = tk.Listbox(
            outer,
            height=4,
            bg=CARD,
            fg=INK,
            font=("Segoe UI", 10),
            relief="flat",
            highlightbackground=LINE,
            highlightthickness=1,
            activestyle="none",
            selectbackground="#d9e4df",
            selectforeground=INK,
        )
        self.file_list.pack(fill="x", pady=(10, 0))

        mode_box = tk.Frame(outer, bg=PAPER)
        mode_box.pack(fill="x", pady=(14, 0))
        tk.Label(mode_box, text="Book type", bg=PAPER, fg=INK, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Radiobutton(
            mode_box,
            text="Text-heavy — fast. Prose, few tables.",
            variable=self.mode,
            value="text",
            bg=PAPER,
            fg=INK,
            activebackground=PAPER,
            selectcolor=CARD,
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x")
        tk.Radiobutton(
            mode_box,
            text="Technical — keeps tables and code. Slower, needs Docling.",
            variable=self.mode,
            value="technical",
            bg=PAPER,
            fg=INK,
            activebackground=PAPER,
            selectcolor=CARD,
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x")

        out = tk.Frame(outer, bg=PAPER)
        out.pack(fill="x", pady=(12, 0))
        tk.Label(out, text="Output folder", bg=PAPER, fg=INK, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = tk.Frame(out, bg=PAPER)
        row.pack(fill="x", pady=(4, 0))
        self.output_entry = tk.Entry(
            row,
            textvariable=self.output_var,
            bg=CARD,
            fg=INK,
            relief="flat",
            highlightbackground=LINE,
            highlightthickness=1,
            font=("Segoe UI", 10),
        )
        self.output_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.output_entry.bind("<Key>", self._mark_output_custom)
        self._button(row, "Change", self.choose_output).pack(side="left", padx=(8, 0))

        run_row = tk.Frame(outer, bg=PAPER)
        run_row.pack(fill="x", pady=(14, 0))
        self.extract_btn = tk.Button(
            run_row,
            text="Extract",
            command=self.extract,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_ACTIVE,
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 11, "bold"),
            padx=18,
            pady=6,
            cursor="hand2",
        )
        self.extract_btn.pack(side="left")
        self.progress = ttk.Progressbar(run_row, mode="indeterminate", length=160)
        self.progress.pack(side="left", padx=(12, 0))

        tk.Label(
            outer,
            textvariable=self.status_var,
            bg=PAPER,
            fg=INK,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(10, 0))

        self.stats = tk.Label(
            outer,
            text="",
            bg=PAPER,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            wraplength=700,
        )
        self.stats.pack(fill="x", pady=(4, 8))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        self.notebook = notebook

        log_frame = tk.Frame(notebook, bg=CARD)
        preview_frame = tk.Frame(notebook, bg=CARD)
        notebook.add(log_frame, text="Log")
        notebook.add(preview_frame, text="Preview")

        self.log = self._text(log_frame)
        self.preview = self._text(preview_frame)

        foot = tk.Frame(outer, bg=PAPER)
        foot.pack(fill="x", pady=(10, 0))
        self._button(foot, "Open folder", self.open_folder).pack(side="left")
        self._button(foot, "Open text file", self.open_text).pack(side="left", padx=(8, 0))

    def _text(self, parent: tk.Widget) -> tk.Text:
        widget = tk.Text(
            parent,
            bg=CARD,
            fg=INK,
            font=("Consolas", 10),
            relief="flat",
            wrap="word",
            padx=8,
            pady=8,
            state="disabled",
        )
        scroll = tk.Scrollbar(parent, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(side="left", fill="both", expand=True)
        return widget

    def _button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=CARD,
            fg=INK,
            activebackground=DROP_HOT,
            relief="flat",
            highlightbackground=LINE,
            font=("Segoe UI", 10),
            padx=12,
            pady=4,
            cursor="hand2",
        )

    def _register_drop(self, *widgets: tk.Widget) -> None:
        if not DND_AVAILABLE:
            return
        for widget in widgets:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_drop)
            widget.dnd_bind("<<DragEnter>>", self.on_drag_enter)
            widget.dnd_bind("<<DragLeave>>", self.on_drag_leave)

    def _center(self, width: int, height: int) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def on_drag_enter(self, _event):
        self._paint_drop(DROP_HOT)
        return "copy"

    def on_drag_leave(self, _event):
        self._paint_drop(CARD)

    def _paint_drop(self, color: str) -> None:
        self.drop.configure(bg=color)
        self.drop_title.configure(bg=color)
        self.drop_hint.configure(bg=color)

    def on_drop(self, event):
        self._paint_drop(CARD)
        try:
            raw = self.root.tk.splitlist(event.data)
        except tk.TclError:
            raw = [event.data]
        self.add_files([Path(item) for item in raw])

    def browse(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        chosen = filedialog.askopenfilenames(
            title="Choose a book",
            filetypes=[("Books and documents", patterns), ("All files", "*.*")],
        )
        if chosen:
            self.add_files([Path(path) for path in chosen])

    def add_files(self, paths: list[Path]) -> None:
        rejected: list[str] = []
        added = False
        for path in paths:
            resolved = path.expanduser()
            if not supported_file(resolved):
                rejected.append(path.name)
                continue
            if resolved.resolve() not in {item.resolve() for item in self.files}:
                self.files.append(resolved.resolve())
                added = True
        self._refresh_files(update_output=added)
        if rejected:
            self.status_var.set(f"Skipped unsupported files: {', '.join(rejected)}")
        elif self.files:
            self.status_var.set(f"{len(self.files)} file(s) ready.")

    def _refresh_files(self, update_output: bool) -> None:
        self.file_list.delete(0, "end")
        for path in self.files:
            self.file_list.insert("end", str(path))
        if update_output and self.files and not self.output_custom:
            self.output_var.set(str(output_dir_for(self.files)))

    def clear_files(self) -> None:
        if self.running:
            return
        self.files.clear()
        self.output_custom = False
        self.output_var.set("")
        self._refresh_files(update_output=False)
        self.status_var.set("Drop a book to extract its text.")
        self.stats.configure(text="")

    def _mark_output_custom(self, _event) -> None:
        self.output_custom = True

    def choose_output(self) -> None:
        chosen = filedialog.askdirectory(title="Choose output folder")
        if chosen:
            self.output_custom = True
            self.output_var.set(chosen)

    def extract(self) -> None:
        if self.running:
            return
        if not self.files:
            self.status_var.set("Drop a book first, or use Browse.")
            return
        workdir = self.output_var.get().strip()
        if not workdir:
            workdir = str(output_dir_for(self.files))
            self.output_var.set(workdir)
        self.running = True
        self.extract_btn.configure(state="disabled", text="Extracting…")
        self.progress.start(12)
        self.status_var.set("Extracting…")
        self.stats.configure(text="")
        self._set_text(self.log, "")
        self._set_text(self.preview, "")
        self.notebook.select(0)
        files = list(self.files)
        mode = self.mode.get()
        target = Path(workdir)

        def worker() -> None:
            try:
                code = run_extract(files, mode, target, lambda line: self.events.put(("log", line)), self.proc_box)
                self.events.put(("done", code, str(target)))
            except Exception as exc:
                self.events.put(("log", f"ERROR: {exc}"))
                self.events.put(("done", 1, str(target)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "log":
                self._append(self.log, event[1] + "\n")
            elif kind == "done":
                self._finish(event[1], Path(event[2]))
        self.root.after(100, self._poll)

    def _finish(self, code: int, workdir: Path) -> None:
        self.running = False
        self.extract_btn.configure(state="normal", text="Extract")
        self.progress.stop()
        meta = load_metadata(workdir) if code == 0 else None
        if code != 0 or meta is None:
            self.status_var.set("Extraction failed. The log has the reason.")
            self.stats.configure(text="", fg=DANGER)
            return
        tokens = meta.get("estimated_tokens_human", "")
        self.status_var.set(f"Saved text to {workdir / 'full_text.txt'}")
        self.stats.configure(
            text=(
                f"{meta.get('pages', 0)} pages · {meta.get('words', 0):,} words · "
                f"{tokens} tokens · {meta.get('chapters_detected', 0)} chapters · "
                f"{meta.get('extraction_method', 'unknown')}"
            ),
            fg=MUTED,
        )
        text_path = workdir / "full_text.txt"
        preview = ""
        if text_path.is_file():
            preview = text_path.read_text(encoding="utf-8", errors="replace")
        if len(preview) > 6000:
            preview = preview[:6000] + "\n\n… preview truncated …"
        self._set_text(self.preview, preview)
        self.notebook.select(1)

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _append(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", value)
        widget.see("end")
        widget.configure(state="disabled")

    def open_folder(self) -> None:
        path = self.output_var.get().strip()
        if path and Path(path).is_dir():
            os.startfile(path)  # noqa: S606 — user-requested folder open on Windows

    def open_text(self) -> None:
        path = self.output_var.get().strip()
        text = Path(path) / "full_text.txt" if path else None
        if text and text.is_file():
            os.startfile(text)  # noqa: S606 — user-requested file open on Windows

    def close(self) -> None:
        proc = self.proc_box.get("proc")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        self.root.destroy()


def main() -> None:
    root = _Root()
    ExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
