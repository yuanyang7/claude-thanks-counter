import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "hooks", "thanks_counter.py")
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))

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
                       "the city is pretty"]:
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
            env = dict(os.environ, THANKS_COUNTER_FILE=os.path.join(d, "c.json"))

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


if __name__ == "__main__":
    unittest.main()
