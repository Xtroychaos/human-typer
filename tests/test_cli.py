"""Checks the terminal version (human_typer_cli.py) by typing into its menus.

    python -m unittest discover -s tests -v
"""
import io
import os
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

_HOME = tempfile.mkdtemp(prefix="human_typer_cli_test_")
os.environ["HOME"] = os.environ["USERPROFILE"] = _HOME

import human_typer as ht  # noqa: E402
import human_typer_cli as cli  # noqa: E402

ht.CONFIG_PATH = os.path.join(_HOME, ".human_typer.json")


class FakeTypist:
    """Stands in for the real typist: 'types' the plan straight away and keeps the result."""
    last = None

    def __init__(self):
        self.wpm, self.wpm_range, self.live_wpm = 60, None, 60
        self.state, self.done_chars, self.total_chars, self.countdown_left = "idle", 0, 0, 0
        self.error, self.thread = "", None
        self.typed, self.jumps_run = [], 0
        self.mouse = type("M", (), {"position": (120, 340)})()
        FakeTypist.last = self

    @property
    def avg_wpm(self):
        return self.wpm

    def start(self, text, plan, countdown, jumps=None, output=None, corner_stop=True):
        self.total_chars = len(text)

        def run():
            self.state = "typing"
            for i, (key, _) in enumerate(plan):
                if jumps and i in jumps:
                    self.jumps_run += 1
                if key == ht.BACKSPACE:
                    self.typed.pop()
                else:
                    self.typed.append(key)
                self.done_chars = len(self.typed)
            self.state = "done"
        self.thread = threading.Thread(target=run)
        self.thread.start()

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def stop(self):
        pass

    def toggle_pause(self):
        pass

    def click_at(self, x, y):
        pass


def run_cli(keys, presses=None, **kw):
    """Run the terminal app with these lines typed in (and, with presses, these single
    keypresses for the menus). Returns (app, everything it printed)."""
    keys = list(keys)
    out = io.StringIO()
    if presses is not None:
        presses = list(presses)

        def press():
            if not presses:
                raise EOFError
            return presses.pop(0)
        kw["keys"] = press

    def read(prompt=""):
        out.write(prompt)
        if not keys:
            raise EOFError
        return keys.pop(0)
    key = kw.pop("secret", "")
    app = cli.CLI(ht, read=read, out=out, colour=False, typist_factory=FakeTypist, secret=lambda label: key)
    app.keys = kw.pop("keys", None)
    for k, v in kw.items():
        setattr(app, k, v)
    try:
        app.run()
    except EOFError:
        pass
    return app, out.getvalue()


