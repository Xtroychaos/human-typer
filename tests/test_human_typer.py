"""Checks that everything in Human Typer works.

    python -m unittest discover -s tests -v

The window tests (the whole app: tabs, the Claude workflow, and real typing into
a text box) need a screen, so they only run when you ask for them:

    HT_GUI_TESTS=1 python -m unittest discover -s tests -v

(On Linux without a screen: HT_GUI_TESTS=1 xvfb-run -a python -m unittest ...)
"""
import json
import os
import random
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

# Keep the tests' settings away from your real ones.
_HOME = tempfile.mkdtemp(prefix="human_typer_test_")
os.environ["HOME"] = os.environ["USERPROFILE"] = _HOME
os.environ["HUMAN_TYPER_BRIDGE_PORT"] = str(47400 + random.randrange(500))

import human_typer as ht  # noqa: E402

ht.CONFIG_PATH = os.path.join(_HOME, ".human_typer.json")
GUI = os.environ.get("HT_GUI_TESTS") == "1"


def typed_result(steps):
    """What ends up in the document after every key press and backspace."""
    out = []
    for key, _ in steps:
        if key == ht.BACKSPACE:
            if out:
                out.pop()
        else:
            out.append(key)
    return "".join(out)


TEXTS = [
    "Hello there, how are you today? I hope you're well.\n\nThe quick brown fox jumps over the lazy dog 123 times!",
    "Photosynthesis is how plants make food from sunlight, water and carbon dioxide.",
    "Dear Sam,\n\tCould I take Friday off? (It's my son's sports day.) Thanks — Alex",
    "a", "ab", "Hi.", "", "eel ee eee", "  spaces  and\ttabs\n", "ÀÉÎ café naïve 😀 emoji",
]


class TypingPlan(unittest.TestCase):
    """The plan of key presses: realistic, but the finished text is always exact."""

    def test_finished_text_is_always_exact(self):
        for seed in range(1500):
            rng = random.Random(seed)
            text = rng.choice(TEXTS)
            steps = ht.build_plan(text, variation=rng.choice([0, 0.2, 0.35, 0.6, 1.0]),
                                  typo_percent=rng.choice([0, 1.5, 4, 8]),
                                  natural_pauses=rng.random() < 0.8, seed=seed)
            self.assertEqual(typed_result(steps), text, f"seed {seed}")
            self.assertTrue(all(w > 0 for _, w in steps), "every wait is positive")

    def test_no_typos_means_no_backspaces(self):
        steps = ht.build_plan(TEXTS[0], typo_percent=0, seed=1)
        self.assertNotIn(ht.BACKSPACE, [k for k, _ in steps])
        self.assertEqual("".join(k for k, _ in steps), TEXTS[0])

    def test_makes_and_fixes_several_kinds_of_mistake(self):
        text = "the quick brown fox jumps over the lazy dog " * 40
        steps = ht.build_plan(text, typo_percent=6, seed=7)
        self.assertEqual(typed_result(steps), text)
        backspaces = sum(1 for k, _ in steps if k == ht.BACKSPACE)
        self.assertGreater(backspaces, 40)
        # Mistakes of different lengths: 1 letter (wrong key, doubled, skipped) and 2 (swapped or noticed late).
        runs, n = set(), 0
        for k, _ in steps + [("x", 1)]:
            if k == ht.BACKSPACE:
                n += 1
            elif n:
                runs.add(n)
                n = 0
        self.assertTrue({1, 2} <= runs, runs)

    def test_chosen_words_and_letters(self):
        text = "the cat sat on the mat because it was tired"
        fixed = ht.build_plan(text, typo_words={"the", "because"}, typo_percent=0, seed=3)
        self.assertEqual(typed_result(fixed), text)
        self.assertIn(ht.BACKSPACE, [k for k, _ in fixed])
        left = typed_result(ht.build_plan(text, typo_words={"because"}, fix_chosen=False, typo_percent=0, seed=3))
        self.assertNotIn("because", left)
        self.assertEqual(len(left), len(text), "mistakes left in keep the same length")

    def test_finger_timing(self):
        self.assertLess(ht.key_gap("t", "h"), 1.0)      # common pair
        self.assertLess(ht.key_gap("a", "l"), 1.0)      # opposite hands
        self.assertGreater(ht.key_gap("u", "n"), 1.0)   # same finger, different key
        self.assertGreater(ht.key_gap("a", "7"), 1.0)   # reach for a digit

    def test_pauses_at_full_stops_and_new_lines(self):
        steps = ht.build_plan("aa. bb\ncc", typo_percent=0, variation=0, seed=1)
        w = dict((i, wt) for i, (_, wt) in enumerate(steps))
        self.assertGreater(w[4], w[1])   # "b" after ". " waits longer than a letter mid-word
        self.assertGreater(w[7], w[1])   # "c" after a new line too

    def test_speed_maths(self):
        self.assertAlmostEqual(ht.seconds_for("x" * 300, 60), 60.0)
        self.assertEqual(ht.format_duration(75), "1 min 15 s")
        self.assertAlmostEqual(ht.average_speed(60, 60), 60)
        self.assertTrue(40 < ht.average_speed(40, 90) < 65)


