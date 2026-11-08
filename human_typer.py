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
import re
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


# --------------------------------------------------------------------------- #
#  Natural tone: make stiff, formal text read like everyday writing
# --------------------------------------------------------------------------- #

def _match_case(original, replacement):
    if not replacement:
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


# Whole phrases that make emails and messages sound stiff -> plainer versions.
_NATURAL_PHRASES = [
    (r"I hope (this|my) (e-?mail|message) finds you well\.?", "Hope you're doing well."),
    (r"I hope you are doing well\.?", "Hope you're doing well."),
    (r"Please do not hesitate to (contact me|reach out|get in touch)( if you have any (further |other )?questions)?\.?",
     "Let me know if you have any questions."),
    (r"Do not hesitate to (contact me|reach out|get in touch)\.?", "Just let me know."),
    (r"Feel free to reach out( to me)?", "Just let me know"),
    (r"at your earliest convenience", "when you get a chance"),
    (r"Thank you (very much )?for your time and consideration\.?", "Thanks for your time."),
    (r"Thank you in advance for your (help|assistance|cooperation)\.?", "Thanks in advance."),
    (r"I would like to take this opportunity to", "I want to"),
    (r"I am writing to (inform you|let you know) that", "Just letting you know that"),
    (r"I wanted to (reach out|touch base)", "I wanted to check in"),
    (r"(It is|It's) (important|worth) (to note|noting) that ", ""),
    (r"In today's fast-paced world, ", ""),
    (r"In conclusion, ", "So, "),
    (r"As an AI( language model)?, ", ""),
    (r"in order to", "to"),
    (r"prior to", "before"),
    (r"a (wide )?(plethora|myriad|multitude) of", "lots of"),
    (r"(plethora|myriad|multitude) of", "lots of"),
    (r"(delve|dive deep) into", "dig into"),
    (r"delves into", "digs into"),
    (r"embark on", "start"),
    (r"a testament to", "proof of"),
    (r"with regard to|in regards? to", "about"),
    (r"due to the fact that", "because"),
    (r"at this point in time", "right now"),
    (r"(Additionally|Furthermore|Moreover|In addition), ", "Also, "),
    (r"(Therefore|Consequently|Thus), ", "So "),
    (r"However, ", "But "),
    (r"Certainly!", "Sure!"),
    (r"Absolutely!", "Sure!"),
]

# Single fancy words -> everyday words (all the forms of each word).
_NATURAL_WORDS = {
    "utilize": "use", "utilizes": "uses", "utilized": "used", "utilizing": "using",
    "utilise": "use", "utilises": "uses", "utilised": "used", "utilising": "using",
    "commence": "start", "commences": "starts", "commenced": "started", "commencing": "starting",
    "demonstrate": "show", "demonstrates": "shows", "demonstrated": "showed", "demonstrating": "showing",
    "ensure": "make sure", "ensures": "makes sure", "ensured": "made sure", "ensuring": "making sure",
    "assist": "help", "assists": "helps", "assisted": "helped", "assisting": "helping", "assistance": "help",
    "showcase": "show", "showcases": "shows", "showcased": "showed", "showcasing": "showing",
    "foster": "build", "fosters": "builds", "fostered": "built", "fostering": "building",
    "regarding": "about", "approximately": "about", "subsequently": "then", "numerous": "lots of",
    "comprehensive": "full", "crucial": "key", "pivotal": "key", "paramount": "really important",
    "seamless": "smooth", "seamlessly": "smoothly", "robust": "solid", "meticulous": "careful",
    "meticulously": "carefully", "endeavour": "try", "kindly": "please", "additionally": "also",
    "furthermore": "also", "moreover": "also", "nevertheless": "still", "nonetheless": "still",
    "commendable": "great", "invaluable": "really useful", "optimal": "best", "facilitate": "help with",
}

# Contractions. "is/are/will/would" only become short forms when a word follows,
# so "I know who you are." stays as it is.
_CONTRACTIONS = [
    (r"do not", "don't"), (r"does not", "doesn't"), (r"did not", "didn't"),
    (r"is not", "isn't"), (r"are not", "aren't"), (r"was not", "wasn't"), (r"were not", "weren't"),
    (r"have not", "haven't"), (r"has not", "hasn't"), (r"had not", "hadn't"),
    (r"will not", "won't"), (r"would not", "wouldn't"), (r"should not", "shouldn't"),
    (r"could not", "couldn't"), (r"cannot", "can't"), (r"can not", "can't"),
    (r"I am(?= \w)", "I'm"), (r"I have been", "I've been"), (r"we have been", "we've been"),
    (r"I will(?= \w)", "I'll"), (r"we will(?= \w)", "we'll"), (r"you will(?= \w)", "you'll"),
    (r"they will(?= \w)", "they'll"), (r"I would(?= \w)", "I'd"),
    (r"you are(?= \w)", "you're"), (r"we are(?= \w)", "we're"), (r"they are(?= \w)", "they're"),
    (r"it is(?= \w)", "it's"), (r"that is(?= \w)", "that's"), (r"there is(?= \w)", "there's"),
    (r"what is(?= \w)", "what's"), (r"here is(?= \w)", "here's"), (r"let us(?= (start|begin|go|see|get|try|move|look))", "let's"),
]