class Menus(unittest.TestCase):
    """The workspace: tab bar, panel, actions, result. 1-6 jump anywhere, Esc goes home, q quits."""

    def setUp(self):
        ht.save_config({})
        self._old = ht.mac_permission_problem
        ht.mac_permission_problem = lambda: None
        self.addCleanup(lambda: setattr(ht, "mac_permission_problem", self._old))

    def test_layout_and_quit(self):
        app, out = run_cli(["q"])
        for part in ("HUMAN TYPER", "1 Write", "2 Polish", "3 Type", "4 Boxes",
                     "5 Settings", "6 AI", "TEXT", "HOME", "1-6 jump", "Bye"):
            self.assertIn(part, out)

    def test_jump_anywhere_and_esc_home(self):
        app, out = run_cli(["3", "5", "?", "esc", "2", "q"])
        for title in ("TYPE", "SETTINGS", "HOW IT WORKS", "HOME", "POLISH"):
            self.assertIn(title, out)

    def test_help(self):
        _, out = run_cli(["?", "q"])
        self.assertIn("HOW IT WORKS", out)
        self.assertIn("Careful, Natural or Messy", out)

    def test_paste_text_and_result_area(self):
        app, out = run_cli(["e", "Hello there.", "Second line.", ".", "x", "q"])
        self.assertEqual(app.undo[-1], "Hello there.\nSecond line.")
        self.assertIn("4 words", out)
        self.assertIn("result", out)
        self.assertIn("Cleared", out)

    def test_settings_are_saved(self):
        run_cli(["5", "w", "90", "y", "Messy", "r", "40-80", "d", "3", "p", "q"])
        s = ht.load_config()["cli"]
        self.assertEqual((s["wpm"], s["variation"], s["typos"], s["random"], s["delay"], s["pauses"]),
                         (90, 60, 4.0, [40, 80], 3, False))
        app, out = run_cli(["q"])
        self.assertIn("Messy", out)                     # remembered next time, shown in the title bar
        self.assertIn("40–80 WPM", out)

    def test_type_screen_quick_keys(self):
        app, _ = run_cli(["3", "+", "+", "-", "y", "q"])
        self.assertEqual(app.s["wpm"], 70)
        self.assertEqual(app.style_name(), "Messy")      # Natural -> Messy

    def test_polish_check_fix_undo(self):
        text = "i went to teh shop and we was tired"
        app, out = run_cli(["2", "l", "4", "c", "f", "q"], text=text)
        self.assertIn("[teh]", out)
        self.assertIn("f fixes them all", out)
        self.assertEqual(app.text, "I went to the shop and we were tired.")
        app, _ = run_cli(["2", "f", "u", "q"], text=text)
        self.assertEqual(app.text, text, "u puts it back")

    def test_ai_check_and_apa(self):
        text = ("Furthermore, it is important to note that technology plays a crucial role in reshaping the "
                "landscape, paving the way for innovation (smith 2020). In conclusion, it remains essential.")
        app, out = run_cli(["2", "i", "r", "m", "n", "John Smith", "2020", "Plants", "n", "BBC",
                            "https://bbc.com", "q"], text=text)
        self.assertIn("AI-style score", out)
        self.assertIn("(Smith, 2020)", app.text)
        self.assertIn("Smith, J. (2020)", out)

    def test_type(self):
        app, out = run_cli(["3", "", "q"], text="Hello there, typing test!")
        self.assertEqual("".join(FakeTypist.last.typed), "Hello there, typing test!")
        self.assertIn("Finished", out)

    def test_boxes_by_tab_and_by_spots(self):
        app, out = run_cli(["4", "p", "First answer.", "", "Second answer.", ".", "m", "m", "", "q"])
        self.assertEqual(app.box_mode, "tab")
        self.assertEqual("".join(FakeTypist.last.typed), "First answer.\tSecond answer.")
        self.assertTrue(all(b["done"] for b in app.boxes))
        app, out = run_cli(["4", "p", "One.", "", "Two.", ".", "m", "o", "", "", "", "q"])
        self.assertEqual("".join(FakeTypist.last.typed), "One.Two.")
        self.assertEqual(FakeTypist.last.jumps_run, 2, "clicked each spot")
        self.assertEqual(app.boxes[0]["spot"], (120, 340))

    def test_write_and_workflow(self):
        """Chat with (a pretend) Claude, then /use: humanise, fix, and it's on Type, ready."""
        replies = iter(["Here is teh email.", "Hi Sam, could i have Friday off?"])

        def fake(prompt, system, on_text, stop, session=None, keep=False, **kw):
            text = next(replies)
            on_text(text)
            return text, "s1"
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            ht.save_config({"cli": {"check_level": 4}})
            app, out = run_cli(["1", "Write an email asking for Friday off", "/use", "", "q"], engine="account")
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old
        self.assertIn("claude › Here is teh email.", out)
        self.assertEqual(app.session, "s1")
        self.assertEqual(app.text, "Hi Sam, could I have Friday off?")
        self.assertIn("Ready to type", out)
        self.assertEqual("".join(FakeTypist.last.typed), app.text, "Enter on Type typed it")

    def test_write_is_a_chat_and_keys_still_jump(self):
        """In Write, '2' on its own jumps to Polish (it isn't sent to Claude); answers stay on screen,
        wrapped; unknown /commands get a hint."""
        sent = []

        def fake(prompt, system, on_text, stop, session=None, keep=False, **kw):
            sent.append(prompt)
            text = "word " * 60
            on_text(text)
            return text, "s1"
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            app, out = run_cli(["1", "hello", "/oops", "2", "q"], engine="account")
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old
        self.assertEqual(sent, ["hello"], "only the real message went to Claude")
        self.assertIn("There's no /oops command", out)
        self.assertIn("POLISH", out)
        chat = out[out.index("claude › "):out.index("/oops")]
        self.assertTrue(all(len(line) <= app.width + 2 for line in chat.split("\n")), "answer wrapped to the width")
        self.assertEqual(out.count("CHAT ·"), 1, "the chat isn't redrawn after every answer")

    def test_flow_wraps_streamed_text(self):
        got = []
        f = cli.Flow(got.append, 30, indent="    ")
        for piece in ["The quick brown fox jumps ", "over the lazy dog and keeps", " running far away.\nNew line"]:
            f.feed(piece)
        f.end()
        lines = "".join(got).split("\n")
        self.assertTrue(all(len(l.rstrip()) <= 30 for l in lines), lines)
        self.assertEqual(" ".join(w for l in lines for w in l.split()),
                         "The quick brown fox jumps over the lazy dog and keeps running far away. New line")

    def test_humanise_stopped_or_failed_keeps_text(self):
        def fake(prompt, system, on_text, stop, session=None, keep=False, **kw):
            raise RuntimeError("Claude Code isn't logged in to your Claude account. Press Connect Claude… → ② Log in, "
                               "then try again.")
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            app, out = run_cli(["2", "h", "q"], text="My own text.", engine="account")
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old
        self.assertEqual(app.text, "My own text.")
        self.assertIn("6 AI → n (log", out, "the message names the terminal's keys")

    def test_write_without_claude_points_to_connect(self):
        old = ht.find_claude_cli
        ht.find_claude_cli = lambda: None
        try:
            app, out = run_cli(["1", "", "q"], engine="account")
        finally:
            ht.find_claude_cli = old
        self.assertIn("isn't connected", out)
        self.assertIn("AI · which one", out, "Enter went to the AI screen")

    def test_pick_the_ai_and_model(self):
        """6 AI: pick the model (one key), it's saved, used for Claude, and shown in the title bar."""
        seen = {}

        def fake(prompt, system, on_text, stop, session=None, keep=False, model=None):
            seen["model"] = model
            on_text("Hi.")
            return "Hi.", "s1"
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            app, out = run_cli(["6", "a", "h", "1", "hello", "", "q"])
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old
        self.assertEqual(seen["model"], "haiku")
        self.assertEqual(ht.load_config()["claude_model"], "haiku")
        self.assertIn("Claude Haiku", out)
        app, _ = run_cli(["6", "e", "q"])
        self.assertEqual(ht.load_config()["claude_model"], "", "e goes back to the default model")

    def test_connect_api_key_and_claude_app(self):
        path = os.path.join(_HOME, "claude_desktop_config.json")
        old = ht.claude_config_path
        ht.claude_config_path = lambda: path
        try:
            app, out = run_cli(["6", "k", "c", "q"], secret="sk-ant-test")     # k = API key, c = Claude app on
        finally:
            ht.claude_config_path = old
        self.assertEqual(ht.load_config()["claude_api_key"], "sk-ant-test")
        self.assertEqual(app.engine, "claude")
        self.assertTrue(os.path.exists(path))

    def test_plain_output_has_no_colour_codes(self):
        _, out = run_cli(["q"])
        self.assertNotIn("\033[", out)

    def test_one_keypress(self):
        """On a real terminal a single key picks: no Enter. Esc goes home, Enter does the main thing."""
        app, out = run_cli([], presses=["5", "p", "esc", "3", "", "q"], text="Hi there.")
        self.assertFalse(app.s["pauses"], "settings: p toggled pauses with one key")
        self.assertEqual("".join(FakeTypist.last.typed), "Hi there.", "Enter on Type started typing")

    def test_yes_no_is_one_key(self):
        ht.save_config({"claude_api_key": "sk-ant-old"})
        app, out = run_cli([], presses=["6", "k", "y", "q"], secret="sk-ant-new")   # "Change the saved key?" y
        self.assertIn("yes", out)
        self.assertEqual(ht.load_config()["claude_api_key"], "sk-ant-new")


