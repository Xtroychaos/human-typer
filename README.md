# Human Typer

Paste in any text, choose how many **words per minute** you want, then click into a Word document. Human Typer types
the text out key by key, like a person would.

![Human Typer window](screenshot.png)

## What it does

- **Any speed you like.** Use the slider (1–300 WPM), type a number into the box (up to 2000), or press a preset
  (25, 40, 60, 90 or 120). You can change the speed **while it's typing** and it speeds up or slows down straight away.
- **Random speed.** Tick **Random speed between** and pick two speeds, like 40 and 90. While it types, the speed keeps
  wandering between them: it speeds up for a few words, slows down, and now and then hits the very slowest or fastest.
- **Type in the background.** With Word, it can type while you keep using your computer. See
  [Typing in the background](#typing-in-the-background).
- **Human rhythm.** Keys don't come at a perfectly even beat. It slows down between words, stops for a breath after
  commas and full stops, waits a bit longer at new lines, and sometimes stops to "think".
- **Typos it fixes itself.** It sometimes hits a key next to the right one, notices, presses Backspace, and types
  the right letter. Sometimes it only notices one letter later. Set this to 0 if you don't want any typos.
- **Speed stays exact.** Pauses and typos are included in the timing, so 60 WPM really takes as long as 60 WPM should
  (one "word" = 5 characters, the same rule typing tests use).
- **Boxes.** Split your text into paragraphs, one per box, and type each one into a different place in your
  document, or fill a Word table cell by cell. See [Boxes](#boxes-one-paragraph-per-box).
- **Auto-click spots.** Show it where each box goes on your screen, and it clicks there and types that box.
- **Connect a Word document.** Pick your worksheet, choose which table cell each paragraph goes in, and it jumps into
  each cell and types there. See [Connect a Word document](#connect-a-word-document-and-pick-the-cells).
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

**If the Mac keeps asking for permission even though Human Typer is switched on:** every new download counts as a
new app to your Mac, so the old switch no longer works. Quit Human Typer (**Cmd+Q**), go to
**System Settings → Privacy & Security → Accessibility**, click **Human Typer** and press the **–** button to remove it
(remove every copy). Make sure the app is in **Applications**, not Downloads. Then open it, press Start, turn it on when
asked, and quit and reopen it once more.

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

## Boxes: one paragraph per box

Use the **Boxes** tab when the text needs to go into different places, like the answer spaces on a worksheet, text
boxes, or the cells of a table.

![The Boxes tab](screenshot-boxes.png)

1. Copy your text and press **Paste & split**. Each paragraph gets its own box. (Paragraphs are split at blank lines.
   If there are none, each line gets its own box.) You can also press **Split the Text tab**, type into the boxes
   yourself, press **+ Add box**, or remove a box with **✕**.
2. Choose how to get from one box to the next:
   - **I click into each box myself.** For text boxes or spaces spread around the page. Press **Type next box**, click
     into the matching spot in Word, and it types that box. Done boxes turn green with a ✓ and the next one turns blue.
     On Windows, you can instead click into the spot in Word and press **F9**, and it starts straight away.
   - **Auto-click my spots.** Works anywhere: Word text boxes, tables, Google Docs, websites. On each box, press
     **Set spot**. Human Typer hides, and you have 4 seconds to point the mouse at the place where that box should be
     typed (just point, don't click). Press **Show** to check a spot: the mouse jumps there. Then press
     **Click & type**: Human Typer gets out of the way, clicks each spot and types its box there, then comes back when
     it's done. Don't move the Word window or scroll the page after setting the spots, or the spots won't line up
     anymore. To stop, push the mouse into the top-left corner of the screen.
   - **Press Tab (for a table in Word).** Click into the first cell of the table and press **Type all boxes**. It types
     box 1, presses Tab to jump to the next cell, types box 2, and so on. (In the last cell of a Word table, Tab adds a
     new row.)
3. **Type this** on any box types just that box. **Start over** clears the ✓ marks.

## Connect a Word document and pick the cells

If your worksheet is a **table** in Word (for example questions in one column and answers in the other), Human Typer
can open it, show you every cell, and jump into the cells you pick by itself.

![Boxes connected to a Word document](screenshot-word.png)

1. Save your document as a `.docx` file.
2. On the **Boxes** tab, put your answers in the boxes (for example with **Paste & split**).
3. Press **Connect Word document…** and pick the file. Human Typer opens it in Word and reads its tables.
4. Under each box, **Goes in:** shows which cell it will be typed into. Each cell is named by the question next to it,
   like *“2. What is photosynthesis?” – row 3, cell 2*. Human Typer fills them in order into the empty cells to start
   with; change any of them, or pick **— skip this box —**. **Fill in order** sets them back to the empty cells in order.
5. Press **Type into Word**. Word comes to the front, and Human Typer clicks into each cell for you and types that box
   there. Keep your hands off the keyboard and mouse until it's done.

Good to know:

- It types **after** anything already in a cell, so a label like "Name:" stays (it adds a space after a `:`, or starts
  a new line otherwise).
- If you **pause** and click around, it jumps back into the right cell when you resume.
- It reads the cells from the saved file. If you change the table in Word, save and connect again.
- **Mac:** the first time, the Mac asks **"Human Typer wants access to control Microsoft Word"**. Click **OK**. If you
  clicked Don't Allow, turn it on in **System Settings → Privacy & Security → Automation → Human Typer → Microsoft Word**.
- **Windows:** if Word shows a yellow **Protected View** bar, click **Enable Editing** first.
- Text boxes and blank lines can't be picked this way. For those, use **I click each one**.

## Typing in the background

Normally Human Typer presses real keys, so Word has to stay in front and you can't touch the keyboard or mouse. Tick
**Type in the background** and it tells Word what to type directly instead. Word fills in live while you switch to other
apps, browse, or type somewhere else.

- **Text tab:** click in Word where the text should go, come back to Human Typer, and press **Start typing**. It types
  at Word's cursor, in the document at the front of Word.
- **Boxes tab:** works with **Word cells** (connect your document first). It moves Word's cursor into each cell without
  bringing Word to the front.
- It doesn't work with **I click**, **Auto-click my spots** or **Press Tab**, because those need real clicks and key
  presses. Turn the tick off to use them.
- Stop it with the **Stop** button. The mouse-corner stop and the F8/Esc keys are off in this mode, since you're using
  the mouse and keyboard yourself.
- **Mac:** the first time, click **OK** when the Mac asks to let Human Typer control Microsoft Word (or turn it on in
  **System Settings → Privacy & Security → Automation**). The Accessibility permission isn't needed for this mode.
- Avoid clicking around inside the same Word document while it types, or the text follows your cursor.

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
- **Anywhere:** `pip install -r requirements.txt`, then `python human_typer.py`.

## How the apps are made

Every time the code changes on `main`, GitHub builds the Mac and Windows apps on its own computers and puts them on
the Releases page (see `.github/workflows/build.yml`). The app icon is `icon.png`.
