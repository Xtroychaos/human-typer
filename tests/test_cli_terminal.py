"""Runs the terminal version for real, in a pseudo-terminal (like the Terminal app),
and drives it the way a person does: single keys, typing in the boxes, pasting,
mouse clicks, Ctrl+C, Ctrl+D, Esc, small windows. A pretend Claude Code (a little
script that answers like the real one, with a delay) stands in for Claude.

    python -m unittest tests.test_cli_terminal -v

Mac and Linux only (Windows has no pseudo-terminals); skipped elsewhere.
"""
import json
import os
import re
import select
import shutil
import signal
import struct
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ANSI = re.compile(r"\x1b\[[0-9;?<]*[A-Za-z]|\x1b[78]")

FAKE_CLAUDE = r'''#!{python}
"""Answers like Claude Code: `auth status`, or a prompt on stdin -> stream-json."""
import json, os, sys, time
args = sys.argv[1:]
if args[:2] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True, "authMethod": "claude.ai", "email": "test@example.com"}}))
    sys.exit(0)
prompt = sys.stdin.read()
system = ""
if "--system-prompt-file" in args:
    system = open(args[args.index("--system-prompt-file") + 1], encoding="utf-8").read()
model = args[args.index("--model") + 1] if "--model" in args else "default"
def say(obj):
    print(json.dumps(obj), flush=True)
say({{"type": "system", "subtype": "init", "session_id": "fake-session"}})
time.sleep(float(os.environ.get("FAKE_DELAY", "0.3")))
if os.environ.get("FAKE_ERROR"):
    say({{"type": "result", "subtype": "success", "is_error": True, "result": os.environ["FAKE_ERROR"],
         "session_id": "fake-session"}})
    sys.exit(1)
if "Humaniser" in system:
    text = "HUMANISED: " + prompt.split("<<<")[-1].split(">>>")[0].strip()
else:
    text = os.environ.get("FAKE_REPLY", "Here is a short answer from Claude (" + model + ").")
for word in text.split(" "):
    say({{"type": "stream_event", "session_id": "fake-session",
         "event": {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": word + " "}}}}}})
    time.sleep(float(os.environ.get("FAKE_WORD_DELAY", "0.01")))
say({{"type": "result", "subtype": "success", "is_error": False, "result": text, "session_id": "fake-session"}})
'''