def naturalize(text):
    """
    Rewrite stiff, formal text so it reads more like everyday writing:
    contractions, plainer words, simpler email phrases, and ordinary
    punctuation (no long dashes or curly quotes). Returns (new_text, changes).
    """
    changes = 0

    def sub(pattern, repl, text, flags=re.IGNORECASE):
        nonlocal changes

        def fix(m):
            out = repl(m) if callable(repl) else _match_case(m.group(0), repl)
            return out

        new, n = re.subn(pattern, fix, text, flags=flags)
        changes += n
        return new

    # Punctuation people don't usually type by hand.
    text = sub(r"\s*—\s*", " - ", text, 0)           # long dash
    text = sub(r"(?<=\w)–(?=\w)", "-", text, 0)       # number ranges
    text = sub(r"\s–\s", " - ", text, 0)
    text = sub("[“”]", '"', text, 0)
    text = sub("[‘’]", "'", text, 0)
    text = sub("…", "...", text, 0)
    text = sub(r"\*\*(.+?)\*\*", lambda m: m.group(1), text, 0)   # **bold** from chat apps
    text = sub(r"(?m)^#{1,6} +", "", text, 0)                       # # headings
    text = sub(r"(?m)^• ?", "- ", text, 0)                      # bullets

    for pattern, repl in _NATURAL_PHRASES:
        # A removed phrase leaves a marker, so the next word can get a capital if it starts a sentence.
        text = sub(r"\b" + pattern, repl or "\x00", text)
    for word, repl in _NATURAL_WORDS.items():
        text = sub(r"\b" + word + r"\b", repl, text)
    for pattern, repl in _CONTRACTIONS:
        text = sub(r"\b" + pattern + r"\b", repl, text)

    # Removing a phrase can leave a sentence starting with a small letter.
    text = re.sub(r"(^|[.!?]\s+|\n\s*)\x00([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text, changes


# --------------------------------------------------------------------------- #
#  Check: typos, spelling (Australian), grammar and punctuation, by level
# --------------------------------------------------------------------------- #
#
# Levels (you choose how far down the list to fix):
#   1  mistakes that make a sentence confusing (needs a person to judge; not checked here)
#   2  spelling mistakes, typos and doubled words
#   3  grammar: "they was", their/there, your/you're, then/than, it's/its, a/an
#   4  punctuation, capital letters, missing apostrophes, very long sentences
#   5  very casual words and the same word repeated close together

LEVEL_NAMES = {
    1: "Only mistakes that make a sentence confusing",
    2: "+ spelling, typos and doubled words",
    3: "+ grammar (they was, their/there, your/you're, then/than, it's/its)",
    4: "+ punctuation, capitals, apostrophes, run-on sentences",
    5: "+ very casual wording and repeated words",
}


def _au_spellings():
    """American spelling -> Australian spelling."""
    pairs = {}

    def forms(us, au, endings=("", "s", "ed", "ing")):
        for e in endings:
            pairs[us + e] = au + e

    for us, au in [("color", "colour"), ("honor", "honour"), ("favor", "favour"), ("labor", "labour"),
                   ("neighbor", "neighbour"), ("humor", "humour"), ("flavor", "flavour"), ("rumor", "rumour"),
                   ("harbor", "harbour"), ("odor", "odour"), ("endeavor", "endeavour"), ("armor", "armour"),
                   ("behavior", "behaviour"), ("vapor", "vapour"), ("savior", "saviour"), ("parlor", "parlour")]:
        forms(us, au, ("", "s", "ed", "ing", "ful", "less", "able", "ite", "ites", "hood", "al"))
    for us, au in [("center", "centre"), ("theater", "theatre"), ("fiber", "fibre"), ("liter", "litre"),
                   ("caliber", "calibre"), ("somber", "sombre"), ("meager", "meagre"), ("kilometer", "kilometre"),
                   ("centimeter", "centimetre"), ("millimeter", "millimetre")]:
        forms(us, au, ("", "s"))
    pairs.update({"centered": "centred", "centering": "centring"})
    for us, au in [("travel", "travel"), ("cancel", "cancel"), ("label", "label"), ("model", "model"),
                   ("fuel", "fuel"), ("signal", "signal"), ("total", "total"), ("level", "level"),
                   ("marvel", "marvel"), ("quarrel", "quarrel"), ("counsel", "counsel")]:
        for e in ("ed", "ing", "er", "ers"):
            pairs[us + e] = au + "l" + e
    pairs.update({
        "defense": "defence", "offense": "offence", "gray": "grey", "mom": "mum", "moms": "mums",
        "aluminum": "aluminium", "plow": "plough", "jewelry": "jewellery", "pajamas": "pyjamas",
        "catalog": "catalogue", "dialog": "dialogue", "enrollment": "enrolment", "fulfill": "fulfil",
        "skillful": "skilful", "cozy": "cosy", "mustache": "moustache", "maneuver": "manoeuvre",
        "pediatric": "paediatric", "anesthetic": "anaesthetic", "esthetic": "aesthetic", "math": "maths",
        "analyze": "analyse", "analyzed": "analysed", "analyzing": "analysing", "paralyze": "paralyse",
        "paralyzed": "paralysed", "program": "program", "tire": "tire", "practice": "practice",
    })
    return {us: au for us, au in pairs.items() if us != au}


AU_SPELLING = _au_spellings()
_IZE_KEEP = {"size", "sized", "sizes", "seize", "seized", "seizes", "seizing", "prize", "prizes", "prized",
             "capsize", "capsized", "maize", "baize", "downsize", "oversize", "oversized", "citizen", "citizens"}
AU_PLACES = {"bondi", "manly", "cronulla", "coogee", "uluru", "kakadu", "parramatta", "penrith", "bankstown",
             "wollongong", "newcastle", "geelong", "ballarat", "bendigo", "cairns", "townsville", "toowoomba",
             "noosa", "byron", "launceston", "fremantle", "mandurah", "alice", "kosciuszko", "tassie", "nsw",
             "qld", "vic", "wa", "sa", "nt", "act"}
AU_WORDS = {"mum", "mums", "arvo", "footy", "uni", "ute", "utes", "maths", "servo", "brekky", "lollies", "doona",
            "aussie", "aussies", "anzac", "anzacs", "centrelink", "yeah", "okay", "ok", "metre", "metres"}

COMMON_MISSPELLINGS = {
    "teh": "the", "alot": "a lot", "definately": "definitely", "recieve": "receive", "recieved": "received",
    "untill": "until", "wich": "which", "becuase": "because", "becasue": "because", "freind": "friend",
    "freinds": "friends", "beleive": "believe", "goverment": "government", "enviroment": "environment",
    "seperate": "separate", "occured": "occurred", "tommorow": "tomorrow", "tomorow": "tomorrow",
    "wierd": "weird", "probly": "probably", "thier": "their", "acheive": "achieve", "arguement": "argument",
    "begining": "beginning", "beautifull": "beautiful", "finaly": "finally", "realy": "really",
    "basicly": "basically", "suprise": "surprise", "wensday": "Wednesday", "febuary": "February",
    "libary": "library", "intresting": "interesting", "diffrent": "different", "cuz": "because",
}

_ise = re.compile(r"(iz)(e|es|ed|ing|ation|ations|er|ers)$")
_yze = re.compile(r"(yz)(e|es|ed|ing)$")


def _to_au(word):
    """Australian spelling of a word, or None if it's fine as it is."""
    low = word.lower()
    au = AU_SPELLING.get(low)
    if au is None and low not in _IZE_KEEP and len(low) > 5 and _ise.search(low):
        au = _ise.sub(lambda m: "is" + m.group(2), low)
    if au is None and _yze.search(low):
        au = _yze.sub(lambda m: "ys" + m.group(2), low)
    if au is None or au == low:
        return None
    return _match_case(word, au)


_spell = None


def _speller():
    """The spelling dictionary, with Australian spellings and words added."""
    global _spell
    if _spell is None:
        try:
            from spellchecker import SpellChecker
            sp = SpellChecker()
            extra = set(AU_WORDS) | AU_PLACES | set(AU_SPELLING.values())
            for w in list(sp.word_frequency.keys()):
                au = _to_au(w)
                if au:
                    extra.add(au.lower())
            sp.word_frequency.load_words(extra)
            _spell = sp
        except Exception:
            _spell = False       # no dictionary: only the built-in list of common misspellings
    return _spell or None


def _issue(start, end, original, suggestion, level, kind, note=""):
    return {"start": start, "end": end, "original": original, "suggestion": suggestion,
            "level": level, "type": kind, "note": note}


def _sentence_starts(text):
    """Positions where a sentence starts (start of text, after . ! ? or a blank line)."""
    starts = {0}
    for m in re.finditer(r"[.!?]+[\"')\]]*\s+|\n\s*", text):
        starts.add(m.end())
    return starts


_CONTRACTION_FIXES = {
    "dont": "don't", "cant": "can't", "wont": "won't", "isnt": "isn't", "arent": "aren't", "doesnt": "doesn't",
    "didnt": "didn't", "wasnt": "wasn't", "werent": "weren't", "shouldnt": "shouldn't", "couldnt": "couldn't",
    "wouldnt": "wouldn't", "havent": "haven't", "hasnt": "hasn't", "hadnt": "hadn't", "im": "I'm",
    "ive": "I've", "youre": "you're", "theyre": "they're", "thats": "that's", "whats": "what's",
    "theres": "there's", "heres": "here's", "shes": "she's", "hes": "he's", "didn't": None,
}
_PROPER = {w.lower(): w for w in [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February", "March",
    "April", "June", "July", "August", "September", "October", "November", "December", "Australia", "Australian",
    "Australians", "Aboriginal", "Indigenous", "Torres", "Strait", "Japan", "Japanese", "China", "Chinese",
    "America", "American", "England", "English", "Britain", "British", "Europe", "European", "India", "Indian",
    "Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Hobart", "Darwin", "Canberra", "Queensland",
    "Victoria", "Tasmania", "Christmas", "Easter", "Anzac", "God", "Asia", "Asian", "Africa", "African",
    "Indonesia", "Indonesian", "Vietnam", "Vietnamese", "Korea", "Korean", "France", "French", "Germany",
    "German", "Italy", "Italian", "Spain", "Spanish", "Pacific", "Antarctica", "Uluru", "Instagram",
    "YouTube", "TikTok", "Google", "Bondi", "Manly", "Uluru", "Kakadu", "Parramatta", "Newcastle",
    "Wollongong", "Geelong", "Cairns", "Townsville", "Fremantle",
]}
_CASUAL = {"gonna": "going to", "wanna": "want to", "gotta": "have to", "kinda": "kind of", "sorta": "sort of",
           "dunno": "don't know", "lemme": "let me", "gimme": "give me", "ya": "you", "u": "you", "ur": "your",
           "coz": "because", "tho": "though", "thru": "through", "nope": "no", "yep": "yes"}
_STOP = set("the a an and or but so of to in on at for with by is are was were be been it its this that these "
            "those i you he she we they them his her their our my your me us as from not no yes do did does "
            "have has had will would can could should there here then than if when what which who how".split())


def check_text(text):
    """Find mistakes. Returns a list of issues (start, end, original,
    suggestion or None, level, type, note), sorted by where they are."""
    issues = []
    starts = _sentence_starts(text)
    speller = _speller()

    def add(*a, **kw):
        issues.append(_issue(*a, **kw))

    # Level 2: doubled words, common misspellings, spelling.
    for m in re.finditer(r"\b(\w+)(\s+)(\1)\b", text, re.IGNORECASE):
        if m.group(1).lower() not in ("had", "that", "is") and not m.group(1).isdigit():
            add(m.start(), m.end(), m.group(0), m.group(1), 2, "doubled word")
    for m in re.finditer(r"[A-Za-z][A-Za-z']*", text):
        word, i = m.group(0), m.start()
        low = word.lower()
        if low in COMMON_MISSPELLINGS:
            add(i, m.end(), word, _match_case(word, COMMON_MISSPELLINGS[low]), 2, "typo")
            continue
        au = _to_au(word)
        if au:
            add(i, m.end(), word, au, 2, "spelling", "Australian spelling")
            continue
        if speller is None or "'" in word or len(word) < 3 or word.isupper():
            continue
        if word[0].isupper() and i not in starts:
            continue                  # probably a name
        if low in _CONTRACTION_FIXES or low in _CASUAL or low in _PROPER:
            continue                  # handled at levels 4 and 5
        if speller.unknown([low]):
            fix = speller.correction(low)
            if fix and fix != low:
                add(i, m.end(), word, _match_case(word, fix), 2, "spelling")

    # Level 3: grammar.
    rules = [
        (r"\b(could|should|would|must|might) of\b", lambda m: m.group(1) + " have", "grammar"),
        (r"\b(they|we|you) was\b", lambda m: m.group(1) + " were", "grammar"),
        (r"\b(have|has|had) (went|ate|saw|did|came|wrote|took|gave|ran|swam|drank|broke|spoke|chose)\b",
         lambda m: m.group(1) + " " + {"went": "gone", "ate": "eaten", "saw": "seen", "did": "done",
                                        "came": "come", "wrote": "written", "took": "taken", "gave": "given",
                                        "ran": "run", "swam": "swum", "drank": "drunk", "broke": "broken",
                                        "spoke": "spoken", "chose": "chosen"}[m.group(2).lower()], "grammar"),
        (r"\byour (welcome|going|not|right|wrong|so|very|really|being|the best|gonna|doing|getting|making)\b",
         lambda m: "you're " + m.group(1), "wrong word"),
        (r"\bits (a|an|the|not|been|going|so|very|really|getting|raining|time|true|important|hard|easy)\b",
         lambda m: "it's " + m.group(1), "wrong word"),
        (r"\bit's (own|name|colou?r|size|shape|tail|fur|people|beaches|history|culture|population|capital|"
         r"purpose|habitat|leaves|body)\b", lambda m: "its " + m.group(1), "wrong word"),
        (r"\bmore (\w+) then\b", lambda m: "more " + m.group(1) + " than", "wrong word"),
        (r"\bthere (own|house|car|friends?|family|parents|mum|dad|teacher|work|homework|names?|things|team|"
         r"school|dog|cat|home|lives|eyes|hands)\b", lambda m: "their " + m.group(1), "wrong word"),
        (r"\btheir (is|are|was|were|will be)\b", lambda m: "there " + m.group(1), "wrong word"),
        (r"\b(more|less|better|worse|bigger|smaller|rather|other|faster|slower|older|younger|higher|lower|"
         r"greater|easier|harder|longer|shorter|taller) then\b", lambda m: m.group(1) + " than", "wrong word"),
        (r"\b(lose|loose) (fitting|clothes|tooth|thread)\b", None, None),
        (r"\b(will|to|might|could|don't|didn't|not) loose\b", lambda m: m.group(1) + " lose", "wrong word"),
        (r"\b(I|you|we|they) no (that|what|how|why|where|who|it)\b",
         lambda m: m.group(1) + " know " + m.group(2), "wrong word"),
        (r"\bwas (suppose|use) to\b", lambda m: "was " + m.group(1) + "d to", "grammar"),
        (r"\bto (much|many|late|early|big|small|hard|easy|hot|cold|long|far|tired|busy|scared|sick|fast|slow|"
         r"loud|quiet|young|old|good|bad|expensive|cheap|full|hungry|short|tall|heavy|close|often)\b",
         lambda m: "too " + m.group(1), "wrong word"),
    ]
    for pattern, fix, kind in rules:
        if fix is None:
            continue
        for m in re.finditer(pattern, text, re.IGNORECASE):
            add(m.start(), m.end(), m.group(0), _match_case(m.group(0), fix(m)), 3, kind)
    for m in re.finditer(r"\b(a|an) ([A-Za-z]+)", text, re.IGNORECASE):
        art, nxt = m.group(1), m.group(2).lower()
        vowel_sound = nxt[0] in "aeio" or (nxt[0] == "u" and not nxt.startswith(("uni", "use", "usu", "ut")))
        vowel_sound = (vowel_sound or nxt.startswith(("hour", "honest", "honour", "heir"))) and \
            not nxt.startswith(("one", "once", "eu"))
        want = "an" if vowel_sound else "a"
        if art.lower() != want and len(nxt) > 1:
            add(m.start(1), m.end(1), art, _match_case(art, want), 3, "grammar")

    # Level 4: apostrophes, capitals, spacing, full stops, run-on sentences.
    for m in re.finditer(r"\b[A-Za-z]+\b", text):
        word, low = m.group(0), m.group(0).lower()
        fix = _CONTRACTION_FIXES.get(low)
        if fix and not (low == "im" and word == "IM"):
            add(m.start(), m.end(), word, _match_case(word, fix) if low != "im" else "I'm", 4, "apostrophe")
        elif word == "i":
            add(m.start(), m.end(), word, "I", 4, "capital letter")
        elif low in _PROPER and word != _PROPER[low] and word.islower():
            add(m.start(), m.end(), word, _PROPER[low], 4, "capital letter")
    for i in sorted(starts):
        if i < len(text) and text[i].islower():
            m = re.match(r"[a-z]+", text[i:])
            if m and m.group(0) not in ("i",):
                w = m.group(0)
                add(i, i + len(w), w, w[0].upper() + w[1:], 4, "capital letter", "start of a sentence")
    for m in re.finditer(r"(\w) +([,.!?;:])(?!\w)", text):
        add(m.start(), m.end(), m.group(0), m.group(1) + m.group(2), 4, "punctuation", "space before punctuation")
    for m in re.finditer(r"([a-z])([,;])([A-Za-z])", text):
        add(m.start(), m.end(), m.group(0), m.group(1) + m.group(2) + " " + m.group(3), 4, "punctuation",
            "missing space")
    for m in re.finditer(r"([A-Za-z0-9')]+)[ \t]*(?=\n\s*\n|\Z)", text):
        para = text[:m.end(1)].rsplit("\n\n", 1)[-1].strip()
        if len(para.split()) >= 6:
            add(m.start(1), m.end(1), m.group(1), m.group(1) + ".", 4, "punctuation", "missing full stop")
    for m in re.finditer(r", (it|i|I|we|they|he|she|you) (was|were|is|are|went|had|did|got|love|loved|want)\b", text):
        add(m.start(), m.start() + 1, ",", None, 4, "run-on sentence",
            "two sentences joined with a comma: think about a full stop")
    for m in re.finditer(r"[^.!?\n]{2,}[.!?]?", text):
        if len(m.group(0).split()) > 40:
            add(m.start(), m.end(), m.group(0), None, 4, "run-on sentence",
                "very long sentence: think about splitting it")

    # Level 5: casual words, a word repeated close together.
    for m in re.finditer(r"\b[A-Za-z]+\b", text):
        low = m.group(0).lower()
        if low in _CASUAL:
            add(m.start(), m.end(), m.group(0), _match_case(m.group(0), _CASUAL[low]), 5, "casual word")
    words = [(m.group(0).lower(), m.start(), m.end()) for m in re.finditer(r"[A-Za-z']+", text)]
    for k, (w, a, b) in enumerate(words):
        if len(w) < 4 or w in _STOP:
            continue
        for w2, a2, b2 in words[k + 1:k + 7]:
            if w2 == w:
                add(a2, b2, text[a2:b2], None, 5, "repeated word", f'"{w}" is used twice close together')
                break

    # One issue per spot: keep the most important (lowest level) where two overlap.
    issues.sort(key=lambda d: (d["level"], d["start"]))
    kept = []
    for d in issues:
        if all(d["end"] <= k["start"] or d["start"] >= k["end"] for k in kept):
            kept.append(d)
    return sorted(kept, key=lambda d: d["start"])


def apply_fixes(text, issues, level):
    """Fix every issue up to the level that has a suggestion. Returns
    (new_text, fixed_issues, left_count): left_count counts the mistakes
    noticed above the level, plus ones that need you to decide."""
    fixed = [d for d in issues if d["level"] <= level and d["suggestion"] is not None]
    left = sum(1 for d in issues if d["level"] > level)
    for d in sorted(fixed, key=lambda d: d["start"], reverse=True):
        text = text[:d["start"]] + d["suggestion"] + text[d["end"]:]
    return text, fixed, left


# --------------------------------------------------------------------------- #
#  AI check: sentences with habits that AI writing tends to have
# --------------------------------------------------------------------------- #

_AI_PHRASES = [
    (r"\bdelv(e|es|ed|ing)\b", '"delve"'), (r"\btapestry\b", '"tapestry"'), (r"\btestament to\b", '"a testament to"'),
    (r"\bunderscor(e|es|ed|ing)\b", '"underscore"'), (r"\bpivotal\b", '"pivotal"'), (r"\bcrucial\b", '"crucial"'),
    (r"\bmultifaceted\b", '"multifaceted"'), (r"\bintricate\b", '"intricate"'), (r"\brealm\b", '"realm"'),
    (r"\bnavigat(e|es|ed|ing) the\b", '"navigate the"'), (r"\bfoster(s|ed|ing)?\b", '"foster"'),
    (r"\bleverag(e|es|ed|ing)\b", '"leverage"'), (r"\brobust\b", '"robust"'), (r"\bseamless(ly)?\b", '"seamless"'),
    (r"\bholistic\b", '"holistic"'), (r"\bnuanced?\b", '"nuanced"'), (r"\bvibrant\b", '"vibrant"'),
    (r"\bprofound(ly)?\b", '"profound"'), (r"\bshowcas(e|es|ed|ing)\b", '"showcase"'),
    (r"\bembark(s|ed|ing)? on\b", '"embark on"'), (r"\bever-(evolving|changing)\b", '"ever-evolving"'),
    (r"\bplays? an? (crucial|vital|pivotal|key|significant) role\b", '"plays a crucial role"'),
    (r"\b(it is|it's) (important|worth|crucial) (to note|noting|to remember)\b", '"it is important to note"'),
    (r"\bin today's (world|society|fast-paced)\b", '"in today\'s world"'),
    (r"\b(serves|stands) as an?\b", '"stands as / serves as"'), (r"\bnot only\b.*\bbut also\b", '"not only... but also"'),
    (r"\ba (rich|diverse|wide) (array|range|tapestry)\b", '"a rich array"'),
    (r"\bin the (realm|world|landscape) of\b", '"in the realm of"'), (r"\blandscape\b", '"landscape"'),
    (r"\bmeticulous(ly)?\b", '"meticulous"'), (r"\bcommendable\b", '"commendable"'),
    (r"\benhanc(e|es|ed|ing)\b", '"enhance"'), (r"\butiliz(e|es|ed|ing)\b|\butilis(e|es|ed|ing)\b", '"utilise"'),
    (r"\bresonat(e|es|ed|ing)\b", '"resonate"'), (r"\bpaving the way\b", '"paving the way"'),
]
_AI_OPENERS = r"^(Furthermore|Moreover|Additionally|In conclusion|Overall|Ultimately|Notably|Consequently|" \
              r"In summary|Importantly|Interestingly|In essence)\b,?"
_AI_TAIL = r", (highlighting|underscoring|showcasing|emphasising|emphasizing|reflecting|demonstrating|" \
           r"illustrating|ensuring|fostering|reinforcing)\b"


def sentences_of(text):
    """(start, end, sentence) for each sentence."""
    out = []
    for m in re.finditer(r"[^.!?\n]+(?:[.!?]+[\"')\]]*)?", text):
        chunk = m.group(0)
        lead = len(chunk) - len(chunk.lstrip())
        sent = chunk.strip()
        if len(sent.split()) >= 3:
            out.append((m.start() + lead, m.start() + lead + len(sent), sent))
    return out


def ai_signals(text):
    """
    Look for writing habits common in AI text, sentence by sentence.
    This is a hint, not proof: people write like this too, and AI text
    can avoid all of it. Returns (sentences, notes) where each sentence is
    {start, end, text, signals, strength 0-2}.
    """
    sents = []
    for a, b, sent in sentences_of(text):
        signals = []
        for pattern, name in _AI_PHRASES:
            if re.search(pattern, sent, re.IGNORECASE):
                signals.append(f"uses {name}")
        if re.search(_AI_OPENERS, sent):
            signals.append("starts with a formal linking word")
        if re.search(_AI_TAIL, sent):
            signals.append('ends with a ", highlighting..." style add-on')
        if "—" in sent:
            signals.append("long dash (—), which is hard to type on a keyboard")
        if re.search(r"\b\w+, \w+(,)? and \w+\b", sent) and len(sent.split()) > 18 and signals:
            signals.append("list of three")
        strength = 0 if not signals else (1 if len(signals) == 1 else 2)
        sents.append({"start": a, "end": b, "text": sent, "signals": signals, "strength": strength})

    notes = []
    lengths = [len(s["text"].split()) for s in sents]
    if len(lengths) >= 5:
        mean = sum(lengths) / len(lengths)
        spread = (sum((x - mean) ** 2 for x in lengths) / len(lengths)) ** 0.5
        if mean > 12 and spread / mean < 0.25:
            notes.append("The sentences are all a very similar length, which is common in AI text "
                         "(people usually mix short and long sentences).")
    if sents and len(text.split()) > 80 and not check_text_quick_has_mistakes(text):
        notes.append("There are no spelling or typing mistakes at all. That's normal for careful writers "
                     "and for AI, so it's only a small hint.")
    return sents, notes


def check_text_quick_has_mistakes(text):
    return any(d["level"] <= 2 for d in check_text(text))


def parse_typo_targets(text):
    """'the, because, e' -> ({'the', 'because'}, {'e'}): words and single letters to mess up."""
    words, letters = set(), set()
    for item in re.split(r"[,\s]+", text or ""):
        item = item.strip().lower()
        if len(item) == 1 and item.isalpha():
            letters.add(item)
        elif len(item) > 1:
            words.add(item)
    return words, letters


def misspell(word, rng, same_length=False):
    """A believable mistake in a word: two letters swapped, a neighbouring key,
    and (unless same_length) a doubled or missing letter."""
    ways = []
    swaps = [k for k in range(len(word) - 1)
             if word[k].isalpha() and word[k + 1].isalpha() and word[k].lower() != word[k + 1].lower()]
    if swaps:
        ways.append("swap")
    near = [k for k, c in enumerate(word) if c.lower() in NEIGHBOURS and c.isalpha()]
    if near:
        ways.append("near")
    if not same_length and len(word) >= 3:
        ways += ["double", "drop"]
    if not ways:
        return word
    way = rng.choice(ways)
    if way == "swap":
        k = rng.choice(swaps)
        return word[:k] + word[k + 1] + word[k] + word[k + 2:]
    if way == "near":
        k = rng.choice(near)
        c = rng.choice(NEIGHBOURS[word[k].lower()])
        return word[:k] + (c.upper() if word[k].isupper() else c) + word[k + 1:]
    k = rng.randrange(1, len(word))
    if way == "double":
        return word[:k] + word[k] + word[k:]
    return word[:k] + word[k + 1:]        # drop a letter


def build_plan(text, variation=0.35, typo_percent=1.5, natural_pauses=True, seed=None,
               typo_words=(), typo_letters=(), fix_chosen=True, letter_chance=0.5):
    """
    Turn text into a list of (key, weight) steps.

    key is a character to type, or BACKSPACE.  weight is how long to wait before
    pressing it, relative to an average letter.  The weights are later scaled so
    the whole text takes exactly as long as the chosen WPM says it should, so
    typos and pauses never change the overall speed.

    typo_words / typo_letters: words that always get a mistake, and letters that
    get one about letter_chance of the time. fix_chosen=False leaves those
    mistakes in (and then only uses mistakes that keep the word the same length).
    """
    rng = random.Random(seed)
    words = {w.lower() for w in typo_words}
    letters = {c.lower() for c in typo_letters}
    steps = []
    prev = ""

    def jitter():
        if variation <= 0:
            return 1.0
        return rng.lognormvariate(0.0, variation)

    def weight(ch, prev):
        w = jitter()
        if natural_pauses:
            if prev in ".!?":
                w *= 4.5          # end of a sentence
            elif prev in ",;:":
                w *= 2.6          # comma, breath
            elif prev in "\n\t":
                w *= 6.0          # new line, paragraph or the next box
            elif prev == " ":
                w *= 1.5          # between words
                if rng.random() < 0.02:
                    w *= 6.0      # now and then, stop to "think"
            if ch.isupper() or ch in '!@#$%^&*()_+{}|:"<>?~':
                w *= 1.25         # reaching for Shift
            if ch == prev and ch.isalpha():
                w *= 0.75         # double letters are quick
        return w

    i = 0
    while i < len(text):
        ch = text[i]

        # A word you chose: type it wrong (and maybe fix it).
        if words and ch.isalpha() and (i == 0 or not text[i - 1].isalnum()):
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "'"):
                j += 1
            word = text[i:j]
            if word.lower() in words and len(word) >= 2:
                wrong = misspell(word, rng, same_length=not fix_chosen)
                if wrong != word:
                    p = prev
                    for c in wrong:
                        steps.append((c, weight(c, p)))
                        p = c
                    if fix_chosen:
                        same = 0
                        while same < min(len(word), len(wrong)) and word[same] == wrong[same]:
                            same += 1
                        back = len(wrong) - same          # letters to rub out
                        for k in range(back):
                            steps.append((BACKSPACE, (2.8 if k == 0 else 0.6) * jitter()))  # notices...
                        for k, c in enumerate(word[same:]):
                            steps.append((c, (2.8 if back == 0 and k == 0 else 1.1) * jitter()))
                    prev = word[-1]
                    i = j
                    continue

        w = weight(ch, prev)
        lower = ch.lower()
        chosen_letter = lower in letters and ch.isalpha() and rng.random() < letter_chance
        random_typo = typo_percent > 0 and rng.random() < typo_percent / 100
        if lower in NEIGHBOURS and ch.isalpha() and (chosen_letter or random_typo):
            wrong = rng.choice(NEIGHBOURS[lower])
            if ch.isupper():
                wrong = wrong.upper()
            steps.append((wrong, w))
            if chosen_letter and not fix_chosen:
                pass                      # leave this one in
            # Sometimes the mistake is noticed a letter late.
            elif natural_pauses and rng.random() < 0.3:
                steps.append((ch, jitter()))  # carries on with the right letter...
                steps.append((BACKSPACE, 2.8 * jitter()))  # ...then spots it and deletes both
                steps.append((BACKSPACE, 0.7 * jitter()))
                steps.append((ch, 1.2 * jitter()))
            else:
                steps.append((BACKSPACE, 2.4 * jitter()))
                steps.append((ch, 1.2 * jitter()))
        else:
            steps.append((ch, w))
        prev = ch
        i += 1

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