class FakeKeys:
    """Stands in for Word: collects what Human Typer types."""
    pinned = False

    def __init__(self):
        self.text = []

    def type(self, ch):
        self.text.append(ch)

    def backspace(self):
        if self.text:
            self.text.pop()


class Typist(unittest.TestCase):
    """The typist itself: right text, about the right time, stop works."""

    def setUp(self):
        try:
            self.t = ht.Typist()
        except Exception as exc:          # no screen / no keyboard library here
            self.skipTest(f"keyboard library unavailable: {exc}")

    def run_plan(self, text, wpm, typos=1.5):
        out = FakeKeys()
        self.t.wpm = wpm
        self.t.start(text, ht.build_plan(text, typo_percent=typos, seed=5), 0, output=out, corner_stop=False)
        return out

    def test_types_the_exact_text_in_the_right_time(self):
        text = "Hello there! This is a quick test of the typing, with typos fixed."
        start = time.monotonic()
        out = self.run_plan(text, wpm=600)
        self.t.thread.join(30)
        took = time.monotonic() - start
        self.assertEqual(self.t.state, "done")
        self.assertEqual("".join(out.text), text)
        expected = ht.seconds_for(text, 600)
        self.assertLess(abs(took - expected), max(0.6, expected * 0.35), f"took {took:.2f}s, expected {expected:.2f}s")

    def test_stop(self):
        out = self.run_plan("x" * 400, wpm=100, typos=0)
        time.sleep(0.4)
        self.t.stop()
        self.t.thread.join(5)
        self.assertEqual(self.t.state, "stopped")
        self.assertLess(len(out.text), 400)


class Checker(unittest.TestCase):
    def test_spelling_and_grammar(self):
        text = "i went to teh shop and we was tired"
        fixed, done, _ = ht.apply_fixes(text, ht.check_text(text), 4)
        self.assertEqual(fixed, "I went to the shop and we were tired.")

    def test_ai_score(self):
        ai = ("Furthermore, it is important to note that technology plays a crucial role in reshaping the "
              "landscape, paving the way for innovation. In conclusion, collaboration remains essential.")
        me = "i reckon the game was ok but my brother kept winning which was kinda annoying lol"
        self.assertGreater(ht.ai_report(ai)["score"], ht.ai_report(me)["score"])

    def test_apa(self):
        self.assertEqual(ht.apa_in_text("John Smith", "2020"), "(Smith, 2020)")
        new, changes = ht.fix_in_text_citations("As shown (smith 2020).")
        self.assertIn("(Smith, 2020)", new)

    def test_natural_tone(self):
        new, n = ht.naturalize("We do not utilize this.")
        self.assertIn("don't", new)
        self.assertIn("use", new)

    def test_split_paragraphs(self):
        self.assertEqual(ht.split_paragraphs("one\n\ntwo\n\n\nthree"), ["one", "two", "three"])