class QuickCommands(unittest.TestCase):
    """One-line commands with no menus: human_typer_cli.py fix notes.txt, and so on."""

    def setUp(self):
        ht.save_config({})

    def run_cmd(self, argv):
        out = io.StringIO()
        app = cli.CLI(ht, read=lambda p="": "", out=out, colour=False, typist_factory=FakeTypist)
        app.pause = lambda: None
        old = sys.stdout
        sys.stdout = out
        try:
            code = cli.quick(app, cli.parse(argv))
        finally:
            sys.stdout = old
        return code, out.getvalue(), app

    def file(self, text):
        path = os.path.join(_HOME, "in.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_fix(self):
        code, out, _ = self.run_cmd(["fix", self.file("i went to teh shop and we was tired"), "--level", "4"])
        self.assertEqual((code, out.strip()), (0, "I went to the shop and we were tired."))

    def test_check_and_ai_check(self):
        _, out, _ = self.run_cmd(["check", self.file("i went to teh shop")])
        self.assertIn("teh  →  the", out)
        _, out, _ = self.run_cmd(["ai-check", self.file(
            "Furthermore, it is important to note that technology plays a crucial role in reshaping the "
            "landscape, paving the way for innovation. In conclusion, it remains essential.")])
        self.assertIn("AI-style score", out)

    def test_type_with_options(self):
        code, out, app = self.run_cmd(["type", self.file("Hello there!"), "--wpm", "90", "--style", "messy"])
        self.assertEqual(code, 0)
        self.assertEqual("".join(FakeTypist.last.typed), "Hello there!")
        self.assertEqual((app.s["wpm"], app.s["variation"]), (90, 60))

    def test_ask_and_write(self):
        def fake(prompt, system, on_text, stop, session=None, keep=False, **kw):
            text = "Hi Sam, could i have Friday off?"
            on_text(text)
            return text, "s1"
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            code, out, _ = self.run_cmd(["ask", "write", "an", "email"])
            self.assertEqual(out.strip(), "Hi Sam, could i have Friday off?")
            code, out, app = self.run_cmd(["write", "an email", "--no-humanise", "--level", "4", "-y"])
            self.assertEqual("".join(FakeTypist.last.typed), "Hi Sam, could I have Friday off?")
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old

    def test_ai_and_model_options(self):
        seen = {}

        def fake(prompt, system, on_text, stop, session=None, keep=False, model=None):
            seen["model"] = model
            on_text("ok")
            return "ok", "s1"
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            code, out, app = self.run_cmd(["ask", "hi", "--ai", "account", "--model", "sonnet"])
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old
        self.assertEqual((code, seen["model"], app.engine), (0, "sonnet", "account"))
        _, _, app = self.run_cmd(["fix", self.file("x"), "--model", "llama3.2"])
        self.assertEqual((app.engine, app.model), ("local", "llama3.2"))

    def test_nothing_to_do(self):
        code, _, _ = self.run_cmd(["fix", self.file("   ")])
        self.assertEqual(code, 1)

if __name__ == "__main__":
    unittest.main()
