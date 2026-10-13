import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "hooks", "thanks_counter.py")
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))

import thanks_counter  # noqa: E402
from thanks_counter import bump_count, classify  # noqa: E402


class ClassifyTest(unittest.TestCase):
    def test_standalone(self):
        for prompt in ["ty", "Thanks!", "thank you so much 🙏", "thx claude",
                       "perfect, thanks again!", "谢谢", "谢谢你啦", "好的谢谢",
                       "cheers mate", "awesome, ty!!"]:
            self.assertEqual(classify(prompt), "standalone", prompt)

    def test_inline(self):
        for prompt in ["thanks! now add a test", "谢谢，帮我改一下标题",
                       "ty, can you also push it"]:
            self.assertEqual(classify(prompt), "inline", prompt)

    def test_not_thanks(self):
        for prompt in ["", "fix the bug", "no thanks", "No, thanks.",
                       "thanks to the cache this is fast", "type check it",
                       "the city is pretty",
                       "not this one? https://github.com/me/claude-thanks-counter",
                       "look at ~/.claude/thanks-count.json"]:
            self.assertIsNone(classify(prompt), prompt)


class CounterTest(unittest.TestCase):
    def test_bump_persists(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "count.json")
            self.assertEqual(bump_count(path), 1)
            self.assertEqual(bump_count(path), 2)
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["count"], 2)
            self.assertIn("first", data)

    def test_hook_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, THANKS_NOTES="0",
                       THANKS_COUNTER_FILE=os.path.join(d, "c.json"))

            def run(prompt):
                return subprocess.run(
                    [sys.executable, HOOK], input=json.dumps({"prompt": prompt}),
                    capture_output=True, text=True, env=env, check=True,
                ).stdout

            self.assertEqual(run("refactor this"), "")
            out = json.loads(run("ty!"))
            note = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("#1", note)
            self.assertIn("#2", run("thanks"))


class NotesTest(unittest.TestCase):
    def test_recent_messages_reads_text_only(self):
        entries = [
            {"message": {"role": "user", "content": "fix the login bug"}},
            {"message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "Fixed the redirect."}]}},
            {"message": {"role": "user", "content": [
                {"type": "tool_result", "content": "ok"}]}},
            {"type": "attachment"},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(json.dumps(e) for e in entries) + "\nnot json\n")
        try:
            self.assertEqual(thanks_counter._recent_messages(f.name), [
                "user: fix the login bug", "assistant: Fixed the redirect."])
        finally:
            os.unlink(f.name)

    def test_write_note_appends_lines(self):
        original = thanks_counter.summarize
        thanks_counter.summarize = lambda prompt, path: "Fixing the login bug."
        try:
            with tempfile.TemporaryDirectory() as d:
                notes = os.path.join(d, "new-dir", "notes.md")
                thanks_counter.write_note(7, "ty", None, "/x/agentdeck", notes)
                thanks_counter.write_note(8, "ty", None, "/x/agentdeck", notes)
                with open(notes) as f:
                    lines = f.read().splitlines()
        finally:
            thanks_counter.summarize = original
        self.assertEqual(lines[0], "# Why I said thanks")
        self.assertEqual(len(lines), 4)
        self.assertRegex(lines[2], r"^- #7 · .* · agentdeck — Fixing the login bug\.$")
        self.assertTrue(lines[3].startswith("- #8 "))

    def test_subscription_env_drops_api_keys(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            env = thanks_counter._subscription_env()
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual(env[thanks_counter.SKIP_ENV], "1")


if __name__ == "__main__":
    unittest.main()
