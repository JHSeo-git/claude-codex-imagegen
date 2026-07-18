---
type: Workflow
title: "Claude Code Skill Workflow & Prompting"
description: "The codex-imagegen Claude Code skill's 5-step workflow (check, guide, compose, generate, verify visually), the labeled prompt schema, the failure-mode table, and the pastel-anime-slides style recipe for cohesive multi-image sets."
resource: skills/codex-imagegen/SKILL.md
tags: [claude-code, skill, workflow, prompting, style-guide]
---

# Claude Code skill workflow & prompting

`skills/codex-imagegen/SKILL.md` is what Claude Code loads when a user asks for an image (triggers include "generate an image", "make an icon", "이미지 만들어줘"). It is deliberately thin on image knowledge: every mechanical step is executed through the [imagegen CLI](imagegen-cli.md), and prompting rules are read live from Codex rather than hardcoded.

## The 5-step workflow

1. **`check`** once per session — not ready → surface the printed `next:` steps and stop. Login failure is user-interactive: ask the user to run `! codex login` (the agent cannot log in for them).
2. **`guide`** before composing any prompt — Codex's own imagegen guide is the source of truth for prompt schema, size limits, and output paths, and it updates with Codex releases. For in-image text, logos, or edits, also read `guide --ref prompting`.
3. **Compose** using the guide's labeled schema: *use case → scene → subject → style → composition → lighting → text verbatim → constraints*. Quote literal text in double quotes, add explicit negatives ("no watermark, no extra text"), skip empty adjectives.
4. **`generate`** with Bash tool timeout ≥ 360000 ms (one image ≈ 40–120 s). Long/multiline prompts go through `--prompt-file`; edits pass the original via `-i` phrased as "change only X; keep everything else identical"; batches run one call per asset, sequentially.
5. **Verify visually** — Read the saved PNG and compare against the request. On drift, regenerate with **one** targeted change, keeping the rest of the prompt identical. On size mismatch (the CLI's `WARN:` line), do *not* regenerate — [size adherence is loose](imagegen-cli.md); downscale locally with `sips` or ImageMagick.

The failure-mode table in `SKILL.md` maps each symptom (login FAIL, missing binary, sandbox-blocked network, timeout, exit 4, size WARN, garbled text) to its fix — keep it in sync with the CLI's actual exit codes and output lines.

## Style recipes: pastel-anime-slides

`examples/pastel-anime-slides/README.md` is the worked demonstration of step 3's prompt schema, aimed at a harder problem than single images: a **cohesive set** (five presentation-deck illustrations that look like one artist drew them). Its transferable rules:

- **Verbatim shared blocks** — paste the exact same `Style:` and `Constraints:` lines into every prompt in the set; repeating identical wording beats hoping the model stays consistent (same for palette color names).
- **One metaphor per image** — pick the slide's message, then a single subject that carries it.
- **Reserve negative space in the prompt** — state which region must stay pale and empty so title text can be overlaid; this is what makes images usable as full-bleed slide backgrounds.
- **No text in the bitmap, ever** — anything with writing becomes "abstract stroke lines" or "blank labels"; titles belong to the slide layer.
- **`--quality medium` suffices** for flat cel-shaded art; reserve `high` for finals and text-heavy images.

New style guides should follow the same shape: preview table, shared blocks, template, rules, then the worked prompts that produced the previews.

## Operating constraints

Image turns burn ChatGPT subscription quota 3–5× faster than text turns — this project is scoped to personal/dev use, not production backends. The sandbox rule (never `--dangerously-bypass-approvals-and-sandbox`) is enforced by the [CLI's codex invocation](imagegen-cli.md), and `SKILL.md` repeats it as an instruction so the agent never adds the flag manually.
