# claude-thanks-counter

A tiny [Claude Code](https://claude.com/claude-code) hook that keeps a running,
global count of how many times you've thanked Claude, notes down why each time,
and lets Claude answer a plain "ty" with one short line instead of a full wrap-up.

```
you:    ty!
claude: Anytime! That's thank-you #42 🙏
```

## How it works

A `UserPromptSubmit` hook runs a small Python script on every message you send:

| Your message | What happens |
| --- | --- |
| Only a thank-you (`ty`, `thanks!`, `thank you so much 🙏`, `谢谢`) | Counter +1. Claude is asked for a one-line reply that mentions the total. |
| A thank-you plus a request (`thanks! now add tests`) | Counter +1. Claude gets a note with the total and handles the request as usual. |
| Anything else, or `no thanks` / `thanks to…` | Nothing. The script prints no output, so these messages cost no extra tokens. |

Links and file paths don't count, so pasting `github.com/you/claude-thanks-counter`
isn't a thank-you.

The script does the counting, not Claude, so the number never drifts. It lives
in `~/.claude/thanks-count.json`, so it carries across every session, window
and project:

```json
{
  "count": 42,
  "first": "2026-10-07T14:03:11-07:00",
  "last": "2026-10-09T09:12:45-07:00"
}
```

## Why you said thanks

Each thank-you also adds one line to `~/.claude/thanks-notes.md` saying what it
was for:

```
# Why I said thanks

- #25 · 2026-10-12 20:45 · agentdeck — Setting up subscription-only Haiku calls for the thank-you notes.
- #26 · 2026-10-12 21:02 · trip-studio — Fixing the shader preset that went black on reload.
```

The hook starts a detached worker, so your prompt isn't held up. The worker
reads the last few messages of the chat and asks Haiku, through `claude -p`,
for a one-sentence reason; the line usually lands a few seconds later. That
call:

- uses your claude.ai subscription: it drops `ANTHROPIC_API_KEY`,
  `ANTHROPIC_AUTH_TOKEN` and the Bedrock/Vertex/Foundry switches, and skips your
  settings files, so it can't pick up an API key;
- isn't saved as a session, so it won't show up in your chat history;
- doesn't run your hooks, so it can't count itself.

If the call fails, the line still gets written, holding the start of your
message marked `(no summary)`.

## Install

Requires `python3`, which ships with macOS.

```bash
git clone https://github.com/yuanyang7/claude-thanks-counter.git
cd claude-thanks-counter
./install.sh
```

The installer copies the hook to `~/.claude/hooks/`, registers it in
`~/.claude/settings.json` (backing up the old file first), and leaves your
other hooks alone. Re-running it is safe. Start a new Claude Code session
afterwards.

## Uninstall

```bash
./uninstall.sh
```

This removes the hook but keeps `thanks-count.json` and `thanks-notes.md`, so
your total and notes survive.

## Customize

- **Phrases**: edit `THANKS_PHRASES` and `FILLER` in
  [`hooks/thanks_counter.py`](hooks/thanks_counter.py), then re-run
  `./install.sh`.
- **Counter location**: set `THANKS_COUNTER_FILE` in the hook's environment.
- **Notes location**: set `THANKS_NOTES_FILE`.
- **No notes**: set `THANKS_NOTES=0` to count only, with no Haiku calls.
- **Reset**: delete `~/.claude/thanks-count.json` (and `thanks-notes.md`).

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

MIT
