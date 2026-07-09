# claude-codex-imagegen

[![skills.sh](https://skills.sh/b/JHSeo-git/claude-codex-imagegen)](https://skills.sh/JHSeo-git/claude-codex-imagegen)

Generate images from Claude Code by driving the **Codex CLI's built-in `imagegen` skill** (`$imagegen`, gpt-image-2) — using your ChatGPT subscription instead of per-image API billing.

```
Claude Code ──(this skill)──▶ codex exec '$imagegen …' ──▶ PNG saved to your path
```

## How it works

1. Claude Code picks up the `codex-imagegen` skill when you ask for an image.
2. The skill runs `scripts/codex_imagegen.py check` — verifies Codex CLI is installed, **logged in** (`codex login`), and that Codex's built-in imagegen skill exists at `$CODEX_HOME/skills/.system/imagegen`.
3. It reads Codex's own imagegen guide (`... guide`) for prompting rules, size limits, and output-path conventions before composing the prompt.
4. It runs `... generate "<prompt>" -o <path>`, which drives `codex exec` non-interactively (`--sandbox workspace-write`, no dangerous bypass) and recovers the image through a 3-tier fallback:
   - Codex saved it to the requested path directly, or
   - copy the newest `ig_*.png` from `$CODEX_HOME/generated_images/<session>/`, or
   - decode the base64 image embedded in the session rollout `.jsonl` (codex ≥ 0.141 behavior).
5. Claude Code visually verifies the result (Read tool) and iterates if it drifts from the request.

## Prerequisites

- [Codex CLI](https://github.com/openai/codex) ≥ 0.130 (`npm i -g @openai/codex`)
- Logged in: `codex login` (`codex login status` should say "Logged in")
- Python 3.9+ (stdlib only — no pip installs)

## Install

Copy the skill into your Claude Code skills directory (project or global):

```bash
# global
cp -r skills/codex-imagegen ~/.claude/skills/

# or per-project
cp -r skills/codex-imagegen <project>/.claude/skills/
```

## Usage

In Claude Code, just ask: *"프로젝트 히어로 이미지 만들어줘"* / *"generate a 1024x1024 icon of …"*.

Or drive the CLI directly:

```bash
python3 skills/codex-imagegen/scripts/codex_imagegen.py check            # prerequisites + login
python3 skills/codex-imagegen/scripts/codex_imagegen.py guide            # print Codex's imagegen guide
python3 skills/codex-imagegen/scripts/codex_imagegen.py generate \
  "A minimalist line-art seedling icon, 2px black stroke on white, no text" \
  -o assets/seedling.png --size 1024x1024
```

Run `... generate --help` for all flags (`--size`, `--quality`, `--image` refs, `--timeout`, `--dry-run`, `--json`).

## Examples

Reusable style recipes with worked prompts and preview images live in [`examples/`](examples/):

- [`pastel-anime-slides`](examples/pastel-anime-slides/) — clean flat anime background art for presentation decks: shared style/constraints blocks, text-safe negative space, five worked prompts.

## Notes

- Image generation consumes ChatGPT subscription quota noticeably faster than text turns; keep it to personal/dev use, not production backends.
- Codex runs sandboxed (`workspace-write`) — no `--dangerously-bypass-approvals-and-sandbox`. Output paths outside the working directory are whitelisted per-run via `--add-dir`.
- Each image takes roughly 40–120 s; the script default timeout is 600 s.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)

## Credits

Patterns studied from [JunSeo99/claude-skill-codex-imagegen](https://github.com/JunSeo99/claude-skill-codex-imagegen), [yazelin/codex-imagegen-skill](https://github.com/yazelin/codex-imagegen-skill), [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc).
