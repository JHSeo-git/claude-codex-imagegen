---
type: Quickstart
title: "claude-codex-imagegen Quickstart"
description: "Entrypoint to the claude-codex-imagegen wiki: a Claude Code skill plus stdlib Python CLI that generates images by driving Codex CLI's built-in $imagegen skill (gpt-image-2) on a ChatGPT subscription instead of per-image API billing."
resource: README.md
tags: [quickstart, overview, claude-code, codex, image-generation]
---

# Quickstart

`claude-codex-imagegen` lets Claude Code generate images without an image-API key by delegating to the **Codex CLI's built-in `$imagegen` skill** (gpt-image-2), billed to the user's existing ChatGPT subscription. The pipeline is:

```
Claude Code ──(codex-imagegen skill)──▶ codex exec '$imagegen …' ──▶ PNG saved to the requested path
```

The repository ships two tightly coupled pieces:

- The **[Claude Code skill workflow](skill-workflow.md)** (`skills/codex-imagegen/SKILL.md`) — the instructions Claude Code follows when a user asks for an image: check prerequisites, read Codex's own prompting guide, compose a labeled prompt, generate, verify visually. It dispatches every step to the CLI below.
- The **[imagegen CLI](imagegen-cli.md)** (`skills/codex-imagegen/scripts/codex_imagegen.py`) — a stdlib-only Python 3.9+ script with `check` / `guide` / `generate` subcommands that wraps `codex exec` non-interactively and recovers the generated PNG through a 3-tier fallback.

Why it exists: image generation through the OpenAI API bills per image, while a ChatGPT subscription already includes gpt-image-2 usage through Codex. This project trades a little orchestration complexity (driving a second CLI) for zero marginal image cost during personal/dev work. It deliberately stays subscription-quota-friendly — the docs warn against production use.

## Install & use

```sh
npx skills add JHSeo-git/claude-codex-imagegen   # primary
# or: cp -r skills/codex-imagegen ~/.claude/skills/
```

Prerequisites: Codex CLI ≥ 0.130 (`npm i -g @openai/codex`), logged in via `codex login`, Python 3.9+ (no pip installs). Then just ask Claude Code for an image, or drive the [CLI](imagegen-cli.md) directly — worked commands are in `README.md`.

## Repository layout

- `skills/codex-imagegen/` — the installable skill: `SKILL.md` + `scripts/codex_imagegen.py`. This is the entire product surface.
- `tests/test_codex_imagegen.py` — unittest suite over the CLI's pure functions (run: `python3 -m unittest discover -s tests -v`).
- `examples/pastel-anime-slides/` — a reusable style recipe (shared style/constraints blocks, five worked prompts, preview PNGs) showing how the [skill's prompt schema](skill-workflow.md) produces a cohesive image set.
- `output/` — gitignored local scratch for generated images.
- `README.md`, `CHANGELOG.md`, `LICENSE` (MIT).

## Guidance for future changes

- The skill and CLI must stay in lockstep: `SKILL.md` documents flags, exit codes, and output lines (`SAVED:`, `WARN:`) that `codex_imagegen.py` actually prints. Change one → check the other, and update the failure-mode table in `SKILL.md`.
- The CLI is intentionally **stdlib-only**; adding a pip dependency breaks the zero-install contract stated in `README.md`.
- Codex CLI behavior shifts between versions (e.g. ≥ 0.141 embeds images in session rollouts instead of writing `generated_images/`); the [3-tier recovery](imagegen-cli.md) exists precisely for this. When Codex changes output behavior, extend recovery rather than pinning versions.
- Add or adjust tests in `tests/test_codex_imagegen.py` for any CLI logic change — the suite mocks subprocess and filesystem, so it runs without Codex installed.
- User-visible behavior changes belong in `CHANGELOG.md` (one bullet per entry).

## Backlog

- (none — all identified areas are documented)