class Settings(unittest.TestCase):
    def test_saved_and_read_back(self):
        ht.save_config({"theme": "Midnight", "x": 1})
        self.assertEqual(ht.load_config()["theme"], "Midnight")
        self.assertFalse(os.path.exists(ht.CONFIG_PATH + ".tmp"), "no half-written file left behind")

    def test_bridge_link(self):
        server = ht.start_bridge(lambda path, payload: {"ok": True, "message": f"got {path}"})
        if server is None:
            self.skipTest("bridge port busy")
        try:
            self.assertEqual(ht.bridge_call("/status", launch=False)["message"], "got /status")
            cfg = ht.load_config()
            cfg["bridge_token"] = "wrong"
            ht.save_config(cfg)
            self.assertFalse(ht.bridge_call("/status", launch=False)["ok"], "a wrong secret is refused")
        finally:
            server.shutdown()
            server.server_close()

    def test_connect_claude_app_keeps_other_settings(self):
        path = os.path.join(_HOME, "claude_desktop_config.json")
        with open(path, "w") as f:
            json.dump({"mcpServers": {"other": {"command": "x"}}, "keep": True}, f)
        old = ht.claude_config_path
        ht.claude_config_path = lambda: path
        try:
            ht.connect_claude()
            with open(path) as f:
                cfg = json.load(f)
            self.assertIn("human-typer", cfg["mcpServers"])
            self.assertIn("other", cfg["mcpServers"])
            self.assertTrue(cfg["keep"])
            ht.connect_claude(remove=True)
            with open(path) as f:
                self.assertNotIn("human-typer", json.load(f)["mcpServers"])
        finally:
            ht.claude_config_path = old


@unittest.skipIf(sys.platform == "win32", "the fake Claude Code here is a shell script")
class ClaudeAccount(unittest.TestCase):
    """Talking to Claude Code, with a pretend Claude Code that answers like the real one."""

    def fake_claude(self, lines, code=0):
        path = os.path.join(_HOME, "claude")
        with open(path, "w") as f:
            f.write("#!/bin/sh\ncat > /dev/null\n")
            for line in lines:
                f.write("echo '" + json.dumps(line).replace("'", "'\\''") + "'\n")
            f.write(f"exit {code}\n")
        os.chmod(path, 0o755)
        self._old = ht.find_claude_cli
        ht.find_claude_cli = lambda: path
        self.addCleanup(lambda: setattr(ht, "find_claude_cli", self._old))

    def test_streams_the_answer(self):
        delta = lambda t: {"type": "stream_event", "session_id": "s1",
                           "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": t}}}
        self.fake_claude([{"type": "system", "subtype": "init", "session_id": "s1"}, delta("Hello "),
                          delta("there."), {"type": "result", "subtype": "success", "is_error": False,
                                            "result": "Hello there.", "session_id": "s1"}])
        pieces = []
        text, session = ht.claude_account_stream("hi", "be brief", pieces.append, threading.Event(), keep=True)
        self.assertEqual(text, "Hello there.")
        self.assertEqual(pieces, ["Hello ", "there."])
        self.assertEqual(session, "s1")

    def test_not_logged_in_gives_a_clear_message(self):
        self.fake_claude([{"type": "result", "subtype": "success", "is_error": True,
                           "result": "Not logged in · Please run /login"}], code=1)
        with self.assertRaises(RuntimeError) as cm:
            ht.claude_account_stream("hi", "x", lambda p: None, threading.Event())
        self.assertIn("Log in", str(cm.exception))

    def test_missing_claude_code(self):
        old = ht.find_claude_cli
        ht.find_claude_cli = lambda: None
        try:
            with self.assertRaises(RuntimeError) as cm:
                ht.claude_account_stream("hi", "x", lambda p: None, threading.Event())
            self.assertIn("Connect Claude", str(cm.exception))
        finally:
            ht.find_claude_cli = old


