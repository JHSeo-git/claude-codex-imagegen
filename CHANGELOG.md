# Changelog

## Unreleased

- README: recommend `npx skills add JHSeo-git/claude-codex-imagegen` as the primary install method; manual `cp` kept as fallback.
- Add `examples/pastel-anime-slides`: reusable style guide (shared style/constraints prompt blocks, text-safe negative space rules, five worked prompts) with preview images.
- Add MIT license.
- Initial release: `codex-imagegen` Claude Code skill + stdlib-only Python CLI (`check` / `guide` / `generate`) driving Codex CLI's built-in `$imagegen` skill, with 3-tier output recovery (direct save → `generated_images` copy → session-rollout base64 decode).
