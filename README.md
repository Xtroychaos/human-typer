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

## Download

Go to the **[Releases page](https://github.com/Xtroychaos/human-typer/releases/latest)** and download the file for
your computer:

| Your computer | Download |
| --- | --- |
| Mac with an Apple chip (M1, M2, M3, M4…, most Macs from 2021 on) | `HumanTyper-Mac-AppleSilicon.zip` |
| Older Mac with an Intel chip | `HumanTyper-Mac-Intel.zip` |
| Windows | `HumanTyper-Windows.exe` |

Not sure which Mac you have? Click the **Apple menu → About This Mac**. It says **Chip: Apple M…** or
**Processor: Intel**.

You don't need to install anything else.

### First time on a Mac

1. Double-click the downloaded zip to unzip it, then drag **Human Typer** into your **Applications** folder.
2. Open it. The Mac will say it can't check the app for malicious software, because the app isn't registered with
   Apple (that costs $99 a year). Click **Done**, then go to **System Settings → Privacy & Security**, scroll down and
   click **Open Anyway** next to Human Typer. On older macOS versions you can right-click the app and choose **Open**
   instead.
3. **Give it permission to press keys.** The first time you press Start, the Mac asks for this. Go to
   **System Settings → Privacy & Security → Accessibility** and turn on **Human Typer**. Then quit Human Typer and open
   it again. Without this the Mac quietly ignores the key presses and nothing gets typed.
4. **To stop on a Mac:** push the mouse into the **top-left corner** of the screen, or press the **Stop** button. (The
   F8 and Esc shortcuts are Windows-only, because on a Mac they can make the window crash.)

When you download a newer version, you may need to turn Human Typer off and on again in the Accessibility list.

### First time on Windows

1. Double-click **HumanTyper-Windows.exe**.
2. Windows may show **"Windows protected your PC"**, because the app isn't registered with Microsoft. Click
   **More info → Run anyway**.
3. Some antivirus programs are suspicious of any app that presses keys for you. If yours blocks it, allow it.

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

## Running it from the code (optional)

If you'd rather not use the downloaded app, you can run the Python file directly:

- **Mac:** install Python from <https://www.python.org/downloads/>, then double-click `start_mac.command`. In the
  Accessibility list, turn on **Terminal** instead of Human Typer.
- **Windows:** install Python (tick **"Add Python to PATH"**), then double-click `Start Human Typer (Windows).bat`.
- **Anywhere:** `pip install pynput`, then `python human_typer.py`.

## How the apps are made

Every time the code changes on `main`, GitHub builds the Mac and Windows apps on its own computers and puts them on
the Releases page (see `.github/workflows/build.yml`). The app icon is `icon.png`.