class Term:
    """The terminal version running in a pseudo-terminal, cols x rows big."""

    def __init__(self, test, cols=100, rows=40, env=None, args=()):
        import pty
        self.home = tempfile.mkdtemp(prefix="ht_term_")
        self.bin = os.path.join(self.home, "bin")
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w") as f:
            f.write(FAKE_CLAUDE.format(python=sys.executable))
        os.chmod(fake, 0o755)
        self.cols, self.rows = cols, rows
        e = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "NO_COLOR")}
        e.update(HOME=self.home, USERPROFILE=self.home, TERM="xterm-256color", PATH=self.bin + os.pathsep + e["PATH"],
                 HUMAN_TYPER_BRIDGE_PORT=str(48000 + os.getpid() % 900))
        e.update(env or {})
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.chdir(ROOT)
            os.execve(sys.executable, [sys.executable, "human_typer_cli.py", *args], e)
        import fcntl
        import termios
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        self.raw = b""
        test.addCleanup(self.close)

    # ----- reading what's on screen -----
    def pump(self, seconds=0.05):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            r, _, _ = select.select([self.fd], [], [], 0.02)
            if r:
                try:
                    self.raw += os.read(self.fd, 65536)
                except OSError:
                    return

    @property
    def text(self):
        return ANSI.sub("", self.raw.decode("utf-8", "replace"))

    def screen(self):
        """The lines of the last full screen (after the last clear), as the person sees them."""
        last = self.raw.decode("utf-8", "replace").split("\x1b[2J\x1b[H")[-1]
        lines = [ANSI.sub("", l.split("\r")[-1]) for l in last.replace("\r\n", "\n").split("\n")]
        return lines

    def wait_for(self, what, timeout=8.0, since=0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            if what in self.text[since:]:
                return True
        raise AssertionError(f"never saw {what!r}. Last screen:\n" + "\n".join(self.screen()[-30:]))

    def mark(self):
        return len(self.text)

    # ----- doing things -----
    def send(self, data, pause=0.25):
        os.write(self.fd, data.encode() if isinstance(data, str) else data)
        self.pump(pause)

    def key(self, k, pause=0.3):
        self.send({"enter": "\r", "esc": "\x1b", "ctrl-c": "\x03", "ctrl-d": "\x04"}.get(k, k), pause)

    def line(self, text, pause=0.3):
        self.send(text + "\r", pause)

    def click(self, label):
        """Click the middle of label where it is on the current screen."""
        self.pump(0.3)
        lines = self.screen()
        top = max(0, len(lines) - self.rows)          # the window shows the last `rows` lines
        for i, line in enumerate(lines):
            col = line.find(label)
            if col >= 0 and i >= top:
                x, y = col + 1 + len(label) // 2, i + 1 - top
                self.send(f"\x1b[<0;{x};{y}M\x1b[<0;{x};{y}m", 0.4)
                return
        raise AssertionError(f"{label!r} isn't on screen:\n" + "\n".join(lines))

    def exited(self, timeout=5.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.pid = None
                return os.waitstatus_to_exitcode(status)
        return None

    def config(self):
        with open(os.path.join(self.home, ".human_typer.json")) as f:
            return json.load(f)

    def close(self):
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
            except OSError:
                pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        shutil.rmtree(self.home, ignore_errors=True)


@unittest.skipIf(sys.platform == "win32", "pseudo-terminals are Mac / Linux only")
class Terminal(unittest.TestCase):

    def start(self, **kw):
        t = Term(self, **kw)
        t.wait_for("HUMAN TYPER")
        t.wait_for("› ")
        return t

    # ----- getting around -----
    def test_starts_and_quits_cleanly(self):
        t = self.start()
        t.key("q")
        t.wait_for("Bye")
        self.assertEqual(t.exited(), 0)

    def test_every_screen_by_its_key(self):
        t = self.start()
        for key, title in (("2", "POLISH"), ("3", "TYPE"), ("4", "BOXES"), ("5", "SETTINGS"), ("6", "AI ·"),
                           ("?", "HOW IT WORKS"), ("esc", "HOME"), ("1", "CHAT")):
            m = t.mark()
            t.key(key)
            t.wait_for(title, since=m)
        m = t.mark()
        t.line("")                                     # an empty line leaves the chat
        t.wait_for("HOME", since=m)
        t.key("q")
        self.assertEqual(t.exited(), 0)

    def test_number_keys_jump_out_of_the_chat_box(self):
        t = self.start()
        t.key("1")
        t.wait_for("you ›")
        m = t.mark()
        t.line("3")
        t.wait_for("TYPE  ", since=m)
        self.assertNotIn("claude ›", t.text[m:], "'3' wasn't sent to Claude")
        t.key("1")
        t.wait_for("you ›")
        m = t.mark()
        t.line("\x1b")                                 # Esc, then Enter
        t.wait_for("HOME", since=m)

    def test_clicking_tabs_and_actions(self):
        t = self.start()
        m = t.mark()
        t.click("3 Type")
        t.wait_for("Start typing", since=m)
        m = t.mark()
        t.click("Faster (+10)")
        t.wait_for("70 WPM", since=m)
        m = t.mark()
        t.click("Style")
        t.wait_for("Style: Messy", since=m)
        m = t.mark()
        t.click("5 Settings")
        t.wait_for("SETTINGS", since=m)
        m = t.mark()
        t.click("Pauses        on")                   # a row in the list...
        t.wait_for("Pauses        off", since=m)
        m = t.mark()
        t.click("p Pauses")                           # ...or the action
        t.wait_for("Pauses        on", since=m)
        m = t.mark()
        t.click("2 Polish")
        t.wait_for("POLISH", since=m)
        t.key("q")
        self.assertEqual(t.exited(), 0)
        self.assertEqual(t.config()["cli"]["wpm"], 70)

    def test_clicking_a_model_on_the_ai_screen(self):
        t = self.start()
        t.key("6")
        m = t.mark()
        t.click("Haiku: fastest and cheapest")
        t.wait_for("Using Claude Haiku", since=m)

    def test_clicking_works_in_a_small_window_that_scrolls(self):
        t = self.start(cols=64, rows=20)
        m = t.mark()
        t.key("2")                                     # Polish is taller than 20 rows: it scrolls
        t.wait_for("POLISH", since=m)
        m = t.mark()
        t.click("Natural tone")
        t.wait_for("There's no text yet", since=m)
        m = t.mark()
        t.click("Type it")
        t.wait_for("Start typing", since=m)

    def test_clicking_nothing_does_nothing(self):
        t = self.start()
        m = t.mark()
        t.send("\x1b[<0;90;2M\x1b[<0;90;2m", 0.5)      # top right: nothing there
        t.key("q")
        self.assertEqual(t.exited(), 0)
        self.assertNotIn("Stopped", t.text[m:])

    # ----- the paste box -----
    def test_paste_box_finishes_on_two_empty_lines(self):
        t = self.start()
        t.key("e")
        t.wait_for("Enter on 2 empty lines")
        t.line("Hello there,")
        t.line("")
        t.line("how are you?")
        m = t.mark()
        t.line("")
        t.line("")
        t.wait_for("5 words", since=m)                  # the blank line between paragraphs stayed in

    def test_paste_box_finishes_with_a_full_stop_or_ctrl_d(self):
        t = self.start()
        t.key("e")
        t.line("One line.")
        m = t.mark()
        t.line(".")
        t.wait_for("2 words", since=m)
        t.key("e")
        t.line("Three more words")
        m = t.mark()
        t.key("ctrl-d", 0.6)
        t.wait_for("3 words", since=m)

    def test_paste_box_cancels_with_ctrl_c_or_esc(self):
        t = self.start()
        t.key("e")
        t.line("Keep me.")
        t.line(".")
        t.key("e")
        t.line("Throw this away")
        m = t.mark()
        t.key("ctrl-c", 0.6)
        t.wait_for("Cancelled: nothing was changed", since=m)
        t.wait_for("2 words", since=m)
        t.key("e")
        m = t.mark()
        t.line("\x1b")
        t.wait_for("Cancelled", since=m)
        t.key("q")
        self.assertEqual(t.exited(), 0)

    def test_paste_box_enter_straight_away_leaves_it(self):
        t = self.start()
        t.key("e")
        m = t.mark()
        t.line("")
        t.wait_for("HOME", since=m)
        self.assertIn("No text yet", t.text[m:])

    def test_cancelling_a_paste_keeps_the_boxes(self):
        t = self.start()
        t.key("4")
        t.key("p")
        t.line("First.")
        t.line("")
        t.line("Second.")
        t.line(".")
        t.wait_for("BOXES · 2")
        t.key("p")
        m = t.mark()
        t.key("ctrl-c", 0.6)
        t.wait_for("BOXES · 2", since=m)

    # ----- Claude working -----
    def test_thinking_then_answer_then_use(self):
        t = self.start(env={"FAKE_DELAY": "1.5"})
        t.key("1")
        t.line("Write me something")
        t.wait_for("Claude is thinking")
        t.wait_for("Here is a short answer from Claude", timeout=10)
        m = t.mark()
        t.line("/use")
        t.wait_for("HUMANISED: Here is a short answer", since=m, timeout=10)
        t.wait_for("Ready to type", since=m)
        t.wait_for("Start typing", since=m)

    def test_ctrl_c_while_claude_is_thinking_and_writing(self):
        t = self.start(env={"FAKE_DELAY": "3", "FAKE_WORD_DELAY": "0.3",
                            "FAKE_REPLY": " ".join(["word"] * 40)})
        t.key("1")
        t.line("A long one please")
        t.wait_for("is thinking")
        m = t.mark()
        t.key("ctrl-c", 1.0)
        t.wait_for("Stopped", since=m)
        t.wait_for("you ›", since=m)                   # still in the chat, still working
        t.line("again")
        t.wait_for("word word", timeout=10)            # writing now
        m = t.mark()
        t.key("ctrl-c", 1.0)
        t.wait_for("/use still works", since=m)
        t.line("")
        t.key("q")
        self.assertEqual(t.exited(), 0)

    def test_claude_error_shows_and_carries_on(self):
        t = self.start(env={"FAKE_ERROR": "Not logged in · Please run /login"})
        t.key("1")
        t.line("hello")
        t.wait_for("isn't logged in")
        t.wait_for("6 AI → n (log in)")
        t.wait_for("you ›")
        t.line("")
        t.key("q")
        self.assertEqual(t.exited(), 0)

    def test_humanise_and_undo_in_polish(self):
        t = self.start()
        t.key("e")
        t.line("my own words")
        t.line(".")
        t.key("2")
        m = t.mark()
        t.key("h", 0.5)
        t.wait_for("HUMANISED: my own words", since=m, timeout=10)
        t.wait_for("Humanised. Read it over", since=m)
        m = t.mark()
        t.key("u")
        t.wait_for("Undone", since=m)
        self.assertIn("my own words", t.screen()[4] + t.screen()[5])

    def test_pick_the_model(self):
        t = self.start()
        t.key("6")
        m = t.mark()
        t.key("s")
        t.wait_for("Using Claude Sonnet", since=m)
        t.key("1")
        t.line("hi")
        t.wait_for("Claude (sonnet)")                  # the pretend Claude says which model it was asked for
        t.line("")
        t.key("q")
        t.exited()
        self.assertEqual(t.config()["claude_model"], "sonnet")

    # ----- keys that used to quit or get stuck -----
    def test_ctrl_c_and_ctrl_d_in_menus_and_questions(self):
        t = self.start()
        m = t.mark()
        t.key("ctrl-c", 0.6)                           # at a menu
        t.wait_for("Stopped.", since=m)
        t.key("5")
        t.key("w")
        t.wait_for("Words per minute")
        m = t.mark()
        t.key("ctrl-d", 0.6)                           # in a question: keeps the old value
        t.wait_for("SETTINGS", since=m)
        t.wait_for("60 WPM", since=m)
        t.key("w")
        m = t.mark()
        t.key("ctrl-c", 0.6)                           # in a question: stops, still running
        t.wait_for("Stopped.", since=m)
        t.key("q")
        self.assertEqual(t.exited(), 0)

    @unittest.skipUnless(sys.platform.startswith("linux"), "on a Mac this could press real keys")
    def test_typing_without_a_keyboard_says_so(self):
        t = self.start()                               # no screen here, so keys can't be pressed
        t.key("e")
        t.line("Type me.")
        t.line(".")
        t.key("3")
        m = t.mark()
        t.key("enter", 1.0)
        t.wait_for("Can't press keys", since=m)
        t.key("q")
        self.assertEqual(t.exited(), 0)

    def test_settings_are_kept_for_next_time(self):
        t = self.start()
        t.key("5")
        t.key("w")
        t.line("85")
        t.wait_for("85 WPM")
        t.key("q")
        t.exited()
        again = Term(self, env={"HOME": t.home})       # a new run, same home folder
        again.wait_for("85 WPM")

    def test_resizing_mid_way(self):
        t = self.start()
        import fcntl
        import termios
        fcntl.ioctl(t.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 22, 60, 0, 0))
        os.kill(t.pid, signal.SIGWINCH)
        m = t.mark()
        t.key("2")
        t.wait_for("POLISH", since=m)
        t.key("q")
        self.assertEqual(t.exited(), 0)


@unittest.skipIf(sys.platform == "win32", "the pretend Claude Code is a script")
class OneLineCommands(unittest.TestCase):
    """The commands with no menus, run the way a script would (pipes, no terminal)."""

    def run_cli(self, *args, stdin=""):
        import subprocess
        home = tempfile.mkdtemp(prefix="ht_cmd_")
        self.addCleanup(shutil.rmtree, home, True)
        bin_dir = os.path.join(home, "bin")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "claude"), "w") as f:
            f.write(FAKE_CLAUDE.format(python=sys.executable))
        os.chmod(os.path.join(bin_dir, "claude"), 0o755)
        env = dict(os.environ, HOME=home, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        env.pop("DISPLAY", None)
        return subprocess.run([sys.executable, "human_typer_cli.py", *args], input=stdin, capture_output=True,
                              text=True, cwd=ROOT, env=env, timeout=60)

    def test_ask_fix_humanise_check_ai_check(self):
        r = self.run_cli("ask", "hello", "--model", "haiku")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "Here is a short answer from Claude (haiku)."))
        r = self.run_cli("fix", "-", "--level", "4", stdin="i went to teh shop and we was tired")
        self.assertEqual(r.stdout.strip(), "I went to the shop and we were tired.")
        r = self.run_cli("humanise", "-", stdin="some words")
        self.assertEqual(r.stdout.strip(), "HUMANISED: some words")
        r = self.run_cli("check", "-", stdin="i went to teh shop")
        self.assertIn("teh  →  the", r.stdout)
        r = self.run_cli("ai-check", "-", stdin=textwrap.dedent("""\
            Furthermore, it is important to note that technology plays a crucial role in reshaping the
            landscape, paving the way for innovation. In conclusion, it remains essential."""))
        self.assertIn("AI-style score", r.stdout)

    def test_errors_go_to_stderr_with_a_code(self):
        r = self.run_cli("fix", "-", stdin="   ")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no text", r.stderr)
        r = self.run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("write", r.stdout)


if __name__ == "__main__":
    unittest.main()
