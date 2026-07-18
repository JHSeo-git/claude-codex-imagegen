---
type: CLI Tool
title: "imagegen CLI (codex_imagegen.py)"
description: "The stdlib-only Python CLI with check/guide/generate subcommands that wraps codex exec '$imagegen …' non-interactively, enforces a save contract, and recovers the generated PNG via a 3-tier fallback. Covers codex args, exit codes, sandbox posture, size-adherence warnings, and tests."
resource: skills/codex-imagegen/scripts/codex_imagegen.py
tags: [cli, python, codex, image-generation, subprocess]
---

# imagegen CLI

`skills/codex-imagegen/scripts/codex_imagegen.py` is the executable half of the project — a single-file, stdlib-only Python 3.9+ CLI. It is driven step-by-step by the [Claude Code skill workflow](skill-workflow.md), but works standalone from any shell. Exit codes are part of the skill contract: `0` ok · `2` prerequisites/usage · `3` codex run failed · `4` image not recovered.

## Subcommands

### `check` — prerequisites gate

`build_check_report()` verifies, in order: `codex` binary present and ≥ `MIN_CODEX_VERSION` (0.130.0); `codex login status` reports "Logged in" (parsed from stderr, tolerating unrelated warnings); Codex's built-in imagegen skill exists (`find_imagegen_skill`: `$CODEX_HOME/skills/.system/imagegen/SKILL.md`, falling back to `skills/imagegen/`); and best-effort the `image_generation` feature flag from `codex features list` (unqueryable → non-blocking "unknown"). Each failed check appends a human-actionable `next:` step; `--json` emits the full report. Exit 2 unless everything passes.

### `guide` — surface Codex's own prompting rules

Prints Codex's built-in imagegen `SKILL.md` verbatim (plus `--ref <name>` / `--list-refs` for its reference docs). This exists because prompt schema, size limits, and output-path conventions are owned by Codex and change with its releases — the wiki and skill deliberately do not duplicate them.

### `generate` — run codex and land the PNG

1. Reads the prompt inline or via `--prompt-file` (mutually exclusive; file avoids shell-quoting long prompts). Validates `--size` as `WIDTHxHEIGHT` or `auto`; caps `-i/--image` refs at 16 (gpt-image edit hard limit).
2. `build_instruction()` composes the message sent to codex: `$imagegen`, a directive to use the built-in image_gen tool (not the CLI fallback needing `OPENAI_API_KEY`), the user prompt, optional Size/Quality/input-image slots, and an explicit **save contract** — copy the final image to exactly the output path and print `SAVED: <path>`.
3. `build_codex_args()` assembles: `codex exec --skip-git-repo-check --sandbox workspace-write --color never -C <cwd>`, `--add-dir` for an output dir outside cwd, `--image` per ref, `--output-last-message <tmpfile>`, then `--` before the positional prompt (stops the variadic `--image` from eating it). `--dry-run` prints this command without spending quota.
4. Runs it with `subprocess.run` (default `--timeout 600`s; one image ≈ 40–120 s), then recovers the image (below). Non-zero codex exit → tail of output + login hint when auth-shaped → exit 3.

## 3-tier image recovery

`recover_image()` exists because where Codex puts the image varies by version and by whether the model honored the save contract:

1. **Direct**: the requested output path exists non-empty (codex followed the contract).
2. **SAVED-line / generated_images copy**: parse `SAVED:` lines from the last-message file and stdout and copy the first real file; else copy the newest `*.png` under `$CODEX_HOME/generated_images/` modified after the run started (2 s clock slack).
3. **Rollout decode**: codex ≥ 0.141 may embed the PNG as base64 in the session rollout `.jsonl` instead of writing files. `parse_session_id` pulls the session id from stdout, `find_rollout` locates the newest matching rollout under `$CODEX_HOME/sessions/`, and `extract_rollout_image` scans `image_generation_end`/`image_generation_call` payloads (cheap substring pre-filter — rollouts are large), keeping the last image and handling `data:` URI prefixes.

Nothing recovered → exit 4 with the codex output tail.

## Size adherence

gpt-image-2 honors `--size` loosely (e.g. 1254×1254 for a 1024×1024 request). `png_dimensions()` reads the IHDR header directly; on mismatch the CLI still exits 0 but prints a `WARN:` line with the exact local downscale command (`sips -z` / ImageMagick) — regenerating will not improve adherence, so the [skill workflow](skill-workflow.md) instructs downscaling instead.

## Security posture

Codex always runs `--sandbox workspace-write`; `--dangerously-bypass-approvals-and-sandbox` is never used. Output paths outside the working directory are whitelisted per-run via `--add-dir` rather than widening the sandbox. Note the inverse failure mode: exit 3 with "Operation not permitted" usually means the *caller's* shell sandbox blocked codex's network, not codex's own sandbox.

## Tests

`tests/test_codex_imagegen.py` (`python3 -m unittest discover -s tests -v`) covers the pure functions — version parsing, `CODEX_HOME` resolution, skill discovery, instruction/args building, `SAVED:` and session-id parsing, rollout base64 extraction, PNG header reading, recovery tiers — with mocked subprocess/filesystem, so it runs without Codex installed. When changing CLI logic, extend this suite; when changing flags, output lines, or exit codes, also update `SKILL.md` per the lockstep rule in the [quickstart](quickstart.md).
