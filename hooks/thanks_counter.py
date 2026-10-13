#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook that counts how often you thank Claude.

Reads the hook payload from stdin. When the prompt contains a thank-you, it
increments a persistent counter and hands Claude a short note with the running
total. A prompt that is *only* a thank-you also asks Claude for a one-line reply.

Each thank-you also gets a one-line note on *why*, appended to
~/.claude/thanks-notes.md. A detached worker reads the end of the transcript,
asks Haiku for a one-sentence reason, and falls back to the raw prompt if that
fails, so the hook itself still returns at once.

Prompts without a thank-you produce no output, so they cost nothing extra.
Standard library only; works with the macOS system Python 3.9.
"""

import datetime
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys

COUNT_FILE = os.path.expanduser(
    os.environ.get("THANKS_COUNTER_FILE", "~/.claude/thanks-count.json")
)
NOTES_FILE = os.path.expanduser(
    os.environ.get("THANKS_NOTES_FILE", "~/.claude/thanks-notes.md")
)
# Set for the nested `claude -p` call so it doesn't count or note itself.
SKIP_ENV = "THANKS_COUNTER_SKIP"
CONTEXT_CHARS = 6000
# With these unset (and --setting-sources "" skipping any apiKeyHelper), the
# nested call falls back to the claude.ai login, i.e. the subscription.
API_AUTH_VARS = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
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

# Links and paths, e.g. github.com/you/claude-thanks-counter, aren't gratitude.
LINKS_AND_PATHS = re.compile(r"\S*://\S*|www\.\S+|\S*[/\\]\S*")

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
    text = _normalize(LINKS_AND_PATHS.sub(" ", prompt))
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


def _recent_messages(transcript_path, limit=8):
    """Return the last few user prompts and assistant replies as plain text."""
    msgs = []
    try:
        with open(transcript_path) as f:
            lines = f.readlines()[-400:]
    except (OSError, TypeError):
        return msgs
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        msg = entry.get("message") or {}
        role, content = msg.get("role"), msg.get("content")
        if entry.get("isMeta") or role not in ("user", "assistant"):
            continue
        if isinstance(content, list):
            content = "\n".join(
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        if isinstance(content, str) and content.strip():
            msgs.append("%s: %s" % (role, content.strip()))
    return msgs[-limit:]


def _subscription_env():
    """Env for the nested call: drop API-key auth so it bills the claude.ai plan."""
    env = {k: v for k, v in os.environ.items() if k not in API_AUTH_VARS}
    env[SKIP_ENV] = "1"
    return env


def summarize(prompt, transcript_path):
    """Ask Haiku in one sentence what the user is thanking Claude for."""
    context = "\n\n".join(_recent_messages(transcript_path))[-CONTEXT_CHARS:]
    claude = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    request = (
        "Below is the end of a conversation with a coding agent, followed by "
        "the user's latest message, which thanks the agent. In one short "
        "English sentence (under 20 words), say what the user is thanking "
        "the agent for. Output only that sentence.\n\n"
        "<conversation>\n%s\n</conversation>\n\n<latest>\n%s\n</latest>"
        % (context, prompt)
    )
    try:
        out = subprocess.run(
            [claude, "-p", "--model", "haiku", "--tools", "",
             "--setting-sources", "", "--no-session-persistence"],
            input=request, capture_output=True, text=True, timeout=120,
            env=_subscription_env(), cwd="/tmp",
        )
        line = out.stdout.strip().splitlines()[0] if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        line = ""
    return line.strip() or "(no summary) " + " ".join(prompt.split())[:120]


def write_note(count, prompt, transcript_path, cwd, path=NOTES_FILE):
    """Append one line to the notes file: number, time, project and reason."""
    reason = summarize(prompt, transcript_path)
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    project = os.path.basename(cwd.rstrip("/")) if cwd else "?"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        if not f.read(1):
            f.write("# Why I said thanks\n\n")
        f.write("- #%d · %s · %s — %s\n" % (count, when, project, reason))


def spawn_note_worker(count, payload):
    """Write the note in a detached process so the prompt isn't held up."""
    job = json.dumps({
        "count": count,
        "prompt": payload.get("prompt", ""),
        "transcript": payload.get("transcript_path"),
        "cwd": payload.get("cwd") or os.getcwd(),
    })
    worker = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--note"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    worker.stdin.write(job.encode())
    worker.stdin.close()  # don't wait; the worker outlives this hook


def main():
    if os.environ.get(SKIP_ENV):
        return 0
    if sys.argv[1:] == ["--note"]:
        job = json.load(sys.stdin)
        write_note(job["count"], job["prompt"], job["transcript"], job["cwd"])
        return 0
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
    if os.environ.get("THANKS_NOTES", "1") != "0":
        try:
            spawn_note_worker(count, payload)
        except (OSError, subprocess.SubprocessError):
            pass

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
