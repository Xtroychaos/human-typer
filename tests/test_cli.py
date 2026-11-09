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


def run_cli(keys, **kw):
    """Run the terminal app with these lines typed in. Returns (app, everything it printed)."""
    keys = list(keys)
    out = io.StringIO()

    def read(prompt=""):
        out.write(prompt)
        if not keys:
            raise EOFError
        return keys.pop(0)
    key = kw.pop("secret", "")
    app = cli.CLI(ht, read=read, out=out, colour=False, typist_factory=FakeTypist, secret=lambda label: key)
    for k, v in kw.items():
        setattr(app, k, v)
    try:
        app.run()
    except EOFError:
        pass
    return app, out.getvalue()


class Menus(unittest.TestCase):
    def setUp(self):
        ht.save_config({})
        self._old = ht.mac_permission_problem
        ht.mac_permission_problem = lambda: None
        self.addCleanup(lambda: setattr(ht, "mac_permission_problem", self._old))

    def test_main_menu_and_quit(self):
        app, out = run_cli(["q"])
        for word in ("WORKFLOW", "[1] Write", "[2] Polish", "[3] Type", "[4] Boxes", "[6] Connect", "Bye"):
            self.assertIn(word, out)

    def test_help(self):
        _, out = run_cli(["?", "", "q"])
        self.assertIn("How it works", out)
        self.assertIn("Careful, Natural or Messy", out)

    def test_paste_text(self):
        app, out = run_cli(["t", "p", "Hello there.", "Second line.", ".", "b", "q"])
        self.assertEqual(app.text, "Hello there.\nSecond line.")
        self.assertIn("4 words", out)

    def test_settings_are_saved(self):
        run_cli(["5", "1", "90", "3", "Messy", "2", "40-80", "8", "3", "b", "q"])
        s = ht.load_config()["cli"]
        self.assertEqual((s["wpm"], s["variation"], s["typos"], s["random"], s["delay"]), (90, 60, 4.0, [40, 80], 3))
        app, out = run_cli(["q"])
        self.assertIn("Messy", out)                     # remembered next time
        self.assertIn("40–80 WPM", out)

    def test_polish_check_and_fix_and_undo(self):
        text = "i went to teh shop and we was tired"
        app, out = run_cli(["2", "l", "4", "c", "y", "", "b", "q"], text=text)
        self.assertIn("teh", out)
        self.assertEqual(app.text, "I went to the shop and we were tired.")
        app, _ = run_cli(["2", "f", "", "u", "", "b", "q"], text=text)
        self.assertEqual(app.text, text, "undo puts it back")

    def test_ai_check_and_apa(self):
        text = ("Furthermore, it is important to note that technology plays a crucial role in reshaping the "
                "landscape, paving the way for innovation (smith 2020). In conclusion, it remains essential.")
        app, out = run_cli(["2", "i", "", "r", "", "m", "n", "John Smith", "2020", "Plants", "n", "BBC",
                            "https://bbc.com", "", "b", "q"], text=text)
        self.assertIn("AI-style score", out)
        self.assertIn("(Smith, 2020)", app.text)
        self.assertIn("Smith, J. (2020)", out)

    def test_type(self):
        app, out = run_cli(["3", "", "", "q"], text="Hello there, typing test!")
        self.assertEqual("".join(FakeTypist.last.typed), "Hello there, typing test!")
        self.assertIn("Finished", out)

    def test_boxes_by_tab_and_by_spots(self):
        app, out = run_cli(["4", "p", "First answer.", "", "Second answer.", ".", "3", "", "", "b", "q"])
        self.assertEqual("".join(FakeTypist.last.typed), "First answer.\tSecond answer.")
        self.assertTrue(all(b["done"] for b in app.boxes))
        app, out = run_cli(["4", "p", "One.", "", "Two.", ".", "2", "", "", "", "", "b", "q"])
        self.assertEqual("".join(FakeTypist.last.typed), "One.Two.")
        self.assertEqual(FakeTypist.last.jumps_run, 2, "clicked each spot")
        self.assertEqual(app.boxes[0]["spot"], (120, 340))

    def test_write_and_workflow(self):
        """Chat with (a pretend) Claude, then /use: humanise, fix, type."""
        replies = iter(["Here is teh email.", "Hi Sam, could i have Friday off?"])

        def fake(prompt, system, on_text, stop, session=None, keep=False):
            text = next(replies)
            on_text(text)
            return text, "s1"
        old = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            ht.save_config({"cli": {"check_level": 4}})
            app, out = run_cli(["1", "Write an email asking for Friday off", "/use", "y", "", "", "q"],
                               engine="account")
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old
        self.assertIn("claude › Here is teh email.", out)
        self.assertEqual(app.session, "s1")
        self.assertEqual(app.text, "Hi Sam, could I have Friday off?")
        self.assertEqual("".join(FakeTypist.last.typed), app.text)

    def test_write_without_claude_offers_connect(self):
        old = ht.find_claude_cli
        ht.find_claude_cli = lambda: None
        try:
            app, out = run_cli(["1", "n", "q"], engine="account")
        finally:
            ht.find_claude_cli = old
        self.assertIn("isn't connected", out)

    def test_connect_api_key_and_claude_app(self):
        path = os.path.join(_HOME, "claude_desktop_config.json")
        old = ht.claude_config_path
        ht.claude_config_path = lambda: path
        try:
            app, out = run_cli(["6", "k", "", "a", "", "b", "q"], secret="sk-ant-test")
        finally:
            ht.claude_config_path = old
        self.assertEqual(ht.load_config()["claude_api_key"], "sk-ant-test")
        self.assertEqual(app.engine, "claude")
        self.assertTrue(os.path.exists(path))

    def test_plain_output_has_no_colour_codes(self):
        _, out = run_cli(["q"])
        self.assertNotIn("\033[", out)


if __name__ == "__main__":
    unittest.main()
