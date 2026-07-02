import base64
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "codex-imagegen" / "scripts"))

import codex_imagegen as ci

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class TestVersion(unittest.TestCase):
    def test_parses_codex_version_string(self):
        self.assertEqual(ci.ver_tuple("codex-cli 0.142.5"), (0, 142, 5))

    def test_garbage_returns_none(self):
        self.assertIsNone(ci.ver_tuple("no digits here"))


class TestCodexHome(unittest.TestCase):
    def test_env_override(self):
        with mock.patch.dict(os.environ, {"CODEX_HOME": "/custom/home"}):
            self.assertEqual(ci.codex_home(), Path("/custom/home"))

    def test_default(self):
        env = {k: v for k, v in os.environ.items() if k != "CODEX_HOME"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(ci.codex_home(), Path.home() / ".codex")


class TestFindSkill(unittest.TestCase):
    def test_finds_system_skill(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            skill = home / "skills" / ".system" / "imagegen" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# imagegen")
            self.assertEqual(ci.find_imagegen_skill(home), skill)

    def test_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(ci.find_imagegen_skill(Path(td)))


class TestInstruction(unittest.TestCase):
    def test_contains_contract(self):
        text = ci.build_instruction("a red fox", "/tmp/out.png")
        self.assertTrue(text.startswith("$imagegen"))
        self.assertIn("a red fox", text)
        self.assertIn("/tmp/out.png", text)
        self.assertIn("SAVED: /tmp/out.png", text)

    def test_optional_slots_only_when_given(self):
        text = ci.build_instruction("x", "/o.png", size="1536x1024", quality="low")
        self.assertIn("Size: 1536x1024", text)
        self.assertIn("Quality: low", text)
        bare = ci.build_instruction("x", "/o.png")
        self.assertNotIn("Size:", bare)
        self.assertNotIn("Quality:", bare)

    def test_reference_images_listed(self):
        text = ci.build_instruction("x", "/o.png", refs=["/a.png", "/b.png"])
        self.assertIn("Image 1: /a.png", text)
        self.assertIn("Image 2: /b.png", text)
        self.assertNotIn("Image 1:", ci.build_instruction("x", "/o.png"))


class TestCodexArgs(unittest.TestCase):
    def test_baseline_args(self):
        args = ci.build_codex_args("PROMPT", cwd="/work", last_msg="/tmp/last.txt")
        self.assertEqual(args[:2], ["codex", "exec"])
        self.assertIn("--skip-git-repo-check", args)
        i = args.index("--sandbox")
        self.assertEqual(args[i + 1], "workspace-write")
        i = args.index("-C")
        self.assertEqual(args[i + 1], "/work")
        i = args.index("--output-last-message")
        self.assertEqual(args[i + 1], "/tmp/last.txt")
        # prompt is positional and must come after `--` so --image can't eat it
        self.assertEqual(args[-2:], ["--", "PROMPT"])

    def test_refs_and_add_dirs(self):
        args = ci.build_codex_args("P", cwd="/w", refs=["/r1.png"], add_dirs=["/elsewhere"])
        i = args.index("--image")
        self.assertEqual(args[i + 1], "/r1.png")
        i = args.index("--add-dir")
        self.assertEqual(args[i + 1], "/elsewhere")


class TestParseSaved(unittest.TestCase):
    def test_parses_and_dedupes(self):
        text = "noise\nSAVED: /a/b.png\nmid\nSAVED: /a/b.png\nSAVED: /c d/e.png\n"
        self.assertEqual(ci.parse_saved_paths(text), ["/a/b.png", "/c d/e.png"])

    def test_none_found(self):
        self.assertEqual(ci.parse_saved_paths("nothing here"), [])


class TestSessionId(unittest.TestCase):
    def test_extracts_uuid(self):
        out = "workdir: /x\nsession id: 019f201f-78d8-7363-b7a4-859d5d29a70a\nmodel: gpt-5.5"
        self.assertEqual(ci.parse_session_id(out), "019f201f-78d8-7363-b7a4-859d5d29a70a")

    def test_missing(self):
        self.assertIsNone(ci.parse_session_id("no session here"))


class TestNewestGeneratedPng(unittest.TestCase):
    def test_picks_newest_since(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = root / "s1" / "ig_old.png"
            old.parent.mkdir()
            old.write_bytes(b"o")
            os.utime(old, (time.time() - 3600, time.time() - 3600))
            new = root / "s2" / "ig_new.png"
            new.parent.mkdir()
            new.write_bytes(b"n")
            self.assertEqual(ci.newest_generated_png(root, since=time.time() - 60), new)

    def test_none_when_all_old(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = root / "s1" / "ig_old.png"
            old.parent.mkdir()
            old.write_bytes(b"o")
            os.utime(old, (time.time() - 3600, time.time() - 3600))
            self.assertIsNone(ci.newest_generated_png(root, since=time.time() - 60))

    def test_missing_root(self):
        self.assertIsNone(ci.newest_generated_png(Path("/nonexistent-xyz"), since=0))


class TestRollout(unittest.TestCase):
    def test_decodes_last_image(self):
        img1 = PNG_MAGIC + b"one"
        img2 = PNG_MAGIC + b"two"
        lines = [
            json.dumps({"payload": {"type": "image_generation_end",
                                    "result": base64.b64encode(img1).decode()}}),
            "not json {",
            json.dumps({"payload": {"type": "other", "result": "zzz"}}),
            json.dumps({"payload": {"type": "image_generation_call",
                                    "result": base64.b64encode(img2).decode()}}),
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "rollout.jsonl"
            p.write_text("\n".join(lines))
            self.assertEqual(ci.extract_rollout_image(p), img2)

    def test_no_image_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r.jsonl"
            p.write_text("{}\n")
            self.assertIsNone(ci.extract_rollout_image(p))

    def test_find_rollout_by_session_id(self):
        with tempfile.TemporaryDirectory() as td:
            sess = Path(td) / "sessions" / "2026" / "07"
            sess.mkdir(parents=True)
            f = sess / "rollout-2026-07-02T10-00-00-abc123.jsonl"
            f.write_text("{}")
            self.assertEqual(ci.find_rollout(Path(td) / "sessions", "abc123"), f)
            self.assertIsNone(ci.find_rollout(Path(td) / "sessions", "zzz999"))


class TestSizeMatch(unittest.TestCase):
    def test_parse_size(self):
        self.assertEqual(ci.parse_size("1024x1024"), (1024, 1024))
        self.assertIsNone(ci.parse_size("auto"))
        self.assertIsNone(ci.parse_size(None))

    def test_match_and_mismatch(self):
        self.assertTrue(ci.size_matches("1024x1024", (1024, 1024)))
        self.assertFalse(ci.size_matches("1024x1024", (1254, 1254)))
        self.assertTrue(ci.size_matches("auto", (1254, 1254)))
        self.assertTrue(ci.size_matches(None, (1254, 1254)))
        self.assertTrue(ci.size_matches("1024x1024", None))


class TestGuideCommand(unittest.TestCase):
    def test_guide_prints_skill(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"CODEX_HOME": td}):
            skill = Path(td) / "skills" / ".system" / "imagegen" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("GUIDE-BODY")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ci.main(["guide"])
            self.assertEqual(rc, 0)
            self.assertIn("GUIDE-BODY", buf.getvalue())

    def test_guide_missing_fails(self):
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.dict(os.environ, {"CODEX_HOME": td}):
            buf, ebuf = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
                rc = ci.main(["guide"])
            self.assertNotEqual(rc, 0)


class TestDryRun(unittest.TestCase):
    def test_prints_command_without_running(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ci.main(["generate", "a fox", "-o", "/tmp/nonexistent-dir-xyz/out.png",
                          "--dry-run"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("codex exec", out)
        self.assertIn("$imagegen", out)
        # dry-run must not create the output directory
        self.assertFalse(Path("/tmp/nonexistent-dir-xyz").exists())


if __name__ == "__main__":
    unittest.main()
