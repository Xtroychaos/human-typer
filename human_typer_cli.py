#!/usr/bin/env python3
"""
Human Typer in the terminal: the same Write -> Polish -> Type as the window,
as simple menus.

    python human_typer_cli.py          (or: python human_typer.py --cli)

Every screen has a short menu: type the letter or number in [ ] and press Enter.
The text you're working on carries from one step to the next, like the tabs in
the window app. Ctrl+C stops whatever is happening (a reply, a rewrite, typing)
and goes back a step.
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

class CLI:
    def __init__(self, ht, read=input, out=None, secret=None, typist_factory=None, colour=None):
        self.ht = ht
        self.read_fn = read
        self.out = out or sys.stdout
        self.secret_fn = secret
        self.p = Paint(colours_wanted(self.out) if colour is None else colour)
        self.typist_factory = typist_factory or ht.Typist
        self.typist = None
        cfg = ht.load_config()
        self.s = dict(DEFAULTS, **cfg.get("cli", {}))
        engine = cfg.get("engine", "account")
        self.engine = engine if engine in ("account", "claude", "local") else "account"
        self.model = cfg.get("ollama_model", "")
        self.audience = cfg.get("audience", ht.AUDIENCES[2])
        self.format = cfg.get("format", ht.FORMATS[0])
        self.text = ""
        self.undo = []                 # earlier versions of the text (Polish)
        self.boxes = []                # {"text", "done", "spot", "cell"}
        self.box_mode = "click"
        self.doc = None                # a connected Word document: {"path", "cells"}
        self.chat = []                 # the conversation
        self.session = None            # Claude account: the conversation to carry on

    # ----- basics -----
    @property
    def width(self):
        return max(50, min(78, shutil.get_terminal_size((80, 24)).columns - 2))

    def say(self, text="", end="\n"):
        self.out.write(text + end)
        self.out.flush()

    def read(self, prompt=""):
        return self.read_fn(prompt)

    def ask(self, label, default=None):
        hint = self.p(f" [{default}]", "grey") if default not in (None, "") else ""
        answer = self.read(f"  {self.p('›', 'accent', 'bold')} {label}{hint} ").strip()
        return answer if answer else ("" if default is None else str(default))

    def yes(self, label, default=True):
        answer = self.ask(label + (" (Y/n)" if default else " (y/N)")).lower()
        return default if not answer else answer.startswith("y")

    def secret(self, label):
        if self.secret_fn:
            return self.secret_fn(label)
        import getpass
        return getpass.getpass(f"  › {label} ")

    def clear(self):
        if self.p.on:
            self.out.write("\033[2J\033[H")

    def note(self, text, kind="grey"):
        icon = {"green": "✓", "red": "✗", "yellow": "!", "grey": "·", "accent": "›"}.get(kind, "·")
        for i, line in enumerate(textwrap.wrap(text, self.width - 6) or [""]):
            self.say("  " + self.p((icon if i == 0 else " ") + " " + line, kind))

    def pause(self):
        self.read(self.p("  press Enter to go on ", "grey"))

    def rule(self, title=""):
        w = self.width
        if title:
            self.say("  " + self.p(title, "bold") + " " + self.p("─" * max(2, w - len(title) - 3), "grey"))
        else:
            self.say("  " + self.p("─" * (w - 2), "grey"))

    def box(self, lines, title=""):
        """A rounded box around some lines, with an optional title in the top edge."""
        w = self.width - 2
        if title:
            t = f" {title} "
            self.say("  " + self.p("╭─", "grey") + self.p(t, "accent", "bold") +
                     self.p("─" * max(0, w - len(t) - 3) + "╮", "grey"))
        else:
            self.say("  " + self.p("╭" + "─" * (w - 2) + "╮", "grey"))
        for line in lines:
            pad = max(0, w - 4 - visible_len(line))
            self.say("  " + self.p("│", "grey") + " " + line + " " * pad + " " + self.p("│", "grey"))
        self.say("  " + self.p("╰" + "─" * (w - 2) + "╯", "grey"))

    def bar(self, fraction, width=28):
        fraction = max(0.0, min(1.0, fraction))
        full = int(round(width * fraction))
        return self.p("█" * full, "accent") + self.p("░" * (width - full), "grey")

    def header(self, step=None):
        self.clear()
        w = self.width
        title = self.p(" ⌨  " + APP + " ", "bold", "white", "accent_bg")
        tag = self.p("terminal", "grey")
        self.say("")
        self.say("  " + title + " " * max(1, w - visible_len(title) - 10) + tag)
        steps = []
        for n, name in ((1, "Write"), (2, "Polish"), (3, "Type")):
            label = f"{n} {name}"
            steps.append(self.p(label, "accent", "bold", "under") if step == n else self.p(label, "grey"))
        self.say("  " + self.p("  ›  ", "grey").join(steps))
        self.say("")

    def status_line(self):
        words = len(self.text.split())
        ai = self.ai_status_short()
        parts = [self.p(f"{words} word{'' if words == 1 else 's'}", "bold"), self.status_speed(), self.style_name(),
                 self.p(ai, "green" if "✓" in ai else "yellow")]
        self.box(["  " + self.p("  ·  ", "grey").join(parts)], "now")

    def menu(self, items, prompt="choose"):
        """items: (key, label, detail) or None for a gap. Returns the key typed (lower case)."""
        for item in items:
            if item is None:
                self.say("")
                continue
            key, label, detail = item
            if key is None:                       # a group heading
                self.say("   " + self.p(label.upper(), "grey", "bold"))
                continue
            k = self.p(f"[{key}]", "accent", "bold")
            self.say(f"   {k} {label:<16}" + (self.p(detail, "grey") if detail else ""))
        self.say("")
        return self.ask(prompt).lower()

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

    def show_text(self, text=None, limit=10):
        text = self.text if text is None else text
        if not text.strip():
            self.note("No text yet.")
            return
        lines = []
        for para in text.split("\n"):
            lines += textwrap.wrap(para, self.width - 8) or [""]
        shown = lines[:limit]
        if len(lines) > limit:
            shown.append(self.p(f"… and {len(lines) - limit} more lines", "grey"))
        self.box(shown, f"{len(text.split())} words")

    def read_block(self, label="Paste or type your text"):
        self.note(label + ". When you're done, type a line with just a full stop ( . ) and press Enter.", "accent")
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

    def set_text(self, text, remember=True):
        if remember and self.text and text != self.text:
            self.undo.append(self.text)
            del self.undo[:-20]
        self.text = text

    # ----- talking to the AI -----
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
            return self.ht.CLAUDE_SETUP_HELP.replace("Connect Claude…", "[6] Connect Claude")
        if self.engine == "claude" and not self.key():
            return "Add your Claude API key first: [6] Connect Claude → [k]."
        if self.engine == "local" and not self.model:
            return "Pick a local AI model first: [6] Connect Claude → [m]."
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

    def humanise(self, text):
        """Rewrite text with the Humaniser, showing it as it's written. Returns the new text or None."""
        problem = self.ai_problem()
        if problem:
            self.note(problem, "red")
            return None
        self.note(f"Humanising for {self.audience[2:]}, as {self.format}… (Ctrl+C stops)", "accent")
        self.say("")
        self.say("  ", end="")
        r = self.ai(self.ht.HUMANISER_PROMPT,
                    [{"role": "user", "content": self.ht.humaniser_request(text, self.audience, self.format)}],
                    lambda piece: self.say(piece.replace("\n", "\n  "), end=""))
        self.say("\n")
        if r.get("stopped"):
            self.note("Stopped. Your text wasn't changed.", "yellow")
            return None
        if "error" in r:
            self.note(r["error"], "red")
            return None
        return (r.get("text") or "").strip() or None

    def fix(self, text, level=None):
        level = level or self.s["check_level"]
        new, fixed, left = self.ht.apply_fixes(text, self.ht.check_text(text), level)
        return new, len(fixed), left

    # ----- main menu -----
    def run(self):
        while True:
            self.header()
            self.status_line()
            self.say("")
            choice = self.menu([
                (None, "Workflow", ""),
                ("1", "Write", "chat with Claude: it writes it for you"),
                ("2", "Polish", "humanise · check mistakes · AI check · APA"),
                ("3", "Type", "type the text into your document"),
                ("4", "Boxes", "one paragraph per box (worksheets, tables)"),
                None,
                (None, "Tools", ""),
                ("t", "Text", "see, paste, open or copy the text"),
                ("5", "Settings", "speed · style · typos · countdown"),
                ("6", "Connect", "Claude account · API key · local AI · Claude app"),
                ("?", "Help", "how it all works"),
                ("q", "Quit", ""),
            ])
            try:
                if choice in ("q", "quit", "exit"):
                    self.save()
                    self.say(self.p("  Bye!", "grey"))
                    return
                action = {"1": self.write, "2": self.polish, "3": self.type_screen, "4": self.boxes_screen,
                          "t": self.text_screen, "5": self.settings, "6": self.connect, "?": self.help,
                          "h": self.help}.get(choice)
                if action:
                    action()
            except KeyboardInterrupt:
                self.say("")

    # ----- 1 Write -----
    def write(self):
        self.header(1)
        self.rule("Write with Claude")
        self.note(f"Using: {self.ai_status_short()}")
        problem = self.ai_problem()
        if problem:
            self.note(problem, "red")
            if self.yes("Open Connect Claude now?"):
                self.connect()
            return
        self.say("")
        self.note("Type a message and press Enter. Ctrl+C stops a reply.")
        self.say("  " + self.p("/use", "accent") + self.p("  send the last answer on (humanise, fix, type)", "grey"))
        self.say("  " + self.p("/paste", "accent") + self.p("  a long message over several lines", "grey"))
        self.say("  " + self.p("/copy  /new  /back", "accent") + self.p("  copy the answer · new chat · main menu", "grey"))
        for m in self.chat:
            self.show_message(m["role"], m["content"])
        while True:
            self.say("")
            try:
                msg = self.read(self.p("  you › ", "accent", "bold")).strip()
            except EOFError:
                return
            if not msg:
                continue
            cmd = msg.lower()
            if cmd in ("/back", "/b", "/q", "/menu"):
                return
            if cmd == "/new":
                self.chat, self.session = [], None
                self.note("New chat.", "green")
                continue
            if cmd == "/copy":
                ans = self.last_answer()
                self.note("Copied." if ans and clipboard_set(ans) else "Nothing copied (no answer, or no clipboard).",
                          "green" if ans else "yellow")
                continue
            if cmd == "/use":
                if self.workflow():
                    return
                continue
            if cmd == "/paste":
                msg = self.read_block("Type or paste your message")
                if not msg.strip():
                    continue
            self.send(msg)

    def show_message(self, role, text):
        who = self.p("you › ", "accent", "bold") if role == "user" else self.p("claude › ", "bold")
        self.say("")
        self.say("  " + who + text.replace("\n", "\n  "))

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
            self.say(reply.replace("\n", "\n  "), end="")
        self.say("")
        if "error" in r and not r.get("stopped"):
            self.chat.pop()
            self.note(r["error"], "red")
            return
        if reply.strip():
            self.chat.append({"role": "assistant", "content": reply})
            if r.get("stopped"):
                self.note("Stopped.", "yellow")
        else:
            self.chat.pop()

    def last_answer(self):
        for m in reversed(self.chat):
            if m["role"] == "assistant":
                return m["content"].strip()
        return ""

    def workflow(self):
        """Claude's last answer -> humanise -> fix -> ready to type. True if it went on to Type."""
        text = self.last_answer()
        if not text:
            self.note("Ask Claude to write something first.", "yellow")
            return False
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
        self.note("Ready to type" + (f" ({', '.join(done)})" if done else "") + ".", "green")
        if self.yes("Type it now?"):
            self.type_screen()
            return True
        return False

    # ----- 2 Polish -----
    def polish(self):
        while True:
            self.header(2)
            self.rule("Polish")
            self.show_text(limit=8)
            self.say("")
            level = self.s["check_level"]
            choice = self.menu([
                ("h", "Humanise", f"for {self.audience[2:]}, as {self.format}"),
                ("a", "Audience", "who it's for, and what shape (format)"),
                None,
                ("c", "Check", f"find mistakes (level {level}: {self.ht.LEVEL_NAMES[level].split(' (')[0]})"),
                ("f", "Fix all", f"fix every mistake up to level {level}"),
                ("l", "Level", "how much Check fixes, 1-5"),
                ("i", "AI check", "how much it reads like AI writing (a hint, not proof)"),
                ("r", "APA citations", "tidy the in-text references"),
                ("m", "APA reference", "make a reference for a source"),
                ("n", "Natural tone", "quick offline tidy: contractions, plain words"),
                None,
                ("e", "Edit text", "paste or type new text"),
                ("u", "Undo", "back to the version before the last change"),
                ("t", "Type it", "go to 3 Type"),
                ("b", "Back", ""),
            ])
            if choice in ("b", ""):
                return
            if choice == "t":
                self.type_screen()
                return
            if choice == "e":
                new = self.read_block()
                if new.strip():
                    self.set_text(new)
                continue
            if choice == "u":
                if self.undo:
                    self.text = self.undo.pop()
                    self.note("Undone.", "green")
                else:
                    self.note("Nothing to undo.", "yellow")
                self.pause()
                continue
            if choice == "a":
                self.pick_audience()
                continue
            if choice == "l":
                lv = self.ask("Fix level 1-5", level)
                if lv.isdigit() and 1 <= int(lv) <= 5:
                    self.s["check_level"] = int(lv)
                    self.save()
                continue
            if not self.text.strip():
                self.note("There's no text yet. Press [e] to paste some, or write it in 1 Write.", "yellow")
                self.pause()
                continue
            if choice == "h":
                new = self.humanise(self.text)
                if new:
                    self.set_text(new)
                    self.note("Done. Read it over, especially names, numbers and dates. [u] undoes it.", "green")
            elif choice == "c":
                self.check()
            elif choice == "f":
                new, n, left = self.fix(self.text)
                self.set_text(new)
                self.note(f"Fixed {n} mistake{'' if n == 1 else 's'}." +
                          (f" {left} more noticed but above level {level}." if left else ""), "green")
            elif choice == "i":
                self.ai_check()
            elif choice == "r":
                new, changes = self.ht.fix_in_text_citations(self.text)
                if changes:
                    self.set_text(new)
                    for a, b in changes:
                        self.say(f"    {a}  {self.p('→', 'grey')}  {self.p(b, 'green')}")
                self.note(f"Tidied {len(changes)} citation{'' if len(changes) == 1 else 's'}." if changes else
                          "The citations already look like APA 7 (or there aren't any).", "green")
            elif choice == "m":
                self.apa_reference()
            elif choice == "n":
                new, n = self.ht.naturalize(self.text)
                self.set_text(new)
                self.note(f"{n} change{'' if n == 1 else 's'}. [u] undoes it." if n else "Nothing needed changing.",
                          "green")
            else:
                continue
            self.pause()

    def pick_audience(self):
        for i, a in enumerate(self.ht.AUDIENCES, 1):
            self.say(f"   {self.p(f'[{i}]', 'accent')} {a[2:]}")
        a = self.ask("Audience", self.ht.AUDIENCES.index(self.audience) + 1)
        if a.isdigit() and 1 <= int(a) <= len(self.ht.AUDIENCES):
            self.audience = self.ht.AUDIENCES[int(a) - 1]
        for i, f in enumerate(self.ht.FORMATS, 1):
            self.say(f"   {self.p(f'[{i}]', 'accent')} {f}")
        f = self.ask("Format", self.ht.FORMATS.index(self.format) + 1)
        if f.isdigit() and 1 <= int(f) <= len(self.ht.FORMATS):
            self.format = self.ht.FORMATS[int(f) - 1]
        self.save()

    def highlight(self, text, spans):
        """spans: (start, end, colour). Returns the text with those parts coloured."""
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
        self.say("")
        self.say("  " + self.highlight(self.text, [(d["start"], d["end"], colours[d["level"]]) for d in issues])
                 .replace("\n", "\n  "))
        self.say("")
        if not issues:
            self.note(f"No mistakes found at level {level}.", "green")
            return
        for n, d in enumerate(issues, 1):
            if d["suggestion"] is None:
                line = f"⚑ {d['type']}: {d['note']}"
            else:
                line = f"{d['original']}  {self.p('→', 'grey')}  {self.p(d['suggestion'], 'green')}  " + \
                    self.p(f"({d['type']}{', ' + d['note'] if d['note'] else ''})", "grey")
            self.say(f"   {self.p(str(n).rjust(2), 'grey')}  {line}")
        self.say("")
        if self.yes(f"Fix them all now (level {level})?"):
            new, n, _ = self.fix(self.text)
            self.set_text(new)
            self.note(f"Fixed {n}. [u] undoes it.", "green")

    def ai_check(self):
        if len(self.text.split()) < 10:
            self.note("Use a bit more text (a few sentences) for the AI check.", "yellow")
            return
        r = self.ht.ai_report(self.text)
        colour = {"High": "red", "Medium": "yellow", "Low": "green"}[r["verdict"]]
        self.say("")
        self.say(f"  AI-style score  {self.bar(r['score'] / 100, 20)}  " +
                 self.p(f"{r['score']}/100  {r['verdict']}", colour, "bold"))
        for reason in r["reasons"][:6]:
            self.say("    " + self.p("• " + reason, "grey"))
        self.say("")
        spans = [(x["start"], x["end"], "hl_orange" if x["strength"] == 2 else "hl_yellow")
                 for x in r["sentences"] if x["strength"]]
        self.say("  " + self.highlight(self.text, spans).replace("\n", "\n  "))
        self.say("")
        self.note("Yellow = some AI habits, orange = many. This can't prove who wrote something: careful writers can "
                  "score high, and edited AI text can score low.")

    def apa_reference(self):
        org = self.yes("Is the author an organisation (not people)?", False)
        authors = self.ask("Organisation name" if org else "Authors (e.g. John Smith; Kate Jones)")
        year = self.ask("Year (blank = n.d.)")
        title = self.ask("Title")
        book = self.yes("Is it a book?", False)
        site = self.ask("Publisher" if book else "Website name")
        url = "" if book else self.ask("Link (URL)")
        self.say("")
        self.say("  In-text:    " + self.p(self.ht.apa_in_text(authors, year, org), "green"))
        self.say("  Reference:  " + self.p(self.ht.apa_reference(authors, year, title, site, url, org,
                                                                 "book" if book else "website"), "green"))
        self.note("Put the title in italics in your document.")

    # ----- 3 Type -----
    def type_screen(self):
        self.header(3)
        self.rule("Type")
        if not self.text.strip():
            self.note("There's nothing to type yet. Write it in [1], paste it in [t] Text, or press Enter to paste "
                      "it now.", "yellow")
            new = self.read_block()
            if not new.strip():
                return
            self.set_text(new)
        self.show_text(limit=6)
        avg = self.ht.average_speed(*self.s["random"]) if self.s["random"] else self.s["wpm"]
        self.note(f"About {self.ht.format_duration(self.ht.seconds_for(self.text, avg))} at "
                  f"{self.status_speed()}, {self.style_name()}"
                  + (", in the background (Word)" if self.s["background"] else "") + ".")
        self.say("")
        choice = self.menu([("enter", "Start typing", f"then click into your document within {self.s['delay']} s"),
                            ("s", "Settings", "speed, style, typos"),
                            ("b", "Back", "")], prompt="press Enter to start")
        if choice == "s":
            self.settings()
            return self.type_screen()
        if choice not in ("", "enter"):
            return
        self.type_text(self.text)

    def status_speed(self):
        return f"{self.s['random'][0]}–{self.s['random'][1]} WPM" if self.s["random"] else f"{self.s['wpm']} WPM"

    def make_typist(self):
        if self.typist is None:
            try:
                self.typist = self.typist_factory()
            except Exception as exc:
                self.note("Can't press keys on this computer: " + str(exc), "red")
                return None
        return self.typist

    def plan(self, text):
        words, letters = self.ht.parse_typo_targets(self.s["targets"])
        return self.ht.build_plan(text, variation=self.s["variation"] / 100.0, typo_percent=float(self.s["typos"]),
                                  natural_pauses=self.s["pauses"], typo_words=words, typo_letters=letters,
                                  fix_chosen=self.s["fix_chosen"])

    def type_text(self, text, plan=None, jumps=None, countdown=None, label="Typing"):
        """Type with a countdown and a live progress bar. Ctrl+C stops. Returns True when it finished."""
        t = self.make_typist()
        if t is None:
            return False
        bg = self.s["background"]
        if not bg:
            problem = self.ht.mac_permission_problem()
            if problem:
                self.note(problem, "red")
                return False
        t.wpm = self.s["wpm"]
        t.wpm_range = tuple(self.s["random"]) if self.s["random"] else None
        output = self.ht.WordBackground(pinned=self.s["pin"]) if bg else None
        t.start(text, plan if plan is not None else self.plan(text),
                countdown if countdown is not None else (2 if bg else self.s["delay"]),
                jumps, output=output, corner_stop=not bg)
        listener = self.hotkeys(t) if not bg else None
        stop_hint = "Ctrl+C here" + ("" if bg else " · mouse to the top-left corner" +
                                     ("" if sys.platform == "darwin" else " · Esc  (F8 pauses)"))
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
            self.say("  " + self.p("✓ Finished!", "green", "bold") + "  " + self.bar(1.0) + " 100%")
            self.pause()
            return True
        if t.state == "error":
            self.note(t.error, "red")
        else:
            self.note(f"Stopped. {t.done_chars} of {t.total_chars} characters typed. ({stop_hint})", "yellow")
        self.pause()
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
    def boxes_screen(self):
        modes = {"click": "I click into each box", "spot": "Auto-click my spots",
                 "tab": "Press Tab (a table in Word)", "word": "Word cells (pick a .docx)"}
        while True:
            self.header(3)
            self.rule("Boxes · one paragraph each")
            if not self.boxes:
                self.note("No boxes yet. [p] pastes text and splits it, one paragraph per box.")
            for i, b in enumerate(self.boxes, 1):
                mark = self.p("✓", "green") if b["done"] else self.p("○", "grey")
                where = ""
                if self.box_mode == "spot":
                    where = self.p(f"  spot {b['spot']}" if b["spot"] else "  no spot yet", "grey")
                elif self.box_mode == "word":
                    where = self.p("  → " + b["cell"]["label"] if b["cell"] else "  → skipped", "grey")
                first = b["text"].split("\n")[0]
                self.say(f"   {mark} {self.p(str(i).rjust(2), 'bold')}  {first[:self.width - 30]}"
                         f"{'…' if len(first) > self.width - 30 else ''}{where}")
            self.say("")
            self.note("Getting to each box: " + self.p(modes[self.box_mode], "bold"))
            self.say("")
            choice = self.menu([
                ("enter", "Type", "type the boxes the way picked below"),
                ("p", "Paste & split", "paste text, one paragraph per box"),
                ("s", "Split my text", "split the current text"),
                ("e", "Edit a box", ""),
                ("x", "Remove a box", ""),
                ("r", "Start over", "clear the ✓ marks"),
                None,
                ("1", "I click", modes["click"]),
                ("2", "Spots", modes["spot"] + (" · [o] set spots" if self.box_mode == "spot" else "")),
                ("3", "Tab", modes["tab"]),
                ("4", "Word cells", modes["word"] + (" · [w] change cells" if self.doc else "")),
                ("b", "Back", ""),
            ], prompt="press Enter to type, or choose")
            if choice == "b":
                return
            if choice in ("p", "s"):
                text = self.read_block() if choice == "p" else self.text
                parts = self.ht.split_paragraphs(text)
                self.boxes = [{"text": t, "done": False, "spot": None, "cell": None} for t in parts]
                self.fill_cells()
            elif choice == "e":
                n = self.ask("Which box?")
                if n.isdigit() and 1 <= int(n) <= len(self.boxes):
                    new = self.read_block(f"New text for box {n}")
                    if new.strip():
                        self.boxes[int(n) - 1]["text"] = new
            elif choice == "x":
                n = self.ask("Remove which box?")
                if n.isdigit() and 1 <= int(n) <= len(self.boxes):
                    del self.boxes[int(n) - 1]
            elif choice == "r":
                for b in self.boxes:
                    b["done"] = False
            elif choice in ("1", "2", "3", "4"):
                self.box_mode = {"1": "click", "2": "spot", "3": "tab", "4": "word"}[choice]
                if self.box_mode == "spot" and not any(b["spot"] for b in self.boxes):
                    self.set_spots()
                if self.box_mode == "word" and not self.doc:
                    self.connect_doc()
            elif choice == "o":
                self.set_spots()
            elif choice == "w":
                self.pick_cells()
            elif choice in ("", "enter"):
                self.type_boxes()

    def set_spots(self):
        t = self.make_typist()
        if t is None or not self.boxes:
            return
        self.note("For each box: point the mouse at the place it should be typed (don't click), then come back "
                  "and press Enter. Don't move the window or scroll afterwards.", "accent")
        for i, b in enumerate(self.boxes, 1):
            self.read(f"  Box {i}: point at its spot, then press Enter ")
            try:
                b["spot"] = tuple(int(v) for v in t.mouse.position)
            except Exception as exc:
                self.note(f"Couldn't read the mouse position: {exc}", "red")
                return
            self.note(f"Box {i} → {b['spot']}", "green")

    def connect_doc(self):
        path = self.ask("Drag your .docx file here (or type its path), then press Enter").strip().strip("'\"")
        if not path:
            self.box_mode = "click"
            return
        try:
            cells = self.ht.read_word_cells(os.path.expanduser(path))
        except Exception as exc:
            self.note(f"Couldn't read that document: {exc}", "red")
            self.box_mode = "click"
            self.pause()
            return
        if not cells:
            self.note("That document has no tables. Use [1] I click or [2] Spots instead.", "yellow")
            self.box_mode = "click"
            self.pause()
            return
        self.doc = {"path": os.path.abspath(os.path.expanduser(path)), "cells": cells}
        self.fill_cells()
        try:
            self.ht.open_in_word(self.doc["path"])
        except Exception:
            pass
        self.note(f"Connected: {len(cells)} cells. Each box goes into the next empty cell; [w] changes them.", "green")
        self.pause()

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
            self.note("Nothing to type: add boxes with [p], or [r] to start over.", "yellow")
            self.pause()
            return
        if self.s["background"] and self.box_mode != "word":
            self.note("Background typing only works with Word cells. Turn it off in Settings for the other ways.",
                      "yellow")
            self.pause()
            return
        if self.box_mode == "click":
            for i, b in enumerate(todo, 1):
                self.say("")
                self.note(f"Box {self.boxes.index(b) + 1} of {len(self.boxes)}: press Enter, then click into its spot.",
                          "accent")
                if self.ask("Enter = go, s = stop").lower().startswith("s"):
                    return
                if not self.type_text(b["text"], label=f"Box {self.boxes.index(b) + 1}"):
                    return
                b["done"] = True
            return
        if self.box_mode == "tab":
            texts = [b["text"].replace("\t", " ") for b in todo]
            self.note("Click into the first cell of the table during the countdown.", "accent")
            if self.type_text("\t".join(texts)):
                for b in todo:
                    b["done"] = True
            return
        plan, jumps, texts = [], {}, []
        t = self.make_typist()
        if t is None:
            return
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
            self.note("No box has a spot / cell yet.", "yellow")
            self.pause()
            return
        self.note("Hands off the keyboard and mouse until it's done.", "accent")
        if self.type_text("".join(texts), plan=plan, jumps=jumps, countdown=3 if self.box_mode == "spot" else 2):
            for b in todo:
                b["done"] = True

    # ----- Text -----
    def text_screen(self):
        while True:
            self.header()
            self.rule("Text")
            self.show_text(limit=14)
            self.say("")
            choice = self.menu([("p", "Paste / type", "replace it with new text"),
                                ("v", "From clipboard", "use what you last copied"),
                                ("o", "Open a file", ".txt or .docx"),
                                ("c", "Copy", "copy the text to the clipboard"),
                                ("x", "Clear", ""),
                                ("b", "Back", "")])
            if choice in ("b", ""):
                return
            if choice == "p":
                new = self.read_block()
                if new.strip():
                    self.set_text(new)
            elif choice == "v":
                clip = clipboard_get()
                if clip and clip.strip():
                    self.set_text(clip.strip("\n"))
                else:
                    self.note("The clipboard is empty (or can't be read here). Use [p] and paste instead.", "yellow")
                    self.pause()
            elif choice == "o":
                self.open_file()
            elif choice == "c":
                self.note("Copied." if self.text and clipboard_set(self.text) else "Couldn't copy here.",
                          "green" if self.text else "yellow")
                self.pause()
            elif choice == "x":
                self.set_text("")

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
            self.note(f"Couldn't open it: {exc}", "red")
            self.pause()
            return
        self.set_text(text.strip("\n"))
        self.note(f"Opened {os.path.basename(path)}: {len(text.split())} words.", "green")
        self.pause()

    # ----- Settings -----
    def settings(self):
        while True:
            self.header(3)
            self.rule("Settings")
            s = self.s
            on = lambda v: self.p("on", "green") if v else self.p("off", "grey")
            rnd = f"{s['random'][0]}–{s['random'][1]} WPM" if s["random"] else "off"
            choice = self.menu([
                ("1", "Speed", f"{s['wpm']} WPM   (or 25, 40, 60, 90, 120)"),
                ("2", "Random speed", rnd),
                ("3", "Style", f"{self.style_name()}   (Careful · Natural · Messy)"),
                ("4", "Rhythm", f"{s['variation']}   how uneven, 0-100"),
                ("5", "Typos", f"{s['typos']:g} %   made and fixed, 0-8"),
                ("6", "Pauses", f"{'on' if s['pauses'] else 'off'}   at commas, full stops, new lines"),
                ("7", "Always wrong", f"{s['targets'] or '—'}   (fix them: {'yes' if s['fix_chosen'] else 'no'})"),
                ("8", "Countdown", f"{s['delay']} s to click into your document"),
                ("9", "Background", f"{'on' if s['background'] else 'off'}   Word only: keep using your computer"
                                    + (f" (pin: {'on' if s['pin'] else 'off'})" if s["background"] else "")),
                ("w", "After /use", f"humanise {on(s['wf_humanise'])} · fix mistakes {on(s['wf_fix'])}"),
                ("b", "Back", ""),
            ])
            if choice in ("b", ""):
                self.save()
                return
            if choice == "1":
                v = self.ask("Words per minute (1-2000)", s["wpm"])
                if v.isdigit() and 1 <= int(v) <= 2000:
                    s["wpm"] = int(v)
            elif choice == "2":
                v = self.ask("Two speeds like 40-90, or 'off'", rnd if s["random"] else "off")
                m = re.match(r"\s*(\d+)\s*[-–to ]+\s*(\d+)", v)
                s["random"] = sorted([int(m.group(1)), int(m.group(2))]) if m else None
            elif choice == "3":
                v = self.ask("Careful, Natural or Messy", self.style_name()).strip().title()
                if v in STYLES:
                    s["variation"], s["typos"] = STYLES[v]
                    s["pauses"] = True
            elif choice == "4":
                v = self.ask("Rhythm 0-100", s["variation"])
                if v.isdigit() and 0 <= int(v) <= 100:
                    s["variation"] = int(v)
            elif choice == "5":
                try:
                    s["typos"] = round(max(0.0, min(8.0, float(self.ask("Typos % (0-8)", s["typos"])))), 1)
                except ValueError:
                    pass
            elif choice == "6":
                s["pauses"] = not s["pauses"]
            elif choice == "7":
                s["targets"] = self.ask("Words and letters to always get wrong, e.g. the, because, e", s["targets"])
                s["fix_chosen"] = self.yes("Fix them after (like normal typos)?", s["fix_chosen"])
            elif choice == "8":
                v = self.ask("Seconds (1-60)", s["delay"])
                if v.isdigit() and 1 <= int(v) <= 60:
                    s["delay"] = int(v)
            elif choice == "9":
                s["background"] = self.yes("Type into Word in the background?", s["background"])
                if s["background"]:
                    s["pin"] = self.yes("Pin it to one spot in Word?", s["pin"])
            elif choice == "w":
                s["wf_humanise"] = self.yes("After /use: humanise it?", s["wf_humanise"])
                s["wf_fix"] = self.yes("After /use: fix mistakes?", s["wf_fix"])
            self.save()

    # ----- 6 Connect -----
    def connect(self):
        ht = self.ht
        while True:
            self.header()
            self.rule("Connect Claude")
            names = {"account": "My Claude account", "claude": "A Claude API key", "local": "A local AI"}
            self.note("Using: " + self.p(names[self.engine], "bold"), "accent")
            acct = ht.claude_account_status()
            self.say("")
            self.say(f"   {self.p('[1]', 'accent', 'bold')} {'My Claude account':<20}" +
                     self.p("recommended · your Pro/Max plan · no API key", "grey"))
            self.say("       " + self.p(acct["text"], "green" if acct.get("logged_in") else "yellow"))
            self.say(f"       {self.p('[i]', 'accent')} install Claude Code   {self.p('[l]', 'accent')} log in")
            self.say(f"   {self.p('[2]', 'accent', 'bold')} {'A Claude API key':<20}" +
                     self.p("pay per use · " + ("key saved ✓" if self.key() else "no key yet"), "grey"))
            self.say(f"       {self.p('[k]', 'accent')} add or change the key")
            self.say(f"   {self.p('[3]', 'accent', 'bold')} {'A local AI':<20}" +
                     self.p(f"free, offline (Ollama) · model: {self.model or 'none'}", "grey"))
            self.say(f"       {self.p('[m]', 'accent')} pick a model")
            self.say("")
            try:
                with open(ht.claude_config_path(), encoding="utf-8") as fh:
                    linked = "human-typer" in (json.load(fh).get("mcpServers") or {})
            except Exception:
                linked = False
            self.say(f"   {self.p('[a]', 'accent', 'bold')} {'Claude app':<20}" +
                     self.p("let the Claude desktop app type with Human Typer · " +
                            ("connected ✓" if linked else "not connected"), "grey"))
            self.say(f"       {self.p('[d]', 'accent')} disconnect it")
            self.say(f"   {self.p('[b]', 'accent', 'bold')} Back")
            self.say("")
            choice = self.ask("choose").lower()
            if choice in ("b", ""):
                self.save()
                return
            if choice in ("1", "2", "3"):
                self.engine = {"1": "account", "2": "claude", "3": "local"}[choice]
                self.session = None
            elif choice == "i":
                cmd = ht.CLAUDE_INSTALL["win" if sys.platform == "win32" else "unix"]
                self.note("This runs Anthropic's installer for Claude Code here:", "accent")
                self.say("     " + self.p(cmd, "bold"))
                if self.yes("Run it now?"):
                    run = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
                           if sys.platform == "win32" else ["bash", "-c", cmd])
                    subprocess.run(run)
                    self.engine = "account"
                    self.note("Now press [l] to log in.", "accent")
                    self.pause()
            elif choice == "l":
                exe = ht.find_claude_cli()
                if not exe:
                    self.note("Install Claude Code first ([i]).", "yellow")
                    self.pause()
                    continue
                self.note("Log in with your Claude account in the browser that opens, then come back here.", "accent")
                subprocess.run([exe, "auth", "login"], env=ht._claude_env(exe))
                self.engine = "account"
            elif choice == "k":
                key = self.secret("Paste your Claude API key (sk-ant-…), or leave blank to remove it:").strip()
                cfg = ht.load_config()
                if key:
                    cfg["claude_api_key"] = key
                    self.engine = "claude"
                else:
                    cfg.pop("claude_api_key", None)
                ht.save_config(cfg)
                self.note("Key saved (only on this computer)." if key else "Key removed.", "green")
                self.pause()
            elif choice == "m":
                try:
                    models = ht.ollama_models()
                except Exception as exc:
                    self.note(str(exc).replace("\n\n", " ").replace("\n", " "), "red")
                    self.pause()
                    continue
                if not models:
                    self.note("Ollama has no models yet. In a terminal run:  ollama pull llama3.2", "yellow")
                    self.pause()
                    continue
                for n, m in enumerate(models, 1):
                    self.say(f"   {self.p(f'[{n}]', 'accent')} {m}")
                a = self.ask("Model", (models.index(self.model) + 1) if self.model in models else 1)
                if a.isdigit() and 1 <= int(a) <= len(models):
                    self.model = models[int(a) - 1]
                    self.engine = "local"
            elif choice in ("a", "d"):
                try:
                    path = ht.connect_claude(remove=choice == "d")
                    self.note(("Disconnected." if choice == "d" else "Connected!") + " Quit the Claude app completely "
                              "and open it again." + ("" if choice == "d" else " Then say: “type it with Human "
                                                      "Typer at 60 WPM”."), "green")
                    self.note(f"(Settings file: {path})")
                except Exception as exc:
                    self.note(f"Couldn't update the Claude app's settings: {exc}", "red")
                self.pause()
            self.save()

    # ----- Help -----
    def help(self):
        self.header()
        self.rule("How it works")
        steps = [
            ("1 Write", "Chat with Claude: ask for what you need. Type /use to send the answer on: it's humanised, "
                        "checked, and ready to type. First time? [6] Connect (two steps, about a minute)."),
            ("2 Polish", "Humanise makes it sound natural for who's reading it. Check finds mistakes (pick a level). "
                         "AI check shows habits that look like AI writing. APA tidies references."),
            ("3 Type", "Press Enter, then click into your document before the countdown ends. Hands off the keyboard "
                       "and mouse while it types."),
            ("4 Boxes", "Worksheets and tables: one paragraph per box. Click each box yourself, let it click spots "
                        "you point at, press Tab through a Word table, or pick Word cells from a .docx."),
            ("To stop", "Ctrl+C here, or push the mouse into the top-left corner of the screen" +
                        ("." if sys.platform == "darwin" else ", or press Esc. F8 pauses.")),
            ("Look real", "Settings → Style: Careful, Natural or Messy. It types in bursts, slows for hard reaches, "
                          "and makes the mistakes people make, then fixes them. The finished text is always right."),
        ]
        for title, body in steps:
            self.say("")
            self.say("  " + self.p(title, "accent", "bold"))
            for line in textwrap.wrap(body, self.width - 6):
                self.say("    " + line)
        self.say("")
        self.pause()


def main(ht=None):
    if ht is None:
        import human_typer as ht
    if sys.platform == "win32":
        os.system("")                     # lets Windows terminals show colours
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        CLI(ht).run()
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