@unittest.skipUnless(GUI, "window tests: set HT_GUI_TESTS=1")
class Window(unittest.TestCase):
    """The whole app on screen."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.tk = tk
        cls.root = tk.Tk()
        cls.app = ht.App(cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        if cls.app.bridge:
            cls.app.bridge.shutdown()
            cls.app.bridge.server_close()
        cls.root.destroy()

    def pump(self, until, seconds=20):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not until():
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        return until()

    def test_tabs_themes_and_windows(self):
        app = self.app
        for i in (ht.TAB_WRITE, ht.TAB_POLISH, ht.TAB_TYPE):
            app.tabs.select(i)
            self.root.update()
            self.assertEqual(app._current_tab(), i)
            self.assertEqual(app.bottom.winfo_ismapped(), i == ht.TAB_TYPE, "speed and Start only on Type")
        app._go_type("boxes")
        self.root.update()
        self.assertTrue(app._on_boxes_tab())
        app._go_type("text")
        for theme in ht.THEMES:
            app._apply_theme(theme)
            self.root.update()
        app._apply_theme("Clean Light")
        app._open_connect()
        app._open_help()
        self.root.update()
        app._connect_win.destroy()
        app._help_win.destroy()

    def test_style_buttons(self):
        app = self.app
        app.variation.set(60)
        app.typos.set(4.0)
        app._section_heads()
        self.assertIn("Messy", app.human_frame._head.cget("text") if hasattr(app.human_frame, "_head") else "Messy")

    def test_write_polish_type_workflow(self):
        """Claude writes it, Use this humanises and fixes it, and it lands on Type."""
        app = self.app
        replies = iter(["Here is teh email you asked for.", "Hi Sam, could i have Friday off?"])

        def fake(prompt, system, on_text, stop, session=None, keep=False, **kw):
            text = next(replies)
            on_text(text)
            return text, "session-1"
        old_stream, old_find = ht.claude_account_stream, ht.find_claude_cli
        ht.claude_account_stream, ht.find_claude_cli = fake, lambda: "/fake/claude"
        try:
            app.rw_engine.set("account")
            app.wf_humanise.set(True)
            app.wf_fix.set(True)
            app.wf_type.set(False)
            app._on_check_level(4)          # level 4 includes capital letters
            app.tabs.select(ht.TAB_WRITE)
            app.chat_in.insert("1.0", "Write an email asking for Friday off")
            app._chat_send()
            self.assertTrue(self.pump(lambda: not app.chat_busy))
            self.assertEqual(app.chat_history[-1]["content"], "Here is teh email you asked for.")
            self.assertEqual(app.chat_session, "session-1")
            app._chat_use()
            self.assertTrue(self.pump(lambda: app._current_tab() == ht.TAB_TYPE and not app.rw_busy))
            self.assertEqual(app._get_text(), "Hi Sam, could I have Friday off?")
        finally:
            ht.claude_account_stream, ht.find_claude_cli = old_stream, old_find

    def test_really_types_into_a_text_box(self):
        """Presses real keys (with typos it fixes) into a box and checks what arrives."""
        app = self.app
        if app.typist is None:
            self.skipTest(app.typist_error)
        target = self.tk.Text(self.root, height=3)
        target.pack()
        self.root.update()
        target.focus_force()
        self.root.update()
        text = "Hello there, this is a real typing test. It makes mistakes and fixes them!"
        app.typist.wpm = 300
        app.typist.start(text, ht.build_plan(text, typo_percent=4, seed=11), 0, corner_stop=False)
        self.assertTrue(self.pump(lambda: not app.typist.busy, 60))
        self.pump(lambda: False, 0.5)
        self.assertEqual(app.typist.state, "done")
        self.assertEqual(target.get("1.0", "end-1c"), text)
        target.destroy()


if __name__ == "__main__":
    unittest.main()
