#!/usr/bin/env python3
"""
Human Typer - types pasted text into any window (Word, Google Docs, Notepad...)
at a words-per-minute speed you choose, with human-like rhythm.

How to use:
  1. Paste your text into the box.
  2. Pick a speed (words per minute).
  3. Press Start, then click inside your Word document before the countdown ends.

Hotkeys while typing:  F8 = pause / resume,  Esc = stop  (Windows and Linux).
On every computer, including Macs: move the mouse into the top-left corner of
the screen to stop.

Needs:  Python 3.8+  and  pynput  (pip install pynput)
"""

import os
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "Human Typer"
IS_MAC = sys.platform == "darwin"
STOP_HINT = "Mouse to top-left corner = stop" if IS_MAC else "F8 = pause, Esc = stop"

# One "word" is counted as 5 characters, the standard used by typing tests.
CHARS_PER_WORD = 5

# Keys next to each other on a QWERTY keyboard, used to make believable typos.
_ROWS = ["`1234567890-=", "qwertyuiop[]", "asdfghjkl;'", "zxcvbnm,./"]
NEIGHBOURS = {}
for r, row in enumerate(_ROWS):
    for c, key in enumerate(row):
        near = set()
        for dr in (-1, 0, 1):
            rr = r + dr
            if 0 <= rr < len(_ROWS):
                for dc in (-1, 0, 1):
                    cc = c + dc
                    if (dr or dc) and 0 <= cc < len(_ROWS[rr]):
                        near.add(_ROWS[rr][cc])
        NEIGHBOURS[key] = "".join(sorted(k for k in near if k.isalpha())) or "".join(sorted(near))


# --------------------------------------------------------------------------- #
#  The plan: every key press, and how long to wait before it (as a weight)
# --------------------------------------------------------------------------- #

BACKSPACE = "\b"


def build_plan(text, variation=0.35, typo_percent=1.5, natural_pauses=True, seed=None):
    """
    Turn text into a list of (key, weight) steps.

    key is a character to type, or BACKSPACE.  weight is how long to wait before
    pressing it, relative to an average letter.  The weights are later scaled so
    the whole text takes exactly as long as the chosen WPM says it should, so
    typos and pauses never change the overall speed.
    """
    rng = random.Random(seed)
    steps = []
    prev = ""

    def jitter():
        if variation <= 0:
            return 1.0
        return rng.lognormvariate(0.0, variation)

    for ch in text:
        w = jitter()

        if natural_pauses:
            if prev in ".!?":
                w *= 4.5          # end of a sentence
            elif prev in ",;:":
                w *= 2.6          # comma, breath
            elif prev == "\n":
                w *= 6.0          # new line / paragraph
            elif prev == " ":
                w *= 1.5          # between words
                if rng.random() < 0.02:
                    w *= 6.0      # now and then, stop to "think"
            if ch.isupper() or ch in '!@#$%^&*()_+{}|:"<>?~':
                w *= 1.25         # reaching for Shift
            if ch == prev and ch.isalpha():
                w *= 0.75         # double letters are quick

        lower = ch.lower()
        if typo_percent > 0 and lower in NEIGHBOURS and ch.isalpha() and rng.random() < typo_percent / 100:
            wrong = rng.choice(NEIGHBOURS[lower])
            if ch.isupper():
                wrong = wrong.upper()
            steps.append((wrong, w))
            # Sometimes the mistake is noticed a letter late.
            late = natural_pauses and rng.random() < 0.3
            if late:
                steps.append((ch, jitter()))  # carries on with the right letter...
                steps.append((BACKSPACE, 2.8 * jitter()))  # ...then spots it and deletes both
                steps.append((BACKSPACE, 0.7 * jitter()))
            else:
                steps.append((BACKSPACE, 2.4 * jitter()))
            steps.append((ch, 1.2 * jitter()))
        else:
            steps.append((ch, w))
        prev = ch

    return steps


def seconds_for(text, wpm):
    """How long the whole text takes at this WPM."""
    if wpm <= 0:
        return 0.0
    return len(text) / (wpm * CHARS_PER_WORD / 60.0)


def format_duration(seconds):
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m} min {s} s"
    h, m = divmod(m, 60)
    return f"{h} h {m} min"


# --------------------------------------------------------------------------- #
#  The typist: presses keys on a background thread
# --------------------------------------------------------------------------- #

