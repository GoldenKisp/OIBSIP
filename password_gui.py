"""
Random Password Generator - desktop GUI (advanced tier).

Run:  python password_gui.py

History is kept in memory only and disappears when the window closes.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections import deque
from tkinter import font as tkfont
from tkinter import ttk

from password_core import (AMBIGUOUS, CHARACTER_SETS, LABELS, MAX_LENGTH,
                           MIN_LENGTH, SYMBOLS, PasswordOptions,
                           PasswordOptionsError, evaluate_strength,
                           generate_password)

try:
    import pyperclip
except ImportError:
    pyperclip = None

HISTORY_SIZE = 5
SLIDER_MAX = 64

BG = "#f3f4f8"
PANEL = "#ffffff"
INK = "#1d2330"
MUTED = "#687085"
ACCENT = "#3d3a8c"
ERROR = "#b42318"
DIGIT_COLOR = "#1f5fbf"
SYMBOL_COLOR = "#b4232a"
BAR_TRACK = "#e3e6ee"
CHARS_PER_LINE = 32


def pick_monospace(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for family in ("Cascadia Mono", "Consolas", "SF Mono", "Menlo",
                   "DejaVu Sans Mono", "Liberation Mono", "Courier New"):
        if family in available:
            return family
    return tkfont.nametofont("TkFixedFont").actual("family")


class PasswordApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=18, style="App.TFrame")
        self.password = ""
        self.history: deque[str] = deque(maxlen=HISTORY_SIZE)
        self._status_job: str | None = None

        self.length_var = tk.StringVar(value="16")
        self.type_vars = {name: tk.BooleanVar(value=True) for name in CHARACTER_SETS}
        self.exclude_var = tk.BooleanVar(value=False)
        self.auto_copy_var = tk.BooleanVar(value=True)
        self.hide_var = tk.BooleanVar(value=False)
        self.error_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.strength_var = tk.StringVar()

        mono = pick_monospace(self)
        base = tkfont.nametofont("TkDefaultFont").actual("family")
        self.font_password = tkfont.Font(family=mono, size=18)
        self.font_mono_small = tkfont.Font(family=mono, size=11)
        self.font_title = tkfont.Font(family=base, size=16, weight="bold")

        self._build()
        for var in (self.length_var, self.exclude_var, *self.type_vars.values()):
            var.trace_add("write", lambda *_: self._validate())
        self.length_var.trace_add("write", lambda *_: self._sync_slider())
        self.hide_var.trace_add("write", lambda *_: self._render())

        master.bind("<Return>", lambda _e: self.generate())
        master.bind("<Control-g>", lambda _e: self.generate())

        # Start with a password on screen, but don't touch the clipboard until asked.
        self.generate(copy=False)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Password generator", font=self.font_title,
                  style="App.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        # Password card
        card = ttk.Frame(self, padding=16, style="Panel.TFrame")
        card.grid(row=1, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)

        self.password_text = tk.Text(card, height=1, width=CHARS_PER_LINE, wrap="char",
                                     font=self.font_password, relief="flat", bg=PANEL, fg=INK,
                                     highlightthickness=0, cursor="xterm", padx=2, pady=4)
        self.password_text.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.password_text.tag_configure("digit", foreground=DIGIT_COLOR)
        self.password_text.tag_configure("symbol", foreground=SYMBOL_COLOR)

        self.strength_bar = tk.Canvas(card, height=8, bg=PANEL, highlightthickness=0)
        self.strength_bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        self.strength_bar.bind("<Configure>", lambda _e: self._draw_strength())
        self.strength_label = ttk.Label(card, textvariable=self.strength_var, style="Panel.TLabel")
        self.strength_label.grid(row=2, column=0, sticky="w")

        ttk.Checkbutton(card, text="Hide", variable=self.hide_var,
                        style="Panel.TCheckbutton").grid(row=2, column=1, sticky="e", padx=8)
        ttk.Button(card, text="Copy", command=self.copy_current).grid(row=2, column=2, sticky="e")

        # Settings
        settings = ttk.Frame(self, padding=16, style="Panel.TFrame")
        settings.grid(row=2, column=0, sticky="ew", pady=12)
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Length", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.slider = ttk.Scale(settings, from_=MIN_LENGTH, to=SLIDER_MAX, orient="horizontal",
                                command=self._on_slider)
        self.slider.grid(row=0, column=1, sticky="ew", padx=10)
        self.slider.set(16)
        self.spinbox = ttk.Spinbox(settings, from_=MIN_LENGTH, to=MAX_LENGTH, width=5,
                                   textvariable=self.length_var)
        self.spinbox.grid(row=0, column=2, sticky="e")

        types = ttk.Frame(settings, style="Panel.TFrame")
        types.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        types.columnconfigure((0, 1), weight=1)
        for index, name in enumerate(CHARACTER_SETS):
            ttk.Checkbutton(types, text=LABELS[name].replace("...", "…"),
                            variable=self.type_vars[name], style="Panel.TCheckbutton"
                            ).grid(row=index // 2, column=index % 2, sticky="w", pady=2)
        ttk.Checkbutton(types, text=f"Exclude look-alikes ({' '.join(AMBIGUOUS)})",
                        variable=self.exclude_var, style="Panel.TCheckbutton"
                        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Checkbutton(types, text="Copy to clipboard automatically when generated",
                        variable=self.auto_copy_var, style="Panel.TCheckbutton"
                        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(settings, textvariable=self.error_var, style="Error.TLabel"
                  ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.generate_btn = ttk.Button(self, text="Generate password", style="Accent.TButton",
                                       command=self.generate)
        self.generate_btn.grid(row=3, column=0, sticky="ew")

        # History (memory only)
        history = ttk.Frame(self, padding=(16, 12), style="Panel.TFrame")
        history.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        history.columnconfigure(0, weight=1)
        ttk.Label(history, text=f"Last {HISTORY_SIZE} passwords (this session only, never saved)",
                  style="Muted.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.history_list = tk.Listbox(history, height=HISTORY_SIZE, font=self.font_mono_small,
                                       activestyle="none", relief="flat", bg="#f7f8fb", fg=INK,
                                       selectbackground=ACCENT, highlightthickness=0)
        self.history_list.grid(row=1, column=0, columnspan=3, sticky="ew", pady=6)
        self.history_list.bind("<Double-Button-1>", lambda _e: self.copy_selected_history())
        ttk.Button(history, text="Copy selected", command=self.copy_selected_history
                   ).grid(row=2, column=1, sticky="e", padx=(0, 6))
        ttk.Button(history, text="Clear history", command=self.clear_history
                   ).grid(row=2, column=2, sticky="e")

        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel"
                  ).grid(row=5, column=0, sticky="w", pady=(8, 0))

    # ------------------------------------------------------------ options
    def _read_options(self) -> PasswordOptions:
        raw = self.length_var.get().strip()
        if not raw.isdigit():
            raise PasswordOptionsError("Length must be a whole number.")
        return PasswordOptions(
            length=int(raw),
            exclude_ambiguous=self.exclude_var.get(),
            **{name: var.get() for name, var in self.type_vars.items()},
        )

    def _validate(self) -> PasswordOptions | None:
        try:
            options = self._read_options()
            options.pools()
        except PasswordOptionsError as error:
            self.error_var.set(str(error))
            self.generate_btn.state(["disabled"])
            return None
        self.error_var.set("")
        self.generate_btn.state(["!disabled"])
        return options

    def _on_slider(self, value: str) -> None:
        length = str(round(float(value)))
        if self.length_var.get() != length:
            self.length_var.set(length)

    def _sync_slider(self) -> None:
        raw = self.length_var.get().strip()
        if raw.isdigit():
            target = min(max(int(raw), MIN_LENGTH), SLIDER_MAX)
            if round(self.slider.get()) != target:
                self.slider.set(target)

    # ------------------------------------------------------------ actions
    def generate(self, copy: bool | None = None) -> None:
        options = self._validate()
        if options is None:
            return
        self.password = generate_password(options)
        self.strength = evaluate_strength(self.password, options.pool_size())
        self.history.appendleft(self.password)
        self._render()
        if copy is None:
            copy = self.auto_copy_var.get()
        if copy:
            self._copy(self.password, "Generated and copied to clipboard.")
        else:
            self._flash("Generated.")

    def copy_current(self) -> None:
        if self.password:
            self._copy(self.password, "Copied to clipboard.")

    def copy_selected_history(self) -> None:
        selection = self.history_list.curselection()
        if not selection:
            self._flash("Select a password in the history first.")
            return
        self._copy(self.history[selection[0]], "Copied from history.")

    def clear_history(self) -> None:
        self.history.clear()
        self._render_history()
        self._flash("History cleared.")

    def _copy(self, text: str, message: str) -> None:
        if pyperclip is not None:
            try:
                pyperclip.copy(text)
                self._flash(message)
                return
            except pyperclip.PyperclipException:
                pass  # e.g. no clipboard tool installed on Linux; use Tk instead
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update_idletasks()
            self._flash(message)
        except tk.TclError:
            self._flash("Couldn't access the clipboard. Select the password and copy it manually.")

    # ---------------------------------------------------------- rendering
    def _render(self) -> None:
        shown = "•" * len(self.password) if self.hide_var.get() else self.password
        text = self.password_text
        text.configure(state="normal", height=max(1, min(4, math.ceil(len(shown) / CHARS_PER_LINE))))
        text.delete("1.0", "end")
        for char in shown:
            if char.isdigit():
                text.insert("end", char, "digit")
            elif char in SYMBOLS:
                text.insert("end", char, "symbol")
            else:
                text.insert("end", char)
        text.configure(state="disabled")  # read-only, but still selectable and copyable
        self.strength_var.set(
            f"{self.strength.label}  ·  about {self.strength.entropy_bits:.0f} bits of entropy"
            f"  ·  {len(self.password)} characters")
        self._draw_strength()
        self._render_history()

    def _render_history(self) -> None:
        self.history_list.delete(0, "end")
        for item in self.history:
            self.history_list.insert("end", "•" * min(len(item), 40) if self.hide_var.get() else item)

    def _draw_strength(self) -> None:
        bar = self.strength_bar
        bar.delete("all")
        width = bar.winfo_width()
        if width <= 1 or not self.password:
            return
        bar.create_rectangle(0, 0, width, 8, fill=BAR_TRACK, outline="")
        bar.create_rectangle(0, 0, max(6, width * self.strength.score), 8,
                             fill=self.strength.color, outline="")
        # tick marks at the Weak/Medium and Medium/Strong boundaries (50 and 75 bits)
        for boundary in (0.5, 0.75):
            bar.create_line(width * boundary, 0, width * boundary, 8, fill=PANEL, width=2)

    def _flash(self, message: str) -> None:
        self.status_var.set(message)
        if self._status_job:
            self.after_cancel(self._status_job)
        self._status_job = self.after(3000, lambda: self.status_var.set(""))


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(bg=BG)
    style.configure("App.TFrame", background=BG)
    style.configure("App.TLabel", background=BG, foreground=INK)
    style.configure("Status.TLabel", background=BG, foreground=ACCENT)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Panel.TLabel", background=PANEL, foreground=INK)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Error.TLabel", background=PANEL, foreground=ERROR)
    style.configure("Panel.TCheckbutton", background=PANEL, foreground=INK)
    style.map("Panel.TCheckbutton", background=[("active", PANEL)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=10)
    style.map("Accent.TButton",
              background=[("disabled", "#a9a8c9"), ("active", "#2f2c70"), ("pressed", "#26235c")],
              foreground=[("disabled", "#eeeeee")])


def main() -> None:
    root = tk.Tk()
    root.title("Password Generator")
    root.resizable(True, False)
    configure_styles(root)
    PasswordApp(root).pack(fill="both", expand=True)
    root.minsize(520, 0)
    root.mainloop()


if __name__ == "__main__":
    main()
