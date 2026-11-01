# Human Typer

Paste in any text, choose how many **words per minute** you want, then click into a Word document. Human Typer types
the text out key by key, like a person would.

![Human Typer window](screenshot.png)

## What it does

- **Any speed you like.** Use the slider (5–200 WPM), type a number into the box (up to 2000), or press a preset
  (25, 40, 60, 90 or 120). You can change the speed **while it's typing** and it speeds up or slows down straight away.
- **Human rhythm.** Keys don't come at a perfectly even beat. It slows down between words, stops for a breath after
  commas and full stops, waits a bit longer at new lines, and sometimes stops to "think".
- **Typos it fixes itself.** It sometimes hits a key next to the right one, notices, presses Backspace, and types
  the right letter. Sometimes it only notices one letter later. Set this to 0 if you don't want any typos.
- **Speed stays exact.** Pauses and typos are included in the timing, so 60 WPM really takes as long as 60 WPM should
  (one "word" = 5 characters, the same rule typing tests use).
- **Pause and stop.** Push the mouse into the **top-left corner** of the screen to stop, on any computer. On Windows,
  **F8** also pauses and resumes and **Esc** stops, even while Word is the active window. When you resume it counts
  down 3 seconds first, so you have time to click back into the document.
- The window shows how many words are in your text and about how long it will take.

## Setting it up (Windows)

1. Install Python from <https://www.python.org/downloads/>. While installing, tick **"Add Python to PATH"**.
2. Double-click **`Start Human Typer (Windows).bat`**. The first time, it downloads one small helper (`pynput`), then the
   window opens.

## Setting it up (Mac)

1. Install Python from <https://www.python.org/downloads/> (the big yellow download button, then open the file and
   click through the installer). Use this one rather than Apple's built-in Python, which can show a blank window.
2. Double-click **`start_mac.command`**. If the Mac says it can't be opened, **right-click** it, choose **Open**, then
   **Open** again. The first time, it downloads one small helper (`pynput`), then the window opens.
3. **Give it permission to press keys.** The first time you press Start, the Mac asks for this. Go to
   **System Settings → Privacy & Security → Accessibility**, turn on **Terminal**, then close Human Typer and open it
   again. Without this the Mac quietly ignores the key presses and nothing gets typed.
4. **To stop on a Mac:** push the mouse into the **top-left corner** of the screen, or press the **Stop** button. (The
   F8 and Esc shortcuts are Windows-only, because on a Mac they can make the window crash.)

If double-clicking does nothing, open the **Terminal** app, type `bash ` (with a space), drag `start_mac.command` into
the Terminal window and press Return.

You can also start it from a terminal: `pip install pynput`, then `python human_typer.py`.

## How to use it

1. Copy your text and press **Paste** (or click in the box and press Ctrl+V).
2. Pick your speed.
3. Press **Start typing**.
4. **Click inside your Word document** where the text should go, before the countdown ends (5 seconds by default).
5. Keep your hands off the keyboard and mouse until it finishes. To stop it, push the mouse into the top-left corner
   of the screen (or press **Esc** on Windows).

## Tips for Word

Word changes some things as you type. The text still ends up right, but it may look a little different:

- `"quotes"` become curly quotes, and `--` can become a dash.
- A line starting with `1.` or `-` can turn into a numbered or bulleted list.
- `(c)` becomes ©, and some words get auto-corrected.

To get an exact copy, turn these off in Word: **File → Options → Proofing → AutoCorrect Options** (on a Mac: **Word → Preferences → AutoCorrect**), then the
**AutoCorrect** and **AutoFormat As You Type** tabs.

Other tips:

- If you click somewhere else while it's typing, the letters go there instead. Pause it first.
- **Keep this window on top** keeps the app visible over Word, so you can always reach the buttons.
- It works in other programs too: Google Docs, Notepad, email and so on.