class Typist:
    def __init__(self):
        # Imported here so a missing library shows as a message in the app.
        from pynput.keyboard import Controller, Key
        from pynput.mouse import Controller as Mouse
        self.kb = Controller()
        self.Key = Key
        self.mouse = Mouse()
        self.wpm = 60.0
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.thread = None
        # Progress, read by the window.
        self.done_chars = 0
        self.total_chars = 0
        self.state = "idle"     # idle, countdown, typing, paused, done, stopped, error
        self.countdown_left = 0
        self.error = ""

    def press(self, key):
        if key == BACKSPACE:
            self.kb.tap(self.Key.backspace)
        elif key == "\n":
            self.kb.tap(self.Key.enter)
        elif key == "\t":
            self.kb.tap(self.Key.tab)
        else:
            self.kb.type(key)

    def start(self, text, plan, countdown):
        self.stop_event.clear()
        self.paused.clear()
        self.done_chars = 0
        self.total_chars = len(text)
        self.error = ""
        self.thread = threading.Thread(target=self._run, args=(text, plan, countdown), daemon=True)
        self.thread.start()

    def _mouse_in_corner(self):
        """Emergency stop: the mouse pushed into the top-left corner of the screen."""
        try:
            x, y = self.mouse.position
            return x <= 3 and y <= 3
        except Exception:
            return False

    def _wait(self, seconds):
        """Sleep, but wake early if stopped. Returns False when stopped."""
        end = time.monotonic() + max(0.0, seconds)
        while True:
            if self._mouse_in_corner():
                self.stop_event.set()
            left = end - time.monotonic()
            if self.stop_event.wait(max(0.0, min(0.1, left))):
                return False
            if left <= 0.1:
                return True

    def _countdown(self, seconds):
        self.state = "countdown"
        end = time.monotonic() + seconds
        while True:
            left = end - time.monotonic()
            self.countdown_left = max(0, int(left + 0.999))
            if left <= 0:
                return True
            if not self._wait(min(0.1, left)):
                return False

    def _run(self, text, plan, countdown):
        try:
            if not self._countdown(countdown):
                self.state = "stopped"
                return
            self.state = "typing"
            total_weight = sum(w for _, w in plan) or 1.0
            # Turns a weight into seconds: an average character at the chosen WPM,
            # stretched so all the steps add up to exactly the text's length.
            per_weight = len(text) / total_weight
            clock = time.monotonic()
            typed_right = 0  # how far we are through the original text

            for key, weight in plan:
                if self.paused.is_set():
                    self.state = "paused"
                    while self.paused.is_set():
                        if not self._wait(0.05):
                            self.state = "stopped"
                            return
                    # Give a moment to click back into the document.
                    if not self._countdown(3):
                        self.state = "stopped"
                        return
                    self.state = "typing"
                    clock = time.monotonic()

                char_seconds = 60.0 / (max(1.0, self.wpm) * CHARS_PER_WORD)
                clock += weight * per_weight * char_seconds
                if not self._wait(clock - time.monotonic()):
                    self.state = "stopped"
                    return
                if self.stop_event.is_set():
                    self.state = "stopped"
                    return
                self.press(key)

                if key == BACKSPACE:
                    typed_right -= 1
                else:
                    typed_right += 1
                self.done_chars = max(self.done_chars, min(typed_right, self.total_chars))

            self.done_chars = self.total_chars
            self.state = "done"
        except Exception as exc:  # show it in the window instead of crashing silently
            self.error = str(exc)
            self.state = "error"

    def toggle_pause(self):
        if self.state == "typing" and not self.paused.is_set():
            self.paused.set()
        elif self.paused.is_set():
            self.paused.clear()

    def stop(self):
        self.paused.clear()
        self.stop_event.set()

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()


# --------------------------------------------------------------------------- #
#  Mac permission
# --------------------------------------------------------------------------- #

MAC_PERMISSION_HELP = (
    "Your Mac needs to let this app press keys.\n\n"
    "1. Open System Settings > Privacy & Security > Accessibility.\n"
    + ("2. Turn on Human Typer (click + and pick it from Applications if it isn't listed).\n"
       if getattr(sys, "frozen", False) else
       "2. Turn on Terminal (or the app you started Human Typer from).\n") +
    "3. Close Human Typer and open it again."
)


def mac_can_type():
    """On a Mac, check that we're allowed to press keys, and ask for it if not.
    Without this permission the Mac silently ignores every key press."""
    if not IS_MAC:
        return True
    try:
        import HIServices  # comes with pynput on Mac
        if HIServices.AXIsProcessTrusted():
            return True
        # Opens the Mac's own "allow access" prompt.
        HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True})
        return False
    except Exception:
        return True  # can't check, so just try


