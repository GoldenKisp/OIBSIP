#!/usr/bin/env python3
"""
BMI Calculator - desktop GUI (advanced tier).

Features: colour-coded results, per-person history stored in SQLite and a
matplotlib trend chart of each person's BMI over time.

Run:  python bmi_gui.py              (uses bmi_records.db next to this file)
      python bmi_gui.py --db my.db   (use a different database file)
      python bmi_gui.py --demo       (adds a 'Demo' person with sample data)
"""
from __future__ import annotations

import argparse
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import font as tkfont
from tkinter import messagebox, simpledialog, ttk

from bmi_core import (CATEGORIES, DEFAULT_DB_PATH, DISCLAIMER, BMIDatabase,
                      BMIResult, DatabaseError, Record, ValidationError,
                      evaluate, healthy_weight_range, parse_height, parse_weight)

try:  # The chart is optional: the rest of the app works without matplotlib.
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Palette
BG = "#eef2f5"
PANEL = "#ffffff"
INK = "#1f2933"
MUTED = "#616e7c"
ACCENT = "#34506b"
ERROR = "#b42318"
NEUTRAL_CARD = "#cbd2d9"

SCALE_MIN, SCALE_MAX = 12.0, 42.0  # BMI range drawn on the scale bar


class BMIApp(ttk.Frame):
    def __init__(self, master: tk.Tk, db: BMIDatabase | None, db_error: str = ""):
        super().__init__(master, padding=16, style="App.TFrame")
        self.db = db
        self.last_result: BMIResult | None = None
        self._scale_value: float | None = None

        self.person_var = tk.StringVar()
        self.weight_var = tk.StringVar()
        self.height_var = tk.StringVar()
        self.save_var = tk.BooleanVar(value=db is not None)
        self.message_var = tk.StringVar()

        self._build_fonts()
        self._build_layout()
        self._draw_scale(None)

        if db is None:
            self.message_var.set(f"History is off: {db_error}")
        else:
            self._refresh_people()
        self.weight_entry.focus_set()

    # ------------------------------------------------------------------ UI
    def _build_fonts(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")
        family = base.actual("family")
        self.font_title = tkfont.Font(family=family, size=16, weight="bold")
        self.font_bmi = tkfont.Font(family=family, size=34, weight="bold")
        self.font_category = tkfont.Font(family=family, size=14, weight="bold")
        self.font_small = tkfont.Font(family=family, size=9)

    def _build_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="BMI Calculator", font=self.font_title,
                  style="App.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        left = ttk.Frame(self, padding=16, style="Panel.TFrame")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        right = ttk.Frame(self, padding=12, style="Panel.TFrame")
        right.grid(row=1, column=1, sticky="nsew")

        self._build_form(left)
        self._build_result(left)
        self._build_history(right)

    def _build_form(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Person", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        person_row = ttk.Frame(parent, style="Panel.TFrame")
        person_row.grid(row=0, column=1, sticky="ew", pady=4)
        person_row.columnconfigure(0, weight=1)
        self.person_combo = ttk.Combobox(person_row, textvariable=self.person_var,
                                         state="readonly", width=16)
        self.person_combo.grid(row=0, column=0, sticky="ew")
        self.person_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_history())
        self.new_person_btn = ttk.Button(person_row, text="Add…", width=6, command=self._add_person)
        self.new_person_btn.grid(row=0, column=1, padx=(6, 0))
        self.remove_person_btn = ttk.Button(person_row, text="Remove", width=7,
                                            command=self._remove_person)
        self.remove_person_btn.grid(row=0, column=2, padx=(4, 0))

        ttk.Label(parent, text="Weight (kg)", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.weight_entry = ttk.Entry(parent, textvariable=self.weight_var, width=12)
        self.weight_entry.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(parent, text="Height (m)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10))
        self.height_entry = ttk.Entry(parent, textvariable=self.height_var, width=12)
        self.height_entry.grid(row=2, column=1, sticky="w", pady=4)

        self.save_check = ttk.Checkbutton(parent, text="Save to this person's history",
                                          variable=self.save_var, style="Panel.TCheckbutton")
        self.save_check.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        ttk.Button(parent, text="Calculate BMI", style="Accent.TButton",
                   command=self.calculate).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 4))

        ttk.Label(parent, textvariable=self.message_var, style="Error.TLabel",
                  wraplength=300, justify="left").grid(row=5, column=0, columnspan=2, sticky="w")

        if self.db is None:
            for widget in (self.person_combo, self.new_person_btn, self.remove_person_btn,
                           self.save_check):
                widget.state(["disabled"])

        for entry in (self.weight_entry, self.height_entry):
            entry.bind("<Return>", lambda _e: self.calculate())

    def _build_result(self, parent: ttk.Frame) -> None:
        self.card = tk.Frame(parent, bg=NEUTRAL_CARD, padx=16, pady=12)
        self.card.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        self.bmi_label = tk.Label(self.card, text="--.--", font=self.font_bmi,
                                  bg=NEUTRAL_CARD, fg=INK)
        self.bmi_label.pack(anchor="w")
        self.category_label = tk.Label(self.card, text="Enter weight and height",
                                       font=self.font_category, bg=NEUTRAL_CARD, fg=INK)
        self.category_label.pack(anchor="w")
        self.note_label = tk.Label(self.card, text="Your result appears here.", bg=NEUTRAL_CARD,
                                   fg=INK, wraplength=360, justify="left")
        self.note_label.pack(anchor="w", pady=(2, 0))

        self.scale = tk.Canvas(parent, width=300, height=46, bg=PANEL, highlightthickness=0)
        self.scale.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        self.scale.bind("<Configure>", lambda _e: self._draw_scale(self._scale_value))

        ttk.Label(parent, text=DISCLAIMER, style="Muted.TLabel", wraplength=380,
                  justify="left").grid(row=8, column=0, columnspan=2, sticky="w")

    def _build_history(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")

        # History table
        table_tab = ttk.Frame(notebook, padding=8, style="Panel.TFrame")
        table_tab.columnconfigure(0, weight=1)
        table_tab.rowconfigure(0, weight=1)
        notebook.add(table_tab, text="History")

        columns = ("date", "weight", "height", "bmi", "category")
        self.tree = ttk.Treeview(table_tab, columns=columns, show="headings", height=12,
                                 selectmode="browse")
        for col, heading, width, anchor in (
            ("date", "Date", 130, "w"), ("weight", "Weight (kg)", 95, "e"),
            ("height", "Height (m)", 90, "e"), ("bmi", "BMI", 60, "e"),
            ("category", "Category", 100, "w"),
        ):
            self.tree.heading(col, text=heading, anchor=anchor)
            self.tree.column(col, width=width, minwidth=50, anchor=anchor, stretch=True)
        for cat in CATEGORIES:
            self.tree.tag_configure(cat.name, foreground=cat.color)
        scrollbar = ttk.Scrollbar(table_tab, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.delete_btn = ttk.Button(table_tab, text="Delete selected record",
                                     command=self._delete_record)
        self.delete_btn.grid(row=1, column=0, sticky="w", pady=(8, 0))
        if self.db is None:
            self.delete_btn.state(["disabled"])

        # Trend chart
        chart_tab = ttk.Frame(notebook, padding=4, style="Panel.TFrame")
        notebook.add(chart_tab, text="Trend")
        if HAS_MATPLOTLIB:
            try:  # constrained layout keeps labels inside the canvas when it resizes
                self.figure = Figure(figsize=(6.2, 4.2), dpi=100, layout="constrained")
            except TypeError:  # matplotlib < 3.5
                self.figure = Figure(figsize=(6.2, 4.2), dpi=100, constrained_layout=True)
            self.ax = self.figure.add_subplot(111)
            self.chart = FigureCanvasTkAgg(self.figure, master=chart_tab)
            self.chart.get_tk_widget().pack(fill="both", expand=True)
            self._draw_chart([])
        else:
            ttk.Label(chart_tab, style="Panel.TLabel", wraplength=360,
                      text="Install matplotlib to see the trend chart:\n  pip install matplotlib"
                      ).pack(padx=20, pady=40)

    # ------------------------------------------------------------ actions
    def calculate(self) -> None:
        self.message_var.set("")
        try:
            weight = parse_weight(self.weight_var.get())
            height = parse_height(self.height_var.get())
        except ValidationError as error:
            self.message_var.set(str(error))
            self._show_result(None)
            return

        result = evaluate(weight, height)
        self.last_result = result
        self._show_result(result)

        if self.db is None:
            self.message_var.set("Not saved: history is unavailable in this session.")
            return
        if not self.save_var.get():
            return
        person = self.person_var.get()
        if not person:
            self.message_var.set("Not saved: add or choose a person to keep a history.")
            return
        try:
            self.db.save_record(person, result)
        except DatabaseError as error:
            messagebox.showerror("Couldn't save record", str(error), parent=self)
            return
        self._load_history()

    def _add_person(self) -> None:
        name = simpledialog.askstring("Add person", "Name:", parent=self)
        if name is None:
            return
        try:
            stored = self.db.add_user(name)
        except ValidationError as error:
            messagebox.showwarning("Add person", str(error), parent=self)
            return
        except DatabaseError as error:
            messagebox.showerror("Couldn't add person", str(error), parent=self)
            return
        self._refresh_people(select=stored)

    def _remove_person(self) -> None:
        person = self.person_var.get()
        if not person:
            return
        if not messagebox.askyesno(
                "Remove person", f"Remove {person} and all of their saved records?",
                icon="warning", parent=self):
            return
        try:
            self.db.delete_user(person)
        except DatabaseError as error:
            messagebox.showerror("Couldn't remove person", str(error), parent=self)
            return
        self._refresh_people()

    def _delete_record(self) -> None:
        selection = self.tree.selection()
        if not selection:
            self.message_var.set("Select a record in the History table first.")
            return
        try:
            self.db.delete_record(int(selection[0]))
        except DatabaseError as error:
            messagebox.showerror("Couldn't delete record", str(error), parent=self)
            return
        self._load_history()

    # ---------------------------------------------------------- rendering
    def _refresh_people(self, select: str | None = None) -> None:
        try:
            people = self.db.list_users()
        except DatabaseError as error:
            messagebox.showerror("Couldn't load people", str(error), parent=self)
            return
        self.person_combo["values"] = people
        current = select or self.person_var.get()
        if current not in people:
            current = people[0] if people else ""
        self.person_var.set(current)
        if not people:
            self.message_var.set("Add a person to start saving results.")
        self._load_history()

    def _load_history(self) -> None:
        person = self.person_var.get()
        records: list[Record] = []
        if self.db is not None and person:
            try:
                records = self.db.get_history(person)
            except DatabaseError as error:
                messagebox.showerror("Couldn't load history", str(error), parent=self)
        self.tree.delete(*self.tree.get_children())
        for rec in reversed(records):  # newest at the top
            self.tree.insert("", "end", iid=str(rec.id), tags=(rec.category,), values=(
                rec.recorded_at.strftime("%Y-%m-%d %H:%M"), f"{rec.weight_kg:.1f}",
                f"{rec.height_m:.2f}", f"{rec.bmi:.2f}", rec.category))
        if HAS_MATPLOTLIB:
            self._draw_chart(records, person)

    def _show_result(self, result: BMIResult | None) -> None:
        if result is None:
            color, fg = NEUTRAL_CARD, INK
            bmi_text, cat_text, note = "--.--", "Check your input", "Fix the input above and try again."
        else:
            low, high = healthy_weight_range(result.height_m)
            color, fg = result.category.color, "#ffffff"
            bmi_text = f"{result.bmi:.2f}"
            cat_text = result.category.name
            note = (f"{result.category.note}\nHealthy weight at {result.height_m:.2f} m: "
                    f"{low:.1f}–{high:.1f} kg")
        self.card.configure(bg=color)
        for label, text in ((self.bmi_label, bmi_text), (self.category_label, cat_text),
                            (self.note_label, note)):
            label.configure(text=text, bg=color, fg=fg)
        self._draw_scale(result.bmi if result else None)

    def _draw_scale(self, bmi: float | None) -> None:
        self._scale_value = bmi
        c = self.scale
        c.delete("all")
        width, top, bar_h = max(c.winfo_width(), int(c["width"])), 14, 12

        def x_for(value: float) -> float:
            value = min(max(value, SCALE_MIN), SCALE_MAX)
            return (value - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * (width - 2) + 1

        for cat in CATEGORIES:
            x0, x1 = x_for(max(cat.lower, SCALE_MIN)), x_for(min(cat.upper, SCALE_MAX))
            c.create_rectangle(x0, top, x1, top + bar_h, fill=cat.color, outline="")
        for boundary in (18.5, 25, 30):
            c.create_text(x_for(boundary), top + bar_h + 10, text=f"{boundary:g}",
                          fill=MUTED, font=self.font_small)
        if bmi is not None:
            x = x_for(bmi)
            c.create_polygon(x - 6, 2, x + 6, 2, x, top - 1, fill=INK, outline="")
            c.create_line(x, top, x, top + bar_h, fill=INK, width=2)

    def _draw_chart(self, records: list[Record], person: str = "") -> None:
        ax = self.ax
        ax.clear()
        bmis = [r.bmi for r in records]
        y_low = min([15.0] + [b - 2 for b in bmis])
        y_high = max([35.0] + [b + 2 for b in bmis])

        for cat in CATEGORIES:  # shaded bands, labelled directly instead of a legend
            band_low, band_high = max(cat.lower, y_low), min(cat.upper, y_high)
            if band_low >= band_high:
                continue
            ax.axhspan(band_low, band_high, color=cat.color, alpha=0.13, linewidth=0)
            ax.text(0.99, (band_low + band_high) / 2, cat.name, transform=ax.get_yaxis_transform(),
                    ha="right", va="center", fontsize=8, color=cat.color, alpha=0.9)
        ax.set_ylim(y_low, y_high)
        ax.set_ylabel("BMI")
        ax.grid(axis="y", alpha=0.3)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        if not records:
            ax.set_xticks([])
            message = (f"No saved records for {person} yet.\nCalculate with 'Save' ticked "
                       "to start a trend." if person else "Add a person to see their trend.")
            ax.text(0.5, 0.5, message, transform=ax.transAxes, ha="center",
                    va="center", color=MUTED)
            ax.set_title("BMI trend", loc="left")
        else:
            dates = [r.recorded_at for r in records]
            ax.plot(dates, bmis, color=INK, linewidth=2, marker="o", markersize=5, zorder=3)
            ax.annotate(f"{bmis[-1]:.2f}", (dates[-1], bmis[-1]), textcoords="offset points",
                        xytext=(0, 9), ha="center", fontsize=9, color=INK, fontweight="bold")
            locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
            if len(dates) == 1:  # give a single point some breathing room
                ax.set_xlim(dates[0] - timedelta(days=3), dates[0] + timedelta(days=3))
            ax.set_title(f"BMI trend for {person} ({len(records)} records)", loc="left")

        self.chart.draw_idle()


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    root.configure(bg=BG)
    style.configure("App.TFrame", background=BG)
    style.configure("App.TLabel", background=BG, foreground=INK)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Panel.TLabel", background=PANEL, foreground=INK)
    style.configure("Panel.TCheckbutton", background=PANEL, foreground=INK)
    style.map("Panel.TCheckbutton", background=[("active", PANEL)])
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Error.TLabel", background=PANEL, foreground=ERROR)
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=8)
    style.map("Accent.TButton", background=[("active", "#27405a"), ("pressed", "#1c3044")])


def seed_demo_data(db: BMIDatabase) -> None:
    """Add a 'Demo' person with a year of sample measurements (once)."""
    if db.get_history("Demo"):
        return
    start = datetime.now() - timedelta(days=330)
    for i, weight in enumerate([92.0, 90.4, 89.1, 87.5, 86.8, 85.0, 83.9, 82.2, 81.5, 80.1, 79.4, 78.6]):
        db.save_record("Demo", evaluate(weight, 1.78), when=start + timedelta(days=30 * i))


def main() -> None:
    parser = argparse.ArgumentParser(description="BMI Calculator (GUI)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database file")
    parser.add_argument("--demo", action="store_true", help="add a 'Demo' person with sample data")
    args = parser.parse_args()

    root = tk.Tk()
    root.title("BMI Calculator")
    root.geometry("1060x640")
    root.minsize(960, 600)
    configure_styles(root)

    db, db_error = None, ""
    try:
        db = BMIDatabase(args.db)
        if args.demo:
            seed_demo_data(db)
    except DatabaseError as error:
        db_error = str(error)
        messagebox.showwarning("History unavailable",
                               f"{error}\n\nYou can still calculate BMI, but results won't be saved.")

    BMIApp(root, db, db_error).pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