def average_speed(lo, hi):
    """The speed that gives the right total time when the speed wanders evenly
    between lo and hi. (Slow stretches take longer, so it's below the middle.)"""
    import math
    lo, hi = sorted((max(1.0, lo), max(1.0, hi)))
    return lo if hi - lo < 1e-9 else (hi - lo) / math.log(hi / lo)


def split_paragraphs(text):
    """Split text into paragraphs for the boxes.

    Paragraphs are separated by blank lines. If there are no blank lines, each
    line becomes its own paragraph.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"\n[ \t]*\n", text)
    if len(parts) == 1:
        parts = text.split("\n")
    return [p.strip("\n").rstrip() for p in parts if p.strip()]


# --------------------------------------------------------------------------- #
#  The typist: presses keys on a background thread
# --------------------------------------------------------------------------- #

class Typist:
    def __init__(self):
        # Imported here so a missing library shows as a message in the app.
        from pynput.keyboard import Controller, Key
        from pynput.mouse import Button, Controller as Mouse
        self.kb = Controller()
        self.Key = Key
        self.mouse = Mouse()
        self.Button = Button
        self.wpm = 60.0
        self.wpm_range = None   # (slowest, fastest) for a speed that wanders, or None
        self.live_wpm = 60.0    # the speed right now
        self.output = None      # None = press real keys; or a WordBackground
        self.corner_stop = True
        self.rng = random.Random()
        self._target_wpm = None
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
        if self.output is not None:       # typing straight into Word
            if key == BACKSPACE:
                self.output.backspace()
            else:
                self.output.type(key)
            return
        if key == BACKSPACE:
            self.kb.tap(self.Key.backspace)
        elif key == "\n":
            self.kb.tap(self.Key.enter)
        elif key == "\t":
            self.kb.tap(self.Key.tab)
        else:
            self.kb.type(key)

    def click_at(self, x, y):
        """Move the mouse to a spot on the screen and click there."""
        self.mouse.position = (x, y)
        time.sleep(0.15)
        self.mouse.click(self.Button.left, 1)
        time.sleep(0.35)  # let the app put its cursor there

    @property
    def avg_wpm(self):
        return average_speed(*self.wpm_range) if self.wpm_range else self.wpm

    def _speed_now(self, key):
        """The typing speed for this key. With a speed range, the speed wanders:
        every few words it picks a new speed in the range and drifts towards it."""
        if not self.wpm_range:
            self.live_wpm = self.wpm
            return self.wpm
        lo, hi = sorted(self.wpm_range)
        if self._target_wpm is None or not lo <= self.live_wpm <= hi:
            self.live_wpm = self.rng.uniform(lo, hi)
            self._target_wpm = self.rng.uniform(lo, hi)
        if key == " " and self.rng.random() < 0.15:
            # A new "mood": usually somewhere in the range, sometimes right at the edge.
            self._target_wpm = self.rng.choice([lo, hi]) if self.rng.random() < 0.2 else self.rng.uniform(lo, hi)
        self.live_wpm += (self._target_wpm - self.live_wpm) * 0.06
        return self.live_wpm

    def start(self, text, plan, countdown, jumps=None, output=None, corner_stop=True):
        """jumps: {step number: function} - each function runs just before that
        step, to move Word's cursor into the right box. output: where the keys
        go (None = real key presses)."""
        self.jumps = jumps or {}
        self.output = output
        self.corner_stop = corner_stop
        self._target_wpm = None
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
            if self.corner_stop and self._mouse_in_corner():
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
            jump = None      # how to get back into the box we're typing in

            for i, (key, weight) in enumerate(plan):
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
                    pinned = getattr(self.output, "pinned", False)
                    if jump and getattr(jump, "again_after_pause", True) and not pinned:
                        jump()  # back into the same box, right after what's typed so far
                    clock = time.monotonic()

                if i in self.jumps:
                    jump = self.jumps[i]
                    jump()
                    if self.output is not None and hasattr(self.output, "repin"):
                        self.output.repin()   # pin to the box we just moved into
                    if self.stop_event.is_set():
                        self.state = "stopped"
                        return
                    clock = time.monotonic()

                char_seconds = 60.0 / (max(1.0, self._speed_now(key)) * CHARS_PER_WORD)
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
#  Word: read the table cells in a document, and put Word's cursor in one
# --------------------------------------------------------------------------- #

def _short(text, n=45):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def read_word_cells(path):
    """
    List every table cell in a .docx file, in reading order.

    Each cell is a dict with: table, row, col (numbered from 1, the way Word
    numbers them), text (what's in it now), hint (nearby text that says what
    the cell is for) and label (a short name to show in the app).
    """
    import docx                       # python-docx
    from docx.table import _Cell

    document = docx.Document(path)
    cells = []
    for t, table in enumerate(document.tables, 1):
        grid = []                     # text of each cell, row by row
        for r, row in enumerate(table.rows, 1):
            texts = []
            for c, tc in enumerate(row._tr.tc_lst, 1):
                text = _Cell(tc, table).text.strip()
                texts.append(text)
                if tc.vMerge == "continue":
                    continue          # the lower half of a merged cell: not its own box
                cells.append({"table": t, "row": r, "col": c, "text": text})
            grid.append(texts)
        for cell in cells:
            if cell["table"] != t:
                continue
            r, c = cell["row"] - 1, cell["col"] - 1
            hint = ""
            if c > 0 and grid[r][c - 1]:
                hint = grid[r][c - 1]               # the question to its left
            elif r > 0 and c < len(grid[0]) and grid[0][c]:
                hint = grid[0][c]                   # the column heading
            cell["hint"] = hint
            where = f"row {cell['row']}, cell {cell['col']}"
            if len(document.tables) > 1:
                where = f"table {t}, " + where
            # The question comes first, because that's how you recognise the cell.
            if cell["text"]:
                cell["label"] = f"has “{_short(cell['text'], 30)}” – {where}"
            elif hint:
                cell["label"] = f"“{_short(hint, 40)}” – {where}"
            else:
                cell["label"] = f"empty – {where}"
    return cells


def open_in_word(path):
    """Open the document in Word (or bring it to the front if it's already open)."""
    import subprocess
    if IS_MAC:
        subprocess.run(["open", "-a", "Microsoft Word", path], check=False)
    elif sys.platform == "win32":
        os.startfile(path)  # opens with Word


WORD_HELP_MAC = (
    "Human Typer couldn't control Word.\n\n"
    "• Make sure the document is open in Microsoft Word.\n"
    "• Allow it: System Settings > Privacy & Security > Automation > Human Typer "
    "(or Terminal) > turn on Microsoft Word.\n\n"
)
WORD_HELP_WIN = (
    "Human Typer couldn't control Word.\n\n"
    "• Make sure the document is open in Microsoft Word (not just the preview).\n"
    "• If Word shows a yellow bar saying Protected View, click Enable Editing.\n\n"
)

# Puts Word's cursor at the end of whatever is already in one table cell.
# The arguments come in as: document name, table, row, cell.
_MAC_JUMP_SCRIPT = """
on run argv
    set docName to item 1 of argv
    set t to (item 2 of argv) as integer
    set r to (item 3 of argv) as integer
    set c to (item 4 of argv) as integer
    tell application "Microsoft Word"
        if (item 5 of argv) is "front" then activate
        set theDoc to missing value
        repeat with d in documents
            if (name of d) is docName then set theDoc to contents of d
        end repeat
        if theDoc is missing value then set theDoc to active document
        set theCell to get cell from table (table t of theDoc) row r column c
        set cellText to text object of theCell
        set p to (end of content of cellText) - 1
        select (create range theDoc start p end p)
    end tell
end run
"""


def word_jump(doc_path, table, row, col, front=True):
    """Move Word's cursor into a table cell, after any text already there.
    front=False leaves Word in the background (for background typing)."""
    if IS_MAC:
        import subprocess
        result = subprocess.run(
            ["osascript", "-e", _MAC_JUMP_SCRIPT, os.path.basename(doc_path), str(table), str(row), str(col),
             "front" if front else "back"],
            capture_output=True, text=True,
            timeout=120,  # the first time, the Mac waits while you answer "allow control of Word?"
        )
        if result.returncode != 0:
            raise RuntimeError(WORD_HELP_MAC + "Details: " + (result.stderr.strip() or "unknown error"))
    elif sys.platform == "win32":
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()     # needed once per thread
            try:
                word = win32com.client.GetActiveObject("Word.Application")
            except Exception:
                word = win32com.client.Dispatch("Word.Application")
            doc = None
            for d in word.Documents:
                if os.path.normcase(str(d.FullName)) == os.path.normcase(doc_path) \
                        or str(d.Name) == os.path.basename(doc_path):
                    doc = d
                    break
            if doc is None:
                doc = word.ActiveDocument
            cell_range = doc.Tables(table).Cell(row, col).Range
            cell_range.MoveEnd(1, -1)    # step back over the end-of-cell mark (1 = one character)
            cell_range.Collapse(0)       # 0 = put the cursor at the end
            if front:
                doc.Activate()
            cell_range.Select()
            if front:
                word.Activate()
        except Exception as exc:
            raise RuntimeError(WORD_HELP_WIN + "Details: " + str(exc)) from exc
    else:
        raise RuntimeError("Jumping into Word works on Mac and Windows only.")
    time.sleep(0.3 if front else 0.05)  # give Word a moment to come to the front


class WordBackground:
    """
    Types straight into Word through Word's own scripting instead of pressing
    real keys, so Word can stay in the background while you use other apps.

    pinned=False: types wherever Word's cursor is (like a person typing).
    pinned=True:  remembers where Word's cursor was when typing started (or
                  when it moved into a table cell) and keeps putting the text
                  exactly there, even if you click somewhere else in Word.

    Make a new one for each run (on Windows it belongs to the thread that uses it).
    """

    def __init__(self, run_on_main=None, pinned=False):
        # On a Mac, AppleScript has to run on the app's main thread.
        self.run_on_main = run_on_main or (lambda fn: fn())
        self.pinned = pinned
        self._word = None
        self._pin = None       # Windows: a Word Range that stays put. Mac: (document name, position)

    @staticmethod
    def _quote(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    @staticmethod
    def _word_length(text):
        """How many characters Word counts (it counts emoji and some symbols as 2)."""
        return len(text.encode("utf-16-le")) // 2

    def _mac(self, command):
        script = 'tell application "Microsoft Word" to ' + command

        def go():
            from Foundation import NSAppleScript
            result, error = NSAppleScript.alloc().initWithSource_(script).executeAndReturnError_(None)
            if error is not None:
                detail = error.get("NSAppleScriptErrorMessage", str(error)) if hasattr(error, "get") else str(error)
                raise RuntimeError(WORD_HELP_MAC + "Details: " + str(detail))
            return result.stringValue() if result is not None else None

        return self.run_on_main(go)

    def _app(self):
        if self._word is None:
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                self._word = win32com.client.GetActiveObject("Word.Application")
            except Exception as exc:
                raise RuntimeError(WORD_HELP_WIN + "Details: " + str(exc)) from exc
        return self._word

    def _selection(self):
        return self._app().Selection

    # ----- the pin -----
    def repin(self):
        """Pin to wherever Word's cursor is right now."""
        if not self.pinned:
            return
        if IS_MAC:
            answer = self._mac("return (name of active document) & tab & ((selection start of selection) as text)")
            name, pos = (answer or "").rsplit("\t", 1)
            self._pin = (name, int(pos))
        elif sys.platform == "win32":
            spot = self._selection().Range.Duplicate
            spot.Collapse(1)          # 1 = the start of whatever is selected
            self._pin = spot          # Word moves this along if text is added above it

    def _mac_spot(self, start, end):
        name, _ = self._pin
        return f"(create range (document {self._quote(name)}) start {start} end {end})"

    # ----- typing -----
    def type(self, ch):
        if self.pinned:
            if self._pin is None:
                self.repin()
            if IS_MAC:
                name, pos = self._pin
                what = {"\n": "return", "\t": "tab"}.get(ch) or self._quote(ch)
                self._mac(f"insert text {what} at {self._mac_spot(pos, pos)}")
                self._pin = (name, pos + self._word_length(ch))
            elif sys.platform == "win32":
                self._pin.InsertAfter("\r" if ch == "\n" else ch)
                self._pin.Collapse(0)  # 0 = move the pin to the end of what was just added
            else:
                raise RuntimeError("Background typing works with Word on Mac and Windows only.")
            return
        if IS_MAC:
            if ch == "\n":
                self._mac("type paragraph selection")
            elif ch == "\t":
                self._mac("type text selection text tab")
            else:
                self._mac("type text selection text " + self._quote(ch))
        elif sys.platform == "win32":
            if ch == "\n":
                self._selection().TypeParagraph()
            else:
                self._selection().TypeText(ch)
        else:
            raise RuntimeError("Background typing works with Word on Mac and Windows only.")

    def backspace(self):
        if self.pinned and self._pin is not None:
            if IS_MAC:
                name, pos = self._pin
                self._mac(f'set content of {self._mac_spot(pos - 1, pos)} to ""')
                self._pin = (name, pos - 1)
            elif sys.platform == "win32":
                gone = self._pin.Duplicate
                gone.MoveStart(1, -1)  # 1 = one character back
                gone.Delete()
                gone.Collapse(1)
                self._pin = gone       # the pin is now where the deleted letter was
            return
        if IS_MAC:
            self._mac("type backspace selection")
        elif sys.platform == "win32":
            self._selection().TypeBackspace()
        else:
            raise RuntimeError("Background typing works with Word on Mac and Windows only.")


# --------------------------------------------------------------------------- #
#  Mac permission
# --------------------------------------------------------------------------- #

_APP_NAME_IN_LIST = "Human Typer" if getattr(sys, "frozen", False) else "Terminal (or the app you started Human Typer from)"

MAC_PERMISSION_HELP = (
    "Your Mac needs to let Human Typer press keys.\n\n"
    "1. Quit Human Typer (Cmd+Q).\n"
    "2. Open System Settings > Privacy & Security > Accessibility.\n"
    f"3. If {_APP_NAME_IN_LIST} is in the list, click it and press the – button to remove it, "
    "even if its switch is on. (After a new download the old switch no longer counts.)\n"
    "4. Open Human Typer again and press Start. When the Mac asks, click Open System Settings "
    f"and turn on {_APP_NAME_IN_LIST}.\n"
    "5. Quit Human Typer (Cmd+Q) and open it one more time."
)

MAC_MOVE_HELP = (
    "Please move Human Typer into your Applications folder first.\n\n"
    "It's running from Downloads, so the Mac can't remember its permission and keeps asking.\n\n"
    "1. Quit Human Typer (Cmd+Q).\n"
    "2. Drag Human Typer from Downloads into Applications.\n"
    "3. Open it from Applications."
)

_asked_mac = False


def mac_permission_problem():
    """
    On a Mac, check that we're allowed to press keys. Without this permission
    the Mac silently ignores every key press. Returns None when all is well,
    or a message saying what to do.
    """
    global _asked_mac
    if not IS_MAC:
        return None
    try:
        import HIServices  # comes with pynput on Mac
        if HIServices.AXIsProcessTrusted():
            return None
        exe = sys.executable
        if getattr(sys, "frozen", False) and ("/AppTranslocation/" in exe or "/Downloads/" in exe):
            return MAC_MOVE_HELP
        if not _asked_mac:
            # Show the Mac's own "allow access" prompt, but only once, so it doesn't nag.
            _asked_mac = True
            HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True})
        return MAC_PERMISSION_HELP
    except Exception:
        return None  # can't check, so just try


