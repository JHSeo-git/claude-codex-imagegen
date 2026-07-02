# Changelog

## Unreleased

- Add MIT license.
- Initial release: `codex-imagegen` Claude Code skill + stdlib-only Python CLI (`check` / `guide` / `generate`) driving Codex CLI's built-in `$imagegen` skill, with 3-tier output recovery (direct save → `generated_images` copy → session-rollout base64 decode).
