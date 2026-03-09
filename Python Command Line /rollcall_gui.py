"""
rollcall_gui.py  —  simple GUI for rollcall_selenium.py
========================================================
Place this file in the same folder as rollcall_selenium.py, then run:

    python rollcall_gui.py

No extra dependencies beyond what rollcall_selenium.py already needs.
"""

import os, sys, threading, tkinter as tk
from tkinter import filedialog, scrolledtext

# ── Import the original script without running its __main__ block ──
import importlib.util
_dir    = os.path.dirname(os.path.abspath(__file__))
_script = os.path.join(_dir, "rollcall_selenium.py")
if not os.path.exists(_script):
    raise SystemExit(f"rollcall_selenium.py not found next to this file.\nExpected: {_script}")

sys.argv = [sys.argv[0]]           # stop argparse from firing
spec     = importlib.util.spec_from_file_location("rc", _script)
rc       = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)        # loads functions, skips if __name__=="__main__"


# ════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Roll Call Automator")
        self.resizable(False, False)

        pad = dict(padx=8, pady=4)

        # ── Row 0: Canvas token ──
        tk.Label(self, text="Canvas token").grid(row=0, column=0, sticky="w", **pad)
        self.token = tk.Entry(self, width=52, show="•")
        self.token.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        # pre-fill from env if available
        self.token.insert(0, os.getenv("CANVAS_ACCESS_TOKEN", ""))

        # ── Row 1: Course URL ──
        tk.Label(self, text="Course URL").grid(row=1, column=0, sticky="w", **pad)
        self.course_url = tk.Entry(self, width=52)
        self.course_url.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        self.course_url.insert(0, "https://alueducation.instructure.com/courses/")

        # ── Row 2: CSV file ──
        tk.Label(self, text="Attendance CSV").grid(row=2, column=0, sticky="w", **pad)
        self.csv_path = tk.StringVar()
        tk.Entry(self, textvariable=self.csv_path, width=42).grid(row=2, column=1, sticky="ew", **pad)
        tk.Button(self, text="Browse…", command=self._browse).grid(row=2, column=2, **pad)

        # ── Row 3: Session start time ──
        tk.Label(self, text="Start time (opt)").grid(row=3, column=0, sticky="w", **pad)
        self.start_time = tk.Entry(self, width=20)
        self.start_time.grid(row=3, column=1, sticky="w", **pad)
        tk.Label(self, text="e.g. 11:30 AM  (auto-detected from filename if blank)",
                 fg="grey").grid(row=3, column=2, sticky="w", **pad)

        # ── Row 4: Dry-run checkbox ──
        self.dry_run = tk.BooleanVar()
        tk.Checkbutton(self, text="Dry run  (calculate statuses, don't open browser)",
                       variable=self.dry_run).grid(row=4, column=1, columnspan=2, sticky="w", **pad)

        # ── Row 5: Run button ──
        self.run_btn = tk.Button(self, text="▶  Run", width=16,
                                 bg="#22d3a0", fg="black", command=self._run)
        self.run_btn.grid(row=5, column=1, sticky="w", **pad)

        # ── Row 6: Log output ──
        self.log = scrolledtext.ScrolledText(self, width=72, height=22,
                                             state="disabled", bg="black",
                                             fg="#d4d4d4", font=("Courier New", 9))
        self.log.grid(row=6, column=0, columnspan=3, padx=8, pady=8)

    # ── helpers ──────────────────────────────────
    def _browse(self):
        p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if p:
            self.csv_path.set(p)
            # auto-fill start time from filename
            _, t = rc.parse_filename_datetime(p)
            if t and not self.start_time.get().strip():
                self.start_time.delete(0, "end")
                self.start_time.insert(0, t)

    def _print(self, *args, **_kw):
        """Redirect print() → log box (called from background thread via after())."""
        msg = " ".join(str(a) for a in args) + "\n"
        self.log.config(state="normal")
        self.log.insert("end", msg)
        self.log.see("end")
        self.log.config(state="disabled")

    def _run(self):
        token      = self.token.get().strip()
        course_url = self.course_url.get().strip()
        csv_path   = self.csv_path.get().strip()
        start_time = self.start_time.get().strip() or None

        if not token:
            return self._print("⚠  Paste your Canvas access token.")
        if "/courses/" not in course_url:
            return self._print("⚠  Enter a valid Canvas course URL.")
        if not csv_path or not os.path.exists(csv_path):
            return self._print("⚠  Select an attendance CSV file.")

        # Inject token into the core module so canvas_get() picks it up
        rc.TOKEN       = token
        rc.CANVAS_BASE = course_url.split("/courses/")[0]

        self.run_btn.config(state="disabled", text="Running…")
        self.log.config(state="normal"); self.log.delete("1.0", "end"); self.log.config(state="disabled")

        # Redirect print inside rc module → our log box
        import builtins
        _orig = builtins.print
        def _patched(*a, **kw):
            self.after(0, self._print, *a)
        builtins.print = _patched

        def _worker():
            try:
                rc.run(
                    csv_path            = csv_path,
                    course_url          = course_url,
                    start_time_override = start_time,
                    dry_run             = self.dry_run.get(),
                )
            except Exception as e:
                self.after(0, self._print, f"❌ {e}")
            finally:
                builtins.print = _orig
                self.after(0, lambda: self.run_btn.config(state="normal", text="▶  Run"))

        threading.Thread(target=_worker, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
