"""Test custom patch parser."""
import os
import tempfile
import zipfile

from patcher.custom_patch import CustomPatchParser


def test_parse_txt_single_target():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "# comment\n"
                "[com/test/A.smali]\n"
                "old_code -> new_code\n"
            )
        parser = CustomPatchParser(path)
        instrs = parser.parse()
        assert len(instrs) == 1
        assert instrs[0]["target_file"] == "com/test/A.smali"
        assert instrs[0]["operations"][0]["pattern"] == "old_code"


def test_parse_txt_multiple_targets():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.txt")
        with open(path, "w") as f:
            f.write(
                "[A.smali]\nx -> y\n"
                "[B.smali]\nfoo -> bar\n"
            )
        instrs = CustomPatchParser(path).parse()
        assert len(instrs) == 2


def test_parse_txt_with_inline_replacement():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.txt")
        with open(path, "w") as f:
            f.write("[A.smali] old -> new\n")
        instrs = CustomPatchParser(path).parse()
        assert instrs[0]["operations"][0]["pattern"] == "old"


def test_parse_lpzip():
    with tempfile.TemporaryDirectory() as tmp:
        lpzip = os.path.join(tmp, "p.lpzip")
        with zipfile.ZipFile(lpzip, "w") as z:
            z.writestr("patch.txt", "[A.smali]\nx -> y\n")
        instrs = CustomPatchParser(lpzip).parse()
        assert len(instrs) == 1


def test_parse_empty_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.txt")
        with open(path, "w") as f:
            f.write("")
        assert CustomPatchParser(path).parse() == []