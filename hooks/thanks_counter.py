#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook that counts how often you thank Claude.

Reads the hook payload from stdin. When the prompt contains a thank-you, it
increments a persistent counter and hands Claude a short note with the running
total. A prompt that is *only* a thank-you also asks Claude for a one-line reply.

Prompts without a thank-you produce no output, so they cost nothing extra.
Standard library only; works with the macOS system Python 3.9.
"""

import datetime
import fcntl
import json
import os
import re
import sys

COUNT_FILE = os.path.expanduser(
    os.environ.get("THANKS_COUNTER_FILE", "~/.claude/thanks-count.json")
)

# Longest phrases first so "thank you so much" wins over "thank you".
THANKS_PHRASES = [
    "thank you so much", "thank you very much", "thanks so much",
    "thanks a lot", "thanks a ton", "many thanks", "much appreciated",
    "appreciate it", "appreciate you", "thank you", "thank u", "thankyou",
    "thanks", "thanx", "thnx", "thx", "tysm", "tyvm", "ty", "cheers",
    "merci", "danke", "gracias", "arigato", "arigatou",
    "非常感谢", "谢谢你", "谢谢", "多谢", "感谢", "谢啦", "谢了",
    "ありがとう",
]

# Words that may surround a thank-you without making it a real request.
FILLER = {
    "again", "a", "lot", "so", "much", "very", "claude", "buddy", "man",
    "mate", "friend", "pal", "dude", "bro", "great", "awesome", "perfect",
    "nice", "cool", "ok", "okay", "kk", "k", "good", "job", "work", "works",
    "worked", "it", "that", "done", "got", "yes", "yay", "wow", "amazing",
    "love", "you", "for", "the", "help", "really", "super", "big", "and",
    "oh", "ah", "excellent", "brilliant", "sweet", "all", "this",
    "啦", "了", "哈", "呀", "啊", "好的", "好", "太好了", "辛苦了", "棒",
}

# A thank-you that is actually a refusal or attribution, not gratitude.
NEGATIVE = re.compile(r"\bno,?\s+thanks?\b|\bthanks\s+to\b|\bthanks\s+but\s+no\b", re.I)

MAX_STANDALONE_LEN = 80


def _normalize(text):
    text = text.lower()
    # Keep letters, digits and CJK; turn punctuation and emoji into spaces.
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _phrase_pattern(phrase):
    if re.match(r"^[a-z ]+$", phrase):
        return r"\b" + re.escape(phrase) + r"\b"
    return re.escape(phrase)  # CJK has no word boundaries


PHRASE_RES = [re.compile(_phrase_pattern(p)) for p in THANKS_PHRASES]


def classify(prompt):
    """Return "standalone", "inline" or None for a user prompt."""
    if not prompt or NEGATIVE.search(prompt):
        return None
    text = _normalize(prompt)
    found = False
    for pattern in PHRASE_RES:
        if pattern.search(text):
            found = True
            text = pattern.sub(" ", text)
    if not found:
        return None
    leftover = [w for w in text.split() if w not in FILLER]
    if not leftover and len(prompt) <= MAX_STANDALONE_LEN:
        return "standalone"
    return "inline"


def bump_count(path=COUNT_FILE):
    """Increment the counter under a file lock and return the new total."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        try:
            data = json.load(f)
        except ValueError:
            data = {}
        data["count"] = int(data.get("count", 0)) + 1
        data.setdefault("first", now)
        data["last"] = now
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)
        f.write("\n")
    return data["count"]


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    kind = classify(payload.get("prompt", ""))
    if kind is None:
        return 0
    try:
        count = bump_count()
    except OSError:
        return 0  # never block the user's prompt over a counter

    if kind == "standalone":
        note = (
            "The user just thanked you. This is thank-you #%d across all "
            "sessions. Reply with one short, warm line that mentions the "
            "number; no summary, no follow-up offers." % count
        )
    else:
        note = (
            "The user thanked you in this message (thank-you #%d across all "
            "sessions). Briefly acknowledge it if natural, then handle the "
            "rest of the request as usual." % count
        )
    json.dump(
        {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": note,
        }},
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
