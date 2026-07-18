---
type: Documentation Index
title: "OpenWiki"
description: "Files and subdirectories in OpenWiki."
---

# Files

- [imagegen CLI (codex_imagegen.py)](imagegen-cli.md) - The stdlib-only Python CLI with check/guide/generate subcommands that wraps codex exec '$imagegen …' non-interactively, enforces a save contract, and recovers the generated PNG via a 3-tier fallback. Covers codex args, exit codes, sandbox posture, size-adherence warnings, and tests.
- [claude-codex-imagegen Quickstart](quickstart.md) - Entrypoint to the claude-codex-imagegen wiki: a Claude Code skill plus stdlib Python CLI that generates images by driving Codex CLI's built-in $imagegen skill (gpt-image-2) on a ChatGPT subscription instead of per-image API billing.
- [Claude Code Skill Workflow & Prompting](skill-workflow.md) - The codex-imagegen Claude Code skill's 5-step workflow (check, guide, compose, generate, verify visually), the labeled prompt schema, the failure-mode table, and the pastel-anime-slides style recipe for cohesive multi-image sets.