# --------------------------------------------------------------------------- #
#  The window
# --------------------------------------------------------------------------- #

class ScrollFrame(ttk.Frame):
    """A frame with a vertical scrollbar; put widgets in .inner."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self._wheel(True))
        self.canvas.bind("<Leave>", lambda e: self._wheel(False))

    def _wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
            self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
            self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.canvas.unbind_all(seq)

    def _on_wheel(self, e):
        step = -e.delta if IS_MAC else -int(e.delta / 120) * 2
        self.canvas.yview_scroll(step, "units")


DIVIDER = "────── cells that already have words ──────"

# Border colours for the boxes.
BOX_IDLE, BOX_NEXT, BOX_TYPING, BOX_DONE = "#c8c8c8", "#3b82f6", "#f59e0b", "#22a559"


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("720x820" if IS_MAC else "680x740")
        root.minsize(540, 600)
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
        self.typo_targets = tk.StringVar(value="")     # words and letters to always mess up
        self.fix_chosen = tk.BooleanVar(value=True)
        self.natural = tk.BooleanVar(value=False)      # Natural tone switch
        self._natural_original = self._natural_result = None
        self.pauses = tk.BooleanVar(value=True)
        self.delay = tk.IntVar(value=5)
        self.on_top = tk.BooleanVar(value=True)
        self.random_speed = tk.BooleanVar(value=False)
        self.wpm_lo = tk.IntVar(value=40)
        self.wpm_hi = tk.IntVar(value=90)
        self.background = tk.BooleanVar(value=False)
        self.pin = tk.BooleanVar(value=True)
        self.box_mode = tk.StringVar(value="click")   # "click", "tab" or "word"
        self.word = None     # the connected Word document: {"path", "name", "cells"}
        self.jumper = word_jump

        self.boxes = []      # each: {"card", "text", "status", "done"}
        self.box_cols = 0
        self.run = None      # what the typist is doing right now

        self._build()
        self._start_hotkeys()
        for var in (self.wpm, self.random_speed, self.wpm_lo, self.wpm_hi):
            var.trace_add("write", lambda *_: self._on_settings())
        self.box_mode.trace_add("write", lambda *_: self._on_mode_changed())
        self.on_top.trace_add("write", lambda *_: root.attributes("-topmost", self.on_top.get()))
        root.attributes("-topmost", True)
        self._add_box()
        self._update_info()
        self._poll()

        if self.typist_error:
            self.status.set(self.typist_error)

    # ----- layout -----
    def _build(self):
        pad = {"padx": 12, "pady": 6}
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        font = ("", 14 if IS_MAC else 11)
        # The settings and buttons go at the bottom first, so they always keep
        # their space and the text area takes what's left.
        bottom = self.bottom = ttk.Frame(main)
        bottom.pack(side="bottom", fill="x")

        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(10, 4))

        # --- Tab 1: one block of text ---
        one = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(one, text="  Text  ")
        ttk.Label(one, text="Paste the text you want typed:", font=("", 11, "bold")).pack(anchor="w", pady=(0, 4))
        box = ttk.Frame(one)
        box.pack(fill="both", expand=True)
        self.text = tk.Text(box, wrap="word", undo=True, height=6, font=font)
        scroll = ttk.Scrollbar(box, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.bind("<<Modified>>", self._on_text_changed)
        row = ttk.Frame(one)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Paste", command=self._paste).pack(side="left")
        ttk.Button(row, text="Clear", command=self._clear_text).pack(side="left", padx=6)
        ttk.Checkbutton(row, text="✨ Natural tone", variable=self.natural, style="Toolbutton",
                        command=self._toggle_natural).pack(side="left")
        self.info = tk.StringVar()
        ttk.Label(row, textvariable=self.info, foreground="#555").pack(side="right")

        # --- Tab 2: one paragraph per box ---
        grid = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(grid, text="  Boxes (one paragraph each)  ")
        tools = ttk.Frame(grid)
        tools.pack(fill="x")
        ttk.Button(tools, text="Paste & split", command=self._paste_split).pack(side="left")
        ttk.Button(tools, text="Split the Text tab", command=self._split_text_tab).pack(side="left", padx=4)
        ttk.Button(tools, text="+ Add box", command=lambda: self._add_box(focus=True)).pack(side="left")
        ttk.Button(tools, text="Start over", command=self._reset_done).pack(side="right")
        ttk.Button(tools, text="Clear", command=self._clear_boxes).pack(side="right", padx=4)

        doc = ttk.Frame(grid)
        doc.pack(fill="x", pady=(6, 0))
        ttk.Button(doc, text="Connect Word document…", command=self._connect_word).pack(side="left")
        self.fill_btn = ttk.Button(doc, text="Fill in order", command=self._fill_in_order, state="disabled")
        self.fill_btn.pack(side="left", padx=4)
        self.word_info = tk.StringVar(value="Not connected. Pick a .docx with a table to choose a cell for each box.")
        ttk.Label(doc, textvariable=self.word_info, foreground="#555").pack(side="left", padx=4)

        mode = ttk.Frame(grid)
        mode.pack(fill="x", pady=(6, 4))
        ttk.Label(mode, text="Getting to each box:").pack(side="left")
        ttk.Radiobutton(mode, text="I click", value="click",
                        variable=self.box_mode).pack(side="left", padx=(6, 2))
        ttk.Radiobutton(mode, text="Auto-click my spots", value="spot",
                        variable=self.box_mode).pack(side="left", padx=2)
        ttk.Radiobutton(mode, text="Press Tab", value="tab",
                        variable=self.box_mode).pack(side="left", padx=2)
        self.word_radio = ttk.Radiobutton(mode, text="Word cells", value="word",
                                          variable=self.box_mode, state="disabled")
        self.word_radio.pack(side="left", padx=2)

        self.box_info = tk.StringVar()
        ttk.Label(grid, textvariable=self.box_info, foreground="#555").pack(side="bottom", anchor="w", pady=(4, 0))
        self.box_area = ScrollFrame(grid)
        self.box_area.pack(fill="both", expand=True)
        self.box_area.canvas.bind("<Configure>", self._on_box_area_resize, add="+")

        self._build_check_tab(font)
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed())

        # Speed
        speed = ttk.LabelFrame(bottom, text="Speed")
        speed.pack(fill="x", **pad)
        ttk.Label(speed, text="Words per minute").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.wpm_scale = ttk.Scale(speed, from_=1, to=300, variable=self.wpm, orient="horizontal",
                                   command=lambda v: self.wpm.set(int(float(v))))
        self.wpm_scale.grid(row=0, column=1, sticky="ew", padx=8)
        self.wpm_box = ttk.Spinbox(speed, from_=1, to=2000, textvariable=self.wpm, width=6)
        self.wpm_box.grid(row=0, column=2, padx=8)
        presets = ttk.Frame(speed)
        presets.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        for label, value in (("Slow 25", 25), ("Average 40", 40), ("Good 60", 60), ("Fast 90", 90), ("Pro 120", 120)):
            ttk.Button(presets, text=label, command=lambda v=value: self.wpm.set(v)).pack(side="left", padx=(0, 4))
        rand = ttk.Frame(speed)
        rand.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        ttk.Checkbutton(rand, text="Random speed between", variable=self.random_speed).pack(side="left")
        ttk.Spinbox(rand, from_=1, to=2000, textvariable=self.wpm_lo, width=5).pack(side="left", padx=4)
        ttk.Label(rand, text="and").pack(side="left")
        ttk.Spinbox(rand, from_=1, to=2000, textvariable=self.wpm_hi, width=5).pack(side="left", padx=4)
        ttk.Label(rand, text="WPM").pack(side="left")
        speed.columnconfigure(1, weight=1)

        # Human touches
        human = ttk.LabelFrame(bottom, text="Make it look human")
        human.pack(fill="x", **pad)
        ttk.Label(human, text="Rhythm variation").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Scale(human, from_=0, to=100, variable=self.variation, orient="horizontal",
                  command=lambda v: self.variation.set(int(float(v)))).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(human, textvariable=self.variation, width=4).grid(row=0, column=2)
        ttk.Label(human, text="Typos (fixed with backspace), % of letters").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Scale(human, from_=0, to=8, variable=self.typos, orient="horizontal",
                  command=lambda v: self.typos.set(round(float(v), 1))).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(human, textvariable=self.typos, width=4).grid(row=1, column=2)
        ttk.Checkbutton(human, text="Pause between words and after punctuation",
                        variable=self.pauses).grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=4)
        chosen = ttk.Frame(human)
        chosen.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 6))
        ttk.Label(chosen, text="Always mess up:").pack(side="left")
        ttk.Entry(chosen, textvariable=self.typo_targets, width=24).pack(side="left", padx=6)
        ttk.Checkbutton(chosen, text="Fix them", variable=self.fix_chosen).pack(side="left")
        ttk.Label(chosen, text="e.g.  the, because, e", foreground="#777").pack(side="left", padx=8)
        human.columnconfigure(1, weight=1)

        # Start options
        opts = ttk.Frame(bottom)
        opts.pack(fill="x", **pad)
        ttk.Label(opts, text="Seconds to click into Word:").pack(side="left")
        ttk.Spinbox(opts, from_=1, to=60, textvariable=self.delay, width=4).pack(side="left", padx=6)
        ttk.Checkbutton(opts, text="Keep this window on top", variable=self.on_top).pack(side="right")
        bg = ttk.Frame(bottom)
        bg.pack(fill="x", padx=12, pady=(0, 4))
        self.bg_check = ttk.Checkbutton(
            bg, text="Type in the background (Word only: keep using your computer while it types)",
            variable=self.background, state="normal" if (IS_MAC or sys.platform == "win32") else "disabled")
        self.bg_check.pack(side="left")
        pin_row = ttk.Frame(bottom)
        pin_row.pack(fill="x", padx=32, pady=(0, 4))
        self.pin_check = ttk.Checkbutton(
            pin_row, text="Pin it to one spot (keeps typing there even if you click somewhere else in Word)",
            variable=self.pin, state="disabled")
        self.pin_check.pack(side="left")
        self.background.trace_add("write", lambda *_: self.pin_check.configure(
            state="normal" if self.background.get() else "disabled"))

        # Controls
        ctl = ttk.Frame(bottom)
        ctl.pack(fill="x", **pad)
        self.start_btn = ttk.Button(ctl, text="▶  Start typing", command=self._start)
        self.start_btn.pack(side="left")
        self.pause_btn = ttk.Button(ctl, text=self._label("Pause"), command=self._pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(ctl, text="Stop" if IS_MAC else "Stop (Esc)", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left")

        self.progress = ttk.Progressbar(bottom, maximum=100)
        self.progress.pack(fill="x", padx=12, pady=(4, 2))
        self.status = tk.StringVar(value="Paste some text, pick a speed, then press Start.")
        ttk.Label(bottom, textvariable=self.status, wraplength=640, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

    # ----- check tab -----
    def _build_check_tab(self, font):
        tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(tab, text="  Check  ")
        self.check_level = tk.IntVar(value=3)
        self.check_issues = []        # from the last Check
        self.check_offset = 0         # where the checked part starts (when you selected a paragraph)

        tools = ttk.Frame(tab)
        tools.pack(fill="x")
        ttk.Button(tools, text="Paste", command=self._check_paste).pack(side="left")
        ttk.Button(tools, text="Use the Text tab", command=self._check_from_text_tab).pack(side="left", padx=4)
        ttk.Button(tools, text="Clear", command=lambda: self.check_text.delete("1.0", "end")).pack(side="left")
        ttk.Button(tools, text="Send to the Text tab ➜", command=self._check_to_text_tab).pack(side="right")

        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True, pady=6)
        self.check_text = tk.Text(body, wrap="word", undo=True, height=6, width=40, font=font)
        bar = ttk.Scrollbar(body, command=self.check_text.yview)
        self.check_text.configure(yscrollcommand=bar.set)
        self.check_text.pack(side="left", fill="both", expand=True)
        bar.pack(side="left", fill="y")
        self.check_list = tk.Listbox(body, width=38, activestyle="none", font=("", 12 if IS_MAC else 9))
        self.check_list.pack(side="left", fill="both", padx=(6, 0))
        self.check_list.bind("<<ListboxSelect>>", lambda e: self._check_show_selected())
        self.check_rows = []          # what each list line points at: (start, end)
        for tag, colour in (("lvl1", "#fecaca"), ("lvl2", "#fecaca"), ("lvl3", "#fed7aa"), ("lvl4", "#bfdbfe"),
                            ("lvl5", "#e5e7eb"), ("ai1", "#fef08a"), ("ai2", "#fdba74")):
            self.check_text.tag_configure(tag, background=colour)
        self.check_text.bind("<<Modified>>", self._on_check_text_changed)

        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Label(row, text="Fix level").pack(side="left")
        ttk.Scale(row, from_=1, to=5, variable=self.check_level, orient="horizontal", length=120,
                  command=lambda v: self._on_check_level(int(round(float(v))))).pack(side="left", padx=6)
        self.check_level_name = tk.StringVar()
        ttk.Label(row, textvariable=self.check_level_name, foreground="#555").pack(side="left")
        row2 = ttk.Frame(tab)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Button(row2, text="✔ Check", command=self._run_check).pack(side="left")
        ttk.Button(row2, text="Fix all at this level", command=self._fix_all).pack(side="left", padx=4)
        ttk.Button(row2, text="🤖 AI check", command=self._run_ai_check).pack(side="left", padx=(12, 0))
        self.check_summary = tk.StringVar(value="Paste text (or select one paragraph), then press Check or AI check.")
        ttk.Label(tab, textvariable=self.check_summary, wraplength=600, justify="left").pack(anchor="w", pady=(6, 0))
        self._on_check_level(3)

    def _on_check_level(self, level):
        self.check_level.set(level)
        self.check_level_name.set(f"{level}: {LEVEL_NAMES[level]}")

    def _on_tab_changed(self):
        # The speed and typing settings aren't needed on the Check tab, so hide them for more room.
        if self._on_check_tab():
            self.bottom.pack_forget()
        elif not self.bottom.winfo_ismapped():
            self.bottom.pack(side="bottom", fill="x", before=self.tabs)
        self._refresh_boxes()

    def _on_check_tab(self):
        try:
            return self.tabs.index("current") == 2
        except tk.TclError:
            return False

    def _check_paste(self):
        try:
            self.check_text.insert("insert", self.root.clipboard_get())
        except tk.TclError:
            pass

    def _check_from_text_tab(self):
        self.check_text.delete("1.0", "end")
        self.check_text.insert("1.0", self._get_text())

    def _check_to_text_tab(self):
        self._set_text(self.check_text.get("1.0", "end-1c"))
        self.tabs.select(0)
        self.status.set("Copied to the Text tab, ready to type.")

    def _on_check_text_changed(self, _event=None):
        if self.check_text.edit_modified():
            self.check_text.edit_modified(False)
            # Tk reports changes a moment late, so compare with the text that was checked
            # and only clear the highlights if it really is different now.
            if self.check_text.get("1.0", "end-1c") != getattr(self, "_checked_text", None):
                self._clear_check_marks()   # the text changed, so old highlights no longer line up

    def _clear_check_marks(self):
        for tag in ("lvl1", "lvl2", "lvl3", "lvl4", "lvl5", "ai1", "ai2"):
            self.check_text.tag_remove(tag, "1.0", "end")
        self.check_list.delete(0, "end")
        self.check_rows = []
        self.check_issues = []

    def _check_part(self):
        """The selected text if you selected some, otherwise all of it. Returns (offset, text)."""
        all_text = self.check_text.get("1.0", "end-1c")
        try:
            a = self.check_text.count("1.0", "sel.first", "chars")
            b = self.check_text.count("1.0", "sel.last", "chars")
            a = a[0] if isinstance(a, tuple) else (a or 0)
            b = b[0] if isinstance(b, tuple) else (b or 0)
            if b > a:
                return a, all_text[a:b]
        except tk.TclError:
            pass
        return 0, all_text

    def _idx(self, n):
        return f"1.0 + {n} chars"

    def _run_check(self):
        offset, part = self._check_part()
        if not part.strip():
            self.check_summary.set("There's nothing to check. Paste some text first.")
            return
        self._clear_check_marks()
        level = self.check_level.get()
        issues = check_text(part)
        self.check_offset, self.check_issues, self.check_part_text = offset, issues, part
        self._checked_text = self.check_text.get("1.0", "end-1c")
        shown = [d for d in issues if d["level"] <= level]
        for d in shown:
            a, b = offset + d["start"], offset + d["end"]
            self.check_text.tag_add(f"lvl{d['level']}", self._idx(a), self._idx(b))
            if d["suggestion"] is None:
                line = f"⚑ {d['type']}: {d['note']}"
            else:
                line = f"{d['original']} → {d['suggestion']}  ({d['type']}{', ' + d['note'] if d['note'] else ''})"
            self.check_list.insert("end", line)
            self.check_rows.append((a, b))
        left = len(issues) - len(shown)
        where = "the selected part" if offset or len(part) < len(self.check_text.get("1.0", "end-1c")) else "the text"
        if not shown:
            msg = f"No mistakes found in {where} at level {level}."
        else:
            fixable = sum(1 for d in shown if d["suggestion"] is not None)
            msg = (f"Found {len(shown)} thing{'' if len(shown) == 1 else 's'} to look at in {where} "
                   f"({fixable} can be fixed with Fix all). Click one in the list to see it.")
        if left:
            msg += f" {left} more noticed but left, because they're above level {level}."
        if level == 1:
            msg += " Confusing sentences (level 1) need a person to read them; this checker can't judge meaning."
        self.check_summary.set(msg)

    def _fix_all(self):
        if not self.check_issues:
            self._run_check()          # nothing checked yet (or the text changed): check first
        if not self.check_issues:
            return
        level = self.check_level.get()
        offset, part = self.check_offset, self.check_part_text
        new_part, fixed, left = apply_fixes(part, self.check_issues, level)
        flags = sum(1 for d in self.check_issues if d["level"] <= level and d["suggestion"] is None)
        self.check_text.edit_separator()
        self.check_text.delete(self._idx(offset), self._idx(offset + len(part)))
        self.check_text.insert(self._idx(offset), new_part)
        self.check_text.edit_separator()
        self._clear_check_marks()
        msg = f"Fixed {len(fixed)} mistake{'' if len(fixed) == 1 else 's'}."
        if flags:
            msg += f" {flags} need{'s' if flags == 1 else ''} you to decide (marked ⚑ when you Check again)."
        if left:
            msg += f" Left {left} because {'it is' if left == 1 else 'they are'} above level {level}."
        msg += " Ctrl+Z / Cmd+Z undoes it."
        self.check_summary.set(msg)

    def _check_show_selected(self):
        sel = self.check_list.curselection()
        if not sel or sel[0] >= len(self.check_rows):
            return
        a, b = self.check_rows[sel[0]]
        self.check_text.tag_remove("sel", "1.0", "end")
        self.check_text.tag_add("sel", self._idx(a), self._idx(b))
        self.check_text.see(self._idx(a))

    def _run_ai_check(self):
        offset, part = self._check_part()
        if len(part.split()) < 10:
            self.check_summary.set("Paste a bit more text (at least a few sentences) for the AI check.")
            return
        self._clear_check_marks()
        self._checked_text = self.check_text.get("1.0", "end-1c")
        sents, notes = ai_signals(part)
        flagged = [x for x in sents if x["strength"]]
        for x in sents:
            if x["strength"]:
                a, b = offset + x["start"], offset + x["end"]
                self.check_text.tag_add(f"ai{x['strength']}", self._idx(a), self._idx(b))
                short = x["text"] if len(x["text"]) < 40 else x["text"][:38] + "…"
                self.check_list.insert("end", f"“{short}”")
                self.check_rows.append((a, b))
                for sig in x["signals"]:
                    self.check_list.insert("end", f"     • {sig}")
                    self.check_rows.append((a, b))
        strong = sum(1 for x in flagged if x["strength"] == 2)
        msg = (f"{len(flagged)} of {len(sents)} sentences have AI-style habits"
               f"{f' ({strong} with several)' if strong else ''}. Yellow = one habit, orange = several.")
        if notes:
            msg += " " + " ".join(notes)
        msg += (" Keep in mind: this only spots habits common in AI writing. Real people write like this too, "
                "and AI text can avoid them, so use it to start a chat, not as proof.")
        self.check_summary.set(msg)

    # ----- boxes -----
    def _add_box(self, text="", focus=False):
        n = len(self.boxes) + 1
        card = tk.Frame(self.box_area.inner, highlightthickness=2, highlightbackground=BOX_IDLE,
                        highlightcolor=BOX_IDLE, bd=0, padx=6, pady=4)
        head = ttk.Frame(card)
        head.pack(fill="x")
        title = ttk.Label(head, text=f"Box {n}", font=("", 10, "bold"))
        title.pack(side="left")
        status = tk.StringVar()
        ttk.Label(head, textvariable=status).pack(side="left", padx=8)
        entry = {"card": card, "title": title, "status": status, "done": False, "target": None, "spot": None}
        ttk.Button(head, text="✕", width=3, command=lambda: self._remove_box(entry)).pack(side="right")
        ttk.Button(head, text="Type this", command=lambda: self._type_box(entry)).pack(side="right", padx=4)
        body = tk.Text(card, wrap="word", undo=True, height=4, font=("", 13 if IS_MAC else 10))
        body.pack(fill="both", expand=True, pady=(4, 0))
        if text:
            body.insert("1.0", text)
        body.bind("<<Modified>>", lambda e, b=body: self._on_box_changed(b))
        entry["text"] = body
        # Which Word cell this box goes in (shown once a document is connected).
        where = ttk.Frame(card)
        ttk.Label(where, text="Goes in:").pack(side="left")
        combo = ttk.Combobox(where, state="readonly", style="Wide.TCombobox",
                             postcommand=lambda: self._widen(combo))
        combo.pack(side="left", fill="x", expand=True, padx=(4, 0))
        combo.bind("<<ComboboxSelected>>", lambda e: self._on_target_picked(entry))
        entry["where"], entry["combo"] = where, combo
        # Where to click on the screen before typing this box.
        spot_row = ttk.Frame(card)
        ttk.Button(spot_row, text="Set spot", command=lambda: self._set_spot(entry)).pack(side="left")
        ttk.Button(spot_row, text="Show", width=6, command=lambda: self._show_spot(entry)).pack(side="left", padx=4)
        entry["spot_var"] = tk.StringVar(value="No spot yet")
        ttk.Label(spot_row, textvariable=entry["spot_var"], foreground="#555").pack(side="left", padx=4)
        entry["spot_row"] = spot_row
        self._show_rows(entry)
        self.boxes.append(entry)
        self._layout_boxes(force=True)
        if focus:
            body.focus_set()
            self.root.after(50, lambda: self.box_area.canvas.yview_moveto(1.0))

    # ----- Word document -----
    def _connect_word(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Pick your Word document",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
        )
        if path:
            self.connect_word(path)

    def connect_word(self, path, open_it=True):
        try:
            cells = read_word_cells(path)
        except ImportError:
            self.status.set("Reading Word documents needs python-docx:  pip install python-docx")
            return
        except Exception as exc:
            self.status.set(f"Couldn't read that document. Is it a .docx file? ({exc})")
            return
        if not cells:
            self.status.set("That document has no tables. Add a table in Word (Insert > Table), save, "
                            "and connect it again. Or use 'I click each one'.")
            return
        # The dropdown lists the empty cells first, since that's where answers go.
        filled = [c for c in cells if c["text"]]
        choices = [None] + [c for c in cells if not c["text"]] + ([DIVIDER] + filled if filled else [])
        self.word = {"path": os.path.abspath(path), "name": os.path.basename(path), "cells": cells,
                     "choices": choices,
                     "labels": [c["label"] if isinstance(c, dict) else c or "— skip this box —" for c in choices]}
        empty = sum(1 for c in cells if not c["text"])
        self.word_info.set(f"{self.word['name']} · {len(cells)} cells ({empty} empty)")
        self.fill_btn.configure(state="normal")
        self.word_radio.configure(state="normal")
        for b in self.boxes:
            b["combo"].configure(values=self.word["labels"])
            b["target"] = None
        self._fill_in_order()
        self.box_mode.set("word")
        for b in self.boxes:
            self._show_rows(b)
        if open_it:
            try:
                open_in_word(self.word["path"])
            except Exception:
                pass
        self.status.set(f"Connected to {self.word['name']}. Check which cell each box goes in, "
                        "then press Type into Word.")

    def _fill_in_order(self):
        """Put the boxes into the empty cells, in order."""
        if not self.word:
            return
        empty = [c for c in self.word["cells"] if not c["text"]]
        for b, cell in zip(self.boxes, empty + [None] * len(self.boxes)):
            self._set_target(b, cell)
        self._refresh_boxes()

    def _set_target(self, entry, cell):
        entry["target"] = cell
        if self.word:
            entry["combo"].configure(values=self.word["labels"])
            entry["combo"].current(self.word["choices"].index(cell) if cell else 0)

    def _on_target_picked(self, entry):
        choice = self.word["choices"][entry["combo"].current()] if self.word else None
        if not isinstance(choice, dict):      # "skip" or the divider line
            choice = None
            self._set_target(entry, None)
        entry["target"] = choice
        self._refresh_boxes()

    def _widen(self, combo):
        """Let the dropdown list be wider than the box, so long questions fit."""
        try:
            from tkinter import font as tkfont
            f = tkfont.nametofont("TkDefaultFont")
            need = max((f.measure(v) for v in combo.cget("values")), default=0) + 40
            extra = max(0, min(need, self.root.winfo_width() - 40) - combo.winfo_width())
            ttk.Style().configure("Wide.TCombobox", postoffset=(0, 0, extra, 0))
        except Exception:
            pass

    def _show_rows(self, entry):
        """Show the 'Goes in:' row in Word mode and the spot row in spot mode."""
        mode = self.box_mode.get()
        if self.word and mode == "word":
            entry["where"].pack(fill="x", pady=(4, 0))
            if entry["target"] is None and not entry["combo"].get():
                self._set_target(entry, None)
        else:
            entry["where"].pack_forget()
        if mode == "spot":
            entry["spot_row"].pack(fill="x", pady=(4, 0))
        else:
            entry["spot_row"].pack_forget()

    def _on_mode_changed(self):
        for b in self.boxes:
            self._show_rows(b)
        self._refresh_boxes()

    # ----- click spots -----
    def _set_spot(self, entry, seconds=4):
        """Hide the window, wait while you point at the spot, then remember it."""
        if self.typist is None:
            self.status.set(self.typist_error)
            return
        if self.typist.busy:
            return
        n = self.boxes.index(entry) + 1
        self.root.iconify()
        toast = None
        try:  # a little countdown at the top of the screen
            toast = tk.Toplevel(self.root)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            label = tk.Label(toast, font=("", 16, "bold"), bg="#1f2937", fg="white", padx=18, pady=10)
            label.pack()
            toast.update_idletasks()
            toast.geometry(f"+{max(0, self.root.winfo_screenwidth() // 2 - 260)}+30")
        except Exception:
            toast, label = None, None

        def tick(left):
            if label is not None:
                label.configure(text=f"Box {n}: point the mouse where it should type…  {left}")
            if left > 0:
                self.root.after(1000, tick, left - 1)
                return
            x, y = self.typist.mouse.position
            entry["spot"] = (int(x), int(y))
            entry["spot_var"].set("✓ Spot set")
            if toast is not None:
                toast.destroy()
            self.root.deiconify()
            self.root.lift()
            self.status.set(f"Box {n} will be typed where the mouse was. Press Show to check it.")
            self._refresh_boxes()

        tick(seconds)

    def _show_spot(self, entry):
        """Move the mouse to the box's spot (without clicking) so you can check it."""
        if self.typist is None or entry["spot"] is None:
            self.status.set("Press Set spot first.")
            return
        self.typist.mouse.position = entry["spot"]

    def _on_box_changed(self, body):
        if body.edit_modified():
            body.edit_modified(False)
            self._refresh_boxes()

    def _remove_box(self, entry):
        if self.run and self.typist and self.typist.busy:
            return
        entry["card"].destroy()
        self.boxes.remove(entry)
        self._layout_boxes(force=True)

    def _clear_boxes(self):
        if self.run and self.typist and self.typist.busy:
            return
        for b in self.boxes:
            b["card"].destroy()
        self.boxes = []
        self._add_box()

    def _fill_boxes(self, text):
        parts = split_paragraphs(text)
        if not parts:
            self.status.set("There was no text to split.")
            return
        spots = [b["spot"] for b in self.boxes]
        for b in self.boxes:
            b["card"].destroy()
        self.boxes = []
        for i, part in enumerate(parts):
            self._add_box(part)
            if i < len(spots) and spots[i]:   # box 1 keeps box 1's spot, and so on
                self.boxes[-1]["spot"] = spots[i]
                self.boxes[-1]["spot_var"].set("✓ Spot set")
        self.box_area.canvas.yview_moveto(0)
        if self.word:
            self._fill_in_order()
        self.status.set(f"Split into {len(parts)} boxes. Check them, then press Type next box (or Type all boxes) at the bottom.")

    def _paste_split(self):
        try:
            self._fill_boxes(self.root.clipboard_get())
        except tk.TclError:
            self.status.set("Nothing to paste. Copy some text first.")

    def _split_text_tab(self):
        self._fill_boxes(self._get_text())

    def _reset_done(self):
        for b in self.boxes:
            b["done"] = False
        self._refresh_boxes()

    def _box_text(self, entry):
        return entry["text"].get("1.0", "end-1c").replace("\r\n", "\n").replace("\r", "\n").strip("\n").rstrip()

    def _on_box_area_resize(self, event):
        self._layout_boxes(width=event.width)

    def _layout_boxes(self, width=None, force=False):
        width = width or self.box_area.canvas.winfo_width()
        cols = 2 if width >= 560 else 1
        if cols == self.box_cols and not force:
            return
        self.box_cols = cols
        for c in range(2):
            self.box_area.inner.columnconfigure(c, weight=1 if c < cols else 0, uniform="box" if c < cols else "")
        for i, b in enumerate(self.boxes):
            b["title"].configure(text=f"Box {i + 1}")
            b["card"].grid(row=i // cols, column=i % cols, sticky="nsew", padx=4, pady=4)
        self._refresh_boxes()

    def _next_box(self):
        for b in self.boxes:
            if not b["done"] and self._box_text(b).strip():
                return b
        return None

    def _refresh_boxes(self):
        """Update colours, labels, the Start button and the box summary."""
        typing_box = self.run.get("current") if self.run else None
        nxt = self._next_box()
        mode = self.box_mode.get()
        click_mode = mode == "click"
        for b in self.boxes:
            if b is typing_box:
                colour, label = BOX_TYPING, "✎ Typing…"
            elif b["done"]:
                colour, label = BOX_DONE, "✓ Done"
            elif b is nxt and click_mode:
                colour, label = BOX_NEXT, "▶ Next"
            elif mode == "word" and b["target"] is None and self._box_text(b).strip():
                colour, label = BOX_IDLE, "(skipped)"
            elif mode == "spot" and b["spot"] is None and self._box_text(b).strip():
                colour, label = BOX_IDLE, "(no spot)"
            else:
                colour, label = BOX_IDLE, ""
            b["card"].configure(highlightbackground=colour, highlightcolor=colour)
            b["status"].set(label)

        filled = [b for b in self.boxes if self._box_text(b).strip()]
        done = sum(1 for b in filled if b["done"])
        words = sum(len(self._box_text(b).split()) for b in filled)
        chars = sum(len(self._box_text(b)) for b in filled)
        wpm = self._avg_wpm()
        self.box_info.set(f"{len(filled)} boxes · {done} done · {words} words · "
                          f"about {format_duration(seconds_for(' ' * chars, wpm))} in all")

        if self._on_boxes_tab():
            if mode == "word":
                n = sum(1 for b in self.boxes if b["target"] and self._box_text(b).strip())
                text = f"▶  Type into Word ({n} box{'' if n == 1 else 'es'})"
            elif mode == "spot":
                n = sum(1 for b in self.boxes if b["spot"] and self._box_text(b).strip())
                text = f"▶  Click & type ({n} box{'' if n == 1 else 'es'})"
            elif mode == "tab":
                text = "▶  Type all boxes"
            elif nxt is not None:
                text = f"▶  Type next box ({self.boxes.index(nxt) + 1})" + ("" if IS_MAC else "  F9")
            else:
                text = "✓  All boxes done"
        else:
            text = "▶  Start typing"
        self.start_btn.configure(text=text)

    def _on_boxes_tab(self):
        try:
            return self.tabs.index("current") == 1
        except tk.TclError:
            return False

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

    def _set_text(self, text):
        self.text.edit_separator()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_separator()   # so Ctrl+Z / Cmd+Z can undo the whole change

    def _clear_text(self):
        self.text.delete("1.0", "end")
        self.natural.set(False)
        self._natural_original = self._natural_result = None

    def _toggle_natural(self):
        """Natural tone on: rewrite the text so it reads like everyday writing.
        Off: put the original back (unless you've edited it since)."""
        if self.natural.get():
            original = self._get_text()
            if not original.strip():
                self.natural.set(False)
                self.status.set("Paste some text first, then switch on Natural tone.")
                return
            new, n = naturalize(original)
            self._natural_original, self._natural_result = original, new
            self._set_text(new)
            self.status.set(f"Natural tone on: {n} change{'' if n == 1 else 's'}. Read it over and tweak anything "
                            "you like. Switch it off to get your original back." if n else
                            "Natural tone on: nothing needed changing.")
        else:
            if self._natural_original is not None and self._get_text() == self._natural_result:
                self._set_text(self._natural_original)
                self.status.set("Natural tone off: your original text is back.")
            else:
                self.status.set("Natural tone off. You'd edited the text, so I kept your edits.")
            self._natural_original = self._natural_result = None

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

    def _speed_range(self):
        """(slowest, fastest) when Random speed is on, otherwise None."""
        if not self.random_speed.get():
            return None
        lo = max(1, self._safe_int(self.wpm_lo, 40))
        hi = max(1, self._safe_int(self.wpm_hi, 90))
        return (min(lo, hi), max(lo, hi))

    def _avg_wpm(self):
        r = self._speed_range()
        return average_speed(*r) if r else max(1, self._safe_int(self.wpm, 60))

    def _on_settings(self):
        if self.typist is not None:
            self.typist.wpm = max(1, self._safe_int(self.wpm, 60))
            self.typist.wpm_range = self._speed_range()
        state = "disabled" if self.random_speed.get() else "normal"
        for w in (self.wpm_scale, self.wpm_box):
            w.configure(state=state)
        self._update_info()
        self._refresh_boxes()

    def _update_info(self):
        text = self._get_text()
        words = len(text.split())
        wpm = self._avg_wpm()
        self.info.set(f"{words} words · {len(text)} characters · about {format_duration(seconds_for(text, wpm))}")

    # ----- actions -----
    def _ready(self):
        """Checks shared by every way of starting. Returns True when we can type."""
        if self.typist is None:
            self.status.set(self.typist_error)
            return False
        if self.typist.busy:
            return False
        if self.background.get():
            return True   # no real key presses, so the Mac's key permission isn't needed
        problem = mac_permission_problem()
        if problem:
            self.status.set(problem.split("\n")[0])
            messagebox.showinfo(APP_NAME, problem)
            return False
        return True

    def _plan(self, text):
        return build_plan(
            text,
            variation=self.variation.get() / 100.0,
            typo_percent=float(self.typos.get()),
            natural_pauses=self.pauses.get(),
            typo_words=parse_typo_targets(self.typo_targets.get())[0],
            typo_letters=parse_typo_targets(self.typo_targets.get())[1],
            fix_chosen=self.fix_chosen.get(),
        )

    def _begin(self, text, run, countdown=None, plan=None, jumps=None):
        plan = plan if plan is not None else self._plan(text)
        bg = self.background.get()
        run["background"] = bg
        self.run = run
        self.typist.wpm = max(1, self._safe_int(self.wpm, 60))
        self.typist.wpm_range = self._speed_range()
        self.typist.start(
            text, plan,
            (countdown or 2) if bg else (countdown or max(1, self._safe_int(self.delay, 5))),
            jumps,
            output=WordBackground(self._on_main, pinned=self.pin.get()) if bg else None,
            corner_stop=not bg,   # you're using the mouse yourself, so no corner stop
        )
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self._refresh_boxes()

    def _on_main(self, fn):
        """Run fn on the window's thread and wait for it (AppleScript needs this on a Mac)."""
        if threading.current_thread() is threading.main_thread():
            return fn()
        box, done = {}, threading.Event()

        def go():
            try:
                box["result"] = fn()
            except Exception as exc:
                box["error"] = exc
            done.set()

        self.root.after(0, go)
        if not done.wait(130):
            raise RuntimeError("Word didn't answer.")
        if "error" in box:
            raise box["error"]
        return box.get("result")

    def _background_ok(self):
        """Background typing only works where Word can be told what to type."""
        if not self.background.get():
            return True
        if self._on_boxes_tab() and self.box_mode.get() != "word":
            self.status.set("Background typing works on the Text tab, and on the Boxes tab with 'Word cells'. "
                            "Turn off 'Type in the background' to use the other ways.")
            return False
        return True

    def _start(self, countdown=None):
        if not self._background_ok():
            return
        if self._on_boxes_tab():
            if self.box_mode.get() == "word":
                self._type_into_word()
            elif self.box_mode.get() == "spot":
                self._type_spots()
            elif self.box_mode.get() == "tab":
                self._type_all_boxes()
            else:
                nxt = self._next_box()
                if nxt is None:
                    self.status.set("All boxes are done. Press Start over to type them again.")
                    return
                self._type_box(nxt, countdown)
            return
        text = self._get_text()
        if not text.strip():
            self.status.set("There's nothing to type yet. Paste some text first.")
            return
        if self._ready():
            self._begin(text, {"kind": "text"}, countdown)

    def _type_box(self, entry, countdown=None):
        if not self._background_ok():
            return
        text = self._box_text(entry)
        if not text.strip():
            self.status.set("That box is empty.")
            return
        if self.box_mode.get() == "spot":
            if entry["spot"] is None:
                self.status.set("Set a spot for that box first (Set spot).")
                return
            self._type_spots([entry])
            return
        if self.box_mode.get() == "word" and self.word:
            if entry["target"] is None:
                self.status.set("Pick a Word cell for that box first (Goes in:).")
                return
            self._type_into_word([entry])
            return
        if self._ready():
            self._begin(text, {"kind": "box", "box": entry, "current": entry}, countdown)

    def _type_all_boxes(self):
        todo = [b for b in self.boxes if self._box_text(b).strip()]
        if not todo:
            self.status.set("The boxes are empty. Paste some text first.")
            return
        if not self._ready():
            return
        # In a Word table, Tab jumps to the next cell, so a Tab inside a box
        # would land in the wrong cell: turn those into spaces.
        texts = [self._box_text(b).replace("\t", " ") for b in todo]
        bounds, pos = [], 0
        for b, t in zip(todo, texts):
            bounds.append((b, pos + len(t)))
            pos += len(t) + 1  # the Tab after it
        for b in todo:
            b["done"] = False
        self._begin("\t".join(texts), {"kind": "tab", "bounds": bounds, "current": todo[0]})

    def _type_spots(self, todo=None):
        """Click each box's spot on the screen and type the box there."""
        if todo is None:
            todo = [b for b in self.boxes if b["spot"] and self._box_text(b).strip()]
        if not todo:
            self.status.set("No box has a spot yet. Press Set spot on a box first.")
            return
        if not self._ready():
            return
        plan, jumps, bounds, texts, pos = [], {}, [], [], 0
        for b in todo:
            text = self._box_text(b)
            click = (lambda xy=b["spot"]: self.typist.click_at(*xy))
            # After a pause, clicking the spot again would land in the middle of
            # what's already typed, so then you click back in yourself.
            click.again_after_pause = False
            jumps[len(plan)] = click
            plan += self._plan(text)
            pos += len(text)
            bounds.append((b, pos))
            texts.append(text)
            b["done"] = False
        self._begin("".join(texts), {"kind": "spot", "bounds": bounds, "current": todo[0]},
                    countdown=3, plan=plan, jumps=jumps)
        # Get this window out of the way, so it can't cover a spot.
        self.root.after(200, self.root.iconify)

    def _type_into_word(self, todo=None):
        """Jump into each box's Word cell and type it there."""
        if not self.word:
            self.status.set("Connect a Word document first.")
            return
        if todo is None:
            todo = [b for b in self.boxes if b["target"] and self._box_text(b).strip()]
        if not todo:
            self.status.set("No box has a Word cell yet. Pick one under 'Goes in:' or press Fill in order.")
            return
        if not self._ready():
            return
        path = self.word["path"]
        plan, jumps, bounds, texts, pos = [], {}, [], [], 0
        for b in todo:
            text = self._box_text(b).replace("\t", " ")  # a Tab would jump to another cell
            cell = b["target"]
            if cell["text"]:
                # The cell already has words in it, like "Name:" - don't glue onto them.
                text = (" " if cell["text"].endswith(":") else "\n") + text
            front = not self.background.get()
            jumps[len(plan)] = (lambda c=cell: self.jumper(path, c["table"], c["row"], c["col"], front=front))
            plan += self._plan(text)
            pos += len(text)
            bounds.append((b, pos))
            texts.append(text)
            b["done"] = False
        # Word comes to the front by itself, so only a short heads-up is needed.
        self._begin("".join(texts), {"kind": "word", "bounds": bounds, "current": todo[0]},
                    countdown=2, plan=plan, jumps=jumps)

    def _pause(self):
        if self.typist:
            self.typist.toggle_pause()

    def _stop(self):
        if self.typist:
            self.typist.stop()

    def _type_next_hotkey(self):
        """F9 on Windows: you're already in the right box, so start almost at once."""
        if self.typist and not self.typist.busy and self._on_boxes_tab() and self.box_mode.get() == "click":
            self._start(countdown=1)

    def _start_hotkeys(self):
        """F8, F9 and Esc work even while Word has focus."""
        # On macOS a global key listener next to the window can crash Tk, so there
        # the on-screen buttons are used instead.
        if self.typist is None or sys.platform == "darwin":
            return
        try:
            from pynput import keyboard
        except Exception:
            return

        def on_press(key):
            if self.run and self.run.get("background"):
                return   # you're typing in other apps; those keys aren't for us
            if key == keyboard.Key.esc and self.typist.busy:
                self.root.after(0, self._stop)
            elif key == keyboard.Key.f8:
                self.root.after(0, self._pause)
            elif key == keyboard.Key.f9:
                self.root.after(0, self._type_next_hotkey)

        try:
            self.listener = keyboard.Listener(on_press=on_press)
            self.listener.daemon = True
            self.listener.start()
        except Exception:
            pass  # hotkeys are a bonus; the buttons still work

    def _track_run(self, t):
        """Tick boxes off as they get typed."""
        run = self.run
        if run is None:
            return
        if run["kind"] in ("tab", "word", "spot"):
            current = None
            for b, end in run["bounds"]:
                if t.done_chars >= end:
                    b["done"] = True
                elif current is None:
                    current = b
            run["current"] = current if t.busy else None
        elif run["kind"] == "box" and t.state == "done":
            run["box"]["done"] = True
        if not t.busy:
            if run["kind"] == "spot":
                self.root.deiconify()   # bring the window back when it's finished
                self.root.lift()
            self.run = None
        self._refresh_boxes()

    def _poll(self):
        t = self.typist
        if t is not None:
            if t.total_chars:
                self.progress["value"] = 100.0 * t.done_chars / t.total_chars
            run_kind = self.run["kind"] if self.run else None
            self._track_run(t)
            state = t.state
            if state == "countdown" and run_kind == "spot":
                self.status.set(f"Clicking your spots in {t.countdown_left}… hands off the keyboard and mouse. "
                                f"{STOP_HINT}.")
            elif state == "countdown" and run_kind == "word":
                self.status.set(f"Switching to Word in {t.countdown_left}… hands off the keyboard and mouse.")
            elif state == "countdown" and self.run and self.run.get("background"):
                self.status.set(f"Typing into Word in the background in {t.countdown_left}… "
                                "you can switch to other apps.")
            elif state == "countdown":
                self.status.set(f"Click inside your Word document now… starting in {t.countdown_left}")
            elif state == "typing":
                left = seconds_for(" " * (t.total_chars - t.done_chars), t.avg_wpm)
                speed = f"{int(t.live_wpm)} WPM" + (f" (random {t.wpm_range[0]}–{t.wpm_range[1]})"
                                                   if t.wpm_range else "")
                if self.run and self.run.get("background"):
                    self.status.set(f"Typing into Word in the background at {speed}… "
                                    f"{t.done_chars}/{t.total_chars} characters, about {format_duration(left)} "
                                    "left. Press Stop here to stop.")
                else:
                    self.status.set(f"Typing at {speed}… {t.done_chars}/{t.total_chars} characters, "
                                    f"about {format_duration(left)} left.  {STOP_HINT}.")
            elif state == "paused":
                self.status.set("Paused. Press Resume, then click back into Word.")
            elif state == "done" and run_kind == "box":
                if self._next_box() is None:
                    self.status.set("Finished! Every box is done ✔")
                elif IS_MAC:
                    self.status.set("Box done ✔  Press Type next box, then click into the next box in Word.")
                else:
                    self.status.set("Box done ✔  Click into the next box in Word and press F9 "
                                    "(or press Type next box).")
            elif state == "done" and run_kind is not None:
                self.status.set("Finished! ✔")
            elif state == "stopped" and run_kind is not None:
                self.status.set("Stopped.")
            elif state == "error" and run_kind is not None:
                self.status.set(t.error if run_kind == "word" else "Something went wrong: " + t.error)

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
