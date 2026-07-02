---
name: codex-imagegen
description: "Use when the user asks to generate, create, or edit an image, icon, banner, logo, OG image, illustration, or texture file — e.g. 'generate an image', 'make an icon', '이미지 만들어줘', '배너 생성해줘' — and Codex CLI is the image backend. Not for analyzing existing images or for SVG/CSS-native graphics."
---

# codex-imagegen

Generate images by driving Codex CLI's built-in `$imagegen` skill (gpt-image-2, billed to the user's ChatGPT subscription) via the bundled CLI. All commands are:

```bash
python3 <skill-dir>/scripts/codex_imagegen.py <command> ...
```

`<skill-dir>` = this skill's base directory (announced when the skill loads).

## Workflow

1. **Check prerequisites** (once per session):
   ```bash
   python3 <skill-dir>/scripts/codex_imagegen.py check
   ```
   Not ready → surface the printed `next:` steps and stop. Login failure → ask the user to run `! codex login` (interactive; you cannot run it for them).

2. **Read Codex's own imagegen guide before composing the prompt** — it is the source of truth for prompt schema, size limits, and output-path behavior, and it updates with Codex itself:
   ```bash
   python3 <skill-dir>/scripts/codex_imagegen.py guide
   ```
   For in-image text, logos, or edits also read `guide --ref prompting` (list: `guide --list-refs`).

3. **Compose the prompt** using the guide's labeled schema (use case → scene → subject → style → composition → lighting → text verbatim → constraints). Quote literal text in double quotes; add explicit negatives ("no watermark, no extra text"); skip empty adjectives like "8K masterpiece".

4. **Generate** (set Bash tool timeout ≥ 360000 ms; one image ≈ 40–120 s):
   ```bash
   python3 <skill-dir>/scripts/codex_imagegen.py generate "<prompt>" \
     -o <path>.png [--size 1024x1024] [--quality low|medium|high|auto] [-i ref.png] [--json]
   ```
   - Success prints `SAVED: <absolute path>`.
   - Long/multiline prompt → write it to a temp file, pass `--prompt-file` (avoids shell quoting).
   - Editing an existing image → pass it with `-i` and phrase "change only X; keep everything else identical".
   - Batch → one `generate` call per asset, sequentially.
   - Preview the exact codex command without spending quota: `--dry-run`.

5. **Verify visually**: Read the saved PNG with the Read tool and compare against the user's request. Drift → regenerate with ONE targeted change, keeping the rest of the prompt identical. Confirm final size with `--size` if exact dimensions matter (model adherence is loose).

## Quick reference

- Sizes: `1024x1024` (fastest) · `1536x1024` · `1024x1536` · up to `3840x2160`; edges must be multiples of 16, ratio ≤ 3:1, or `auto`.
- Quality: `low` for drafts/iteration, `high` for finals and text-heavy images.
- Default output: `./generated-images/img-<timestamp>.png` when `-o` is omitted.

## Failure modes

| Symptom | Fix |
|---|---|
| `check` FAIL codex login | User runs `! codex login`, then re-run `check` |
| `command not found: codex` | `npm install -g @openai/codex` |
| Exit 3 (codex failed/timeout) | Retry with `--timeout 900`; simplify the prompt |
| Exit 4 (no image recovered) | Re-run with `--verbose` and inspect codex output |
| Garbled in-image text | Wrap exact text in double quotes, add "no duplicate text", `--quality high` |

## Notes

- Image turns burn ChatGPT subscription quota 3–5× faster than text turns — personal/dev use, not production backends.
- Codex runs sandboxed (`--sandbox workspace-write`); never add `--dangerously-bypass-approvals-and-sandbox`.