# --------------------------------------------------------------------------- #
#  The window
# --------------------------------------------------------------------------- #

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("680x720" if IS_MAC else "640x620")
        root.minsize(520, 520)
        try:  # the window icon (the .app / .exe get theirs when they're built)
            here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            self._icon = tk.PhotoImage(file=os.path.join(here, "icon.png")).subsample(4)
            root.iconphoto(True, self._icon)
        except Exception:
            pass

        self.typist = None
        self.typist_error = ""
        try:
            self.typist = Typist()
        except Exception as exc:
            self.typist_error = (
                "Could not load the keyboard library (pynput).\n"
                "Install it with:   pip install pynput\n\n" + str(exc)
            )

        self.wpm = tk.IntVar(value=60)
        self.variation = tk.IntVar(value=35)
        self.typos = tk.DoubleVar(value=1.5)
        self.pauses = tk.BooleanVar(value=True)
        self.delay = tk.IntVar(value=5)
        self.on_top = tk.BooleanVar(value=True)

        self._build()
        self._start_hotkeys()
        self.wpm.trace_add("write", lambda *_: self._on_settings())
        self.on_top.trace_add("write", lambda *_: root.attributes("-topmost", self.on_top.get()))
        root.attributes("-topmost", True)
        self._update_info()
        self._poll()

        if self.typist_error:
            self.status.set(self.typist_error)

    # ----- layout -----
    def _build(self):
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Paste the text you want typed:", font=("", 11, "bold")).pack(anchor="w", **pad)

        box = ttk.Frame(main)
        box.pack(fill="both", expand=True, padx=12)
        self.text = tk.Text(box, wrap="word", undo=True, height=6, font=("", 14 if IS_MAC else 11))
        scroll = ttk.Scrollbar(box, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.bind("<<Modified>>", self._on_text_changed)

        row = ttk.Frame(main)
        row.pack(fill="x", **pad)
        ttk.Button(row, text="Paste", command=self._paste).pack(side="left")
        ttk.Button(row, text="Clear", command=lambda: self.text.delete("1.0", "end")).pack(side="left", padx=6)
        self.info = tk.StringVar()
        ttk.Label(row, textvariable=self.info, foreground="#555").pack(side="right")

        # Speed
        speed = ttk.LabelFrame(main, text="Speed")
        speed.pack(fill="x", **pad)
        ttk.Label(speed, text="Words per minute").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Scale(speed, from_=5, to=200, variable=self.wpm, orient="horizontal",
                  command=lambda v: self.wpm.set(int(float(v)))).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Spinbox(speed, from_=1, to=2000, textvariable=self.wpm, width=6).grid(row=0, column=2, padx=8)
        presets = ttk.Frame(speed)
        presets.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        for label, value in (("Slow 25", 25), ("Average 40", 40), ("Good 60", 60), ("Fast 90", 90), ("Pro 120", 120)):
            ttk.Button(presets, text=label, command=lambda v=value: self.wpm.set(v)).pack(side="left", padx=(0, 4))
        speed.columnconfigure(1, weight=1)

        # Human touches
        human = ttk.LabelFrame(main, text="Make it look human")
        human.pack(fill="x", **pad)
        ttk.Label(human, text="Rhythm variation").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Scale(human, from_=0, to=80, variable=self.variation, orient="horizontal",
                  command=lambda v: self.variation.set(int(float(v)))).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(human, textvariable=self.variation, width=4).grid(row=0, column=2)
        ttk.Label(human, text="Typos (fixed with backspace), % of letters").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Scale(human, from_=0, to=8, variable=self.typos, orient="horizontal",
                  command=lambda v: self.typos.set(round(float(v), 1))).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(human, textvariable=self.typos, width=4).grid(row=1, column=2)
        ttk.Checkbutton(human, text="Pause between words and after punctuation",
                        variable=self.pauses).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        human.columnconfigure(1, weight=1)

        # Start options
        opts = ttk.Frame(main)
        opts.pack(fill="x", **pad)
        ttk.Label(opts, text="Seconds to click into Word:").pack(side="left")
        ttk.Spinbox(opts, from_=1, to=60, textvariable=self.delay, width=4).pack(side="left", padx=6)
        ttk.Checkbutton(opts, text="Keep this window on top", variable=self.on_top).pack(side="right")

        # Controls
        ctl = ttk.Frame(main)
        ctl.pack(fill="x", **pad)
        self.start_btn = ttk.Button(ctl, text="▶  Start typing", command=self._start)
        self.start_btn.pack(side="left")
        self.pause_btn = ttk.Button(ctl, text=self._label("Pause"), command=self._pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(ctl, text="Stop" if IS_MAC else "Stop (Esc)", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left")

        self.progress = ttk.Progressbar(main, maximum=100)
        self.progress.pack(fill="x", padx=12, pady=(4, 2))
        self.status = tk.StringVar(value="Paste some text, pick a speed, then press Start.")
        ttk.Label(main, textvariable=self.status, wraplength=600, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

    # ----- helpers -----
    @staticmethod
    def _label(word):
        return word if IS_MAC else f"{word} (F8)"

    def _get_text(self):
        text = self.text.get("1.0", "end-1c")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _safe_int(self, var, default):
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return default

    def _paste(self):
        try:
            clip = self.root.clipboard_get()
        except tk.TclError:
            return
        self.text.insert("insert", clip)

    def _on_text_changed(self, _event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._update_info()

    def _on_settings(self):
        if self.typist is not None:
            self.typist.wpm = max(1, self._safe_int(self.wpm, 60))
        self._update_info()

    def _update_info(self):
        text = self._get_text()
        words = len(text.split())
        wpm = max(1, self._safe_int(self.wpm, 60))
        self.info.set(f"{words} words · {len(text)} characters · about {format_duration(seconds_for(text, wpm))}")

    # ----- actions -----
    def _start(self):
        if self.typist is None:
            self.status.set(self.typist_error)
            return
        if self.typist.busy:
            return
        text = self._get_text()
        if not text.strip():
            self.status.set("There's nothing to type yet. Paste some text first.")
            return
        if not mac_can_type():
            self.status.set(MAC_PERMISSION_HELP)
            messagebox.showinfo(APP_NAME, MAC_PERMISSION_HELP)
            return
        plan = build_plan(
            text,
            variation=self.variation.get() / 100.0,
            typo_percent=float(self.typos.get()),
            natural_pauses=self.pauses.get(),
        )
        self.typist.wpm = max(1, self._safe_int(self.wpm, 60))
        self.typist.start(text, plan, max(1, self._safe_int(self.delay, 5)))
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")

    def _pause(self):
        if self.typist:
            self.typist.toggle_pause()

    def _stop(self):
        if self.typist:
            self.typist.stop()

    def _start_hotkeys(self):
        """F8 and Esc work even while Word has focus."""
        # On macOS a global key listener next to the window can crash Tk, so there
        # the on-screen buttons are used instead.
        if self.typist is None or sys.platform == "darwin":
            return
        try:
            from pynput import keyboard
        except Exception:
            return

        def on_press(key):
            if key == keyboard.Key.esc and self.typist.busy:
                self.root.after(0, self._stop)
            elif key == keyboard.Key.f8:
                self.root.after(0, self._pause)

        try:
            self.listener = keyboard.Listener(on_press=on_press)
            self.listener.daemon = True
            self.listener.start()
        except Exception:
            pass  # hotkeys are a bonus; the buttons still work

    def _poll(self):
        t = self.typist
        if t is not None:
            if t.total_chars:
                self.progress["value"] = 100.0 * t.done_chars / t.total_chars
            state = t.state
            if state == "countdown":
                self.status.set(f"Click inside your Word document now… starting in {t.countdown_left}")
            elif state == "typing":
                left = seconds_for(" " * (t.total_chars - t.done_chars), t.wpm)
                self.status.set(f"Typing at {int(t.wpm)} WPM… {t.done_chars}/{t.total_chars} characters, "
                                f"about {format_duration(left)} left.  {STOP_HINT}.")
            elif state == "paused":
                self.status.set("Paused. Press Resume, then click back into Word.")
            elif state == "done":
                self.status.set("Finished! ✔")
            elif state == "stopped":
                self.status.set("Stopped.")
            elif state == "error":
                self.status.set("Something went wrong: " + t.error)

            self.pause_btn.configure(text=self._label("Resume" if t.paused.is_set() else "Pause"))
            if not t.busy and str(self.start_btn["state"]) == "disabled":
                self.start_btn.configure(state="normal")
                self.pause_btn.configure(state="disabled")
                self.stop_btn.configure(state="disabled")
        self.root.after(100, self._poll)


def main():
    try:  # sharper text on high-DPI Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
