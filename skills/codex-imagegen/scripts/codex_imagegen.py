#!/usr/bin/env python3
"""Drive Codex CLI's built-in $imagegen skill from Claude Code (or any shell).

Subcommands:
  check     verify codex binary, version, login, and the built-in imagegen skill
  guide     print Codex's own imagegen SKILL.md (prompting rules, sizes, output paths)
  generate  run `codex exec '$imagegen ...'` non-interactively and land the image
            at the requested path

stdlib only; Python 3.9+.

Exit codes: 0 ok · 2 prerequisites/usage · 3 codex run failed · 4 image not recovered
"""

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MIN_CODEX_VERSION = (0, 130, 0)
DEFAULT_TIMEOUT = 600  # seconds; a single image usually takes 40-120s
QUALITIES = ("low", "medium", "high", "auto")


def err(*parts):
    print(*parts, file=sys.stderr)


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def find_imagegen_skill(home):
    """Locate Codex's imagegen SKILL.md (built-in system skill, or user-installed)."""
    for rel in ("skills/.system/imagegen/SKILL.md", "skills/imagegen/SKILL.md"):
        path = Path(home) / rel
        if path.is_file():
            return path
    return None


def ver_tuple(text):
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    return tuple(int(g) for g in match.groups()) if match else None


def build_instruction(prompt, out_path, size=None, quality=None, refs=()):
    """Prompt sent to codex exec: $imagegen invocation + explicit save contract."""
    lines = [
        "$imagegen",
        "Use the built-in image_gen tool (default mode). Do not use the CLI fallback;"
        " no OPENAI_API_KEY is required.",
        "",
        "Primary request: {}".format(prompt),
    ]
    if size:
        lines.append("Size: {}".format(size))
    if quality:
        lines.append("Quality: {}".format(quality))
    if refs:
        lines.append("Input images:")
        for i, ref in enumerate(refs, 1):
            lines.append("Image {}: {}".format(i, ref))
    lines += [
        "",
        "After generating, copy the final selected image to exactly this path: {}".format(out_path),
        "Create parent directories if needed. Do not write any other files.",
        "Then print exactly one line: SAVED: {}".format(out_path),
    ]
    return "\n".join(lines)


def build_codex_args(instruction, cwd, refs=(), last_msg=None, add_dirs=()):
    args = [
        "codex", "exec",
        "--skip-git-repo-check",
        "--sandbox", "workspace-write",
        "--color", "never",
        "-C", str(cwd),
    ]
    for d in add_dirs:
        args += ["--add-dir", str(d)]
    for ref in refs:
        args += ["--image", str(ref)]
    if last_msg:
        args += ["--output-last-message", str(last_msg)]
    # `--` stops the variadic --image flag from eating the positional prompt
    args += ["--", instruction]
    return args


def parse_saved_paths(text):
    found = []
    for line in (text or "").splitlines():
        match = re.match(r"^\s*SAVED:\s*(.+?)\s*$", line)
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return found


def parse_session_id(text):
    match = re.search(r"session id: ([0-9a-f][0-9a-f-]{7,})", text or "")
    return match.group(1) if match else None


