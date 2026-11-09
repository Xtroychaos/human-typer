#!/usr/bin/env python3
"""
Human Typer in the terminal: the same Write -> Polish -> Type as the window,
as simple menus.

    python human_typer_cli.py          (or: python human_typer.py --cli)

Every screen has a short menu: press the letter or number in [ ] (no Enter
needed). Esc goes back, Enter does the main thing on the screen. The text you're
working on carries from one step to the next, like the tabs in the window app.
Ctrl+C stops whatever is happening (a reply, a rewrite, typing) and goes back.

Quick commands, with no menus (handy in scripts, and they chain with |):

    human_typer_cli.py type notes.txt --wpm 70 --style Messy
    human_typer_cli.py ask "write a short email asking for Friday off" | human_typer_cli.py fix -
    human_typer_cli.py write "a thank-you note for my son's teacher"   (Claude -> humanise -> fix -> type)

Run  human_typer_cli.py --help  for them all.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time

APP = "HUMAN TYPER"
STYLES = {"Careful": (20, 0.5), "Natural": (35, 1.5), "Messy": (60, 4.0)}
DEFAULTS = {
    "wpm": 60, "random": None, "variation": 35, "typos": 1.5, "pauses": True,
    "targets": "", "fix_chosen": True, "delay": 5, "background": False, "pin": True,
    "wf_humanise": True, "wf_fix": True, "check_level": 3,
}


# --------------------------------------------------------------------------- #
#  Looks: colours, boxes and bars (plain text when colours aren't wanted)
# --------------------------------------------------------------------------- #

class Paint:
    CODES = {"bold": "1", "dim": "2", "italic": "3", "under": "4", "accent": "38;5;99", "accent_bg": "48;5;99",
             "green": "38;5;35", "yellow": "38;5;178", "orange": "38;5;208", "red": "38;5;203", "grey": "38;5;245",
             "white": "97", "hl_red": "48;5;224;38;5;16", "hl_orange": "48;5;223;38;5;16",
             "hl_blue": "48;5;153;38;5;16", "hl_grey": "48;5;252;38;5;16", "hl_yellow": "48;5;229;38;5;16"}

    def __init__(self, on):
        self.on = on

    def __call__(self, text, *names):
        if not self.on or not names:
            return text
        return "\033[" + ";".join(self.CODES[n] for n in names) + "m" + text + "\033[0m"


def colours_wanted(stream):
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def visible_len(text):
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


# --------------------------------------------------------------------------- #
#  One keypress, no Enter (on a real terminal)
# --------------------------------------------------------------------------- #

def getkey():
    """Wait for one key. Returns it in lower case; "" for Enter and "esc" for Esc.
    Ctrl+C raises KeyboardInterrupt and Ctrl+D / Ctrl+Z raise EOFError, as usual.
    Arrow keys and other special keys are ignored."""
    while True:
        if sys.platform == "win32":
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):          # a special key: its second half follows
                msvcrt.getwch()
                continue
        else:
            import select
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                data = os.read(fd, 4)
                if data == b"\x1b":
                    while select.select([fd], [], [], 0.02)[0]:   # an arrow key: swallow the rest
                        data += os.read(fd, 8)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            ch = data.decode("utf-8", "replace")
            if ch.startswith("\x1b") and len(ch) > 1:
                continue
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch in ("\x04", "\x1a"):
            raise EOFError
        if ch in ("\r", "\n"):
            return ""
        if ch == "\x1b":
            return "esc"
        if ch.isprintable() and len(ch) == 1:
            return ch.lower()


# --------------------------------------------------------------------------- #
#  Clipboard, without extra libraries
# --------------------------------------------------------------------------- #

def clipboard_get():
    if sys.platform == "darwin":
        cmds = [["pbpaste"]]
    elif sys.platform == "win32":
        cmds = [["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]]
    else:
        cmds = [["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "-b", "-o"]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
                if r.returncode == 0:
                    return r.stdout.replace("\r\n", "\n")
            except Exception:
                pass
    return None


def clipboard_set(text):
    if sys.platform == "darwin":
        cmds = [["pbcopy"]]
    elif sys.platform == "win32":
        cmds = [["powershell", "-NoProfile", "-Command", "[Console]::In.ReadToEnd() | Set-Clipboard"]]
    else:
        cmds = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text, text=True, encoding="utf-8", timeout=10, check=True)
                return True
            except Exception:
                pass
    return False


# --------------------------------------------------------------------------- #
#  The terminal app
# --------------------------------------------------------------------------- #

GLOBAL = {"1": "write", "2": "polish", "3": "type", "4": "boxes", "5": "settings", "6": "connect", "?": "help",
          "q": "quit", "esc": "home"}
TABS = [("1", "Write", "write"), ("2", "Polish", "polish"), ("3", "Type", "type"), ("4", "Boxes", "boxes"),
        None, ("5", "Settings", "settings"), ("6", "Connect", "connect"), ("?", "Help", "help")]
BOX_MODES = ["click", "spot", "tab", "word"]
BOX_MODE_NAMES = {"click": "I click into each box", "spot": "auto-click my spots",
                  "tab": "Tab through a Word table", "word": "Word cells from a .docx"}


class CLI:
    """The terminal app. Every screen is the same workspace, top to bottom:

        title bar  (and what's set: Claude, speed, style)
        tab bar    1 Write  2 Polish  3 Type  4 Boxes | 5 Settings  6 Connect  ? Help
        panel      the text you're working on (or the chat, the boxes, the settings)
        actions    what this screen can do, one key each, in a grid
        result     what the last action did (stays until the next one)
        footer     the keys that work everywhere

    The number keys jump to any screen from anywhere; Esc goes home; q quits.
    """

    def __init__(self, ht, read=input, out=None, secret=None, typist_factory=None, colour=None, keys=None):
        self.ht = ht
        self.read_fn = read
        self.keys = keys               # one-keypress menus (None: type the choice and press Enter)
        self.out = out or sys.stdout
        self.secret_fn = secret
        self.p = Paint(colours_wanted(self.out) if colour is None else colour)
        self.typist_factory = typist_factory or ht.Typist
        self.typist = None
        self._account = None           # Claude login status, checked once (it can take a second or two)
        cfg = ht.load_config()
        self.s = dict(DEFAULTS, **cfg.get("cli", {}))
        engine = cfg.get("engine", "account")
        self.engine = engine if engine in ("account", "claude", "local") else "account"
        self.model = cfg.get("ollama_model", "")
        self.audience = cfg.get("audience", ht.AUDIENCES[2])
        self.format = cfg.get("format", ht.FORMATS[0])
        self.text = ""
        self.undo = []                 # earlier versions of the text
        self.boxes = []                # {"text", "done", "spot", "cell"}
        self.box_mode = "click"
        self.doc = None                # a connected Word document: {"path", "cells"}
        self.chat = []                 # the conversation
        self.session = None            # Claude account: the conversation to carry on
        self.msg = []                  # the result area: what the last action did
        self.where = "home"

    # ================================================================== #
    #  Drawing
    # ================================================================== #
    @property
    def width(self):
        return max(56, min(96, shutil.get_terminal_size((80, 24)).columns - 2))

    def say(self, text="", end="\n"):
        self.out.write(text + end)
        self.out.flush()

    def clear(self):
        if self.p.on:
            self.out.write("\033[2J\033[H")

    def tell(self, text, kind="grey"):
        """Add a line to the result area (shown under the actions until the next action)."""
        icon = {"green": "✓", "red": "✗", "yellow": "!", "grey": "·", "accent": "›"}.get(kind, "·")
        for i, line in enumerate(textwrap.wrap(text, self.width - 6) or [""]):
            self.msg.append(self.p((icon if i == 0 else " ") + " " + line, kind))

    def note(self, text, kind="grey"):
        """Print a line straight away (for steps that happen below the workspace)."""
        icon = {"green": "✓", "red": "✗", "yellow": "!", "grey": "·", "accent": "›"}.get(kind, "·")
        for i, line in enumerate(textwrap.wrap(text, self.width - 6) or [""]):
            self.say("  " + self.p((icon if i == 0 else " ") + " " + line, kind))

    def flush_msg(self):
        for line in self.msg:
            self.say("  " + line)
        self.msg = []

    def rule(self, title="", detail=""):
        w = self.width
        room = w - 8 - len(title)
        if detail and len(detail) > room:
            detail = detail[:max(0, room - 1)] + "…"
        head = (self.p(title, "bold") + ("  " + self.p(detail, "grey") if detail else "")) if title else ""
        fill = w - 2 - visible_len(head) - (1 if head else 0)
        self.say("  " + head + (" " if head else "") + self.p("─" * max(2, fill), "grey"))

    def panel(self, lines, title, height=None):
        """The workspace: a rounded box, always the same width. height pads it so the screen doesn't jump."""
        w = self.width - 2
        t = f" {title} "
        self.say("  " + self.p("╭─", "grey") + self.p(t, "accent", "bold") +
                 self.p("─" * max(0, w - visible_len(t) - 3) + "╮", "grey"))
        lines = list(lines)
        if height:                                  # at least a few rows, so short text still looks like a page
            lines += [""] * max(0, min(height, 3) - len(lines))
        for line in lines:
            if visible_len(line) > w - 4:
                line = line[:w - 5] + "…"
            self.say("  " + self.p("│", "grey") + " " + line + " " * max(0, w - 4 - visible_len(line)) + " " +
                     self.p("│", "grey"))
        self.say("  " + self.p("╰" + "─" * (w - 2) + "╯", "grey"))

    def bar(self, fraction, width=28):
        fraction = max(0.0, min(1.0, fraction))
        full = int(round(width * fraction))
        return self.p("█" * full, "accent") + self.p("░" * (width - full), "grey")

    def header(self, where):
        self.clear()
        w = self.width
        title = self.p(" ⌨  " + APP + " ", "bold", "white", "accent_bg")
        ai = self.ai_status_short()
        right = (self.p(ai, "green" if "✓" in ai else "yellow") + self.p("  ·  ", "grey") +
                 self.p(self.status_speed(), "grey") + self.p("  ·  ", "grey") + self.p(self.style_name(), "grey"))
        self.say("")
        self.say("  " + title + " " * max(1, w - visible_len(title) - visible_len(right) - 2) + right)
        tabs = []
        for tab in TABS:
            if tab is None:
                tabs.append(self.p("│", "grey"))
                continue
            key, name, screen = tab
            if not self.p.on:
                tabs.append(f"[{key} {name}]" if screen == where else f" {key} {name} ")
            elif screen == where:
                tabs.append(self.p(f" {key} {name} ", "bold", "white", "accent_bg"))
            else:
                tabs.append(self.p(key, "accent", "bold") + self.p(f" {name} ", "grey"))
        self.say("  " + " ".join(tabs))

    def actions(self, items, title, detail=""):
        """The actions grid: (key, label) pairs, a few to a row."""
        self.rule(title.upper(), detail)
        items = [i for i in items if i]
        cols = 3 if self.width >= 72 else 2
        cell = (self.width - 4) // cols
        for r in range(0, len(items), cols):
            row = ""
            for key, label in items[r:r + cols]:
                k = "⏎" if key == "enter" else key
                text = self.p(k.rjust(2), "accent", "bold") + " " + label
                row += text + " " * max(1, cell - visible_len(text))
            self.say("  " + row.rstrip())

    def footer(self):
        if self.msg:
            self.rule("result")
            self.flush_msg()
        self.say("  " + self.p("1-6 jump · ? help · Esc home · q quit", "grey"))

    def screen(self, where, panel_lines, panel_title, items, title, detail="", height=8):
        """Draw a whole screen and read one choice. Returns a key, or the name of a screen to go to."""
        self.header(where)
        self.panel(panel_lines, panel_title, height)
        self.actions(items, title, detail)
        self.footer()
        local = {i[0] for i in items if i}
        return self.choose(local)

    def choose(self, local):
        """One keypress (or a typed line). Local keys win; then the keys that work everywhere."""
        prompt = f"  {self.p('›', 'accent', 'bold')} "
        while True:
            if self.keys:
                self.out.write(prompt)
                self.out.flush()
                k = self.keys()
            else:
                k = self.read(prompt).strip().lower()
            if k == "" and "enter" in local:
                k = "enter"
            if k in local:
                if self.keys:
                    self.say(self.p("⏎" if k == "enter" else k, "accent"))
                return k
            if k in GLOBAL:
                if self.keys:
                    self.say(self.p(k, "accent"))
                return GLOBAL[k]
            if not self.keys:
                return ""                          # line mode: anything else just redraws

    # ================================================================== #
    #  Reading input
    # ================================================================== #
    def read(self, prompt=""):
        return self.read_fn(prompt)

    def ask(self, label, default=None):
        hint = self.p(f" [{default}]", "grey") if default not in (None, "") else ""
        answer = self.read(f"  {self.p('›', 'accent', 'bold')} {label}{hint} ").strip()
        return answer if answer else ("" if default is None else str(default))

    def yes(self, label, default=True):
        if self.keys:
            self.out.write(f"  {self.p('›', 'accent', 'bold')} {label} " + self.p("(Y/n) " if default else "(y/N) ", "grey"))
            self.out.flush()
            while True:
                k = self.keys()
                if k in ("y", "n", "", "esc"):
                    answer = default if k == "" else k == "y"
                    self.say("yes" if answer else "no")
                    return answer
        answer = self.ask(label + (" (Y/n)" if default else " (y/N)")).lower()
        return default if not answer else answer.startswith("y")

    def secret(self, label):
        if self.secret_fn:
            return self.secret_fn(label)
        import getpass
        return getpass.getpass(f"  › {label} ")

    def read_block(self, label="Paste or type your text"):
        self.note(label + ". Finish with a line that's just a full stop ( . ).", "accent")
        lines = []
        while True:
            try:
                line = self.read("  " + self.p("│ ", "grey"))
            except EOFError:
                break
            if line.strip() == ".":
                break
            lines.append(line)
        return "\n".join(lines).strip("\n")

    def pause(self):
        """Only for one-line commands that print and stop; screens show results instead."""

    # ================================================================== #
    #  State
    # ================================================================== #
    def save(self):
        cfg = self.ht.load_config()
        cfg["cli"] = self.s
        cfg.update(engine=self.engine, ollama_model=self.model, audience=self.audience, format=self.format)
        self.ht.save_config(cfg)

    def style_name(self):
        for name, (v, t) in STYLES.items():
            if self.s["variation"] == v and abs(float(self.s["typos"]) - t) < 1e-9:
                return name
        return f"rhythm {self.s['variation']} · typos {self.s['typos']:g}%"

    def status_speed(self):
        return f"{self.s['random'][0]}–{self.s['random'][1]} WPM" if self.s["random"] else f"{self.s['wpm']} WPM"

    def avg_wpm(self):
        return self.ht.average_speed(*self.s["random"]) if self.s["random"] else self.s["wpm"]

    def set_text(self, text, remember=True):
        if remember and self.text and text != self.text:
            self.undo.append(self.text)
            del self.undo[:-20]
        self.text = text

    def text_lines(self, text=None, limit=8):
        text = self.text if text is None else text
        if not text.strip():
            return [self.p("No text yet.", "grey")]
        lines = []
        for para in text.split("\n"):
            lines += textwrap.wrap(para, self.width - 8) or [""]
        if len(lines) > limit:
            lines = lines[:limit - 1] + [self.p(f"… {len(lines) - limit + 1} more lines  (t on Home shows it all)", "grey")]
        return lines

    def text_title(self):
        words = len(self.text.split())
        if not words:
            return "TEXT"
        took = self.ht.format_duration(self.ht.seconds_for(self.text, self.avg_wpm()))
        return f"TEXT · {words} word{'' if words == 1 else 's'} · about {took}"

    # ================================================================== #
    #  The AI
    # ================================================================== #
    def ai_status_short(self):
        if self.engine == "account":
            return "Claude ✓" if self.ht.find_claude_cli() else "Claude: not connected"
        if self.engine == "claude":
            return "Claude (API key ✓)" if self.key() else "Claude (API key): none"
        return f"local AI ({self.model or 'no model'})"

    def key(self):
        return self.ht.load_config().get("claude_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")

    def ai_problem(self):
        if self.engine == "account" and not self.ht.find_claude_cli():
            return self.ht.CLAUDE_SETUP_HELP.replace("Connect Claude…", "6 Connect")
        if self.engine == "claude" and not self.key():
            return "Add your Claude API key first: 6 Connect → k."
        if self.engine == "local" and not self.model:
            return "Pick a local AI model first: 6 Connect → m."
        return None

    def ai(self, system, messages, on_text, session=None, keep=False):
        """Ask the chosen AI. Ctrl+C stops it. Returns {"text", "session"} or {"error"} (+ "stopped")."""
        ht, stop, result = self.ht, threading.Event(), {}
        engine, key, model = self.engine, self.key(), self.model

        def work():
            try:
                if engine == "account":
                    text, sid = ht.claude_account_stream(messages[-1]["content"], system, on_text, stop,
                                                         session=session, keep=keep)
                    result.update(text=text, session=sid)
                elif engine == "claude":
                    result["text"] = ht.claude_api_stream(system, messages, key, on_text, stop)
                else:
                    result["text"] = ht.ollama_stream(system, messages, model, on_text, stop)
            except Exception as exc:
                result["error"] = str(exc).replace("\n\n", " ").replace("\n", " ")

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        try:
            while thread.is_alive():
                thread.join(0.1)
        except KeyboardInterrupt:
            stop.set()
            thread.join(10)
            result["stopped"] = True
        return result

    def humanise(self, text, show=True):
        """Rewrite text with the Humaniser (shown as it's written). Returns the new text, or None."""
        problem = self.ai_problem()
        if problem:
            self.tell(problem, "red")
            return None
        if show:
            self.note(f"Humanising for {self.audience[2:]}, as {self.format}… (Ctrl+C stops)", "accent")
            self.say("  ", end="")
        r = self.ai(self.ht.HUMANISER_PROMPT,
                    [{"role": "user", "content": self.ht.humaniser_request(text, self.audience, self.format)}],
                    (lambda piece: self.say(piece.replace("\n", "\n  "), end="")) if show else (lambda piece: None))
        if show:
            self.say("")
        if r.get("stopped"):
            self.tell("Stopped. The text wasn't changed.", "yellow")
            return None
        if "error" in r:
            self.tell(r["error"], "red")
            return None
        return (r.get("text") or "").strip() or None

    def fix(self, text, level=None):
        level = level or self.s["check_level"]
        new, fixed, left = self.ht.apply_fixes(text, self.ht.check_text(text), level)
        return new, len(fixed), left

    def workflow(self, text):
        """Claude's answer -> humanise -> fix. Sets the text and returns True, or False if it stopped."""
        done = []
        if self.s["wf_humanise"]:
            new = self.humanise(text)
            if new is None:
                return False
            text = new
            done.append("humanised")
        if self.s["wf_fix"]:
            text, n, _ = self.fix(text)
            done.append(f"fixed {n} mistake{'' if n == 1 else 's'}")
        self.set_text(text)
        self.tell("Ready to type" + (f" ({', '.join(done)})" if done else "") + ". Press Enter to start.", "green")
        return True

    # ================================================================== #
    #  The screens (each draws itself, takes one choice, says where to go next)
    # ================================================================== #
    def run(self):
        screens = {"home": self.home, "write": self.write, "polish": self.polish, "type": self.type_screen,
                   "boxes": self.boxes_screen, "settings": self.settings, "connect": self.connect, "help": self.help}
        while self.where != "quit":
            try:
                self.where = screens[self.where]() or self.where
            except KeyboardInterrupt:
                self.say("")
                self.tell("Stopped.", "yellow")
        self.save()
        self.say(self.p("  Bye!", "grey"))

    # ----- Home: the text, and ways to bring it in or take it out -----
    def home(self):
        nothing = not self.text.strip()
        k = self.screen("home", self.text_lines(limit=10), self.text_title(), [
            ("e", "Paste / type"), ("v", "From clipboard"), ("o", "Open a file"),
            ("t", "See it all"), ("c", "Copy"), ("x", "Clear"),
            ("enter", "Write with Claude" if nothing else "Type it")],
            "home", "start at 1 Write, or bring in your own text" if nothing else "next: 2 Polish or 3 Type",
            height=10)
        if k in GLOBAL.values():
            return k
        if k == "enter":
            return "write" if nothing else "type"
        if k == "e":
            new = self.read_block()
            if new.strip():
                self.set_text(new)
        elif k == "v":
            clip = clipboard_get()
            if clip and clip.strip():
                self.set_text(clip.strip("\n"))
                self.tell(f"Pasted {len(clip.split())} words from the clipboard.", "green")
            else:
                self.tell("The clipboard is empty (or can't be read here). Use e and paste instead.", "yellow")
        elif k == "o":
            self.open_file()
        elif k == "t":
            for line in self.text_lines(limit=10 ** 6):
                self.msg.append(line)
        elif k == "c":
            self.tell("Copied." if self.text and clipboard_set(self.text) else "Couldn't copy here.",
                      "green" if self.text else "yellow")
        elif k == "x":
            self.set_text("")
            self.tell("Cleared (u in 2 Polish brings it back).", "green")

    def open_file(self):
        path = os.path.expanduser(self.ask("Drag the file here (or type its path)").strip().strip("'\""))
        if not path:
            return
        try:
            if path.lower().endswith(".docx"):
                import docx
                text = "\n\n".join(p.text for p in docx.Document(path).paragraphs if p.text.strip())
            else:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
        except Exception as exc:
            self.tell(f"Couldn't open it: {exc}", "red")
            return
        self.set_text(text.strip("\n"))
        self.tell(f"Opened {os.path.basename(path)}: {len(text.split())} words.", "green")

    # ----- 1 Write: the chat -----
    def chat_lines(self, limit=12):
        if not self.chat:
            return [self.p("Ask Claude to write something, for example:", "grey"),
                    self.p("  “Write a short email asking my boss for Friday off”", "grey"),
                    self.p("  “Help my son answer: why do leaves change colour? Year 5 level”", "grey"),
                    "",
                    self.p("Then /use: it's humanised, checked and ready to type.", "grey")]
        lines = []
        for m in self.chat:
            who = self.p("you › ", "accent", "bold") if m["role"] == "user" else self.p("claude › ", "bold")
            first = True
            for para in m["content"].split("\n"):
                for line in textwrap.wrap(para, self.width - 18) or [""]:
                    lines.append((who if first else " " * (6 if m["role"] == "user" else 9)) + line)
                    first = False
            lines.append("")
        return lines[-limit:]

    def write(self):
        self.header("write")
        self.panel(self.chat_lines(), f"CHAT · {self.ai_status_short()}", 12)
        wf = []
        if self.s["wf_humanise"]:
            wf.append("humanise")
        if self.s["wf_fix"]:
            wf.append("fix")
        self.rule("WRITE", "type a message and press Enter · empty line = back")
        self.say("  " + self.p("/use", "accent", "bold") + self.p(f" → {' + '.join(wf + ['type'])}   ", "grey") +
                 self.p("/paste", "accent", "bold") + self.p(" long message   ", "grey") +
                 self.p("/copy  /new  /1-6", "accent", "bold") + self.p(" jump", "grey"))
        problem = self.ai_problem()
        if problem:
            self.tell(problem, "red")
        self.footer()
        if problem:
            k = self.choose({"enter"})
            return "connect" if k == "enter" else k
        try:
            msg = self.read(self.p("  you › ", "accent", "bold")).strip()
        except EOFError:
            return "quit"
        if not msg:
            return "home"
        cmd = msg.lower()
        if re.fullmatch(r"/[1-6?]", cmd):
            return GLOBAL[cmd[1]]
        if cmd in ("/back", "/b", "/menu", "/home"):
            return "home"
        if cmd == "/new":
            self.chat, self.session = [], None
            self.tell("New chat.", "green")
            return None
        if cmd == "/copy":
            ans = self.last_answer()
            self.tell("Copied." if ans and clipboard_set(ans) else "Nothing copied (no answer, or no clipboard).",
                      "green" if ans else "yellow")
            return None
        if cmd == "/use":
            ans = self.last_answer()
            if not ans:
                self.tell("Ask Claude to write something first.", "yellow")
                return None
            return "type" if self.workflow(ans) else None
        if cmd == "/paste":
            msg = self.read_block("Type or paste your message")
            if not msg.strip():
                return None
        self.send(msg)
        return None

    def send(self, msg):
        self.chat.append({"role": "user", "content": msg})
        self.say("")
        self.say("  " + self.p("claude › ", "bold"), end="")
        got = []

        def piece(t):
            got.append(t)
            self.say(t.replace("\n", "\n  "), end="")
        r = self.ai(self.ht.CHAT_PROMPT, list(self.chat), piece, session=self.session, keep=True)
        if r.get("session"):
            self.session = r["session"]
        reply = "".join(got)
        if not r.get("stopped") and "error" not in r and not reply.strip() and r.get("text"):
            reply = r["text"]
        self.say("")
        if "error" in r and not r.get("stopped"):
            self.chat.pop()
            self.tell(r["error"], "red")
            return
        if reply.strip():
            self.chat.append({"role": "assistant", "content": reply})
            if r.get("stopped"):
                self.tell("Stopped.", "yellow")
        else:
            self.chat.pop()

    def last_answer(self):
        for m in reversed(self.chat):
            if m["role"] == "assistant":
                return m["content"].strip()
        return ""

    # ----- 2 Polish -----
    def polish(self):
        level = self.s["check_level"]
        lname = self.ht.LEVEL_NAMES[level].split(" (")[0].lstrip("+ ")
        k = self.screen("polish", self.text_lines(), self.text_title(), [
            ("h", "Humanise"), ("c", "Check mistakes"), ("i", "AI check"),
            ("a", "Audience/format"), ("f", "Fix all"), ("r", "APA citations"),
            ("n", "Natural tone"), ("l", f"Level ({level})"), ("m", "APA reference"),
            ("e", "Edit text"), ("u", "Undo"), ("enter", "Type it")],
            "polish", f"humanise for {self.audience[2:]} · as {self.format} · check level {level} ({lname})")
        if k in GLOBAL.values():
            return k
        if k == "enter":
            return "type"
        if k == "e":
            new = self.read_block()
            if new.strip():
                self.set_text(new)
            return None
        if k == "u":
            if self.undo:
                self.text = self.undo.pop()
                self.tell("Undone.", "green")
            else:
                self.tell("Nothing to undo.", "yellow")
            return None
        if k == "a":
            self.pick_audience()
            return None
        if k == "l":
            lv = self.ask("Fix level: 1 confusing only · 2 spelling · 3 grammar · 4 punctuation · 5 style", level)
            if lv.isdigit() and 1 <= int(lv) <= 5:
                self.s["check_level"] = int(lv)
                self.save()
            return None
        if k == "m":
            self.apa_reference()
            return None
        if not self.text.strip():
            if k:
                self.tell("There's no text yet. Press e to paste some, or write it in 1 Write.", "yellow")
            return None
        if k == "h":
            new = self.humanise(self.text)
            if new:
                self.set_text(new)
                self.tell("Humanised. Read it over, especially names, numbers and dates. u undoes it.", "green")
        elif k == "c":
            self.check()
        elif k == "f":
            new, n, left = self.fix(self.text)
            self.set_text(new)
            self.tell(f"Fixed {n} mistake{'' if n == 1 else 's'}." +
                      (f" {left} more noticed but above level {level}." if left else "") + " u undoes it.", "green")
        elif k == "i":
            self.ai_check()
        elif k == "r":
            new, changes = self.ht.fix_in_text_citations(self.text)
            if changes:
                self.set_text(new)
                for a, b in changes:
                    self.msg.append(f"{a}  {self.p('→', 'grey')}  {self.p(b, 'green')}")
            self.tell(f"Tidied {len(changes)} citation{'' if len(changes) == 1 else 's'}." if changes else
                      "The citations already look like APA 7 (or there aren't any).", "green")
        elif k == "n":
            new, n = self.ht.naturalize(self.text)
            self.set_text(new)
            self.tell(f"Natural tone: {n} change{'' if n == 1 else 's'}. u undoes it." if n else
                      "Natural tone: nothing needed changing.", "green")
        return None

    def pick_audience(self):
        self.say("  " + "   ".join(f"{self.p(str(i), 'accent')} {a[2:]}" for i, a in enumerate(self.ht.AUDIENCES, 1)))
        a = self.ask("Audience", self.ht.AUDIENCES.index(self.audience) + 1)
        if a.isdigit() and 1 <= int(a) <= len(self.ht.AUDIENCES):
            self.audience = self.ht.AUDIENCES[int(a) - 1]
        self.say("  " + "   ".join(f"{self.p(str(i), 'accent')} {f}" for i, f in enumerate(self.ht.FORMATS, 1)))
        f = self.ask("Format", self.ht.FORMATS.index(self.format) + 1)
        if f.isdigit() and 1 <= int(f) <= len(self.ht.FORMATS):
            self.format = self.ht.FORMATS[int(f) - 1]
        self.save()

    def highlight(self, text, spans):
        """spans: (start, end, colour). Returns the text with those parts coloured ([marked] without colour)."""
        out, pos = [], 0
        for a, b, colour in sorted(spans):
            if a < pos:
                continue
            out += [text[pos:a], self.p(text[a:b], colour) if self.p.on else f"[{text[a:b]}]"]
            pos = b
        out.append(text[pos:])
        return "".join(out)

    def check(self):
        level = self.s["check_level"]
        issues = [d for d in self.ht.check_text(self.text) if d["level"] <= level]
        colours = {1: "hl_red", 2: "hl_red", 3: "hl_orange", 4: "hl_blue", 5: "hl_grey"}
        if not issues:
            self.tell(f"No mistakes found at level {level}.", "green")
            return
        marked = self.highlight(self.text, [(d["start"], d["end"], colours[d["level"]]) for d in issues])
        self.msg += marked.split("\n") + [""]
        for n, d in enumerate(issues, 1):
            if d["suggestion"] is None:
                line = f"⚑ {d['type']}: {d['note']}"
            else:
                line = (f"{d['original']}  {self.p('→', 'grey')}  {self.p(d['suggestion'], 'green')}  " +
                        self.p(f"({d['type']}{', ' + d['note'] if d['note'] else ''})", "grey"))
            self.msg.append(f"{self.p(str(n).rjust(2), 'grey')}  {line}")
        self.tell(f"{len(issues)} to look at. f fixes them all.", "accent")

    def ai_check(self):
        if len(self.text.split()) < 10:
            self.tell("Use a bit more text (a few sentences) for the AI check.", "yellow")
            return
        r = self.ht.ai_report(self.text)
        colour = {"High": "red", "Medium": "yellow", "Low": "green"}[r["verdict"]]
        self.msg.append(f"AI-style score  {self.bar(r['score'] / 100, 20)}  " +
                        self.p(f"{r['score']}/100  {r['verdict']}", colour, "bold"))
        for reason in r["reasons"][:6]:
            self.msg.append("  " + self.p("• " + reason, "grey"))
        spans = [(x["start"], x["end"], "hl_orange" if x["strength"] == 2 else "hl_yellow")
                 for x in r["sentences"] if x["strength"]]
        self.msg += [""] + self.highlight(self.text, spans).split("\n") + [""]
        self.tell("Yellow = some AI habits, orange = many. A hint, not proof: careful writers can score high, "
                  "and edited AI text can score low.")

    def apa_reference(self):
        org = self.yes("Is the author an organisation (not people)?", False)
        authors = self.ask("Organisation name" if org else "Authors (e.g. John Smith; Kate Jones)")
        year = self.ask("Year (blank = n.d.)")
        title = self.ask("Title")
        book = self.yes("Is it a book?", False)
        site = self.ask("Publisher" if book else "Website name")
        url = "" if book else self.ask("Link (URL)")
        self.msg.append("In-text:    " + self.p(self.ht.apa_in_text(authors, year, org), "green"))
        self.msg.append("Reference:  " + self.p(self.ht.apa_reference(authors, year, title, site, url, org,
                                                                      "book" if book else "website"), "green"))
        self.tell("Put the title in italics in your document.")

    # ----- 3 Type -----
    def type_screen(self):
        bg = " · in the background (Word)" if self.s["background"] else ""
        k = self.screen("type", self.text_lines(), self.text_title(), [
            ("enter", "Start typing"), ("+", "Faster (+10)"), ("-", "Slower (−10)"),
            ("y", "Style"), ("d", f"Countdown ({self.s['delay']} s)"), ("g", "Background"),
            ("e", "Edit text")],
            "type", f"{self.status_speed()} · {self.style_name()} · click into your document within "
                    f"{self.s['delay']} s{bg}")
        if k in GLOBAL.values():
            return k
        s = self.s
        if k in ("+", "-"):
            if s["random"]:
                d = 10 if k == "+" else -10
                s["random"] = [max(1, s["random"][0] + d), max(1, s["random"][1] + d)]
            else:
                s["wpm"] = max(5, min(2000, s["wpm"] + (10 if k == "+" else -10)))
            self.save()
        elif k == "y":
            names = list(STYLES)
            cur = self.style_name()
            nxt = names[(names.index(cur) + 1) % len(names)] if cur in names else "Natural"
            s["variation"], s["typos"] = STYLES[nxt]
            s["pauses"] = True
            self.save()
            self.tell(f"Style: {nxt}.", "green")
        elif k == "d":
            v = self.ask("Seconds to click into your document (1-60)", s["delay"])
            if v.isdigit() and 1 <= int(v) <= 60:
                s["delay"] = int(v)
                self.save()
        elif k == "g":
            s["background"] = not s["background"]
            self.save()
            self.tell("Background typing (Word only) is " + ("on." if s["background"] else "off."), "green")
        elif k == "e":
            new = self.read_block()
            if new.strip():
                self.set_text(new)
        elif k == "enter":
            if not self.text.strip():
                self.tell("There's nothing to type yet. Press e to paste it, or write it in 1 Write.", "yellow")
                return None
            self.type_text(self.text)
        return None

    def make_typist(self):
        if self.typist is None:
            try:
                self.typist = self.typist_factory()
            except Exception as exc:
                self.tell("Can't press keys on this computer: " + str(exc), "red")
                return None
        return self.typist

    def plan(self, text):
        words, letters = self.ht.parse_typo_targets(self.s["targets"])
        return self.ht.build_plan(text, variation=self.s["variation"] / 100.0, typo_percent=float(self.s["typos"]),
                                  natural_pauses=self.s["pauses"], typo_words=words, typo_letters=letters,
                                  fix_chosen=self.s["fix_chosen"])

    def type_text(self, text, plan=None, jumps=None, countdown=None, label="Typing"):
        """Type with a countdown and a live progress bar (under the workspace). Ctrl+C stops.
        Returns True when it finished."""
        t = self.make_typist()
        if t is None:
            return False
        bg = self.s["background"]
        if not bg:
            problem = self.ht.mac_permission_problem()
            if problem:
                self.tell(problem, "red")
                return False
        t.wpm = self.s["wpm"]
        t.wpm_range = tuple(self.s["random"]) if self.s["random"] else None
        output = self.ht.WordBackground(pinned=self.s["pin"]) if bg else None
        t.start(text, plan if plan is not None else self.plan(text),
                countdown if countdown is not None else (2 if bg else self.s["delay"]),
                jumps, output=output, corner_stop=not bg)
        listener = self.hotkeys(t) if not bg else None
        stop_hint = "Ctrl+C" + ("" if bg else ", or the mouse to the top-left corner" +
                                ("" if sys.platform == "darwin" else ", or Esc (F8 pauses)"))
        self.say("")
        last = None
        try:
            while t.busy:
                if t.state == "countdown":
                    where = "Word (in the background)" if bg else "your document"
                    line = self.p(f"  ⏱  Click into {where} now… starting in {t.countdown_left}", "yellow", "bold")
                elif t.state == "paused":
                    line = self.p("  ⏸  Paused. Press F8 to carry on (3 s to click back in).", "yellow")
                else:
                    done, total = t.done_chars, max(1, t.total_chars)
                    left = self.ht.seconds_for(" " * (total - done), t.avg_wpm)
                    line = (f"  {label} {self.bar(done / total)} {self.p(f'{int(100 * done / total):3d}%', 'bold')}"
                            f"  {int(t.live_wpm)} WPM · {self.ht.format_duration(left)} left")
                if self.p.on:                     # a real terminal: one line that updates itself
                    self.out.write("\r\033[K" + line)
                    self.out.flush()
                else:                             # a log or a pipe: a new line now and then
                    step = (t.state, t.countdown_left if t.state == "countdown" else
                            4 * t.done_chars // max(1, t.total_chars))
                    if step != last:
                        self.say(line)
                        last = step
                time.sleep(0.1)
        except KeyboardInterrupt:
            t.stop()
            while t.busy:
                time.sleep(0.05)
        finally:
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self.say("")
        if t.state == "done":
            self.tell(f"Finished! {t.total_chars} characters typed.", "green")
            return True
        if t.state == "error":
            self.tell(t.error, "red")
        else:
            self.tell(f"Stopped: {t.done_chars} of {t.total_chars} characters typed. (To stop: {stop_hint}.)",
                      "yellow")
        return False

    def hotkeys(self, t):
        """Esc stops and F8 pauses, even while Word is in front (not on a Mac, where it can crash)."""
        if sys.platform == "darwin":
            return None
        try:
            from pynput import keyboard

            def on_press(key):
                if key == keyboard.Key.esc and t.busy:
                    t.stop()
                elif key == keyboard.Key.f8:
                    t.toggle_pause()
            listener = keyboard.Listener(on_press=on_press)
            listener.daemon = True
            listener.start()
            return listener
        except Exception:
            return None

    # ----- 4 Boxes -----
    def box_lines(self):
        if not self.boxes:
            return [self.p("No boxes yet. p pastes text and splits it, one paragraph per box;", "grey"),
                    self.p("s splits the text you already have.", "grey")]
        lines = []
        for i, b in enumerate(self.boxes, 1):
            mark = self.p("✓", "green") if b["done"] else self.p("○", "grey")
            where = ""
            if self.box_mode == "spot":
                where = self.p(f"  @ {b['spot']}" if b["spot"] else "  (no spot)", "grey")
            elif self.box_mode == "word":
                where = self.p("  → " + b["cell"]["label"] if b["cell"] else "  → skipped", "grey")
            first = b["text"].split("\n")[0]
            room = self.width - 14 - visible_len(where)
            lines.append(f"{mark} {self.p(str(i).rjust(2), 'bold')}  " +
                         (first if len(first) <= room else first[:max(5, room - 1)] + "…") + where)
        return lines

    def boxes_screen(self):
        done = sum(1 for b in self.boxes if b["done"])
        items = [("enter", "Type the boxes"), ("p", "Paste & split"), ("s", "Split my text"),
                 ("m", "Way: " + self.box_mode), ("e", "Edit a box"), ("x", "Remove a box"),
                 ("r", "Start over")]
        if self.box_mode == "spot":
            items.append(("o", "Set the spots"))
        if self.box_mode == "word":
            items += [("w", "Pick a .docx"), ("k", "Change cells")]
        k = self.screen("boxes", self.box_lines(), f"BOXES · {len(self.boxes)} · {done} done", items,
                        "boxes", "getting to each box: " + BOX_MODE_NAMES[self.box_mode], height=8)
        if k in GLOBAL.values():
            return k
        if k in ("p", "s"):
            text = self.read_block() if k == "p" else self.text
            parts = self.ht.split_paragraphs(text)
            self.boxes = [{"text": t, "done": False, "spot": None, "cell": None} for t in parts]
            self.fill_cells()
            self.tell(f"Split into {len(parts)} box{'' if len(parts) == 1 else 'es'}.", "green")
        elif k == "e":
            n = self.ask("Which box?")
            if n.isdigit() and 1 <= int(n) <= len(self.boxes):
                new = self.read_block(f"New text for box {n}")
                if new.strip():
                    self.boxes[int(n) - 1]["text"] = new
        elif k == "x":
            n = self.ask("Remove which box?")
            if n.isdigit() and 1 <= int(n) <= len(self.boxes):
                del self.boxes[int(n) - 1]
        elif k == "r":
            for b in self.boxes:
                b["done"] = False
        elif k == "m":
            self.box_mode = BOX_MODES[(BOX_MODES.index(self.box_mode) + 1) % len(BOX_MODES)]
            self.tell("Getting to each box: " + BOX_MODE_NAMES[self.box_mode] + ".", "green")
            if self.box_mode == "spot" and self.boxes and not any(b["spot"] for b in self.boxes):
                self.tell("Press o to point at each box's spot.", "accent")
            if self.box_mode == "word" and not self.doc:
                self.tell("Press w to pick your .docx.", "accent")
        elif k == "o":
            self.set_spots()
        elif k == "w":
            self.connect_doc()
        elif k == "k":
            self.pick_cells()
        elif k == "enter":
            self.type_boxes()
        return None

    def set_spots(self):
        t = self.make_typist()
        if t is None or not self.boxes:
            return
        self.note("For each box: point the mouse at where it should be typed (don't click), then press Enter here. "
                  "Don't move the window or scroll afterwards.", "accent")
        for i, b in enumerate(self.boxes, 1):
            self.read(f"  Box {i}: point at its spot, then press Enter ")
            try:
                b["spot"] = tuple(int(v) for v in t.mouse.position)
            except Exception as exc:
                self.tell(f"Couldn't read the mouse position: {exc}", "red")
                return
        self.tell(f"Spots set for {len(self.boxes)} boxes.", "green")

    def connect_doc(self):
        path = self.ask("Drag your .docx file here (or type its path)").strip().strip("'\"")
        if not path:
            return
        try:
            cells = self.ht.read_word_cells(os.path.expanduser(path))
        except Exception as exc:
            self.tell(f"Couldn't read that document: {exc}", "red")
            return
        if not cells:
            self.tell("That document has no tables. Use m to pick another way.", "yellow")
            return
        self.doc = {"path": os.path.abspath(os.path.expanduser(path)), "cells": cells}
        self.box_mode = "word"
        self.fill_cells()
        try:
            self.ht.open_in_word(self.doc["path"])
        except Exception:
            pass
        self.tell(f"Connected: {len(cells)} cells. Each box goes into the next empty cell; k changes them.", "green")

    def fill_cells(self):
        if not self.doc:
            return
        empty = [c for c in self.doc["cells"] if not c["text"]] + [c for c in self.doc["cells"] if c["text"]]
        for b, c in zip(self.boxes, empty):
            b["cell"] = c
        for b in self.boxes[len(empty):]:
            b["cell"] = None

    def pick_cells(self):
        if not self.doc:
            self.tell("Pick a .docx first (w).", "yellow")
            return
        for n, c in enumerate(self.doc["cells"], 1):
            self.say(f"   {self.p(str(n).rjust(3), 'accent')}  {c['label']}")
        for i, b in enumerate(self.boxes, 1):
            cur = self.doc["cells"].index(b["cell"]) + 1 if b["cell"] else 0
            a = self.ask(f"Box {i} goes in cell (0 = skip)", cur)
            if a.isdigit():
                k = int(a)
                b["cell"] = self.doc["cells"][k - 1] if 1 <= k <= len(self.doc["cells"]) else None

    def type_boxes(self):
        todo = [b for b in self.boxes if b["text"].strip() and not b["done"]]
        if not todo:
            self.tell("Nothing to type: p adds boxes, r starts over.", "yellow")
            return
        if self.s["background"] and self.box_mode != "word":
            self.tell("Background typing only works with Word cells. Turn it off with g on 3 Type.", "yellow")
            return
        if self.box_mode == "click":
            for b in todo:
                n = self.boxes.index(b) + 1
                self.note(f"Box {n} of {len(self.boxes)}: press Enter, then click into its spot.", "accent")
                if self.keys:
                    self.out.write(f"  {self.p('›', 'accent', 'bold')} " + self.p("Enter = go · Esc = stop ", "grey"))
                    self.out.flush()
                    stop = self.keys() in ("esc", "s", "b")
                    self.say("")
                else:
                    stop = self.ask("Enter = go, s = stop").lower().startswith("s")
                if stop or not self.type_text(b["text"], label=f"Box {n}"):
                    return
                b["done"] = True
            self.tell("Every box is done.", "green")
            return
        if self.box_mode == "tab":
            self.note("Click into the first cell of the table during the countdown.", "accent")
            if self.type_text("\t".join(b["text"].replace("\t", " ") for b in todo)):
                for b in todo:
                    b["done"] = True
            return
        t = self.make_typist()
        if t is None:
            return
        plan, jumps, texts = [], {}, []
        for b in todo:
            text = b["text"]
            if self.box_mode == "spot":
                if not b["spot"]:
                    continue
                click = (lambda xy=b["spot"]: t.click_at(*xy))
                click.again_after_pause = False
                jumps[len(plan)] = click
            else:
                c = b["cell"]
                if not c:
                    continue
                text = text.replace("\t", " ")
                if c["text"]:
                    text = (" " if c["text"].endswith(":") else "\n") + text
                front = not self.s["background"]
                jumps[len(plan)] = (lambda c=c: self.ht.word_jump(self.doc["path"], c["table"], c["row"], c["col"],
                                                                  front=front))
            plan += self.plan(text)
            texts.append(text)
        if not texts:
            self.tell("No box has a " + ("spot (press o)" if self.box_mode == "spot" else "Word cell (press w)") +
                      " yet.", "yellow")
            return
        self.note("Hands off the keyboard and mouse until it's done.", "accent")
        if self.type_text("".join(texts), plan=plan, jumps=jumps, countdown=3 if self.box_mode == "spot" else 2):
            for b in todo:
                b["done"] = True

    # ----- 5 Settings -----
    def settings(self):
        s = self.s
        on = lambda v: self.p("on", "green") if v else self.p("off", "grey")
        rows = [("Speed", f"{s['wpm']} WPM"), ("Random speed", f"{s['random'][0]}–{s['random'][1]} WPM"
                                                if s["random"] else "off"),
                ("Style", self.style_name()), ("Rhythm", f"{s['variation']}  (how uneven, 0-100)"),
                ("Typos", f"{s['typos']:g} %  (made and fixed)"), ("Pauses", on(s["pauses"])),
                ("Always wrong", (s["targets"] or "—") + (f"  (fixed: {'yes' if s['fix_chosen'] else 'no'})"
                                                         if s["targets"] else "")),
                ("Countdown", f"{s['delay']} s"),
                ("Background", on(s["background"]) + (f"  (pin: {'on' if s['pin'] else 'off'})" if s["background"]
                                                      else "")),
                ("After /use", f"humanise {on(s['wf_humanise'])} · fix {on(s['wf_fix'])}")]
        lines = [self.p(name.ljust(14), "grey") + value for name, value in rows]
        k = self.screen("settings", lines, "SETTINGS · saved for next time", [
            ("w", "Speed"), ("r", "Random speed"), ("y", "Style"),
            ("h", "Rhythm"), ("t", "Typos"), ("p", "Pauses"),
            ("a", "Always wrong"), ("d", "Countdown"), ("g", "Background"),
            ("u", "After /use")], "settings", "pick one to change it", height=10)
        if k in GLOBAL.values():
            return k
        if k == "w":
            v = self.ask("Words per minute (1-2000; 25 slow · 40 average · 60 good · 90 fast · 120 pro)", s["wpm"])
            if v.isdigit() and 1 <= int(v) <= 2000:
                s["wpm"] = int(v)
        elif k == "r":
            v = self.ask("Two speeds like 40-90, or 'off'", "off")
            m = re.match(r"\s*(\d+)\s*[-–to ]+\s*(\d+)", v)
            s["random"] = sorted([int(m.group(1)), int(m.group(2))]) if m else None
        elif k == "y":
            v = self.ask("Careful, Natural or Messy", self.style_name()).strip().title()
            if v in STYLES:
                s["variation"], s["typos"] = STYLES[v]
                s["pauses"] = True
        elif k == "h":
            v = self.ask("Rhythm 0-100", s["variation"])
            if v.isdigit() and 0 <= int(v) <= 100:
                s["variation"] = int(v)
        elif k == "t":
            try:
                s["typos"] = round(max(0.0, min(8.0, float(self.ask("Typos % (0-8)", s["typos"])))), 1)
            except ValueError:
                pass
        elif k == "p":
            s["pauses"] = not s["pauses"]
        elif k == "a":
            s["targets"] = self.ask("Words and letters to always get wrong, e.g. the, because, e", s["targets"])
            s["fix_chosen"] = self.yes("Fix them after (like normal typos)?", s["fix_chosen"])
        elif k == "d":
            v = self.ask("Seconds (1-60)", s["delay"])
            if v.isdigit() and 1 <= int(v) <= 60:
                s["delay"] = int(v)
        elif k == "g":
            s["background"] = self.yes("Type into Word in the background?", s["background"])
            if s["background"]:
                s["pin"] = self.yes("Pin it to one spot in Word?", s["pin"])
        elif k == "u":
            s["wf_humanise"] = self.yes("After /use: humanise it?", s["wf_humanise"])
            s["wf_fix"] = self.yes("After /use: fix mistakes?", s["wf_fix"])
        self.save()
        return None

    # ----- 6 Connect -----
    def connect(self):
        ht = self.ht
        if self._account is None:
            self._account = ht.claude_account_status()
        acct = self._account
        try:
            with open(ht.claude_config_path(), encoding="utf-8") as fh:
                linked = "human-typer" in (json.load(fh).get("mcpServers") or {})
        except Exception:
            linked = False
        use = lambda e: self.p("● ", "accent") if self.engine == e else self.p("○ ", "grey")
        lines = [
            use("account") + self.p("My Claude account", "bold") + self.p("   recommended · your Pro/Max plan", "grey"),
            "    " + self.p(acct["text"], "green" if acct.get("logged_in") else "yellow"),
            use("claude") + self.p("A Claude API key", "bold") + self.p("    pay per use · ", "grey") +
            (self.p("key saved ✓", "green") if self.key() else self.p("no key yet", "grey")),
            use("local") + self.p("A local AI", "bold") + self.p(f"          free, offline · model: {self.model or 'none'}",
                                                                 "grey"),
            "",
            self.p("Claude app", "bold") + self.p("          types from the Claude desktop app · ", "grey") +
            (self.p("connected ✓", "green") if linked else self.p("not connected", "grey")),
        ]
        k = self.screen("connect", lines, "CONNECT CLAUDE", [
            ("a", "Use my account"), ("i", "Install Claude Code"), ("l", "Log in"),
            ("k", "Use an API key"), ("m", "Use a local AI"), ("r", "Check again"),
            ("c", "Connect Claude app"), ("d", "Disconnect it")], "connect", "● = the one in use", height=6)
        if k in GLOBAL.values():
            self.save()
            return k
        if k == "a":
            self.engine, self.session = "account", None
        elif k == "r":
            self._account = None
        elif k == "i":
            cmd = ht.CLAUDE_INSTALL["win" if sys.platform == "win32" else "unix"]
            self.note("This runs Anthropic's installer for Claude Code here:  " + cmd, "accent")
            if self.yes("Run it now?"):
                run = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
                       if sys.platform == "win32" else ["bash", "-c", cmd])
                subprocess.run(run)
                self._account = None
                self.engine = "account"
                self.tell("Installed. Now press l to log in.", "accent")
        elif k == "l":
            exe = ht.find_claude_cli()
            if not exe:
                self.tell("Install Claude Code first (i).", "yellow")
            else:
                self.note("Log in with your Claude account in the browser that opens, then come back here.", "accent")
                subprocess.run([exe, "auth", "login"], env=ht._claude_env(exe))
                self._account = None
                self.engine = "account"
        elif k == "k":
            if not self.key() or self.yes("Change the saved key?", False):
                key = self.secret("Paste your Claude API key (sk-ant-…), or leave blank to remove it:").strip()
                cfg = ht.load_config()
                if key:
                    cfg["claude_api_key"] = key
                else:
                    cfg.pop("claude_api_key", None)
                ht.save_config(cfg)
                self.tell("Key saved (only on this computer)." if key else "Key removed.", "green")
            if self.key():
                self.engine, self.session = "claude", None
        elif k == "m":
            try:
                models = ht.ollama_models()
            except Exception as exc:
                self.tell(str(exc).replace("\n\n", " ").replace("\n", " "), "red")
                models = None
            if models == []:
                self.tell("Ollama has no models yet. In a terminal run:  ollama pull llama3.2", "yellow")
            elif models:
                self.say("  " + "   ".join(f"{self.p(str(n), 'accent')} {m}" for n, m in enumerate(models, 1)))
                a = self.ask("Model", (models.index(self.model) + 1) if self.model in models else 1)
                if a.isdigit() and 1 <= int(a) <= len(models):
                    self.model = models[int(a) - 1]
                    self.engine, self.session = "local", None
        elif k in ("c", "d"):
            try:
                path = ht.connect_claude(remove=k == "d")
                self.tell(("Disconnected." if k == "d" else "Connected!") + " Quit the Claude app completely and open "
                          "it again." + ("" if k == "d" else " Then say: “type it with Human Typer at 60 "
                                                             "WPM”."), "green")
                self.tell(f"(Settings file: {path})")
            except Exception as exc:
                self.tell(f"Couldn't update the Claude app's settings: {exc}", "red")
        self.save()
        return None

    # ----- ? Help -----
    def help(self):
        steps = [
            ("1 Write", "Chat with Claude. /use sends the answer on: humanised, checked, ready on 3 Type."),
            ("2 Polish", "h humanise · c check · f fix · i AI check · r/m APA. u undoes."),
            ("3 Type", "Enter starts; click into your document during the countdown. + − speed, y style."),
            ("4 Boxes", "One paragraph per box: click each, auto-click spots, Tab through a table, Word cells."),
            ("5 Settings", "Speed, style, typos, countdown, background. Saved for next time."),
            ("6 Connect", "Your Claude account (install + log in, about a minute), an API key, or a local AI."),
            ("Keys", "1-6 jump anywhere · Esc home · q quit · Ctrl+C stops a reply, a rewrite or typing."),
            ("Stop typing", "Ctrl+C, or the mouse to the top-left corner of the screen" +
                            ("." if sys.platform == "darwin" else ", or Esc. F8 pauses.")),
            ("Look real", "Careful, Natural or Messy: bursts, slow reaches, real mistakes it fixes. "
                          "The finished text is always right."),
        ]
        lines = []
        for title, body in steps:
            wrapped = textwrap.wrap(body, self.width - 22)
            lines.append(self.p(title.ljust(13), "accent", "bold") + wrapped[0])
            lines += [" " * 13 + more for more in wrapped[1:]]
        k = self.screen("help", lines, "HOW IT WORKS", [("enter", "Home")], "help",
                        "quick commands: human_typer_cli.py --help", height=len(lines))
        return "home" if k == "enter" else k


COMMANDS = {
    "type": "type FILE (or - for what's piped in) into your document, after the countdown",
    "check": "list the mistakes in FILE (up to --level)",
    "fix": "print FILE with its mistakes fixed (up to --level)",
    "humanise": "print FILE rewritten to sound natural (--audience, --format)",
    "ai-check": "print FILE's AI-style score, the reasons and the most AI-like sentences",
    "ask": "ask Claude (the words after it), print the answer",
    "write": "ask Claude, then humanise, fix and type the answer: the whole workflow in one go",
}


def parse(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog="human_typer_cli.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Human Typer in the terminal. With no command it opens the menus.",
        epilog="commands:\n" + "\n".join(f"  {k:<10} {v}" for k, v in COMMANDS.items()) +
        "\n\nexamples:\n  human_typer_cli.py type notes.txt --wpm 70 --style Messy\n"
        "  human_typer_cli.py ask \"a short email asking for Friday off\" | human_typer_cli.py fix -\n"
        "  human_typer_cli.py write \"a thank-you note for my son's teacher\" --audience 2")
    ap.add_argument("command", nargs="?", choices=list(COMMANDS), metavar="command")
    ap.add_argument("what", nargs="*", help="a file, - for what's piped in, or (for ask/write) your request")
    ap.add_argument("--wpm", type=int, help="typing speed, words per minute")
    ap.add_argument("--random", metavar="LO-HI", help="a speed that wanders between two, e.g. 40-90")
    ap.add_argument("--style", choices=list(STYLES), type=str.title, help="how human the typing looks")
    ap.add_argument("--typos", type=float, help="typos it makes and fixes, %% (0-8)")
    ap.add_argument("--delay", type=int, help="seconds to click into your document first")
    ap.add_argument("--background", action="store_true", help="type into Word in the background")
    ap.add_argument("--level", type=int, choices=range(1, 6), metavar="1-5", help="how much check/fix covers")
    ap.add_argument("--audience", type=int, choices=range(1, 6), metavar="1-5",
                    help="1 Year 8, 2 General, 3 Team, 4 Executive, 5 Finance")
    ap.add_argument("--format", choices=["original", "notes", "slides", "speaker"], help="shape of a rewrite")
    ap.add_argument("--no-humanise", action="store_true", help="write: skip humanising")
    ap.add_argument("--yes", "-y", action="store_true", help="write: type without asking first")
    ap.add_argument("--no-color", action="store_true", help="plain text, no colours")
    return ap.parse_args(argv)


def quick(app, args):
    """Run one command with no menus. Returns the exit code."""
    ht, s = app.ht, app.s
    if args.wpm:
        s["wpm"] = max(1, min(2000, args.wpm))
    if args.random:
        m = re.match(r"\s*(\d+)\s*[-–]\s*(\d+)", args.random)
        s["random"] = sorted([int(m.group(1)), int(m.group(2))]) if m else None
    if args.style:
        s["variation"], s["typos"] = STYLES[args.style]
    if args.typos is not None:
        s["typos"] = max(0.0, min(8.0, args.typos))
    if args.delay:
        s["delay"] = args.delay
    if args.background:
        s["background"] = True
    if args.level:
        s["check_level"] = args.level
    if args.audience:
        app.audience = ht.AUDIENCES[args.audience - 1]
    if args.format:
        app.format = {"original": ht.FORMATS[0], "notes": ht.FORMATS[1], "slides": ht.FORMATS[2],
                      "speaker": ht.FORMATS[3]}[args.format]

    def source():
        what = " ".join(args.what)
        if not what or what == "-":
            return sys.stdin.read().strip("\n")
        path = os.path.expanduser(what)
        if os.path.isfile(path):
            if path.lower().endswith(".docx"):
                import docx
                return "\n\n".join(p.text for p in docx.Document(path).paragraphs if p.text.strip())
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read().strip("\n")
        return what                                  # the words themselves

    def fail(msg):
        sys.stderr.write("human typer: " + msg + "\n")
        return 1

    cmd = args.command
    if cmd in ("ask", "write"):
        request = " ".join(args.what) if args.what and args.what != ["-"] else sys.stdin.read().strip()
        if not request:
            return fail("say what Claude should write, e.g.  ask \"a short email asking for Friday off\"")
        problem = app.ai_problem()
        if problem:
            return fail(problem)
        loud = cmd == "write"
        pieces = []

        def piece(t):
            pieces.append(t)
            if loud:
                app.say(t, end="")
        r = app.ai(ht.CHAT_PROMPT, [{"role": "user", "content": request}], piece)
        if "error" in r:
            return fail(r["error"])
        text = ("".join(pieces) or r.get("text") or "").strip()
        if cmd == "ask":
            print(text)
            return 0
        app.say("\n")
        app.s["wf_humanise"] = not args.no_humanise
        app.s["wf_fix"] = True
        ok = app.workflow(text)
        app.flush_msg()
        if not ok:
            return 1
        if args.yes or app.yes("Type it now?"):
            ok = app.type_text(app.text)
            app.flush_msg()
            return 0 if ok else 1
        return 0

    text = source()
    if not text.strip():
        return fail(f"there's no text to {cmd}. Give a file, or pipe text in with -")
    if cmd == "type":
        app.text = text
        ok = app.type_text(text)
        app.flush_msg()
        return 0 if ok else 1
    if cmd == "fix":
        print(app.fix(text)[0])
        return 0
    if cmd == "check":
        app.text = text
        app.check()
        app.flush_msg()
        return 0
    if cmd == "humanise":
        new = app.humanise(text) if sys.stdout.isatty() else None
        app.flush_msg()
        if not sys.stdout.isatty():                  # piped: print only the result
            problem = app.ai_problem()
            if problem:
                return fail(problem)
            r = app.ai(ht.HUMANISER_PROMPT, [{"role": "user", "content": ht.humaniser_request(
                text, app.audience, app.format)}], lambda t: None)
            if "error" in r:
                return fail(r["error"])
            new = (r.get("text") or "").strip()
            print(new)
        return 0 if new else 1
    if cmd == "ai-check":
        app.text = text
        app.ai_check()
        app.flush_msg()
        return 0
    return 2


def main(ht=None, argv=None):
    if ht is None:
        import human_typer as ht
    argv = sys.argv[1:] if argv is None else argv
    argv = [a for a in argv if a != "--cli"]
    if sys.platform == "win32":
        os.system("")                     # lets Windows terminals show colours
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = parse(argv)
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    app = CLI(ht, colour=False if args.no_color else None, keys=getkey if interactive else None)
    if args.command:
        try:
            sys.exit(quick(app, args))
        except KeyboardInterrupt:
            sys.exit(130)
    try:
        app.run()
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