def newest_generated_png(gen_root, since):
    """Newest PNG under $CODEX_HOME/generated_images/<session>/ modified after `since`."""
    root = Path(gen_root)
    if not root.is_dir():
        return None
    best = None
    for path in root.glob("**/*.png"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= since and (best is None or mtime > best[0]):
            best = (mtime, path)
    return best[1] if best else None


def find_rollout(sessions_dir, session_id):
    root = Path(sessions_dir)
    if not session_id or not root.is_dir():
        return None
    matches = sorted(root.rglob("*{}.jsonl".format(session_id)),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def extract_rollout_image(jsonl_path):
    """codex >= 0.141 can embed the PNG as base64 in the session rollout instead of
    writing generated_images/<session>/ig_*.png. Pull the newest one out."""
    found = None
    try:
        fh = open(str(jsonl_path), encoding="utf-8")
    except OSError:
        return None
    with fh:
        for line in fh:
            # cheap pre-filter; rollouts are large and image events are rare
            if "image_generation" not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            payload = obj.get("payload", {}) if isinstance(obj, dict) else {}
            if payload.get("type") in ("image_generation_end", "image_generation_call"):
                result = payload.get("result")
                if isinstance(result, str) and result:
                    found = result  # keep the last (newest) image
    if not found:
        return None
    if found.startswith("data:"):
        found = found.split(",", 1)[-1]
    try:
        return base64.b64decode(found)
    except ValueError:
        return None


def parse_size(size):
    match = re.match(r"^(\d+)x(\d+)$", size or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def size_matches(size, dims):
    """gpt-image-2 size adherence is loose; True when no warning is warranted."""
    want = parse_size(size)
    if want is None or dims is None:
        return True
    return tuple(dims) == want


def png_dimensions(path):
    try:
        with open(str(path), "rb") as fh:
            head = fh.read(26)
    except OSError:
        return None
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def run_capture(args, timeout=30):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return None, "not found"
    except subprocess.TimeoutExpired:
        return None, "timed out"


# ---------------------------------------------------------------- check

def image_generation_feature():
    """Best effort: parse `codex features list` for the image_generation flag."""
    rc, out = run_capture(["codex", "features", "list"])
    if rc != 0:
        return None
    for line in out.splitlines():
        match = re.match(r"^image_generation\s+\S+.*\s(true|false)\s*$", line.strip())
        if match:
            return match.group(1) == "true"
    return None


def build_check_report():
    report = {"ready": False, "checks": [], "next_steps": []}

    def add(name, ok, detail):
        report["checks"].append({"name": name, "ok": ok, "detail": detail})

    binary = shutil.which("codex")
    rc, out = (run_capture(["codex", "--version"]) if binary else (None, ""))
    version = ver_tuple(out)
    codex_ok = bool(binary) and rc == 0 and version is not None and version >= MIN_CODEX_VERSION
    detail = "{} ({})".format(binary or "not found", out.strip().splitlines()[0] if out.strip() else "-")
    add("codex binary >= {}".format(".".join(map(str, MIN_CODEX_VERSION))), codex_ok, detail)
    if not binary:
        report["next_steps"].append("Install Codex CLI: npm install -g @openai/codex")
    elif not codex_ok:
        report["next_steps"].append("Upgrade Codex CLI: npm install -g @openai/codex")

    login_ok = False
    if codex_ok:
        rc, out = run_capture(["codex", "login", "status"])
        login_ok = rc == 0 and re.search(r"logged in", out, re.I) is not None
        # codex prints its status line to stderr, possibly after unrelated warnings
        lines = [l for l in out.strip().splitlines() if l.strip()]
        status_line = next((l for l in lines if re.search(r"logged in", l, re.I)), None)
        add("codex login", login_ok, status_line or (lines[0] if lines else "unknown"))
        if not login_ok:
            report["next_steps"].append("Run `codex login` (in Claude Code: `! codex login`)")

    skill = find_imagegen_skill(codex_home())
    add("built-in imagegen skill", skill is not None, str(skill or "not found under {}".format(codex_home() / "skills")))
    if skill is None:
        report["next_steps"].append("Update Codex CLI so the built-in imagegen skill is installed, then re-run check")

    feature = image_generation_feature() if codex_ok else None
    if feature is None:
        add("image_generation feature", True, "unknown (could not query; not blocking)")
    else:
        add("image_generation feature", feature, "enabled" if feature else "disabled")
        if not feature:
            report["next_steps"].append("Enable it: codex features enable image_generation")

    report["ready"] = all(c["ok"] for c in report["checks"]) and login_ok
    return report


def cmd_check(args):
    report = build_check_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for c in report["checks"]:
            print("{:4} {}: {}".format("OK" if c["ok"] else "FAIL", c["name"], c["detail"]))
        print("Ready: {}".format("yes" if report["ready"] else "no"))
        for step in report["next_steps"]:
            print("  next: {}".format(step))
    return 0 if report["ready"] else 2


# ---------------------------------------------------------------- guide

def cmd_guide(args):
    skill = find_imagegen_skill(codex_home())
    if not skill:
        err("Codex built-in imagegen skill not found under {}".format(codex_home() / "skills"))
        err("Update Codex CLI (npm install -g @openai/codex), then re-run `check`.")
        return 2
    refs_dir = skill.parent / "references"
    if args.list_refs:
        for ref in sorted(refs_dir.glob("*.md")) if refs_dir.is_dir() else []:
            print(ref.stem)
        return 0
    if args.ref:
        ref_path = refs_dir / "{}.md".format(args.ref)
        if not ref_path.is_file():
            err("No such reference: {} (try --list-refs)".format(args.ref))
            return 2
        print(ref_path.read_text(encoding="utf-8"))
        return 0
    print("[source] {}\n".format(skill))
    print(skill.read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------- generate

def read_prompt(args):
    if args.prompt_file:
        if args.prompt:
            err("Give the prompt either inline or via --prompt-file, not both.")
            return None
        try:
            text = Path(args.prompt_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            err("Cannot read --prompt-file: {}".format(exc))
            return None
        return text or None
    return " ".join(args.prompt).strip() or None


def recover_image(out_path, stdout_text, last_msg_text, started_at):
    """3-tier recovery. Returns (path_or_None, how)."""
    out_path = Path(out_path)
    if out_path.is_file() and out_path.stat().st_size > 0:
        return out_path, "saved directly by codex"

    for cand in parse_saved_paths((last_msg_text or "") + "\n" + (stdout_text or "")):
        cand = Path(cand)
        if cand.is_file() and cand.stat().st_size > 0:
            if cand.resolve() != out_path.resolve():
                shutil.copyfile(str(cand), str(out_path))
            return out_path, "copied from SAVED path {}".format(cand)

    newest = newest_generated_png(codex_home() / "generated_images", since=started_at - 2)
    if newest:
        shutil.copyfile(str(newest), str(out_path))
        return out_path, "copied from {}".format(newest)

    session = parse_session_id(stdout_text)
    rollout = find_rollout(codex_home() / "sessions", session)
    if rollout:
        data = extract_rollout_image(rollout)
        if data:
            out_path.write_bytes(data)
            return out_path, "decoded from session rollout {}".format(rollout.name)

    return None, "not recovered"


def cmd_generate(args):
    prompt = read_prompt(args)
    if not prompt:
        err("Empty prompt. Pass it inline or via --prompt-file.")
        return 2
    if args.size and args.size != "auto" and not re.match(r"^\d+x\d+$", args.size):
        err("--size must be WIDTHxHEIGHT (e.g. 1024x1024) or 'auto'.")
        return 2

    cwd = Path.cwd()
    out = Path(args.output or "generated-images/img-{}.png".format(time.strftime("%Y%m%d-%H%M%S")))
    out = out if out.is_absolute() else cwd / out

    refs = []
    for ref in args.image or []:
        path = Path(ref)
        path = path if path.is_absolute() else cwd / path
        if not path.is_file():
            err("Reference image not found: {}".format(ref))
            return 2
        refs.append(str(path.resolve()))

    add_dirs = []
    try:
        out.parent.resolve().relative_to(cwd.resolve())
    except ValueError:
        add_dirs.append(str(out.parent))

    instruction = build_instruction(prompt, str(out), size=args.size,
                                    quality=args.quality, refs=refs)

    if args.dry_run:
        print(shlex.join(build_codex_args(instruction, cwd, refs=refs, add_dirs=add_dirs)))
        return 0

    if not shutil.which("codex"):
        err("codex CLI not found. Install: npm install -g @openai/codex")
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    fd, last_msg = tempfile.mkstemp(prefix="codex-imagegen-", suffix=".txt")
    os.close(fd)
    codex_args = build_codex_args(instruction, cwd, refs=refs, last_msg=last_msg,
                                  add_dirs=add_dirs)
    started_at = time.time()
    try:
        try:
            proc = subprocess.run(codex_args, capture_output=True, text=True,
                                  timeout=args.timeout, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            err("codex exec timed out after {}s (image gen usually takes 40-120s; "
                "raise --timeout for complex prompts).".format(args.timeout))
            return 3
        try:
            last_msg_text = Path(last_msg).read_text(encoding="utf-8")
        except OSError:
            last_msg_text = ""
    finally:
        try:
            os.unlink(last_msg)
        except OSError:
            pass

    stdout_text = (proc.stdout or "") + "\n" + (proc.stderr or "")

    if args.verbose:
        print(stdout_text)

    if proc.returncode != 0:
        err("codex exec failed (exit {}). Output tail:".format(proc.returncode))
        err("\n".join(stdout_text.strip().splitlines()[-40:]))
        if re.search(r"login|auth", stdout_text, re.I):
            err("Hint: run `codex login` (in Claude Code: `! codex login`).")
        return 3

    path, how = recover_image(out, stdout_text, last_msg_text, started_at)
    elapsed = round(time.time() - started_at, 1)
    if path is None:
        err("codex finished but no image could be recovered ({}). Output tail:".format(how))
        err("\n".join(stdout_text.strip().splitlines()[-40:]))
        return 4

    dims = png_dimensions(path)
    size_ok = size_matches(args.size, dims)
    if args.json:
        print(json.dumps({"ok": True, "path": str(path), "how": how,
                          "width": dims[0] if dims else None,
                          "height": dims[1] if dims else None,
                          "size_ok": size_ok,
                          "seconds": elapsed}))
    else:
        print("SAVED: {}".format(path))
        print("({}, {}{} in {}s)".format(how, "{}x{} ".format(*dims) if dims else "",
                                         "{} bytes".format(path.stat().st_size), elapsed))
    if not size_ok:
        want = parse_size(args.size)
        err("WARN: requested {} but got {}x{} — regenerating will not guarantee adherence; "
            "downscale locally instead, e.g. `sips -z {} {} {}` (macOS) or "
            "ImageMagick `magick {} -resize {}! {}`.".format(
                args.size, dims[0], dims[1], want[1], want[0], path, path, args.size, path))
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="codex_imagegen.py",
        description="Generate images via Codex CLI's built-in $imagegen skill.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="verify codex binary, login, imagegen skill")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_guide = sub.add_parser("guide", help="print Codex's imagegen guide (read before prompting)")
    p_guide.add_argument("--ref", help="print a specific reference doc (e.g. prompting)")
    p_guide.add_argument("--list-refs", action="store_true", help="list available reference docs")
    p_guide.set_defaults(func=cmd_guide)

    p_gen = sub.add_parser("generate", help="generate an image and save it to -o path")
    p_gen.add_argument("prompt", nargs="*", help="image prompt (or use --prompt-file)")
    p_gen.add_argument("--prompt-file", help="read the prompt from a file (avoids shell quoting)")
    p_gen.add_argument("-o", "--output", help="output path (default: generated-images/img-<ts>.png)")
    p_gen.add_argument("--size", help="WIDTHxHEIGHT (e.g. 1024x1024, 1536x1024) or 'auto'")
    p_gen.add_argument("--quality", choices=QUALITIES, help="gpt-image-2 quality")
    p_gen.add_argument("-i", "--image", action="append",
                       help="reference/edit input image (repeatable, max 16)")
    p_gen.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                       help="seconds to wait for codex exec (default {})".format(DEFAULT_TIMEOUT))
    p_gen.add_argument("--dry-run", action="store_true",
                       help="print the codex command instead of running it")
    p_gen.add_argument("--verbose", action="store_true", help="print full codex output")
    p_gen.add_argument("--json", action="store_true", help="machine-readable result line")
    p_gen.set_defaults(func=cmd_generate)

    args = parser.parse_args(argv)
    if getattr(args, "image", None) and len(args.image) > 16:
        err("At most 16 reference images (gpt-image edit hard cap).")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
